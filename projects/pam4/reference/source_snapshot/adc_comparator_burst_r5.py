#!/usr/bin/env python3
"""Bounded short-reset comparator screen, NOT seven dependent SAR decisions.

One 3um TG/5fF sampler reacquires from a 50ohm source for 10ps per decision.
This deliberately tests local comparator reset/decision cadence; it does not
replace the 35.714ps master aperture or simulate a CDAC/reference/controller.
Six cases = StrongARM/double-tail x (55ps/15ps,55ps/20ps,48ps/20ps eval/reset).
Python3.6. Generate-only by default; cards and raw traces stay VM-side.
"""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import adc_comparator_r5 as r
import adc_doubletail_r5 as dt

a = r.a
NAME = 'adc_comparator_burst_r5_20261013'
TRACK = 10e-12
SCHEDULES = {'e55_r15': (55., 15.), 'e55_r20': (55., 20.), 'e48_r20': (48., 20.)}


def cases():
    return {top+'_'+s: (top, s) for top in ('sa', 'dt') for s in SCHEDULES}


def timing(schedule):
    evaluation, reset = [x*1e-12 for x in SCHEDULES[schedule]]
    launch = TRACK+a.EDGE/2+r.GUARD
    high = evaluation+r.MARGIN
    period = high+reset
    fall = launch+high
    # Prior comparator fall must finish before the next sampler rising edge starts.
    gap = period-a.EDGE/2-(fall+a.EDGE/2)
    if gap <= 0:
        raise ValueError('Next acquisition overlaps comparator evaluation/reset edge')
    return dict(schedule=schedule, period_s=period, track_duration_s=TRACK,
                launch_offset_s=launch, reset_offset_s=fall,
                usable_evaluation_s=evaluation, reset_low_midpoint_interval_s=reset,
                acquisition_after_previous_reset_edge_gap_s=gap,
                actual_14GHz=False, scope='local repeated comparator cadence, not master sampling rate')


def seven_decision_arithmetic(tm):
    """Explicit integration warning using supplied r5 secondary-interface timing."""
    next_track_begin = 64./112e9+1.5e-12
    result = {}
    for label, first in [('nominal_secondary', 64.21428571428571e-12),
                         ('late_secondary', 71.21428571428571e-12)]:
        last = first+6*tm['period_s']+tm['usable_evaluation_s']
        result[label] = dict(first_compare_launch_s=first, seventh_decision_endpoint_s=last,
                             next_same_secondary_track_begin_s=next_track_begin,
                             remaining_time_s=next_track_begin-last)
    return dict(cases=result, valid_complete_ADC_schedule=False,
                note='Conditional comparator-only arithmetic, excludes seven dependent DAC residuals, settling, control, capture and reference timing. Acquisitions in this screen are not physical SAR CDAC updates.')


def make_deck(cfg, tm, topology, mos):
    widths = r.candidates()['in100_tail3'] if topology == 'sa' else dt.candidates()['dt_balanced']
    lines = r.make_deck(cfg, tm, widths, mos) if topology == 'sa' else dt.make_deck(cfg, tm, widths, mos)
    vdd, cm, lsb = cfg['supply_V'], cfg['common_mode_V'], cfg['fullscale_differential_Vpp']/128
    stop = a.T0+(cfg['cycles']+1)*tm['period_s']
    tr, cp, sig = [], [], []
    for q in range(cfg['cycles']+1):
        start = a.T0+q*tm['period_s']
        tr += [(start, vdd), (start+TRACK, 0.)]
        cp += [(start+tm['launch_offset_s'], vdd), (start+tm['reset_offset_s'], 0.)]
        sig.append((start+2e-12, r.PATTERN[q % len(r.PATTERN)]))
    tr, cp = a.pwl(0., tr, stop), a.pwl(0., cp, stop)
    inv, cb = [(t, vdd-x) for t, x in tr], [(t, vdd-x) for t, x in cp]
    sp = a.pwl(cm+r.PATTERN[-1]*lsb/2, [(t, cm+x*lsb/2) for t, x in sig], stop)
    sn = a.pwl(cm-r.PATTERN[-1]*lsb/2, [(t, cm-x*lsb/2) for t, x in sig], stop)
    waveforms = {'VSP': ('srcp', sp), 'VSN': ('srcn', sn), 'VCMP': ('cmp', cp),
                 'VDCK': ('dck', tr), 'VDKB': ('dkb', inv), 'VRCK': ('rck', tr),
                 'VRKB': ('rkb', inv), 'VCMPB': ('cmpb', cb)}
    out = []
    for line in lines:
        name = line.split()[0] if line else ''
        if name in waveforms:
            node, points = waveforms[name]
            line = '%s (%s 0) vsource type=pwl wave=%s' % (name, node, a.wave(points))
        out.append(line)
    return out


def analyze(raw, cfg, tm, topology):
    t, v = raw.values[raw.sweep_names[0]], raw.values
    vdd, lsb = cfg['supply_V'], cfg['fullscale_differential_Vpp']/128
    for tag in ('d', 'r'):
        if max(abs(x+y-vdd) for x, y in zip(v[tag+'ck'], v[tag+'kb'])) > 1e-8:
            raise ValueError('Sampler clock complement mismatch')
    if max(abs(x-y) for x, y in zip(v['dck'], v['rck'])) > 1e-8:
        raise ValueError('DUT/reference clock mismatch')
    if topology == 'dt' and max(abs(x+y-vdd) for x, y in zip(v['cmp'], v['cmpb'])) > 1e-8:
        raise ValueError('Double-tail clock complement mismatch')
    rises = a.crossings(t, v['cmp'], vdd/2, True)
    falls = a.crossings(t, v['cmp'], vdd/2, False)
    track_rises = a.crossings(t, v['dck'], vdd/2, True)
    track_falls = a.crossings(t, v['dck'], vdd/2, False)
    diff = [p-n for p, n in zip(v['dhp'], v['dhn'])]
    ref = [p-n for p, n in zip(v['rhp'], v['rhn'])]
    extra = [x-y for x, y in zip(diff, ref)]
    extra_cm = [(p+n-rp-rn)/2 for p, n, rp, rn in zip(v['dhp'], v['dhn'], v['rhp'], v['rhn'])]
    rows = []
    for q in range(cfg['warmup_cycles'], cfg['cycles']):
        start = a.T0+q*tm['period_s']
        launch = a.near(rises, start+tm['launch_offset_s'])
        reset = a.near(falls, start+tm['reset_offset_s'])
        prior = a.near(falls, start-tm['period_s']+tm['reset_offset_s'])
        next_launch = a.near(rises, launch+tm['period_s'])
        tr = a.near(track_rises, start)
        tf = a.near(track_falls, start+TRACK)
        before, end = launch-r.MARGIN, launch+tm['usable_evaluation_s']
        if end > reset-a.EDGE/2-.05e-12 or tr-a.EDGE/2 <= prior+a.EDGE/2:
            raise ValueError('Acquisition/evaluation intrudes into adjacent clock edge')
        target = r.PATTERN[q % len(r.PATTERN)]
        held = a.interpolate(t, diff, before)
        row = dict(cycle=q, source_LSB=target, previous_source_LSB=r.PATTERN[(q-1) % len(r.PATTERN)],
                   held_input_prelaunch_V=held, held_source_sign_disagreement=held*target <= 0,
                   held_input_error_V=held-target*lsb, reference_input_error_V=a.interpolate(t, ref, before)-target*lsb,
                   actual_reset_low_midpoint_interval_s=launch-prior,
                   actual_track_duration_s=tf-tr, actual_compare_after_track_fall_end_s=launch-tf-a.EDGE/2,
                   prelaunch_P_minus_Q_V=a.interpolate(t, v['p'], before)-a.interpolate(t, v['q'], before),
                   prelaunch_X_minus_Y_V=a.interpolate(t, v['x'], before)-a.interpolate(t, v['y'], before),
                   prelaunch_p_q_min_V=min(a.interpolate(t, v[n], before) for n in ('p', 'q')),
                   prelaunch_x_y_min_V=min(a.interpolate(t, v[n], before) for n in ('x', 'y')),
                   prelaunch_x_y_max_V=max(a.interpolate(t, v[n], before) for n in ('x', 'y')),
                   endpoints={}, stable_resolution_s={})
        points = [(str(ps)+'ps', launch+ps*1e-12) for ps in (29, 40, 48, 50, 55)
                  if ps*1e-12 <= tm['usable_evaluation_s']+1e-18] + [('end', end)]
        for basis, sign in [('source', 1 if target > 0 else -1),
                            ('held', 1 if held > 0 else (-1 if held < 0 else 0))]:
            row['stable_resolution_s'][basis] = {}
            for label, hp, lp in [('raw', 'y', 'x'), ('buffered', 'bx', 'by')]:
                hi, lo = (hp, lp) if sign >= 0 else (lp, hp)
                valid = [r.classify(h, l, vdd) == 'correct' for h, l in zip(v[hi], v[lo])]
                stable = a.first_stable(t, valid, launch, end) if sign else None
                if r.classify(a.interpolate(t, v[hi], end), a.interpolate(t, v[lo], end), vdd) != 'correct':
                    stable = None
                row['stable_resolution_s'][basis][label] = None if stable is None else stable-launch
                for label_point, at in points:
                    high, low = a.interpolate(t, v[hi], at), a.interpolate(t, v[lo], at)
                    row['endpoints'].setdefault(label_point, {}).setdefault(basis, {})[label] = dict(
                        classification=r.classify(high, low, vdd) if sign else 'unresolved',
                        signed_difference_V=high-low if sign else 0.)
        for label, trace in [('differential', extra), ('common_mode', extra_cm)]:
            baseline = a.interpolate(t, trace, before)
            unused, z = a.window(t, trace, launch-a.EDGE/2, end)
            row['additional_'+label+'_excursion_peak_V'] = max(abs(x-baseline) for x in z)
        for label, current, voltage in [('comparator', 'VA:p', None), ('buffer', 'VB:p', None),
                                        ('compare_clock', 'VCMP:p', 'cmp')]+(
                                        [('compare_clock_bar', 'VCMPB:p', 'cmpb')] if topology == 'dt' else []):
            volts = v[voltage] if voltage else [vdd]*len(t)
            power = [-x*y for x, y in zip(volts, v[current])]
            row[label+'_energy_J'] = a.integral(t, power, launch, next_launch)
        rows.append(row)
    summary = dict(decisions=len(rows), endpoints={}, complete_ADC_verified=False,
                   held_source_sign_disagreements=sum(x['held_source_sign_disagreement'] for x in rows),
                   stable_resolution_max_s={})
    for point in rows[0]['endpoints']:
        summary['endpoints'][point] = {basis: {label: {state: sum(x['endpoints'][point][basis][label]['classification'] == state for x in rows)
                                                     for state in r.STATES} for label in ('raw', 'buffered')}
                                       for basis in ('source', 'held')}
    for basis in ('source', 'held'):
        summary['stable_resolution_max_s'][basis] = {}
        for label in ('raw', 'buffered'):
            times = [x['stable_resolution_s'][basis][label] for x in rows if x['stable_resolution_s'][basis][label] is not None]
            summary['stable_resolution_max_s'][basis][label] = max(times) if times else None
    for key in ('held_input_error_V', 'reference_input_error_V', 'prelaunch_P_minus_Q_V', 'prelaunch_X_minus_Y_V',
                'additional_differential_excursion_peak_V', 'additional_common_mode_excursion_peak_V'):
        summary['max_abs_'+key] = max(abs(x[key]) for x in rows)
    for label in ('comparator', 'buffer', 'compare_clock')+(('compare_clock_bar',) if topology == 'dt' else ()):
        energy = sum(x[label+'_energy_J'] for x in rows)/len(rows)
        summary[label+'_mean_energy_J'], summary[label+'_mean_power_W'] = energy, energy/tm['period_s']
    summary['minimum_prelaunch_p_q_V'] = min(x['prelaunch_p_q_min_V'] for x in rows)
    summary['minimum_prelaunch_x_y_V'] = min(x['prelaunch_x_y_min_V'] for x in rows)
    summary['maximum_prelaunch_x_y_V'] = max(x['prelaunch_x_y_max_V'] for x in rows)
    return rows, summary


def self_test():
    def fake(n, d, g, s, bulk, **kw):
        return '%s (%s %s %s %s) TEST w=%.15g' % (n, d, g, s, bulk, kw['w'])
    for top, schedule in cases().values():
        tm = timing(schedule)
        deck = make_deck(r.configuration(), tm, top, fake)
        names = [x.split()[0] for x in deck if x and not x.startswith('//') and '(' in x and not x.startswith('save ')]
        assert len(names) == len(set(names))
        assert tm['acquisition_after_previous_reset_edge_gap_s'] > 0
        assert abs(tm['period_s']-tm['usable_evaluation_s']-r.MARGIN-tm['reset_low_midpoint_interval_s']) < 1e-18
        assert not seven_decision_arithmetic(tm)['valid_complete_ADC_schedule']
    assert seven_decision_arithmetic(timing('e55_r20'))['cases']['late_secondary']['remaining_time_s'] < 0
    # Exercise the analyzer on the actual generated finite-edge clock waves.
    # One held polarity is reversed on purpose, and must be separated from a
    # comparator mistake even when the comparator faithfully follows its input.
    for top, schedule in [('sa', 'e55_r20'), ('dt', 'e48_r20')]:
        cfg, tm = r.configuration(), timing(schedule)
        deck = make_deck(cfg, tm, top, fake)
        stop = a.T0+(cfg['cycles']+1)*tm['period_s']
        t = [i*.25e-12 for i in range(int(stop/.25e-12)+1)]
        v = {'time': t}
        for line in deck:
            if ' vsource type=pwl wave=' in line:
                node = line.split('(')[1].split()[0]
                numbers = [float(x) for x in line.split('wave=')[1].strip(' []').split()]
                xx, yy = numbers[::2], numbers[1::2]
                v[node] = [a.interpolate(xx, yy, at) for at in t]
        for n in ('p', 'q', 'x', 'y', 'bx', 'by', 'dhp', 'dhn', 'rhp', 'rhn', 'VA:p', 'VB:p', 'VCMP:p', 'VCMPB:p'):
            v[n] = [0.]*len(t)
        for i, at in enumerate(t):
            q = max(0, int((at-a.T0)/tm['period_s']))
            source = r.PATTERN[q % len(r.PATTERN)]*.1/128
            held = -source if q == 4 else source
            v['dhp'][i], v['dhn'][i] = .75+held/2, .75-held/2
            v['rhp'][i], v['rhn'][i] = .75+source/2, .75-source/2
            v['p'][i], v['q'][i] = .9, .9
            v['x'][i] = v['y'][i] = .9 if top == 'sa' else 0.
            if at-(a.T0+q*tm['period_s']+tm['launch_offset_s']) >= 20e-12 and v['cmp'][i] > .45:
                hi, lo = (.9, 0.) if held > 0 else (0., .9)
                v['y'][i], v['x'][i], v['bx'][i], v['by'][i] = hi, lo, hi, lo
        rows, summary = analyze(SimpleNamespace(sweep_names=['time'], values=v), cfg, tm, top)
        assert summary['decisions'] == 32 and summary['held_source_sign_disagreements'] == 1
        assert summary['endpoints']['end']['source']['buffered']['wrong'] == 1
        assert summary['endpoints']['end']['held']['buffered']['correct'] == 32
        assert abs(rows[0]['actual_track_duration_s']-TRACK) < 1e-15
        assert abs(rows[0]['actual_reset_low_midpoint_interval_s']-tm['reset_low_midpoint_interval_s']) < 1e-15
    print(json.dumps({'self_test': 'passed', 'cases': 6, 'simulator_executed': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', choices=sorted(cases()))
    p.add_argument('--cards', type=Path, default=r.PROJECT/'configs/native_geometry_cards_r5.json')
    p.add_argument('--run', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--noise-seed', type=int)
    p.add_argument('--timeout', type=int, default=180)
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if not args.case or not 10 <= args.timeout <= 600 or (args.noise_seed is not None and args.noise_seed < 1):
        p.error('Case required; timeout10..600; positive noise seed')
    import native_geometry_r5 as geometry
    geometry.install(args.cards)
    top, schedule = cases()[args.case]
    cfg, tm = r.configuration(args.noise_seed), timing(schedule)
    cfg['local_sampler_track_s'] = TRACK
    lines = make_deck(cfg, tm, top, geometry.mos)
    deck = '\n'.join(lines)+'\n'
    case = args.case+('' if args.noise_seed is None else '_noise%d' % args.noise_seed)
    directory = r.PROJECT/'runs'/NAME/case
    identity = dict(script_sha256=a.digest(__file__), comparator_script_sha256=a.digest(r.__file__),
                    doubletail_script_sha256=a.digest(dt.__file__), probe_helpers_sha256=a.digest(a.__file__),
                    geometry_helper_sha256=a.digest(geometry.__file__), native_cards_sha256=a.digest(args.cards),
                    deck_sha256=hashlib.sha256(deck.encode('utf-8')).hexdigest(), configuration=cfg, timing=tm,
                    topology=top, candidate='in100_tail3' if top == 'sa' else 'dt_balanced', input_pattern_LSB=r.PATTERN)
    path = directory/'comparator_burst_r5_summary.json'
    if path.exists():
        prior = json.loads(path.read_text())
        if prior['identity'] != identity:
            raise ValueError('Existing case identity differs')
        if prior.get('status') == 'complete':
            if a.digest(directory/'bench.scs') != identity['deck_sha256'] or a.digest(a._raw_file(directory)) != prior['raw_sha256']:
                raise ValueError('Completed result provenance differs')
            print(json.dumps({'case': case, 'status': 'verified_existing_complete', 'summary': prior['summary']}), flush=True)
            return
    if (directory/'raw').exists():
        raise ValueError('Refusing to overwrite existing incomplete/unbound raw')
    if (directory/'bench.scs').exists() and a.digest(directory/'bench.scs') != identity['deck_sha256']:
        raise ValueError('Existing deck differs')
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'bench.scs').write_text(deck)
    record = dict(schema_version=1, case=case, identity=identity, status='generated_only',
                  scope='Repeated local comparator reset/cadence stress screen, NOT seven-bit ADC or complete backend',
                  conditional_seven_decision_timing=seven_decision_arithmetic(tm),
                  limitations=['10ps local TG reacquisition differs from master35.714ps aperture and actual SAR DAC switching.',
                               'Every decision uses a fresh prescribed external voltage; seven dependent residual decisions absent.',
                               'Finite50ohm input,5fFper-side capacitor; actual AFE/demultiplexer/CDAC/reference/controller absent.',
                               'TT25C0.9V only; ideal1ps clocks; no mismatch, PVT, clockskew or PEX.',
                               'Held-input error and sign disagreement reveal short-acquisition memory; source and held classifications differ.',
                               'Limited deterministic sequence is a screen, not BER, noise, ENOB or full-rate ADC proof.',
                               'Double-tail resets latchoutputs LOW; StrongARM resets them HIGH.',
                               'Clock-source energy is signed ideal-source energy, not a clock-driver power model.'])
    if args.run:
        record['run_status'] = a.b.run(directory, lines, timeout=args.timeout)
        if record['run_status']['exit_code'] != 0:
            record['status'] = 'simulation_failed'
            a.atomic_json(path, record)
            raise RuntimeError('Burst comparator simulation failed')
        raw = a.parse_file(a._raw_file(directory))
        rows, summary = analyze(raw, cfg, tm, top)
        record.update(status='complete', raw_sha256=raw.sha256, cycles=rows, summary=summary)
    a.atomic_json(path, record)
    print(json.dumps({'case': case, 'status': record['status'], 'summary': record.get('summary')}), flush=True)


if __name__ == '__main__':
    main()
