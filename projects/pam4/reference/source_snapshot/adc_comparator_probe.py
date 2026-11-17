#!/usr/bin/env python3
"""Native-MOS sampler/StrongARM loading probe; generate-only unless --run.

Prepared for execution only after the parent frontend-reduction gate.
Topology: Razavi, The StrongARM Latch, Fig. 1(b), DOI 10.1109/MSSC.2015.2418155.
https://www.seas.ucla.edu/brweb/papers/Journals/BR_Magzine4.pdf

This is one decision element with an isolated sampler reference, NOT a 7-bit
ADC, CDAC, 64-lane implementation, PEX result, or complete receiver simulation.
Python 3.6 and standard library. Native cards and raw traces stay on the VM.
"""
import argparse
import bisect
import hashlib
import json
import math
import re
from pathlib import Path

import p6_bench as b
from pam4_integration import _raw_file, install_native_cards
from psf_ascii import parse_file

PROJECT = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
REFERENCE = 'https://www.seas.ucla.edu/brweb/papers/Journals/BR_Magzine4.pdf'
PERIOD = 8.0 / 112e9
EDGE = 1e-12
T0 = 100e-12


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n')
    tmp.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def interpolate(t, y, x):
    if x < t[0] - 1e-18 or x > t[-1] + 1e-18:
        raise ValueError('Analysis point outside saved transient')
    i = bisect.bisect_left(t, x)
    if i == 0:
        return y[0]
    if i == len(t):
        return y[-1]
    alpha = (x - t[i-1]) / (t[i] - t[i-1])
    return y[i-1] * (1-alpha) + y[i] * alpha


def window(t, y, lo, hi):
    if hi <= lo:
        raise ValueError('Empty analysis window')
    first, last = bisect.bisect_right(t, lo), bisect.bisect_left(t, hi)
    return ([lo] + t[first:last] + [hi],
            [interpolate(t, y, lo)] + y[first:last] + [interpolate(t, y, hi)])


def integral(t, y, lo, hi):
    x, z = window(t, y, lo, hi)
    return sum((x[i+1]-x[i]) * (z[i+1]+z[i])/2 for i in range(len(x)-1))


def crossings(t, y, level, rising):
    points = []
    for i in range(1, len(t)):
        a, z = y[i-1], y[i]
        crossed = a < level <= z if rising else a > level >= z
        if crossed:
            points.append(t[i-1] + (level-a) * (t[i]-t[i-1]) / (z-a))
    return points


def near(points, expected, tolerance=2e-12):
    if not points:
        raise ValueError('Required saved clock edge missing')
    closest = min(points, key=lambda x: abs(x-expected))
    if abs(closest-expected) > tolerance:
        raise ValueError('Actual clock edge differs from generated timing')
    return closest


def first_stable(t, valid, lo, hi):
    """First saved instant remaining valid through hi; no interpolated logic."""
    indices = [i for i, x in enumerate(t) if lo <= x <= hi]
    if not indices or not valid[indices[-1]]:
        return None
    answer = indices[-1]
    for i in reversed(indices):
        if not valid[i]:
            break
        answer = i
    return t[answer]


def pwl(initial, changes, stop):
    """changes are midpoint-time/value pairs with explicit finite edges."""
    points = [(0.0, initial)]
    value = initial
    for midpoint, new in changes:
        begin, end = midpoint-EDGE/2, midpoint+EDGE/2
        if begin <= points[-1][0]:
            raise ValueError('Overlapping or nonmonotonic PWL transitions')
        points += [(begin, value), (end, new)]
        value = new
    if stop > points[-1][0]:
        points.append((stop, value))
    return points


def wave(points):
    return '[ ' + ' '.join('%.15g %.15g' % pair for pair in points) + ' ]'


def clock_changes(cycles, vdd):
    track, compare = [], []
    for q in range(cycles+1):
        start = T0 + q*PERIOD
        track += [(start, vdd), (start+PERIOD/2, 0.0)]
        # Compare rising MIDPOINT is 2 ps after the END of track's falling edge.
        compare += [(start+PERIOD/2+EDGE/2+2e-12, vdd),
                    (start+PERIOD-4e-12, 0.0)]
    return track, compare


def strongarm(vdd='avdd', clk='cmp', inp='cg_p', inn='cg_n', copies=None):
    """Fig. 1(b): N input pair, cross-coupled N/P, tail, four P precharges.

    M3 is (X,Y,P,0), M4 is (Y,X,Q,0). Positive inp-inn drives X low/Y high.
    Geometry is provided by the installed native b.mos function, never resized.
    """
    count = dict(input=1, regen_n=1, regen_p=1, tail=1, precharge=1, buffer=1)
    count.update(copies or {})
    if any(not isinstance(x, int) or x < 1 or x > 16 for x in count.values()):
        raise ValueError('Native copies must be integers from 1 to 16')
    devices = [('M1', 'p', inp, 'tail', '0', False, 'input'),
               ('M2', 'q', inn, 'tail', '0', False, 'input'),
               ('M3', 'x', 'y', 'p', '0', False, 'regen_n'),
               ('M4', 'y', 'x', 'q', '0', False, 'regen_n'),
               ('M5', 'x', 'y', vdd, vdd, True, 'regen_p'),
               ('M6', 'y', 'x', vdd, vdd, True, 'regen_p'),
               ('M7', 'tail', clk, '0', '0', False, 'tail')]
    devices += [('S'+node.upper(), node, clk, vdd, vdd, True, 'precharge')
                for node in ('p', 'q', 'x', 'y')]
    lines = []
    for name, d, g, s, bulk, pmos, group in devices:
        for j in range(count[group]):
            lines.append(b.mos(name+'_'+str(j), d, g, s, bulk, pmos=pmos, l=30e-9))
    for output, gate in [('bx', 'x'), ('by', 'y')]:
        for j in range(count['buffer']):
            lines += [b.mos('BN'+output+str(j), output, gate, '0', '0'),
                      b.mos('BP'+output+str(j), output, gate, 'bvdd', 'bvdd', pmos=True)]
    return lines


def validate_card_identity(path):
    """Check the actual N/P model and one-finger, unit-multiplicity claims."""
    cards = json.loads(Path(path).read_text())
    for key, expected_model in [('n_l30', 'nmos_lvt'), ('p_l30', 'pmos_lvt')]:
        card = cards[key]
        if card['model'] != expected_model:
            raise ValueError('Incorrect native model polarity/flavor for '+key)
        for parameter in ('nf', 'multi'):
            match = re.search(r'(?<!\w)'+parameter+r'\s*=\s*\(?\s*([+\-0-9.eE]+)\s*\)?(?=\s|$)', card['parameters'])
            if not match or float(match.group(1)) != 1.0:
                raise ValueError('Probe requires native nf=1 and multi=1: '+key)


def sampler(tag, vdd):
    lines = []
    for side in ('p', 'n'):
        hold, source = tag+'h'+side, tag+'i'+side
        lines += [b.mos(tag+'SN'+side, hold, tag+'ck', source, '0'),
                  b.mos(tag+'SP'+side, hold, tag+'kb', source, vdd, pmos=True),
                  '%sCH%s (%s 0) capacitor c=5f' % (tag, side, hold),
                  '%sRH%s (%s %s) resistor r=1T' % (tag, side, hold, source)]
    return lines


def make_deck(config, magnitude_lsb):
    vdd, cm = config['supply_V'], config['common_mode_V']
    cycles, fullscale = config['cycles'], config['fullscale_differential_Vpp']
    delta = magnitude_lsb * fullscale/128
    stop = T0 + (cycles+1)*PERIOD
    track, compare = clock_changes(cycles, vdd)
    # Alternating polarity exercises memory/reset and finite acquisition.
    differential = [(T0+q*PERIOD+2e-12, delta if q % 2 == 0 else -delta)
                    for q in range(cycles+1)]
    sigp = pwl(cm-delta/2, [(t, cm+x/2) for t, x in differential], stop)
    sign = pwl(cm+delta/2, [(t, cm-x/2) for t, x in differential], stop)
    tr = pwl(0.0, track, stop)
    inv = [(t, vdd-x) for t, x in tr]
    cmp = pwl(0.0, compare, stop)
    lines = b.header(temp=config['temperature_C']) + [
        '// One StrongARM decision element; native card geometry; no ADC conversion claim.',
        '// Topology: '+REFERENCE+' Fig.1(b). All sizing is a new unoptimized candidate.',
        'VSP (srcp 0) vsource type=pwl wave='+wave(sigp),
        'VSN (srcn 0) vsource type=pwl wave='+wave(sign),
        'VA (avdd 0) vsource dc=%.15g' % vdd,
        'VB (bvdd 0) vsource dc=%.15g' % vdd,
        'VSD (dvdd 0) vsource dc=%.15g' % vdd,
        'VSR (rvdd 0) vsource dc=%.15g' % vdd,
        'VCMP (cmp 0) vsource type=pwl wave='+wave(cmp)]
    for tag in ('d', 'r'):
        lines += ['V%sCK (%sck 0) vsource type=pwl wave=%s' % (tag.upper(), tag, wave(tr)),
                  'V%sKB (%skb 0) vsource type=pwl wave=%s' % (tag.upper(), tag, wave(inv))]
        for side in ('p', 'n'):
            r = config['source_resistance_per_side_ohm']
            if r:
                lines.append('R%s%s (src%s %srs%s) resistor r=%.15g' % (tag, side, side, tag, side, r))
                upstream = tag+'rs'+side
            else:
                upstream = 'src'+side
            lines.append('VI%s%s (%s %si%s) vsource dc=0' % (tag.upper(), side.upper(), upstream, tag, side))
        lines += sampler(tag, tag+'vdd')
    lines += ['VGIP (dhp cg_p) vsource dc=0', 'VGIN (dhn cg_n) vsource dc=0']
    lines += strongarm(copies=config['copies'])
    lines += ['CBX (bx 0) capacitor c=%.15g' % config['buffer_output_capacitance_F'],
              'CBY (by 0) capacitor c=%.15g' % config['buffer_output_capacitance_F']]
    saves = ['srcp', 'srcn', 'dip', 'din', 'rip', 'rin', 'dhp', 'dhn', 'rhp', 'rhn',
             'dck', 'dkb', 'rck', 'rkb', 'cmp', 'p', 'q', 'x', 'y', 'tail', 'bx', 'by',
             'VA:p', 'VB:p', 'VSD:p', 'VSR:p', 'VDCK:p', 'VDKB:p', 'VRCK:p', 'VRKB:p',
             'VCMP:p', 'VGIP:p', 'VGIN:p', 'VIDP:p', 'VIDN:p', 'VIRP:p', 'VIRN:p']
    noise = ''
    if config['noise_seed'] is not None:
        noise = ' noisefmax=150G noisefmin=500M noiseseed=%d' % config['noise_seed']
    lines += ['saveOptions options save=selected currents=selected', 'save '+' '.join(saves),
              'tranResponse tran stop=%.15g maxstep=%.15g outputstart=%.15g errpreset=conservative%s' % (
                  stop, config['maxstep_s'], T0+(config['warmup_cycles']-1)*PERIOD, noise)]
    return lines


def analyze_values(t, values, config, magnitude_lsb):
    vdd, lsb = config['supply_V'], config['fullscale_differential_Vpp']/128
    if max(abs(a-z) for a, z in zip(values['dck'], values['rck'])) > 1e-8 or \
            max(abs(a-z) for a, z in zip(values['dkb'], values['rkb'])) > 1e-8:
        raise ValueError('Reference and DUT sampler clocks differ')
    if max(abs(a+z-vdd) for a, z in zip(values['dck'], values['dkb'])) > 1e-8:
        raise ValueError('Sampler clocks are not the intended complements')
    d = [a-b for a, b in zip(values['dhp'], values['dhn'])]
    r = [a-b for a, b in zip(values['rhp'], values['rhn'])]
    dp = [a-b for a, b in zip(values['dhp'], values['rhp'])]
    dn = [a-b for a, b in zip(values['dhn'], values['rhn'])]
    dd = [a-b for a, b in zip(dp, dn)]
    dc = [(a+b)/2 for a, b in zip(dp, dn)]
    dcm = [(a+b)/2 for a, b in zip(values['dhp'], values['dhn'])]
    falls = crossings(t, values['dck'], vdd/2, False)
    rises = crossings(t, values['dck'], vdd/2, True)
    launches = crossings(t, values['cmp'], vdd/2, True)
    resets = crossings(t, values['cmp'], vdd/2, False)
    rows = []
    for q in range(config['warmup_cycles'], config['cycles']):
        start = T0+q*PERIOD
        track_rise = near(rises, start)
        track_fall = near(falls, start+PERIOD/2)
        launch = near(launches, start+PERIOD/2+EDGE/2+2e-12)
        reset = near(resets, start+PERIOD-4e-12)
        next_launch = near(launches, launch+PERIOD)
        eval_end, sample_time = reset-EDGE/2-.1e-12, track_fall+EDGE/2+1e-12
        baseline_time = launch-EDGE/2-.1e-12
        target = magnitude_lsb*lsb*(1 if q % 2 == 0 else -1)
        positive = target > 0
        raw_valid = [a >= .8*vdd and z <= .2*vdd for a, z in
                     zip(values['y'] if positive else values['x'], values['x'] if positive else values['y'])]
        buffered_valid = [a >= .8*vdd and z <= .2*vdd for a, z in
                          zip(values['bx'] if positive else values['by'], values['by'] if positive else values['bx'])]
        raw_time = first_stable(t, raw_valid, launch, eval_end)
        buf_time = first_stable(t, buffered_valid, launch, eval_end)
        reset_valid = [min(v) >= .95*vdd for v in zip(*(values[n] for n in ('p', 'q', 'x', 'y')))]
        reset_time = first_stable(t, reset_valid, reset, next_launch-EDGE/2-.1e-12)
        acq_start = start+2e-12+EDGE/2
        settling = first_stable(t, [abs(z-target) <= lsb/2 for z in d], acq_start, track_fall-EDGE/2)
        row = {'cycle': q, 'input_differential_LSB': target/lsb,
               'actual_track_rise_s': track_rise, 'actual_track_fall_midpoint_s': track_fall,
               'actual_compare_rise_midpoint_s': launch,
               'actual_compare_after_track_fall_end_s': launch-(track_fall+EDGE/2),
               'sampler_only_held_error_V': interpolate(t, r, sample_time)-target,
               'loaded_sampler_held_error_V': interpolate(t, d, sample_time)-target,
               'loaded_sampler_common_mode_error_V': interpolate(t, dcm, sample_time)-config['common_mode_V'],
               'added_loading_differential_error_at_capture_V': interpolate(t, dd, sample_time),
               'tracking_settling_to_half_LSB_s': None if settling is None else settling-acq_start,
               'raw_resolution_s': None if raw_time is None else raw_time-launch,
               'buffered_resolution_s': None if buf_time is None else buf_time-launch,
               'resolved_before_reset': buf_time is not None,
               'meets_provisional_25ps_budget': buf_time is not None and buf_time-launch <= 25e-12,
               'reset_to_95pct_VDD_s': None if reset_time is None else reset_time-reset,
               'reset_before_next_track': reset_time is not None and reset_time <= start+PERIOD-EDGE/2,
               'reset_before_next_compare': reset_time is not None}
        for name, trace in [('differential', dd), ('common_mode', dc), ('p_side', dp), ('n_side', dn)]:
            baseline = interpolate(t, trace, baseline_time)
            x, z = window(t, trace, launch-EDGE/2, eval_end)
            row['compare_kickback_'+name+'_peak_V'] = max(abs(v-baseline) for v in z)
            row['compare_kickback_'+name+'_at_25ps_V'] = interpolate(t, trace, launch+25e-12)-baseline
            row['total_DUT_minus_reference_'+name+'_at_25ps_V'] = interpolate(t, trace, launch+25e-12)
            before_reset = interpolate(t, trace, reset-EDGE/2-.1e-12)
            rx, rz = window(t, trace, reset-EDGE/2, start+PERIOD-EDGE/2)
            row['reset_kickback_'+name+'_peak_before_next_track_V'] = max(abs(v-before_reset) for v in rz)
        for side, gate_current, source_current, reference_current in [
                ('p', 'VGIP:p', 'VIDP:p', 'VIRP:p'), ('n', 'VGIN:p', 'VIDN:p', 'VIRN:p')]:
            row['comparator_input_'+side+'_evaluation_charge_C'] = integral(t, values[gate_current], launch-EDGE/2, eval_end)
            extra = [a-z for a, z in zip(values[source_current], values[reference_current])]
            row['extra_source_'+side+'_acquisition_charge_C'] = integral(t, extra, track_rise-EDGE/2, sample_time)
        # Full period includes both evaluation and recharge, not just tail discharge.
        for label, source in [('comparator_VDD', 'VA:p'), ('output_buffers_VDD', 'VB:p'),
                              ('DUT_sampler_VDD', 'VSD:p'), ('reference_sampler_VDD', 'VSR:p')]:
            row[label+'_energy_J'] = -vdd*integral(t, values[source], launch, next_launch)
        for label, voltage, source in [('compare_clock', 'cmp', 'VCMP:p'),
                                       ('DUT_track_clock', 'dck', 'VDCK:p'),
                                       ('DUT_track_complement', 'dkb', 'VDKB:p')]:
            power = [-a*z for a, z in zip(values[voltage], values[source])]
            row[label+'_ideal_source_net_energy_J'] = integral(t, power, launch, next_launch)
        rows.append(row)
    return rows


def summarize(rows, config):
    resolved = [r['buffered_resolution_s'] for r in rows if r['buffered_resolution_s'] is not None]
    result = {'decisions_observed': len(rows), 'unresolved_or_wrong_polarity_count': sum(not r['resolved_before_reset'] for r in rows),
              'provisional_25ps_fail_count': sum(not r['meets_provisional_25ps_budget'] for r in rows),
              'reset_before_next_compare_fail_count': sum(not r['reset_before_next_compare'] for r in rows),
              'max_buffered_resolution_s': max(resolved) if resolved else None,
              'max_abs_loaded_sample_error_V': max(abs(r['loaded_sampler_held_error_V']) for r in rows),
              'max_differential_compare_kickback_V': max(r['compare_kickback_differential_peak_V'] for r in rows),
              'max_common_mode_compare_kickback_V': max(r['compare_kickback_common_mode_peak_V'] for r in rows)}
    for label in ('comparator_VDD', 'output_buffers_VDD', 'DUT_sampler_VDD'):
        mean = sum(r[label+'_energy_J'] for r in rows)/len(rows)
        result[label+'_mean_energy_per_decision_J'] = mean
        result[label+'_average_power_W'] = mean/PERIOD
    result['noise_is_enabled'] = config['noise_seed'] is not None
    result['noise_note'] = ('DUT/reference noise is independent; their difference is not purely deterministic kickback.'
                            if config['noise_seed'] is not None else 'Deterministic loading/kickback screen; comparator decision noise is unmeasured.')
    return result


def winner_parameters(path):
    if path is None:
        return {}, {}
    data = json.loads(Path(path).read_text())
    if 'designs' in data:
        selected = [x['record'] for x in data['designs'] if x['role'] == 'optimized']
        if len(selected) != 1:
            raise ValueError('Expected exactly one optimized frozen design')
        record = selected[0]
    else:
        record = data.get('selected_new_candidate', data)
    fullscale = record.get('selection', {}).get('ADC_fullscale_differential_Vpp')
    return {'fullscale_differential_Vpp': fullscale,
            'supply_V': record.get('config', {}).get('vdd', .9),
            'common_mode_V': record.get('output_common_mode_average_V')}, {
                'winner_source_sha256': digest(path), 'winner_candidate_id': record.get('candidate_id'),
                'winner_native_cards_sha256': data.get('native_cards_sha256')}


def self_test():
    captured, saved = [], b.mos
    try:
        def fake(name, d, g, s, bulk, pmos=False, **kwargs):
            captured.append((name, d, g, s, bulk, pmos))
            return name+' (stub) native_test_placeholder'
        b.mos = fake
        strongarm()
        assert len(captured) == 15
        m = {r[0]: r[1:] for r in captured}
        assert m['M3_0'] == ('x', 'y', 'p', '0', False)
        assert m['M4_0'] == ('y', 'x', 'q', '0', False)
        assert m['M7_0'] == ('tail', 'cmp', '0', '0', False)
        assert all(m['S'+x.upper()+'_0'] == (x, 'cmp', 'avdd', 'avdd', True) for x in ('p', 'q', 'x', 'y'))
    finally:
        b.mos = saved
    t = [0., 1., 2., 3.]
    assert interpolate(t, [0., 2., 4., 6.], 1.5) == 3.
    assert integral(t, [0., 2., 4., 6.], .5, 2.5) == 6.
    assert crossings(t, [0., 0., 1., 1.], .5, True) == [1.5]
    assert first_stable(t, [False, True, False, True], 0., 3.) == 3.
    assert first_stable(t, [True, True, True, False], 0., 3.) is None
    tr, cp = clock_changes(3, .9)
    assert abs(cp[0][0]-(tr[1][0]+EDGE/2)-2e-12) < 1e-24
    assert abs(cp[1][0]-cp[0][0]-29.2142857142857e-12) < 1e-24
    # Independent ideal-waveform fixture checks sign, event timing, reference
    # subtraction and full-period supply energy. No device simulation is used.
    cfg = dict(supply_V=.9, common_mode_V=.45, fullscale_differential_Vpp=.128,
               cycles=6, warmup_cycles=2, noise_seed=None)
    stop = T0+7*PERIOD
    tt = [i*.1e-12 for i in range(int(stop/.1e-12)+2)]
    track, compare = clock_changes(6, .9)
    track_wave, cmp_wave = pwl(0., track, stop), pwl(0., compare, stop)
    def at_wave(points, x):
        a, z = zip(*points)
        if x > a[-1]:
            return z[-1]
        return interpolate(list(a), list(z), x)
    vv = {name: [] for name in ('dhp', 'dhn', 'rhp', 'rhn', 'dck', 'dkb', 'rck', 'rkb', 'cmp',
                                'p', 'q', 'x', 'y', 'bx', 'by', 'VA:p', 'VB:p', 'VSD:p', 'VSR:p',
                                'VCMP:p', 'VDCK:p', 'VDKB:p', 'VGIP:p', 'VGIN:p',
                                'VIDP:p', 'VIDN:p', 'VIRP:p', 'VIRN:p')}
    for x in tt:
        q = max(0, int((x-T0)/PERIOD))
        launch = T0+q*PERIOD+PERIOD/2+EDGE/2+2e-12
        reset = T0+(q+1)*PERIOD-4e-12
        sign = 1 if q % 2 == 0 else -1
        evaluated = launch+8e-12 <= x < reset+1e-12
        buffered = launch+10e-12 <= x < reset+1e-12
        kick = .0001 if launch+1e-12 <= x < reset else 0.
        vv['rhp'].append(.45+sign*.0005)
        vv['rhn'].append(.45-sign*.0005)
        vv['dhp'].append(vv['rhp'][-1]+kick/2)
        vv['dhn'].append(vv['rhn'][-1]-kick/2)
        vv['dck'].append(at_wave(track_wave, x)); vv['dkb'].append(.9-vv['dck'][-1])
        vv['rck'].append(vv['dck'][-1]); vv['rkb'].append(vv['dkb'][-1])
        vv['cmp'].append(at_wave(cmp_wave, x))
        vv['p'].append(0. if evaluated else .9); vv['q'].append(0. if evaluated else .9)
        vv['x'].append(0. if evaluated and sign > 0 else .9)
        vv['y'].append(0. if evaluated and sign < 0 else .9)
        vv['bx'].append(.9 if buffered and sign > 0 else 0.)
        vv['by'].append(.9 if buffered and sign < 0 else 0.)
        for name in vv:
            if name.endswith(':p'):
                vv[name].append(-.001 if name == 'VA:p' else 0.)
    measured = analyze_values(tt, vv, cfg, 1.)
    assert len(measured) == 4 and {r['input_differential_LSB'] for r in measured} == {-1., 1.}
    assert all(r['meets_provisional_25ps_budget'] and r['reset_before_next_compare'] for r in measured)
    assert all(abs(r['buffered_resolution_s']-10e-12) < .11e-12 for r in measured)
    assert all(abs(r['compare_kickback_differential_peak_V']-.0001) < 1e-12 for r in measured)
    assert all(abs(r['comparator_VDD_energy_J']-.9*.001*PERIOD) < 1e-24 for r in measured)
    print(json.dumps({'self_test': 'passed', 'simulator_executed': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--run', action='store_true', help='Execute only after the parent frontend gate; default just generates decks.')
    p.add_argument('--analyze-existing', action='store_true')
    p.add_argument('--cards', type=Path, default=PROJECT/'configs/native_device_cards.json')
    p.add_argument('--winner-json', type=Path)
    p.add_argument('--fullscale', type=float, help='ADC differential Vpp, frozen before this probe')
    p.add_argument('--common-mode', type=float, help='Measured AFE output CM; NOT winner.config.cm (AFE input CM)')
    p.add_argument('--vdd', type=float)
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--source-resistance-ohm', type=float, default=50., help='Per-side source R assumption; actual AFE is not instantiated')
    p.add_argument('--temperature', type=float, default=25.)
    p.add_argument('--cycles', type=int, default=24)
    p.add_argument('--warmup-cycles', type=int, default=8)
    p.add_argument('--maxstep-ps', type=float, default=.1)
    p.add_argument('--noise-seed', type=int)
    p.add_argument('--buffer-load-fF', type=float, default=1.)
    p.add_argument('--lsb-magnitudes', default='0.25,0.5,1,2,4')
    for group in ('input', 'regen-n', 'regen-p', 'tail', 'precharge', 'buffer'):
        p.add_argument('--'+group+'-copies', type=int, default=1)
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if args.output_dir is None:
        p.error('--output-dir is required')
    selected, provenance = winner_parameters(args.winner_json)
    cm = args.common_mode if args.common_mode is not None else selected.get('common_mode_V')
    fs = args.fullscale if args.fullscale is not None else selected.get('fullscale_differential_Vpp')
    if cm is None or fs is None:
        p.error('Provide frozen --fullscale and measured --common-mode, or a winner with those explicit fields')
    vdd = args.vdd if args.vdd is not None else selected.get('supply_V', .9)
    magnitudes = [float(x) for x in args.lsb_magnitudes.split(',')]
    if not all(math.isfinite(x) for x in magnitudes+[fs, cm, vdd, args.source_resistance_ohm,
                                                   args.maxstep_ps, args.temperature, args.buffer_load_fF]):
        p.error('All numeric settings must be finite')
    if not magnitudes or any(x <= 0 for x in magnitudes) or fs <= 0 or vdd <= 0:
        p.error('Fullscale, supply and LSB magnitudes must be positive')
    if cm-max(magnitudes)*fs/256 <= 0 or cm+max(magnitudes)*fs/256 >= vdd:
        p.error('Input voltage outside supply rails')
    if args.cycles < args.warmup_cycles+4 or args.warmup_cycles < 2 or args.source_resistance_ohm < 0 or args.maxstep_ps <= 0 or args.buffer_load_fF <= 0:
        p.error('Invalid acquisition/timing settings')
    validate_card_identity(args.cards)
    native = install_native_cards(args.cards)
    native['native_geometry'] = ('Every comparator, buffer and TG copy uses native W=3um/L=30nm; '
                                 'the available NMOS L=60nm card is unused in this probe.')
    if provenance.get('winner_native_cards_sha256') not in (None, native['native_cards_sha256']):
        raise ValueError('Native cards differ from frozen frontend winner')
    config = {'supply_V': vdd, 'common_mode_V': cm, 'fullscale_differential_Vpp': fs,
              'temperature_C': args.temperature, 'cycles': args.cycles, 'warmup_cycles': args.warmup_cycles,
              'maxstep_s': args.maxstep_ps*1e-12, 'noise_seed': args.noise_seed,
              'source_resistance_per_side_ohm': args.source_resistance_ohm,
              'buffer_output_capacitance_F': args.buffer_load_fF*1e-15,
              'copies': {g: getattr(args, g+'_copies') for g in ('input', 'regen_n', 'regen_p', 'tail', 'precharge', 'buffer')}}
    result = {'schema_version': 1, 'scope': 'One native sampler/StrongARM decision-element loading probe; not a physical ADC',
              'configuration': config, 'native_cards': native, 'winner': provenance,
              'topology_reference': REFERENCE, 'reference_figure': '1(b)',
              'provisional_engineering_decision_budget_s': 25e-12,
              'half_LSB_error_allocation_V': fs/256,
              'not_course_pass_fail_specifications': True,
              'decision_polarity': 'Positive sampled INP-INN predicts raw Y high/X low and buffered BX high/BY low.',
              'kickback_definition': 'DUT minus sampler-only reference, with the pre-compare differential/common-mode/per-side difference subtracted; total differences also retained.',
              'timing_resolution_note': 'Resolution/reset/settling use saved instants conservatively; precision is limited by maxstep.',
              'testbench_assumptions': ['Ideal zero-jitter PWL clocks; explicit 1ps transitions.',
                  'One 14GHz sampler lane, 5fF hold per side; no secondary CDAC.',
                  'Finite lumped source R; actual frontend and remaining seven sampler lanes absent.',
                  'Native W3um/L30nm comparator is unoptimized; MOS geometry is callback-derived.',
                  'Two native inverter buffers plus explicit output capacitors; no RS latch or ADC logic.',
                  'Optional transient noise has 150GHz cutoff and flattens below500MHz.',
                  'No mismatch/offset calibration, PVT qualification, PEX, or noise BER claim.'], 'cases': []}
    for index, magnitude in enumerate(magnitudes):
        directory = args.output_dir / ('lsb_%02d' % index)
        lines = make_deck(config, magnitude)
        deck = '\n'.join(lines)+'\n'
        expected = hashlib.sha256(deck.encode()).hexdigest()
        if args.analyze_existing and not args.run:
            if digest(directory/'bench.scs') != expected:
                raise ValueError('Existing deck differs from requested analysis configuration')
            identity = json.loads((directory/'probe_run_identity.json').read_text())
            if identity['deck_sha256'] != expected or identity['raw_sha256'] != digest(_raw_file(directory)):
                raise ValueError('Existing raw data is not bound to this probe deck')
        else:
            directory.mkdir(parents=True, exist_ok=True)
            if (directory/'raw').exists() and (directory/'bench.scs').exists() and digest(directory/'bench.scs') != expected:
                raise ValueError('Refusing to replace a different existing experiment; choose another output directory')
            (directory/'bench.scs').write_text(deck)
        record = {'magnitude_LSB': magnitude, 'polarities': [-1, 1], 'deck_sha256': expected}
        if args.run:
            status = b.run(directory, lines, timeout=180)
            record['run_status'] = status
            if status['exit_code'] != 0:
                result['cases'].append(record)
                atomic_json(args.output_dir/'comparator_probe_summary.json', result)
                raise RuntimeError('Comparator probe simulation failed')
        if args.run or args.analyze_existing:
            raw = parse_file(_raw_file(directory))
            if args.run:
                atomic_json(directory/'probe_run_identity.json', {'deck_sha256': expected, 'raw_sha256': raw.sha256})
            t = raw.values[raw.sweep_names[0]]
            rows = analyze_values(t, raw.values, config, magnitude)
            record.update(raw_sha256=raw.sha256, cycles=rows, summary=summarize(rows, config))
        else:
            record['status'] = 'generated_only_not_simulated'
        result['cases'].append(record)
        atomic_json(args.output_dir/'comparator_probe_summary.json', result)
        print(json.dumps({'case': index, 'magnitude_LSB': magnitude, 'status': record.get('status', 'analyzed')}), flush=True)


if __name__ == '__main__':
    main()
