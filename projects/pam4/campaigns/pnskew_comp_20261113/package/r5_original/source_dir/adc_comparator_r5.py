#!/usr/bin/env python3
"""Native-geometry StrongARM screen; generate-only unless --run (Python 3.6).

One actual 3um TG/5fF sampler drives one comparator, with an independent
sampler-only reference. Geometry cards must be produced by native callbacks.
This is not a seven-bit ADC, BER test, PVT/offset proof, or full AFE simulation.
Model-bearing decks/cards and raw waveforms remain on the VM.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import adc_comparator_probe as a

PROJECT = a.PROJECT
NAME = 'adc_comparator_r5_20261013'
PERIOD = 8.0 / 112e9
TRACK = PERIOD / 2
GUARD = 2e-12
MARGIN = a.EDGE / 2 + .1e-12
# Repeats and large-to-opposite-small transitions expose acquisition/reset memory.
PATTERN = [.25, .25, -.25, -.25, 32., -.25, -32., .25,
           1., -1., 32., -1., -32., 1., .25, -.25]
STATES = ('correct', 'wrong', 'unresolved')


def candidates():
    # Widths are um; each device has one native finger and unit multiplicity.
    # input, regeneration N/P, tail, precharge, equalizer; zero omits equalizers.
    rows = [
        ('mini', .24, .24, .24, .5, .24, 0.),
        ('mini_eq', .24, .24, .24, .5, .24, .24),
        ('in050', .5, .24, .24, 1., .5, 0.),
        ('in050_eq', .5, .24, .24, 1., .5, .24),
        ('in100_minregen', 1., .24, .24, 2., .5, .24),
        ('in100_nregen', 1., .5, .24, 2., .5, .24),
        ('in100_balanced', 1., .5, .5, 2., .5, .24),
        ('in100_reset', 1., .5, .5, 2., 1., .5),
        ('in200', 2., .5, .5, 3., .5, .24),
        ('in200_nregen', 2., 1., .5, 3., 1., .24),
        ('in100_tail3', 1., .5, .5, 3., .5, .24),
        ('in050_tail2', .5, .24, .24, 2., .5, .24),
        ('in050_balanced', .5, .5, .5, 2., .5, .24),
        ('in100_pregen', 1., .5, 1., 2., .5, .24),
        ('in100_noeq', 1., .5, .5, 2., .5, 0.),
        ('legacy3um', 3., 3., 3., 3., 3., 0.)]
    result = {}
    for name, inp, rn, rp, tail, pre, eq in rows:
        result[name] = dict(input=inp, regen_n=rn, regen_p=rp, tail=tail,
                            precharge=pre, equalizer=eq,
                            buffer_n=3. if name == 'legacy3um' else .24,
                            buffer_p=3. if name == 'legacy3um' else .5)
    return result


def timing(kind):
    launch = TRACK + a.EDGE/2 + GUARD
    period = PERIOD if kind == 'fast' else 300e-12
    # Three ps reset lead preserves a real 29ps endpoint with finite 1ps edges.
    # The old 4ps lead offers only 28.614ps after the actual launch midpoint.
    reset = period-3e-12 if kind == 'fast' else launch+120e-12+MARGIN
    if reset <= launch+29e-12+MARGIN:
        raise ValueError('Insufficient evaluation interval')
    return dict(mode=kind, period_s=period, track_duration_s=TRACK,
                launch_offset_s=launch, reset_offset_s=reset,
                usable_evaluation_s=reset-launch-MARGIN,
                reset_low_midpoint_interval_s=period+launch-reset,
                reset_lead_before_next_track_midpoint_s=period-reset,
                actual_14GHz=kind == 'fast', extended_control_not_14GHz=kind != 'fast',
                post_track_fall_end_guard_s=GUARD)


def events(cycles, tm, vdd):
    track, compare, signal = [], [], []
    for q in range(cycles+1):
        start = a.T0 + q*tm['period_s']
        track += [(start, vdd), (start+TRACK, 0.)]
        compare += [(start+tm['launch_offset_s'], vdd),
                    (start+tm['reset_offset_s'], 0.)]
        signal.append((start+2e-12, PATTERN[q % len(PATTERN)]))
    return track, compare, signal


def sized_strongarm(widths, mos=None, inp='cg_p', inn='cg_n', vdd='avdd',
                   buffer_vdd='bvdd', clk='cmp'):
    """Fig 1(b) StrongARM. Positive input resolves y high/x low and bx high/by low."""
    if mos is None:
        import native_geometry_r5 as geometry
        mos = geometry.mos
    devices = [('M1', 'p', inp, 'tail', '0', False, 'input'),
               ('M2', 'q', inn, 'tail', '0', False, 'input'),
               ('M3', 'x', 'y', 'p', '0', False, 'regen_n'),
               ('M4', 'y', 'x', 'q', '0', False, 'regen_n'),
               ('M5', 'x', 'y', vdd, vdd, True, 'regen_p'),
               ('M6', 'y', 'x', vdd, vdd, True, 'regen_p'),
               ('M7', 'tail', clk, '0', '0', False, 'tail')]
    devices += [('S'+n.upper(), n, clk, vdd, vdd, True, 'precharge')
                for n in ('p', 'q', 'x', 'y')]
    if widths['equalizer']:
        devices += [('MEQPQ', 'p', clk, 'q', vdd, True, 'equalizer'),
                    ('MEQXY', 'x', clk, 'y', vdd, True, 'equalizer')]
    for out, gate in [('bx', 'x'), ('by', 'y')]:
        devices += [('BN'+out, out, gate, '0', '0', False, 'buffer_n'),
                    ('BP'+out, out, gate, buffer_vdd, buffer_vdd, True, 'buffer_p')]
    return [mos(name, d, g, s, bulk, pmos=pmos, w=widths[group]*1e-6, l=30e-9)
            for name, d, g, s, bulk, pmos, group in devices]


def strongarm(widths, mos):
    return sized_strongarm(widths, mos)


def sampler(tag, mos):
    lines = []
    for side in ('p', 'n'):
        hold, source = tag+'h'+side, tag+'i'+side
        lines += [mos(tag+'SN'+side, hold, tag+'ck', source, '0', w=3e-6, l=30e-9),
                  mos(tag+'SP'+side, hold, tag+'kb', source, tag+'vdd',
                      pmos=True, w=3e-6, l=30e-9),
                  '%sCH%s (%s 0) capacitor c=5f' % (tag, side, hold),
                  '%sRH%s (%s %s) resistor r=1T' % (tag, side, hold, source)]
    return lines


def make_deck(cfg, tm, widths, mos):
    vdd, cm, lsb = cfg['supply_V'], cfg['common_mode_V'], cfg['fullscale_differential_Vpp']/128
    stop = a.T0+(cfg['cycles']+1)*tm['period_s']
    tr_events, cmp_events, sig_events = events(cfg['cycles'], tm, vdd)
    tr = a.pwl(0., tr_events, stop)
    cp = a.pwl(0., cmp_events, stop)
    inv = [(t, vdd-x) for t, x in tr]
    sp = a.pwl(cm+PATTERN[-1]*lsb/2, [(t, cm+x*lsb/2) for t, x in sig_events], stop)
    sn = a.pwl(cm-PATTERN[-1]*lsb/2, [(t, cm-x*lsb/2) for t, x in sig_events], stop)
    lines = a.b.header(temp=cfg['temperature_C']) + [
        '// Native geometric comparator screen, direct TG sampler; not complete ADC.',
        '// StrongARM topology: '+a.REFERENCE+' Fig.1(b).',
        'VSP (srcp 0) vsource type=pwl wave='+a.wave(sp),
        'VSN (srcn 0) vsource type=pwl wave='+a.wave(sn),
        'VA (avdd 0) vsource dc=%.15g' % vdd,
        'VB (bvdd 0) vsource dc=%.15g' % vdd,
        'VSD (dvdd 0) vsource dc=%.15g' % vdd,
        'VSR (rvdd 0) vsource dc=%.15g' % vdd,
        'VCMP (cmp 0) vsource type=pwl wave='+a.wave(cp)]
    for tag in ('d', 'r'):
        lines += ['V%sCK (%sck 0) vsource type=pwl wave=%s' % (tag.upper(), tag, a.wave(tr)),
                  'V%sKB (%skb 0) vsource type=pwl wave=%s' % (tag.upper(), tag, a.wave(inv))]
        for side in ('p', 'n'):
            lines += ['R%s%s (src%s %srs%s) resistor r=%.15g' %
                      (tag, side, side, tag, side, cfg['source_resistance_per_side_ohm']),
                      'VI%s%s (%srs%s %si%s) vsource dc=0' %
                      (tag.upper(), side.upper(), tag, side, tag, side)]
        lines += sampler(tag, mos)
    lines += ['VGIP (dhp cg_p) vsource dc=0', 'VGIN (dhn cg_n) vsource dc=0']
    lines += strongarm(widths, mos)
    lines += ['CBX (bx 0) capacitor c=%.15g' % cfg['buffer_output_capacitance_F'],
              'CBY (by 0) capacitor c=%.15g' % cfg['buffer_output_capacitance_F']]
    saves = ['srcp', 'srcn', 'dhp', 'dhn', 'rhp', 'rhn', 'dck', 'dkb', 'rck', 'rkb',
             'cmp', 'p', 'q', 'x', 'y', 'tail', 'bx', 'by', 'VA:p', 'VB:p', 'VSD:p',
             'VSR:p', 'VCMP:p', 'VDCK:p', 'VDKB:p', 'VGIP:p', 'VGIN:p']
    noise = '' if cfg['noise_seed'] is None else ' noisefmax=150G noisefmin=500M noiseseed=%d' % cfg['noise_seed']
    lines += ['saveOptions options save=selected currents=selected', 'save '+' '.join(saves),
              'tranResponse tran stop=%.15g maxstep=%.15g outputstart=%.15g errpreset=conservative%s' %
              (stop, cfg['maxstep_s'], a.T0+(cfg['warmup_cycles']-1)*tm['period_s'], noise)]
    return lines


def classify(high, low, vdd):
    if high >= .8*vdd and low <= .2*vdd:
        return 'correct'
    if low >= .8*vdd and high <= .2*vdd:
        return 'wrong'
    return 'unresolved'


def analyze_values(t, v, cfg, tm):
    vdd, lsb = cfg['supply_V'], cfg['fullscale_differential_Vpp']/128
    for tag in ('d', 'r'):
        if max(abs(x+z-vdd) for x, z in zip(v[tag+'ck'], v[tag+'kb'])) > 1e-8:
            raise ValueError('Sampler clocks not complementary')
    if max(abs(x-z) for x, z in zip(v['dck'], v['rck'])) > 1e-8:
        raise ValueError('DUT/reference clocks differ')
    rises = a.crossings(t, v['cmp'], vdd/2, True)
    falls = a.crossings(t, v['cmp'], vdd/2, False)
    track_falls = a.crossings(t, v['dck'], vdd/2, False)
    diff = [p-n for p, n in zip(v['dhp'], v['dhn'])]
    ref = [p-n for p, n in zip(v['rhp'], v['rhn'])]
    extra = [x-z for x, z in zip(diff, ref)]
    extra_cm = [(p+n-rp-rn)/2 for p, n, rp, rn in zip(v['dhp'], v['dhn'], v['rhp'], v['rhn'])]
    rows = []
    for q in range(cfg['warmup_cycles'], cfg['cycles']):
        start = a.T0+q*tm['period_s']
        launch = a.near(rises, start+tm['launch_offset_s'])
        reset = a.near(falls, start+tm['reset_offset_s'])
        prior_reset = a.near(falls, start-tm['period_s']+tm['reset_offset_s'])
        next_launch = a.near(rises, launch+tm['period_s'])
        track_fall = a.near(track_falls, start+TRACK)
        end, before = reset-MARGIN, launch-MARGIN
        if end-launch < 29e-12-1e-16:
            raise ValueError('29 ps endpoint intrudes into reset')
        target_lsb = PATTERN[q % len(PATTERN)]
        held = a.interpolate(t, diff, before)
        row = dict(cycle=q, source_LSB=target_lsb,
                   previous_source_LSB=PATTERN[(q-1) % len(PATTERN)],
                   held_input_prelaunch_V=held,
                   held_source_sign_disagreement=(held*target_lsb <= 0),
                   held_input_prelaunch_error_V=held-target_lsb*lsb,
                   sampler_only_prelaunch_error_V=a.interpolate(t, ref, before)-target_lsb*lsb,
                   actual_reset_low_midpoint_interval_s=launch-prior_reset,
                   actual_compare_after_track_fall_end_s=launch-track_fall-a.EDGE/2,
                   actual_usable_evaluation_s=end-launch,
                   prelaunch_P_minus_Q_V=a.interpolate(t, v['p'], before)-a.interpolate(t, v['q'], before),
                   prelaunch_X_minus_Y_V=a.interpolate(t, v['x'], before)-a.interpolate(t, v['y'], before),
                   prelaunch_internal_min_V=min(a.interpolate(t, v[n], before) for n in ('p', 'q', 'x', 'y')),
                   endpoints={}, stable_resolution_s={})
        points = [('20ps', launch+20e-12), ('25ps', launch+25e-12), ('29ps', launch+29e-12), ('end', end)]
        for basis, sign in [('source', 1 if target_lsb > 0 else -1),
                            ('held', 1 if held > 0 else (-1 if held < 0 else 0))]:
            row['stable_resolution_s'][basis] = {}
            for label, hp, lp in [('raw', 'y', 'x'), ('buffered', 'bx', 'by')]:
                hi, lo = (hp, lp) if sign >= 0 else (lp, hp)
                valid = [classify(h, l, vdd) == 'correct' for h, l in zip(v[hi], v[lo])]
                stable = a.first_stable(t, valid, launch, end) if sign else None
                if classify(a.interpolate(t, v[hi], end), a.interpolate(t, v[lo], end), vdd) != 'correct':
                    stable = None
                row['stable_resolution_s'][basis][label] = None if stable is None else stable-launch
                for point, at in points:
                    high, low = a.interpolate(t, v[hi], at), a.interpolate(t, v[lo], at)
                    state = classify(high, low, vdd) if sign else 'unresolved'
                    row['endpoints'].setdefault(point, {}).setdefault(basis, {})[label] = {
                        'classification': state, 'signed_difference_V': high-low if sign else 0.}
        for name, trace in [('differential', extra), ('common_mode', extra_cm)]:
            baseline = a.interpolate(t, trace, before)
            unused, values = a.window(t, trace, launch-a.EDGE/2, end)
            row['additional_'+name+'_excursion_peak_V'] = max(abs(x-baseline) for x in values)
        for name, src in [('comparator', 'VA:p'), ('buffer', 'VB:p'), ('sampler_body', 'VSD:p'),
                          ('compare_clock', 'VCMP:p'), ('sample_clock', 'VDCK:p'), ('sample_clock_bar', 'VDKB:p')]:
            voltage = v['cmp'] if name == 'compare_clock' else (v['dck'] if name == 'sample_clock' else (v['dkb'] if name == 'sample_clock_bar' else None))
            watts = [-x*y for x, y in zip(voltage, v[src])] if voltage is not None else [-vdd*x for x in v[src]]
            row[name+'_full_period_energy_J'] = a.integral(t, watts, launch, next_launch)
        rows.append(row)
    return rows


def summarize(rows, tm):
    out = dict(decisions=len(rows), endpoints={}, real_14GHz=tm['actual_14GHz'],
               held_source_sign_disagreements=sum(r['held_source_sign_disagreement'] for r in rows))
    for point in ('20ps', '25ps', '29ps', 'end'):
        out['endpoints'][point] = {
            basis: {label: {state: sum(r['endpoints'][point][basis][label]['classification'] == state for r in rows)
                            for state in STATES} for label in ('raw', 'buffered')}
            for basis in ('source', 'held')}
    out['stable_resolution_max_s'] = {}
    for basis in ('source', 'held'):
        out['stable_resolution_max_s'][basis] = {}
        for label in ('raw', 'buffered'):
            times = [r['stable_resolution_s'][basis][label] for r in rows
                     if r['stable_resolution_s'][basis][label] is not None]
            out['stable_resolution_max_s'][basis][label] = max(times) if times else None
    for key in ('prelaunch_P_minus_Q_V', 'prelaunch_X_minus_Y_V', 'held_input_prelaunch_error_V',
                'sampler_only_prelaunch_error_V', 'additional_differential_excursion_peak_V',
                'additional_common_mode_excursion_peak_V'):
        out['max_abs_'+key] = max(abs(r[key]) for r in rows)
    out['minimum_prelaunch_internal_V'] = min(r['prelaunch_internal_min_V'] for r in rows)
    for label in ('comparator', 'buffer', 'sampler_body', 'compare_clock', 'sample_clock', 'sample_clock_bar'):
        energy = sum(r[label+'_full_period_energy_J'] for r in rows)/len(rows)
        out[label+'_mean_energy_J'] = energy
        out[label+'_mean_power_W'] = energy/tm['period_s']
    out['all_source_decisions_resolved_by_29ps_screen'] = (
        tm['actual_14GHz'] and out['endpoints']['29ps']['source']['buffered']['correct'] == len(rows) and
        out['endpoints']['end']['source']['buffered']['correct'] == len(rows) and
        all(r['stable_resolution_s']['source']['buffered'] is not None and
            r['stable_resolution_s']['source']['buffered'] <= 29e-12 for r in rows))
    out['screen_is_not_complete_ADC_or_BER_qualification'] = True
    return out


def configuration(noise_seed=None):
    return dict(supply_V=.9, common_mode_V=.7568554324932689,
                fullscale_differential_Vpp=.1, temperature_C=25., cycles=36,
                warmup_cycles=4, maxstep_s=.1e-12, noise_seed=noise_seed,
                source_resistance_per_side_ohm=50., buffer_output_capacitance_F=1e-15,
                sampler_capacitance_per_side_F=5e-15, sampler_N_P_width_um=3.)


def self_test():
    assert len(candidates()) == 16
    cfg = configuration()
    def placeholder(name, d, g, s, bulk, **kw):
        return '%s (%s %s %s %s) TEST w=%.12g l=%.12g' % (name, d, g, s, bulk, kw['w'], kw['l'])
    for mode in ('fast', 'control'):
        tm = timing(mode)
        assert tm['reset_low_midpoint_interval_s'] > tm['launch_offset_s']
        assert tm['usable_evaluation_s'] >= 29e-12
        for widths in candidates().values():
            lines = make_deck(cfg, tm, widths, placeholder)
            names = [x.split()[0] for x in lines if x and not x.startswith('//') and '(' in x and not x.startswith('save ')]
            assert len(names) == len(set(names)), 'Duplicate Spectre instance identifier'
        # Synthetic waveforms verify source versus held classification and observed
        # clock alignment without native cards or a simulator. A positive command
        # is deliberately held negative in one cycle to expose sign bookkeeping.
        stop = a.T0+(cfg['cycles']+1)*tm['period_s']
        t = [i*.1e-12 for i in range(int(stop/.1e-12)+2)]
        tracks, compares, unused = events(cfg['cycles'], tm, .9)
        def sample(points):
            xx, yy = zip(*points)
            return [a.interpolate(xx, yy, min(x, stop)) for x in t]
        tr = sample(a.pwl(0., tracks, stop))
        cp = sample(a.pwl(0., compares, stop))
        v = {n: [0.]*len(t) for n in ('p', 'q', 'x', 'y', 'bx', 'by', 'dhp', 'dhn', 'rhp', 'rhn',
                                      'VA:p', 'VB:p', 'VSD:p', 'VCMP:p', 'VDCK:p', 'VDKB:p')}
        for tag in ('d', 'r'):
            v[tag+'ck'], v[tag+'kb'] = tr, [.9-x for x in tr]
        v['cmp'] = cp
        for i, at in enumerate(t):
            q = max(0, int((at-a.T0)/tm['period_s']))
            value = PATTERN[q % len(PATTERN)]*.1/128
            held = -value if q == 4 else value
            v['dhp'][i], v['dhn'][i] = .75+held/2, .75-held/2
            v['rhp'][i], v['rhn'][i] = .75+value/2, .75-value/2
            local = at-(a.T0+q*tm['period_s']+tm['launch_offset_s'])
            if local >= 18e-12 and cp[i] > .89:
                hi, lo = (.9, 0.) if held > 0 else (0., .9)
                v['y'][i], v['x'][i], v['bx'][i], v['by'][i] = hi, lo, hi, lo
            else:
                v['y'][i], v['x'][i] = .9, .9
            v['p'][i] = v['q'][i] = .9
        rows = analyze_values(t, v, cfg, tm)
        summary = summarize(rows, tm)
        assert len(rows) == 32
        assert summary['held_source_sign_disagreements'] == 1
        assert summary['endpoints']['29ps']['held']['buffered']['correct'] == 32
        assert summary['endpoints']['29ps']['source']['buffered']['wrong'] == 1
        assert abs(rows[0]['actual_compare_after_track_fall_end_s']-GUARD) < 1e-15
    print(json.dumps({'self_test': 'passed', 'candidates': 16, 'synthetic_analysis': True, 'simulator_executed': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', choices=sorted(candidates()), required=False)
    p.add_argument('--timing', choices=('fast', 'control'), default='fast')
    p.add_argument('--cards', type=Path, default=PROJECT/'configs/native_geometry_cards_r5.json')
    p.add_argument('--noise-seed', type=int)
    p.add_argument('--run', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--timeout', type=int, default=180)
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if args.case is None:
        p.error('--case is required except for --self-test')
    if not 10 <= args.timeout <= 600 or (args.noise_seed is not None and args.noise_seed < 1):
        p.error('Timeout must be 10..600; noise seed must be positive')
    import native_geometry_r5 as geometry
    geometry.install(args.cards)
    cfg, tm, widths = configuration(args.noise_seed), timing(args.timing), candidates()[args.case]
    lines = make_deck(cfg, tm, widths, geometry.mos)
    deck = '\n'.join(lines)+'\n'
    case = args.case+'_'+args.timing+('' if args.noise_seed is None else '_noise%d' % args.noise_seed)
    directory = PROJECT/'runs'/NAME/case
    identity = dict(script_sha256=a.digest(__file__), helper_sha256=a.digest(geometry.__file__),
                    probe_helpers_sha256=a.digest(a.__file__), native_cards_sha256=a.digest(args.cards),
                    deck_sha256=hashlib.sha256(deck.encode('utf-8')).hexdigest(),
                    configuration=cfg, timing=tm, geometry_widths_um=widths, input_pattern_LSB=PATTERN)
    record_path = directory/'comparator_r5_summary.json'
    if record_path.exists():
        previous = json.loads(record_path.read_text())
        if previous['identity'] != identity:
            raise ValueError('Existing case identity differs; refusing overwrite')
        if previous.get('status') == 'complete':
            if a.digest(directory/'bench.scs') != identity['deck_sha256'] or a.digest(a._raw_file(directory)) != previous['raw_sha256']:
                raise ValueError('Completed case provenance differs')
            print(json.dumps({'case': case, 'status': 'verified_existing_complete', 'summary': previous['summary']}), flush=True)
            return
    if (directory/'raw').exists():
        raise ValueError('Unbound/incomplete raw results exist; refusing overwrite')
    if (directory/'bench.scs').exists() and a.digest(directory/'bench.scs') != identity['deck_sha256']:
        raise ValueError('Existing deck differs; refusing overwrite')
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'bench.scs').write_text(deck)
    record = dict(schema_version=1, case=case, identity=identity, status='generated_only',
                  scope='Native-geometric single comparator timing/loading screen; no complete ADC claim',
                  assumptions=['TT 25C 0.9V; actual native CDF geometry including parasitic flags.',
                               '50ohm per-side sources, original 3um TG and 5fF per-side hold; real AFE absent.',
                               'Input source is updated 2ps after track begins; source and held correctness reported separately.',
                               'Clock-source energy is ideal-source signed delivered energy, not clock-tree power.',
                               'DUT minus sampler-only reference includes comparator loading and evaluation disturbance.',
                               'With noise enabled, DUT and reference have independent noise; their difference is not pure kickback.',
                               '80/20 percent supply output thresholds; small deterministic sequence is not BER or mismatch evidence.',
                               'Control timing is 300ps per decision and never a 14GHz pass; no DAC/logic/7-bit conversion here.'])
    if args.run:
        record['run_status'] = a.b.run(directory, lines, timeout=args.timeout)
        if record['run_status']['exit_code'] != 0:
            record['status'] = 'simulation_failed'
            a.atomic_json(record_path, record)
            raise RuntimeError('Simulation failed: '+case)
        raw = a.parse_file(a._raw_file(directory))
        rows = analyze_values(raw.values[raw.sweep_names[0]], raw.values, cfg, tm)
        record.update(status='complete', raw_sha256=raw.sha256, cycles=rows, summary=summarize(rows, tm))
    a.atomic_json(record_path, record)
    print(json.dumps({'case': case, 'status': record['status'], 'summary': record.get('summary')}), flush=True)


if __name__ == '__main__':
    main()
