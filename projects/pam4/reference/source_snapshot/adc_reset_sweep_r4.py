#!/usr/bin/env python3
"""Bounded native StrongARM reset diagnostic, Python 3.6, generate-only default.

Reuses the original native cards and direct 5 fF sampler. This is not an ADC
or an isolation proof. All model-bearing decks and raw waves stay on the VM.
The 28 ps reset case deliberately exposes acquisition/evaluation overlap.
"""
import argparse
import copy
import hashlib
import itertools
import json
import math
from pathlib import Path

import adc_comparator_probe as a

PROJECT = a.PROJECT
TRACK = 8.0 / 112e9 / 2
GUARD = 2e-12
EVALUATION = 120e-12
EDGE_MARGIN = a.EDGE / 2 + .1e-12
# Extra 0.6 ps keeps the 120 ps observation before the falling edge starts.
HIGH_MIDPOINT = EVALUATION + EDGE_MARGIN
PATTERN = [1., 1., -1., -1., .25, -.25, .25, -.25,
           32., -.25, -32., .25, 32., .25, -32., -.25]
OBSERVATIONS = (80e-12, 100e-12, 120e-12)


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def timing(reset_ps):
    reset = reset_ps * 1e-12
    period = HIGH_MIDPOINT + reset
    launch_offset = TRACK + a.EDGE / 2 + GUARD
    return {'reset_low_midpoint_interval_s': reset,
            'period_s': period, 'track_duration_s': TRACK,
            'compare_high_midpoint_interval_s': HIGH_MIDPOINT,
            'usable_evaluation_s': EVALUATION,
            'launch_offset_s': launch_offset,
            'track_overlaps_previous_evaluation_s': max(0., launch_offset-reset),
            'post_track_fall_end_guard_s': GUARD}


def events(cycles, tm, vdd):
    tr, cp, signal = [], [], []
    for q in range(cycles+1):
        start = a.T0 + q*tm['period_s']
        launch = start+tm['launch_offset_s']
        tr += [(start, vdd), (start+TRACK, 0.)]
        cp += [(launch, vdd), (launch+HIGH_MIDPOINT, 0.)]
        signal.append((start+2e-12, PATTERN[q % len(PATTERN)]))
    return tr, cp, signal


def make_deck(cfg, tm):
    vdd, cm = cfg['supply_V'], cfg['common_mode_V']
    lsb = cfg['fullscale_differential_Vpp']/128
    stop = a.T0 + (cfg['cycles']+1)*tm['period_s']
    tr_changes, cp_changes, sig_changes = events(cfg['cycles'], tm, vdd)
    tr = a.pwl(0., tr_changes, stop)
    inv = [(t, vdd-v) for t, v in tr]
    cp = a.pwl(0., cp_changes, stop)
    previous = PATTERN[-1]*lsb
    sp = a.pwl(cm+previous/2, [(t, cm+x*lsb/2) for t, x in sig_changes], stop)
    sn = a.pwl(cm-previous/2, [(t, cm-x*lsb/2) for t, x in sig_changes], stop)
    lines = a.b.header(temp=cfg['temperature_C']) + [
        '// Native direct-sampler reset diagnostic. No isolation or ADC claim.',
        '// Input sequence LSB: '+','.join(str(x) for x in PATTERN),
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
            resistance = cfg['source_resistance_per_side_ohm']
            if resistance:
                lines.append('R%s%s (src%s %srs%s) resistor r=%.15g' %
                             (tag, side, side, tag, side, resistance))
                upstream = tag+'rs'+side
            else:
                upstream = 'src'+side
            lines.append('VI%s%s (%s %si%s) vsource dc=0' %
                         (tag.upper(), side.upper(), upstream, tag, side))
        lines += a.sampler(tag, tag+'vdd')
    lines += ['VGIP (dhp cg_p) vsource dc=0', 'VGIN (dhn cg_n) vsource dc=0']
    lines += a.strongarm(copies=cfg['copies'])
    lines += ['CBX (bx 0) capacitor c=%.15g' % cfg['buffer_output_capacitance_F'],
              'CBY (by 0) capacitor c=%.15g' % cfg['buffer_output_capacitance_F']]
    saves = ['srcp', 'srcn', 'dhp', 'dhn', 'rhp', 'rhn', 'dck', 'dkb', 'rck', 'rkb',
             'cmp', 'p', 'q', 'x', 'y', 'tail', 'bx', 'by', 'VA:p', 'VB:p',
             'VSD:p', 'VSR:p', 'VCMP:p', 'VDCK:p', 'VDKB:p', 'VGIP:p', 'VGIN:p']
    lines += ['saveOptions options save=selected currents=selected', 'save '+' '.join(saves),
              'tranResponse tran stop=%.15g maxstep=%.15g outputstart=%.15g errpreset=conservative' %
              (stop, cfg['maxstep_s'], a.T0+(cfg['warmup_cycles']-1)*tm['period_s'])]
    return lines


def classify(high, low, vdd):
    if high >= .8*vdd and low <= .2*vdd:
        return 'correct'
    if low >= .8*vdd and high <= .2*vdd:
        return 'wrong'
    return 'unresolved'


def analyze_values(t, v, cfg, tm):
    vdd, lsb = cfg['supply_V'], cfg['fullscale_differential_Vpp']/128
    if max(abs(x-z) for x, z in zip(v['dck'], v['rck'])) > 1e-8:
        raise ValueError('DUT and reference track clocks differ')
    if max(abs(x+z-vdd) for x, z in zip(v['dck'], v['dkb'])) > 1e-8:
        raise ValueError('DUT sampler clocks are not complementary')
    rises = a.crossings(t, v['cmp'], vdd/2, True)
    falls = a.crossings(t, v['cmp'], vdd/2, False)
    track_falls = a.crossings(t, v['dck'], vdd/2, False)
    d = [x-z for x, z in zip(v['dhp'], v['dhn'])]
    rd = [x-z for x, z in zip(v['rhp'], v['rhn'])]
    dd = [x-z for x, z in zip(d, rd)]
    dc = [(p+n-rp-rn)/2 for p, n, rp, rn in zip(v['dhp'], v['dhn'], v['rhp'], v['rhn'])]
    rows = []
    for q in range(cfg['warmup_cycles'], cfg['cycles']):
        start = a.T0+q*tm['period_s']
        launch = a.near(rises, start+tm['launch_offset_s'])
        reset = a.near(falls, launch+HIGH_MIDPOINT)
        prior_reset = a.near(falls, launch-tm['reset_low_midpoint_interval_s'])
        next_launch = a.near(rises, launch+tm['period_s'])
        track_fall = a.near(track_falls, start+TRACK)
        end = launch+EVALUATION
        if end > reset-a.EDGE/2-.05e-12:
            raise ValueError('120 ps endpoint intrudes into the reset edge')
        target_lsb = PATTERN[q % len(PATTERN)]
        sign = 1 if target_lsb > 0 else -1
        before = launch-a.EDGE/2-.1e-12
        row = {'cycle': q, 'input_LSB': target_lsb,
               'previous_input_LSB': PATTERN[(q-1) % len(PATTERN)],
               'actual_reset_low_midpoint_interval_s': launch-prior_reset,
               'actual_compare_after_track_fall_end_s': launch-track_fall-a.EDGE/2,
               'prelaunch_P_minus_Q_V': a.interpolate(t, v['p'], before)-a.interpolate(t, v['q'], before),
               'prelaunch_X_minus_Y_V': a.interpolate(t, v['x'], before)-a.interpolate(t, v['y'], before),
               'prelaunch_internal_min_V': min(a.interpolate(t, v[n], before) for n in ('p', 'q', 'x', 'y')),
               'held_input_at_launch_V': a.interpolate(t, d, launch),
               'held_input_error_at_launch_V': a.interpolate(t, d, launch)-target_lsb*lsb,
               'sampler_only_input_error_at_launch_V': a.interpolate(t, rd, launch)-target_lsb*lsb,
               'endpoints': {}}
        for label, hp, lp in [('raw', 'y', 'x'), ('buffered', 'bx', 'by')]:
            hi, lo = (hp, lp) if sign > 0 else (lp, hp)
            correct = [classify(h, l, vdd) == 'correct' for h, l in zip(v[hi], v[lo])]
            first = a.first_stable(t, correct, launch, end)
            if classify(a.interpolate(t, v[hi], end), a.interpolate(t, v[lo], end), vdd) != 'correct':
                first = None
            row[label+'_stable_correct_resolution_s'] = None if first is None else first-launch
            for delta in OBSERVATIONS:
                key = str(int(round(delta*1e12)))+'ps'
                at = launch+delta
                h, l = a.interpolate(t, v[hi], at), a.interpolate(t, v[lo], at)
                row['endpoints'].setdefault(key, {})[label] = {
                    'classification': classify(h, l, vdd), 'signed_difference_V': h-l}
        for name, trace in [('differential', dd), ('common_mode', dc)]:
            baseline = a.interpolate(t, trace, before)
            unused, z = a.window(t, trace, launch-a.EDGE/2, end)
            row['compare_kickback_'+name+'_peak_V'] = max(abs(x-baseline) for x in z)
        for name, source in [('comparator', 'VA:p'), ('buffer', 'VB:p'), ('DUT_sampler', 'VSD:p')]:
            row[name+'_full_period_energy_J'] = -vdd*a.integral(t, v[source], launch, next_launch)
        # Diagnostic screen only: residual output differential is not input-referred offset.
        row['reset_screen_internal_above_95pct_and_abs_pair_residual_below_quarter_input_LSB'] = (
            row['prelaunch_internal_min_V'] >= .95*vdd and
            abs(row['prelaunch_P_minus_Q_V']) <= lsb/4 and
            abs(row['prelaunch_X_minus_Y_V']) <= lsb/4)
        rows.append(row)
    return rows


def summarize(rows, tm):
    out = {'decisions': len(rows), 'endpoints': {},
           'acquisition_overlap_case': tm['track_overlaps_previous_evaluation_s'] > 1e-18}
    for point in ('80ps', '100ps', '120ps'):
        out['endpoints'][point] = {label: {state: sum(r['endpoints'][point][label]['classification'] == state for r in rows)
                                         for state in ('correct', 'wrong', 'unresolved')}
                                  for label in ('raw', 'buffered')}
    for label in ('raw', 'buffered'):
        times = [r[label+'_stable_correct_resolution_s'] for r in rows if r[label+'_stable_correct_resolution_s'] is not None]
        out[label+'_stable_correct_resolution_max_s'] = max(times) if times else None
    for pair in ('P_minus_Q', 'X_minus_Y'):
        out['max_abs_prelaunch_'+pair+'_V'] = max(abs(r['prelaunch_'+pair+'_V']) for r in rows)
    out['minimum_prelaunch_internal_V'] = min(r['prelaunch_internal_min_V'] for r in rows)
    out['reset_residual_screen_failures'] = sum(not r['reset_screen_internal_above_95pct_and_abs_pair_residual_below_quarter_input_LSB'] for r in rows)
    out['reset_screen_is_diagnostic_not_input_offset_proof'] = True
    for label in ('differential', 'common_mode'):
        out['max_'+label+'_kickback_V'] = max(r['compare_kickback_'+label+'_peak_V'] for r in rows)
    for label in ('comparator', 'buffer', 'DUT_sampler'):
        energy = sum(r[label+'_full_period_energy_J'] for r in rows)/len(rows)
        out[label+'_mean_energy_J'] = energy
        out[label+'_mean_power_W'] = energy/tm['period_s']
    out['max_abs_loaded_input_error_at_launch_V'] = max(abs(r['held_input_error_at_launch_V']) for r in rows)
    return out


def self_test():
    assert len(list(itertools.product((1, 4), (1, 4), (28, 42, 70, 100)))) == 16
    assert timing(28)['track_overlaps_previous_evaluation_s'] > 10e-12
    assert timing(42)['track_overlaps_previous_evaluation_s'] == 0
    assert classify(.85, .05, .9) == 'correct'
    assert classify(.05, .85, .9) == 'wrong'
    assert classify(.4, .4, .9) == 'unresolved'
    cfg = {'supply_V': .9, 'fullscale_differential_Vpp': .128,
           'cycles': 20, 'warmup_cycles': 4}
    tm = timing(70)
    stop = a.T0+21*tm['period_s']
    times = [i*.2e-12 for i in range(int(stop/.2e-12)+2)]
    tr, cp, unused = events(20, tm, .9)
    tr, cp = a.pwl(0., tr, stop), a.pwl(0., cp, stop)
    def wave_at(points, at):
        xx, yy = zip(*points)
        return a.interpolate(list(xx), list(yy), min(at, xx[-1]))
    signals = {name: [] for name in ('dck', 'dkb', 'rck', 'rkb', 'cmp', 'dhp', 'dhn',
               'rhp', 'rhn', 'p', 'q', 'x', 'y', 'bx', 'by', 'VA:p', 'VB:p', 'VSD:p')}
    for at in times:
        q = max(0, int((at-a.T0)/tm['period_s']))
        target = PATTERN[q % 16]*.001
        launch = a.T0+q*tm['period_s']+tm['launch_offset_s']
        reset = launch+HIGH_MIDPOINT
        active = launch+60e-12 <= at < reset
        # One wrong and one unresolved scored cycle exercise classification.
        sign = (1 if target > 0 else -1)*(-1 if q == 5 else 1)
        if q == 6:
            active = False
        tc, cc = wave_at(tr, at), wave_at(cp, at)
        for name, value in [('dck', tc), ('rck', tc), ('dkb', .9-tc), ('rkb', .9-tc), ('cmp', cc),
                            ('dhp', .45+target/2), ('rhp', .45+target/2), ('dhn', .45-target/2), ('rhn', .45-target/2),
                            ('p', .1 if active else .9), ('q', .1 if active else .9),
                            ('x', 0. if active and sign > 0 else .9), ('y', 0. if active and sign < 0 else .9),
                            ('bx', .9 if active and sign > 0 else 0.), ('by', .9 if active and sign < 0 else 0.),
                            ('VA:p', -.001), ('VB:p', 0.), ('VSD:p', 0.)]:
            signals[name].append(value)
    rows = analyze_values(times, signals, cfg, tm)
    result = summarize(rows, tm)
    assert len(rows) == 16
    assert result['endpoints']['120ps']['buffered'] == {'correct': 14, 'wrong': 1, 'unresolved': 1}
    assert result['reset_residual_screen_failures'] == 0
    assert abs(result['comparator_mean_energy_J']-.9*.001*tm['period_s']) < 1e-24
    assert abs(result['buffered_stable_correct_resolution_max_s']-60e-12) < .21e-12
    print(json.dumps({'self_test': 'passed', 'simulator_executed': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--timeout', type=int, default=180)
    p.add_argument('--output-dir', type=Path, default=PROJECT/'runs/adc_reset_r4_20261013')
    p.add_argument('--baseline-summary', type=Path, default=PROJECT/'runs/adc_comparator_r3_tt/comparator_probe_summary.json')
    p.add_argument('--cards', type=Path, default=PROJECT/'configs/native_device_cards.json')
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if args.timeout < 10 or args.timeout > 600:
        p.error('Timeout must be 10..600 seconds per bounded case')
    output = args.output_dir.resolve()
    allowed = (PROJECT/'runs').resolve()
    if allowed not in output.parents or output.name != 'adc_reset_r4_20261013':
        p.error('Output must be the new adc_reset_r4_20261013 directory under project runs')
    original = json.loads(args.baseline_summary.read_text())
    cfg = copy.deepcopy(original['configuration'])
    cfg.update(cycles=20, warmup_cycles=4, noise_seed=None)
    a.validate_card_identity(args.cards)
    native = a.install_native_cards(args.cards)
    if original['native_cards']['native_cards_sha256'] != native['native_cards_sha256']:
        raise ValueError('Native cards differ from original comparator probe')
    if cfg['common_mode_V']-max(PATTERN)*cfg['fullscale_differential_Vpp']/256 <= 0 or \
            cfg['common_mode_V']+max(PATTERN)*cfg['fullscale_differential_Vpp']/256 >= cfg['supply_V']:
        raise ValueError('Diagnostic input exceeds supplies')
    identity = {'script_sha256': a.digest(__file__),
                'baseline_summary_sha256': a.digest(args.baseline_summary),
                'native_cards_sha256': native['native_cards_sha256'],
                'input_pattern_LSB': PATTERN, 'base_configuration': cfg,
                'evaluation_s': EVALUATION, 'compare_high_midpoint_interval_s': HIGH_MIDPOINT}
    output.mkdir(parents=True, exist_ok=True)
    identity_path = output/'sweep_identity.json'
    if identity_path.exists():
        if json.loads(identity_path.read_text()) != identity:
            raise ValueError('Existing sweep identity differs; refusing mutation')
    else:
        a.atomic_json(identity_path, identity)
    result = {'schema_version': 1, 'scope': 'Native direct-sampler StrongARM reset diagnostic; not an ADC or isolation proof',
              'status': 'running' if args.run else 'generating', 'identity': identity,
              'endpoint_note': 'Compare rising midpoint +80/+100/+120 ps; reset falling midpoint is +120.6 ps.',
              'overlap_note': '28 ps low reset overlaps prior evaluation with next 35.714 ps acquisition; not a pure reset test.',
              'assumptions': ['Deterministic TT baseline conditions, no transient noise, mismatch, PVT or extracted wiring.',
                              'Actual native 3um/30nm copies; direct TG and 5fF per side, finite baseline source R.',
                              'All 7-bit LSB labels use frozen baseline differential ADC range; no seven-step conversion.',
                              'Reset residual threshold is a screening metric, not input-referred offset or proof.',
                              'Ideal clocks have 1ps edges; full-period supply energy excludes physical clock/bias generation.'],
              'cases': []}
    for precharge, tail, reset_ps in itertools.product((1, 4), (1, 4), (28, 42, 70, 100)):
        case = 'pre%d_tail%d_reset%dps' % (precharge, tail, reset_ps)
        cc = copy.deepcopy(cfg)
        cc['copies'].update(precharge=precharge, tail=tail)
        tm = timing(reset_ps)
        lines = make_deck(cc, tm)
        deck = '\n'.join(lines)+'\n'
        directory = output/case
        directory.mkdir(exist_ok=True)
        deck_path, record_path = directory/'bench.scs', directory/'reset_case_summary.json'
        if deck_path.exists() and a.digest(deck_path) != sha(deck):
            raise ValueError('Existing case deck differs: '+case)
        if record_path.exists():
            prior = json.loads(record_path.read_text())
            if prior.get('raw_sha256') is not None:
                if prior['deck_sha256'] != sha(deck) or prior['raw_sha256'] != a.digest(a._raw_file(directory)):
                    raise ValueError('Completed case provenance differs: '+case)
                result['cases'].append(prior)
                a.atomic_json(output/'reset_sweep_summary.json', result)
                print(json.dumps({'case': case, 'status': 'verified_existing_complete'}), flush=True)
                continue
        if (directory/'raw').exists():
            raise ValueError('Unbound raw results exist; refusing overwrite: '+case)
        deck_path.write_text(deck)
        record = {'case': case, 'precharge_copies': precharge, 'tail_copies': tail,
                  'timing': tm, 'deck_sha256': sha(deck), 'status': 'generated_only'}
        if args.run:
            record['run_status'] = a.b.run(directory, lines, timeout=args.timeout)
            if record['run_status']['exit_code'] != 0:
                record['status'] = 'simulation_failed'
                a.atomic_json(record_path, record)
                result['cases'].append(record)
                result['status'] = 'failed'
                a.atomic_json(output/'reset_sweep_summary.json', result)
                raise RuntimeError('Reset case failed: '+case)
            raw = a.parse_file(a._raw_file(directory))
            rows = analyze_values(raw.values[raw.sweep_names[0]], raw.values, cc, tm)
            record.update(status='complete', raw_sha256=raw.sha256, cycles=rows, summary=summarize(rows, tm))
        a.atomic_json(record_path, record)
        result['cases'].append(record)
        a.atomic_json(output/'reset_sweep_summary.json', result)
        print(json.dumps({'case': case, 'status': record['status'], 'summary': record.get('summary')}), flush=True)
    result['status'] = 'complete' if all(x['status'] == 'complete' for x in result['cases']) else 'generated_only'
    a.atomic_json(output/'reset_sweep_summary.json', result)


if __name__ == '__main__':
    main()
