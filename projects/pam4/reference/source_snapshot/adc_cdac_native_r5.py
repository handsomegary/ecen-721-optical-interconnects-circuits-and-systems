#!/usr/bin/env python3
"""Native MOM/TG charge-step diagnostic; not SAR conversion (Python 3.6).

Two fixed differential arrays: binary 128 units/side, split4+3 with 23 units
and one existing native N8 bridge/side. Seven separate reset/sample/hold/step
episodes measure positive-side bit weights. Clocks/references are ideal;
capacitors, sample/reset/reference TGs and reset comparator are native.
Generate-only unless --run. Native cards and raw waveforms remain on VM.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import adc_comparator_probe as a
import adc_comparator_r5 as cmp
import native_capacitor_r5 as cap
import native_geometry_r5 as ng

PROJECT = a.PROJECT
NAME = 'adc_cdac_native_r5_20261013'
UNIT = 'l1000_n4'  # Legacy request key; saved native geometry MUST be N=6.
BRIDGE = 'l1000_n8'
VDD, VINIT, VREF, VHIGH = .9, .756, .45, .50
FRAME, T0 = 1e-9, 100e-12
SAMPLE_OFF, LOW_OFF, STEP = 200e-12, 190e-12, 300e-12
OBS_END = 900e-12
STOP = T0+7*FRAME
HALF_INPUT_LSB = .1/256


def source_clock(lines, saves, name, initial, changes):
    points = a.pwl(initial, changes, STOP)
    for suffix, wave in [('c', points), ('b', [(t, VDD-x) for t, x in points])]:
        node = name+suffix
        lines.append('V%s (%s 0) vsource type=pwl wave=%s' % (node, node, a.wave(wave)))
        saves += [node]


def tg(lines, name, left, right, clock, width=1e-6):
    lines += [ng.mos(name+'N', left, clock+'c', right, '0', w=width),
              ng.mos(name+'P', left, clock+'b', right, 'vdd', pmos=True, w=width)]


def array_spec(topology):
    if topology == 'binary':
        return [('m', 1 << bit) for bit in range(7)], 'm'
    if topology == 'split':
        return [('l', 1 << bit) if bit < 3 else ('m', 1 << (bit-3)) for bit in range(7)], 'l'
    raise ValueError('Unknown array topology')


def build(topology):
    spec, dummy_node = array_spec(topology)
    lines = a.b.header(temp=25)+[
        '// Native CDAC bit-step characterization; no complete ADC conversion.',
        '// UNIT key l1000_n4 is the saved actual N6 cell; bridge is saved actual N8.',
        'VDD (vdd 0) vsource dc=.9', 'VAVDD (avdd 0) vsource dc=.9',
        'VBVDD (bvdd 0) vsource dc=.9', 'VIN (vin 0) vsource dc=.756',
        'VREF (ref 0) vsource dc=.45', 'VHIGH (high 0) vsource dc=.50']
    saves = ['vdd', 'vin', 'ref', 'high', 'mp', 'mn', 'VDD:p', 'VAVDD:p',
             'VBVDD:p', 'VIN:p', 'VREF:p', 'VHIGH:p']
    sample, low_reset = [], []
    for episode in range(7):
        start = T0+episode*FRAME
        sample += [(start, VDD), (start+SAMPLE_OFF, 0.)]
        low_reset += [(start, VDD), (start+LOW_OFF, 0.)]
    source_clock(lines, saves, 'sample', 0., sample)
    if topology == 'split':
        source_clock(lines, saves, 'lowreset', 0., low_reset)
        saves += ['lp', 'ln']
    # Each bit has two reference TGs. Only positive side bit k switches in
    # episode k; negative side remains at .45 V, preserving real gate loading.
    for side in ('p', 'n'):
        tg(lines, 'SAMPLE'+side, 'm'+side, 'vin', 'sample')
        lines.append('RBIAS%s (m%s vin) resistor r=1T' % (side, side))
        if topology == 'split':
            tg(lines, 'LOWRESET'+side, 'l'+side, 'vin', 'lowreset')
            lines += ['RLBIAS%s (l%s vin) resistor r=1T' % (side, side),
                      cap.capacitor('CBRIDGE'+side, 'm'+side, 'l'+side, '0', BRIDGE)]
        for bit, (top, copies) in enumerate(spec):
            name = side+str(bit)
            base_events, high_events = [], []
            if side == 'p':
                start = T0+bit*FRAME
                # Break before make; reference restores before next acquisition.
                base_events = [(start+STEP-2e-12, 0.), (start+FRAME-10e-12, VDD)]
                high_events = [(start+STEP, VDD), (start+FRAME-12e-12, 0.)]
            source_clock(lines, saves, 'base'+name, VDD, base_events)
            source_clock(lines, saves, 'high'+name, 0., high_events)
            bottom = 'b'+name
            tg(lines, 'REFBASE'+name, bottom, 'ref', 'base'+name)
            tg(lines, 'REFHIGH'+name, bottom, 'high', 'high'+name)
            saves.append(bottom)
            for unit in range(copies):
                lines.append(cap.capacitor('C%s_%d' % (name, unit), top+side, bottom, '0', UNIT))
        lines.append(cap.capacitor('CDUMMY'+side, dummy_node+side, 'ref', '0', UNIT))
    lines += cmp.sized_strongarm(cmp.candidates()['in100_tail3'], ng.mos,
                                inp='mp', inn='mn', clk='0')
    lines += ['CBX (bx 0) capacitor c=1f', 'CBY (by 0) capacitor c=1f']
    saves += ['p', 'q', 'x', 'y', 'tail', 'bx', 'by']
    lines += ['saveOptions options save=selected currents=selected', 'save '+' '.join(dict.fromkeys(saves)),
              'tranResponse tran stop=%.15g maxstep=100f errpreset=conservative' % STOP]
    return lines


def composed_linearity(steps):
    if len(steps) != 7 or any(not math.isfinite(x) for x in steps):
        raise ValueError('Require seven finite bit steps')
    span = sum(steps)
    if span <= 0:
        raise ValueError('Non-positive composed DAC span')
    lsb = span/127
    codes = [sum(steps[bit] for bit in range(7) if code & (1 << bit)) for code in range(128)]
    dnl = [(codes[code+1]-codes[code])/lsb-1 for code in range(127)]
    inl = [(value-code*lsb)/lsb for code, value in enumerate(codes)]
    worst = max(range(127), key=lambda index: abs(dnl[index]))
    return {'individual_step_V': steps, 'normalized_sum_weights': [x/span for x in steps],
            'ideal_normalized_weights': [(1 << bit)/127 for bit in range(7)],
            'composed_span_V': span, 'endpoint_normalized_LSB_V': lsb,
            'adjacent_step_DNL_min_LSB': min(dnl), 'adjacent_step_DNL_max_LSB': max(dnl),
            'worst_abs_DNL_LSB': abs(dnl[worst]), 'worst_transition': [worst, worst+1],
            'nonpositive_composed_code_steps': sum(value <= -1 for value in dnl),
            'endpoint_INL_max_abs_LSB': max(abs(x) for x in inl),
            'carry_DNL_LSB': {'%d_to_%d' % (code, code+1): dnl[code] for code in (1, 3, 7, 15, 31, 63)},
            'interpretation': 'Analytically composed independent one-bit transient steps; endpoint gain normalized, no weight fit. Not direct all-code DNL/INL or SAR conversion.'}


def stable_time(t, values, target, tolerance, start, end):
    valid = [abs(x-target) <= tolerance for x in values]
    point = a.first_stable(t, valid, start, end)
    if abs(a.interpolate(t, values, end)-target) > tolerance:
        return None
    return None if point is None else max(0., point-start)


def analyze(raw, topology):
    t, v = raw.values[raw.sweep_names[0]], raw.values
    d = [p-n for p, n in zip(v['mp'], v['mn'])]
    cm = [(p+n)/2 for p, n in zip(v['mp'], v['mn'])]
    captures = a.crossings(t, v['samplec'], VDD/2, False)
    rows, final_targets = [], []
    for bit in range(7):
        start = T0+bit*FRAME
        capture = a.near(captures, start+SAMPLE_OFF)
        launch = a.near(a.crossings(t, v['highp%dc' % bit], VDD/2, True), start+STEP)
        before, end = launch-5e-12, start+OBS_END
        baseline = a.interpolate(t, d, before)
        final = a.integral(t, d, end-50e-12, end)/50e-12
        unused, last = a.window(t, d, end-50e-12, end)
        unused, held = a.window(t, d, capture+a.EDGE/2+2e-12, before)
        bottom = v['bp%d' % bit]
        row = {'bit_LSB_index': bit, 'sample_capture_midpoint_s': capture,
               'reference_high_gate_midpoint_s': launch,
               'post_capture_guard_before_reference_change_s': launch-capture-a.EDGE/2,
               'pre_step_differential_V': baseline, 'settled_differential_V': final,
               'step_differential_V': final-baseline,
               'weight_divided_by_50mV_reference_step': (final-baseline)/(VHIGH-VREF),
               'last_50ps_differential_peak_to_peak_V': max(last)-min(last),
               'sample_hold_differential_drift_peak_V': max(abs(x-held[0]) for x in held),
               'top_common_mode_at_capture_V': a.interpolate(t, cm, capture+a.EDGE/2+2e-12),
               'top_common_mode_final_V': a.interpolate(t, cm, end),
               'bottom_final_V': a.interpolate(t, bottom, end),
               'bottom_settling_to_50mV_over_256_s': stable_time(t, bottom, VHIGH, (VHIGH-VREF)/256, launch, end),
               'top_settling_to_half_100mVpp_input_LSB_s': stable_time(t, d, final, HALF_INPUT_LSB, launch, end)}
        if topology == 'split':
            row['low_node_plus_final_V'] = a.interpolate(t, v['lp'], end)
            row['low_node_minus_final_V'] = a.interpolate(t, v['ln'], end)
        rows.append(row)
        final_targets.append((launch, end, final))
    linearity = composed_linearity([row['step_differential_V'] for row in rows])
    for row, (launch, end, final) in zip(rows, final_targets):
        row['top_settling_to_half_composed_endpoint_LSB_s'] = stable_time(
            t, d, final, linearity['endpoint_normalized_LSB_V']/2, launch, end)
    for label, source, voltage in [('sample_source', 'VIN:p', VINIT), ('reference_base', 'VREF:p', VREF),
                                   ('reference_high', 'VHIGH:p', VHIGH), ('reset_comparator', 'VAVDD:p', VDD),
                                   ('reset_comparator_buffers', 'VBVDD:p', VDD)]:
        for row in rows:
            start = T0+row['bit_LSB_index']*FRAME
            row[label+'_episode_energy_J'] = -voltage*a.integral(t, v[source], start, start+FRAME-.02e-12)
    return {'bit_steps': rows, 'composed_linearity': linearity,
            'bottom_settling_max_s': max((row['bottom_settling_to_50mV_over_256_s'] for row in rows
                                         if row['bottom_settling_to_50mV_over_256_s'] is not None), default=None),
            'settling_includes_switch_clock_feedthrough': True,
            'effective_input_capacitance_extracted': False,
            'short_acquisition_13ps_or_full_7bit_conversion_proven': False}


def self_test():
    result = composed_linearity([float(1 << i) for i in range(7)])
    assert result['worst_abs_DNL_LSB'] == 0.
    assert result['endpoint_INL_max_abs_LSB'] == 0.
    broken = composed_linearity([.9*(1 << i) if i < 3 else float(1 << i) for i in range(7)])
    assert broken['carry_DNL_LSB']['7_to_8'] > .6
    original_mos, original_cap = ng.mos, cap.capacitor
    def fake_mos(name, d, g, s, bulk, **kw):
        return '%s (%s %s %s %s) TESTMOS' % (name, d, g, s, bulk)
    def fake_cap(name, p, n, bulk, key):
        return '%s (%s %s %s) TESTCAP key=%s' % (name, p, n, bulk, key)
    try:
        ng.mos, cap.capacitor = fake_mos, fake_cap
        for topology, expected in [('binary', 256), ('split', 48)]:
            lines = build(topology)
            ids = [x.split()[0] for x in lines if x and not x.startswith('//') and '(' in x]
            assert len(ids) == len(set(ids))
            assert sum(' TESTCAP ' in x for x in lines) == expected
            assert sum('key='+UNIT in x for x in lines) == (256 if topology == 'binary' else 46)
            assert sum('key='+BRIDGE in x for x in lines) == (0 if topology == 'binary' else 2)
            assert all('capacitor c=' not in x for x in lines if x.split()[0].startswith(('Cp', 'Cn', 'CDUMMY', 'CBRIDGE')))
            assert any('M1 (p mp tail 0)' in x for x in lines)
            assert any('M2 (q mn tail 0)' in x for x in lines)
    finally:
        ng.mos, cap.capacitor = original_mos, original_cap
    tt = [0., 1., 2., 3., 4.]
    assert stable_time(tt, [0., 1., 2., 2., 2.], 2., .1, 0., 4.) == 2.
    assert stable_time(tt, [0., 2., 2., 1., 1.], 2., .1, 0., 4.) is None
    print(json.dumps({'self_test': 'passed', 'two_fixed_topologies': True, 'simulator_executed': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--timeout', type=int, default=240)
    p.add_argument('--topology', choices=('both', 'binary', 'split'), default='both')
    p.add_argument('--mos-cards', type=Path, default=ng.CARD_PATH)
    p.add_argument('--cap-cards', type=Path, default=cap.CARD_PATH)
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if not 10 <= args.timeout <= 600:
        p.error('Timeout must be 10..600 seconds per topology')
    if not (PROJECT/'.codex_project6_owned').exists():
        raise ValueError('Project ownership marker absent')
    mos_metadata, cap_metadata = ng.install(args.mos_cards), cap.install(args.cap_cards)
    for key, fingers in [(UNIT, 6), (BRIDGE, 8)]:
        saved = cap.CARDS[key].get('saved_CDF_geometry')
        if saved is None or int(float(saved['Nfinger'])) != fingers:
            raise ValueError('Native capacitor saved finger count differs: '+key)
    root = PROJECT/'runs'/NAME
    root.mkdir(exist_ok=True)
    identity = {'script_sha256': a.digest(__file__), 'mos_cards_sha256': a.digest(args.mos_cards),
                'capacitor_cards_sha256': a.digest(args.cap_cards),
                'mos_geometry_helper_sha256': a.digest(ng.__file__),
                'capacitor_helper_sha256': a.digest(cap.__file__),
                'comparator_helper_sha256': a.digest(cmp.__file__),
                'unit_key': UNIT, 'unit_actual_Nfinger': 6, 'bridge_key': BRIDGE, 'bridge_actual_Nfinger': 8}
    identity_path = root/'cdac_identity.json'
    if identity_path.exists() and json.loads(identity_path.read_text()) != identity:
        raise ValueError('Existing CDAC experiment identity differs; refusing mutation')
    if not identity_path.exists():
        a.atomic_json(identity_path, identity)
    result = {'schema_version': 1, 'identity': identity, 'status': 'running' if args.run else 'generating',
              'scope': 'Native-capacitor/reference-TG independent bit-step experiment with comparator held reset; not ADC conversion',
              'conditions': {'supply_V': VDD, 'top_sample_voltage_V': VINIT, 'bottom_baseline_V': VREF,
                             'selected_positive_bottom_reference_V': VHIGH, 'temperature_C': 25.,
                             'episode_period_s': FRAME, 'sample_duration_s': SAMPLE_OFF,
                             'split_low_reset_release_s': LOW_OFF, 'reference_step_s': STEP,
                             'observation_endpoint_s': OBS_END, 'sample_reset_reference_TG_width_m': 1e-6,
                             'comparator': 'in100_tail3', 'comparator_clock_held_at_V': 0.},
              'assumptions': ['All seven bit steps use separate full sample/reset episodes; no adaptive calibration/weight fit.',
                              'Positive-side selected reference switches .45 to .50V; all negative-side references remain .45V.',
                              'Native MOM substrate terminals are grounded, including both bridge terminals parasitics.',
                              'References/sample source/clocks are ideal; MOS sample, low-reset and reference switches are real.',
                              '1T resistors provide DC paths; top nodes float during the finite hold interval.',
                              'Reported DNL/INL are analytically composed independent-step diagnostics, not a direct all-code ADC test.',
                              '13ps acquisition, current CML drive, reference generator impedance, noise/mismatch/PEX remain unproven.',
                              'Lossless nominal native capacitor models do not establish RF Q.'], 'cases': []}
    for topology in (('binary', 'split') if args.topology == 'both' else (args.topology,)):
        directory = root/topology
        directory.mkdir(exist_ok=True)
        lines = build(topology)
        deck = '\n'.join(lines)+'\n'
        deck_sha = hashlib.sha256(deck.encode()).hexdigest()
        deck_path, summary_path = directory/'bench.scs', directory/'cdac_case_summary.json'
        if deck_path.exists() and a.digest(deck_path) != deck_sha:
            raise ValueError('Existing topology deck differs: '+topology)
        if summary_path.exists():
            prior = json.loads(summary_path.read_text())
            if prior.get('raw_sha256'):
                if prior['deck_sha256'] != deck_sha or prior['raw_sha256'] != a.digest(a._raw_file(directory)):
                    raise ValueError('Completed topology provenance differs')
                result['cases'].append(prior)
                continue
        if (directory/'raw').exists():
            raise ValueError('Unbound raw results exist; refusing overwrite')
        deck_path.write_text(deck)
        record = {'topology': topology, 'deck_sha256': deck_sha, 'status': 'generated_only',
                  'native_unit_capacitors_per_side': 128 if topology == 'binary' else 23,
                  'native_bridge_capacitors_per_side': 0 if topology == 'binary' else 1}
        if args.run:
            record['run_status'] = a.b.run(directory, lines, timeout=args.timeout)
            if record['run_status']['exit_code'] != 0:
                record['status'] = 'simulation_failed'
                a.atomic_json(summary_path, record)
                result['cases'].append(record)
                result['status'] = 'failed'
                a.atomic_json(root/'cdac_summary.json', result)
                raise RuntimeError('CDAC topology failed: '+topology)
            raw = a.parse_file(a._raw_file(directory))
            record.update(status='complete', raw_sha256=raw.sha256, metrics=analyze(raw, topology))
        a.atomic_json(summary_path, record)
        result['cases'].append(record)
        a.atomic_json(root/'cdac_summary.json', result)
        print(json.dumps({'topology': topology, 'status': record['status'],
                          'linearity': record.get('metrics', {}).get('composed_linearity')}), flush=True)
    result['status'] = 'complete' if all(x['status'] == 'complete' for x in result['cases']) else 'generated_only'
    a.atomic_json(root/'cdac_summary.json', result)


if __name__ == '__main__':
    main()
