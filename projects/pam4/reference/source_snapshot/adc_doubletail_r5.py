#!/usr/bin/env python3
"""Four native-sized Schinkel double-tail candidates; generate-only by default.

Topology visually checked against Fig.2(a), Schinkel et al., ProRISC 2007:
https://ris.utwente.nl/ws/portalfiles/portal/5463411/Schinkel_Prorisc_2007.pdf
The paper's 18ps number is setup+hold, not clock-to-output delay. No 29ps
performance is presumed here. Retains the r5 source, sampler, sequence and
clock timing, and reports commanded-input and held-input polarity separately.
All model-bearing decks and raw traces stay on the VM. Python 3.6.
"""
import argparse
import hashlib
import json
from pathlib import Path

import adc_comparator_r5 as r

a = r.a
NAME = 'adc_doubletail_r5_20261013'
REFERENCE = 'https://ris.utwente.nl/ws/portalfiles/portal/5463411/Schinkel_Prorisc_2007.pdf'


def candidates():
    # Widths um, all L30nm, one native finger and unit multiplicity.
    result = {}
    for name, inp, itail, clamp, header in [
            ('dt_light', .5, .5, .24, 1.),
            ('dt_balanced', 1., 1., .5, 2.),
            ('dt_fastinput', 1., 2., .24, 3.),
            ('dt_gain', 1., .5, .24, 2.)]:
        result[name] = dict(input=inp, input_tail=itail, reset=.5,
                            intermediate=clamp, latch_n=.24, latch_p=.5,
                            latch_header=header, buffer_n=.24, buffer_p=.5)
    return result


def doubletail(widths, mos):
    """p=Di-, q=Di+, y=Out+, x=Out-. Reset p/q HIGH and x/y LOW.

    Independent NMOS input tail and PMOS latch header, exactly Fig.2(a).
    Positive cg_p-cg_n makes p fall first, releases y first and yields bx high.
    """
    devices = [
        ('DM5', 'p', 'cg_p', 'tail', '0', False, 'input'),
        ('DM6', 'q', 'cg_n', 'tail', '0', False, 'input'),
        ('DM7', 'p', 'cmp', 'avdd', 'avdd', True, 'reset'),
        ('DM8', 'q', 'cmp', 'avdd', 'avdd', True, 'reset'),
        ('DM9', 'tail', 'cmp', '0', '0', False, 'input_tail'),
        ('DM10', 'y', 'p', '0', '0', False, 'intermediate'),
        ('DM11', 'x', 'q', '0', '0', False, 'intermediate'),
        ('DM1', 'y', 'x', '0', '0', False, 'latch_n'),
        ('DM3', 'x', 'y', '0', '0', False, 'latch_n'),
        ('DM2', 'y', 'x', 'latvdd', 'avdd', True, 'latch_p'),
        ('DM4', 'x', 'y', 'latvdd', 'avdd', True, 'latch_p'),
        ('DM12', 'latvdd', 'cmpb', 'avdd', 'avdd', True, 'latch_header')]
    for out, gate in [('bx', 'x'), ('by', 'y')]:
        devices += [('DBN'+out, out, gate, '0', '0', False, 'buffer_n'),
                    ('DBP'+out, out, gate, 'bvdd', 'bvdd', True, 'buffer_p')]
    return [mos(n, d, g, s, bulk, pmos=p, w=widths[group]*1e-6, l=30e-9)
            for n, d, g, s, bulk, p, group in devices]


def make_deck(cfg, tm, widths, mos):
    # Reuse the immutable r5 stimulus/sampler without global monkeypatching.
    placeholder_widths = r.candidates()['in100_tail3']
    base = r.make_deck(cfg, tm, placeholder_widths, mos)
    old = r.sized_strongarm(placeholder_widths, mos)
    starts = [i for i in range(len(base)) if base[i:i+len(old)] == old]
    if len(starts) != 1:
        raise ValueError('Expected unique complete StrongARM block in unchanged r5 bench')
    vdd = cfg['supply_V']
    stop = a.T0+(cfg['cycles']+1)*tm['period_s']
    unused, cp_events, unused2 = r.events(cfg['cycles'], tm, vdd)
    cb = [(t, vdd-x) for t, x in a.pwl(0., cp_events, stop)]
    addition = ['// Double-tail Fig.2(a): '+REFERENCE,
                '// Latch output reset level is ground; p/q precharge to VDD.',
                'VCMPB (cmpb 0) vsource type=pwl wave='+a.wave(cb)] + doubletail(widths, mos)
    at = starts[0]
    lines = base[:at]+addition+base[at+len(old):]
    lines = ['// Source/sampler/timing fixture inherited from r5; StrongARM core replaced.'
             if line.startswith('// StrongARM topology:') else line for line in lines]
    return [line+' cmpb latvdd VCMPB:p' if line.startswith('save ') else line for line in lines]


def analyze(raw, cfg, tm):
    t, v = raw.values[raw.sweep_names[0]], raw.values
    if max(abs(x+y-cfg['supply_V']) for x, y in zip(v['cmp'], v['cmpb'])) > 1e-8:
        raise ValueError('Comparator clocks not complementary')
    rows = r.analyze_values(t, v, cfg, tm)
    launches = a.crossings(t, v['cmp'], cfg['supply_V']/2, True)
    for row in rows:
        start = a.T0+row['cycle']*tm['period_s']
        launch = a.near(launches, start+tm['launch_offset_s'])
        next_launch = a.near(launches, launch+tm['period_s'])
        before = launch-r.MARGIN
        row['prelaunch_input_internal_min_V'] = min(a.interpolate(t, v[n], before) for n in ('p', 'q'))
        row['prelaunch_output_internal_max_V'] = max(a.interpolate(t, v[n], before) for n in ('x', 'y'))
        watts = [-x*y for x, y in zip(v['cmpb'], v['VCMPB:p'])]
        row['compare_clock_bar_full_period_energy_J'] = a.integral(t, watts, launch, next_launch)
    summary = r.summarize(rows, tm)
    summary['minimum_prelaunch_p_q_V'] = min(row['prelaunch_input_internal_min_V'] for row in rows)
    summary['maximum_prelaunch_x_y_V'] = max(row['prelaunch_output_internal_max_V'] for row in rows)
    summary['reset_residual_note'] = 'Double-tail resets p/q to VDD, x/y to ground; generic all-node minimum is not a reset pass criterion.'
    energy = sum(row['compare_clock_bar_full_period_energy_J'] for row in rows)/len(rows)
    summary['compare_clock_bar_mean_energy_J'] = energy
    summary['compare_clock_bar_mean_power_W'] = energy/tm['period_s']
    return rows, summary


def self_test():
    r.self_test()
    captured = []
    def placeholder(n, d, g, s, bulk, **kw):
        captured.append((n, d, g, s, bulk, kw))
        return '%s (%s %s %s %s) TEST w=%.12g l=%.12g' % (n, d, g, s, bulk, kw['w'], kw['l'])
    for mode in ('fast', 'control'):
        for widths in candidates().values():
            deck = make_deck(r.configuration(), r.timing(mode), widths, placeholder)
            names = [x.split()[0] for x in deck if x and not x.startswith('//') and '(' in x and not x.startswith('save ')]
            assert len(names) == len(set(names))
            assert 'DM12' in names and 'M7' not in names and 'VCMPB' in names
            assert len([n for n in names if n.startswith('DM')]) == 12
            assert 'save ' in '\n'.join(deck)
    print(json.dumps({'doubletail_self_test': 'passed', 'candidate_count': 4, 'simulation_executed': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', choices=sorted(candidates()))
    p.add_argument('--timing', choices=('fast', 'control'), default='fast')
    p.add_argument('--cards', type=Path, default=r.PROJECT/'configs/native_geometry_cards_r5.json')
    p.add_argument('--noise-seed', type=int)
    p.add_argument('--run', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--timeout', type=int, default=180)
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if args.case is None or not 10 <= args.timeout <= 600 or (args.noise_seed is not None and args.noise_seed < 1):
        p.error('Case required; timeout 10..600; positive noise seed')
    import native_geometry_r5 as geometry
    geometry.install(args.cards)
    cfg, tm, widths = r.configuration(args.noise_seed), r.timing(args.timing), candidates()[args.case]
    lines = make_deck(cfg, tm, widths, geometry.mos)
    deck = '\n'.join(lines)+'\n'
    case = args.case+'_'+args.timing+('' if args.noise_seed is None else '_noise%d' % args.noise_seed)
    directory = r.PROJECT/'runs'/NAME/case
    identity = dict(script_sha256=a.digest(__file__), strongarm_bench_sha256=a.digest(r.__file__),
                    helper_sha256=a.digest(geometry.__file__), native_cards_sha256=a.digest(args.cards),
                    probe_helpers_sha256=a.digest(a.__file__),
                    deck_sha256=hashlib.sha256(deck.encode('utf-8')).hexdigest(),
                    configuration=cfg, timing=tm, geometry_widths_um=widths, input_pattern_LSB=r.PATTERN,
                    primary_topology_source=REFERENCE, schematic='Figure 2(a)')
    record_path = directory/'doubletail_r5_summary.json'
    if record_path.exists():
        prior = json.loads(record_path.read_text())
        if prior['identity'] != identity:
            raise ValueError('Existing case identity differs')
        if prior.get('status') == 'complete':
            if a.digest(directory/'bench.scs') != identity['deck_sha256'] or a.digest(a._raw_file(directory)) != prior['raw_sha256']:
                raise ValueError('Completed result provenance differs')
            print(json.dumps({'case': case, 'status': 'verified_existing_complete', 'summary': prior['summary']}), flush=True)
            return
    if (directory/'raw').exists():
        raise ValueError('Refusing to overwrite incomplete/unbound raw data')
    if (directory/'bench.scs').exists() and a.digest(directory/'bench.scs') != identity['deck_sha256']:
        raise ValueError('Existing deck differs')
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'bench.scs').write_text(deck)
    record = dict(schema_version=1, case=case, identity=identity, status='generated_only',
                  scope='Single native double-tail comparator, direct sampler; not complete ADC or BER qualification',
                  limitations=['Same ideal 1ps clock/complement and 50ohm source as r5; physical AFE absent.',
                               'Nominal geometry, TT25C0.9V; mismatch, clock skew and PEX excluded.',
                               'Input p/q reset HIGH and latch x/y reset LOW; reset-minimum metrics differ from StrongARM.',
                               'Input source correctness and held-sign agreement are separately counted.',
                               'DUT/reference difference is additional loading/evaluation disturbance, not pure kickback.',
                               'Noise DUT/reference traces are independent; small sample count is not BER evidence.',
                               'Reported ideal clock-source energy excludes a real clock driver/tree.',
                               'Topology reference 18ps setup+hold cannot be used as clock-to-output performance evidence.'])
    if args.run:
        record['run_status'] = a.b.run(directory, lines, timeout=args.timeout)
        if record['run_status']['exit_code'] != 0:
            record['status'] = 'simulation_failed'
            a.atomic_json(record_path, record)
            raise RuntimeError('Double-tail simulation failed')
        raw = a.parse_file(a._raw_file(directory))
        rows, summary = analyze(raw, cfg, tm)
        record.update(status='complete', raw_sha256=raw.sha256, cycles=rows, summary=summary)
    a.atomic_json(record_path, record)
    print(json.dumps({'case': case, 'status': record['status'], 'summary': record.get('summary')}), flush=True)


if __name__ == '__main__':
    main()
