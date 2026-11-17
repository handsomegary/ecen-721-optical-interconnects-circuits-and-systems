#!/usr/bin/env python3
"""Real CML drive of one native split CDAC, versus a matched 10fF branch.

Two bounded main-sample-TG sizes, native reset comparators on both paths,
and seven other secondary branches switching at the established timing.
The split low node samples the SAME physical CML output and opens 10ps
before the main node. No ideal signal clamp/buffer, CDAC switching, noise,
SAR conversion or 13ps acquisition claim. Python3.6, generate-only default.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import adc_acquisition_r5 as acq
import adc_cdac_native_r5 as cdac
import adc_comparator_r5 as cmp
import native_capacitor_r5 as cap
import native_geometry_r5 as ng

a, base, PROJECT = acq.a, acq.base, acq.a.PROJECT
NAME = 'adc_cdac_acquisition_r6_20261013'
LOW_EARLY = 10e-12


def switch(lines, name, left, right, ck, kb, supply, width):
    lines += [ng.mos(name+'N', left, ck, right, '0', w=width),
              ng.mos(name+'P', left, kb, right, supply, pmos=True, w=width)]


def build(cfg, width):
    original = acq.build(cfg)
    old_comparator = set(base.comparator_lines(cfg['comparator_candidate']))
    stop = a.T0+(base.GROUPS*8+8)*base.P
    discard_names = {'VCMP', 'CBX', 'CBY', 'CdH0p', 'CdH0n'}
    lines, save_line, analysis = [], None, None
    for line in original:
        if line in old_comparator or line.split()[0] in discard_names:
            continue
        if line.startswith('saveOptions '):
            continue
        if line.startswith('save '):
            save_line = line
            continue
        if line.startswith('tranResponse '):
            analysis = line
            continue
        replaced = False
        for tag in ('r', 'd'):
            for side in ('p', 'n'):
                for polarity in ('N', 'P'):
                    name = tag+'S'+polarity+'0'+side
                    if line.startswith(name+' '):
                        pmos = polarity == 'P'
                        lines.append(ng.mos(name, tag+'h0'+side, 's0kb' if pmos else 's0ck',
                                            tag+'f'+side, tag+'supply' if pmos else '0', pmos=pmos, w=width))
                        replaced = True
        if not replaced:
            lines.append(line)
    if save_line is None or analysis is None:
        raise ValueError('Established parent deck save/analysis missing')
    removed = {'p', 'q', 'x', 'y', 'tail', 'bx', 'by', 'cmp', 'VCMP:p'}
    saves = [n for n in save_line.split()[1:] if n not in removed]
    lines += ['VRAC (ravdd 0) vsource dc=.9', 'VRBC (rbvdd 0) vsource dc=.9',
              'VCDREF (cdref 0) vsource dc=.45', 'VCDHI (cdhi 0) vsource dc=.50',
              'subckt RESETCMP (inp inn avdd bvdd)']
    lines += cmp.sized_strongarm(cmp.candidates()[cfg['comparator_candidate']], ng.mos,
                                inp='inp', inn='inn', clk='0')
    lines += ['CBX (bx 0) capacitor c=1f', 'CBY (by 0) capacitor c=1f', 'ends RESETCMP',
              'COMPD (dh0p dh0n avdd bvdd) RESETCMP',
              'COMPR (rh0p rh0n ravdd rbvdd) RESETCMP']
    saves += ['VRAC:p', 'VRBC:p', 'VCDREF:p', 'VCDHI:p', 'dlp', 'dln']
    events = []
    for group in range(base.GROUPS+1):
        start = a.T0+group*base.SUPER
        if start+acq.SECOND_OFF-LOW_EARLY+a.EDGE/2 < stop:
            events += [(start+2e-12, .9), (start+acq.SECOND_OFF-LOW_EARLY, 0.)]
    base.r4.clock(lines, saves, 'low', events, stop, .9)
    spec, dummy = cdac.array_spec('split')
    for side in ('p', 'n'):
        main, low, out = 'dh0'+side, 'dl'+side, 'df'+side
        # Real CML drive for both sampled tops; no independent ideal VCM clamp.
        switch(lines, 'LOW'+side, low, out, 'lowck', 'lowkb', 'dsupply', 1e-6)
        lines += ['RLOW%s (%s %s) resistor r=1T' % (side, low, out),
                  cap.capacitor('DBRIDGE'+side, main, low, '0', cdac.BRIDGE)]
        for bit, (node, units) in enumerate(spec):
            top = main if node == 'm' else low
            bottom = 'db'+side+str(bit)
            switch(lines, 'DBASE'+side+str(bit), bottom, 'cdref', 'dsupply', '0', 'dsupply', 1e-6)
            switch(lines, 'DHIGH'+side+str(bit), bottom, 'cdhi', '0', 'dsupply', 'dsupply', 1e-6)
            for index in range(units):
                lines.append(cap.capacitor('DU%s%d_%d' % (side, bit, index), top, bottom, '0', cdac.UNIT))
        lines.append(cap.capacitor('DDUMMY'+side, low, 'cdref', '0', cdac.UNIT))
    lines += ['saveOptions options save=selected currents=selected',
              'save '+' '.join(dict.fromkeys(saves)), analysis]
    return lines


def signed(value, deadband=10e-6):
    return 1 if value > deadband else (-1 if value < -deadband else 0)


def aggregate(rows, fields):
    return {field: {'rms_V': math.sqrt(sum(row[field]**2 for row in rows)/len(rows)),
                    'peak_abs_V': max(abs(row[field]) for row in rows),
                    'mean_V': sum(row[field] for row in rows)/len(rows)} for field in fields}


def analyze(raw, cfg):
    t, v = raw.values[raw.sweep_names[0]], raw.values
    at = lambda node, time: a.interpolate(t, v[node], time)
    diff = lambda prefix, time: at(prefix+'p', time)-at(prefix+'n', time)
    cm = lambda prefix, time: (at(prefix+'p', time)+at(prefix+'n', time))/2
    falls = a.crossings(t, v['s0ck'], .45, False)
    low_falls = a.crossings(t, v['lowck'], .45, False)
    rows = []
    for group in range(base.WARMUP, base.GROUPS):
        start = a.T0+group*base.SUPER
        close = a.near(falls, start+acq.SECOND_OFF)
        low_close = a.near(low_falls, close-LOW_EARLY)
        before, after = close-a.EDGE/2-.1e-12, close+a.EDGE/2+.1e-12
        hold_end = start+base.SUPER+2e-12-a.EDGE/2-.1e-12
        row = {'group': group, 'source_differential_V': base.r4.stimulus(group*8),
               'secondary_close_midpoint_s': close, 'low_close_midpoint_s': low_close,
               'dual_sample_release_gap_s': close-low_close,
               'primary_DUT_capture_V': diff('dm', start+base.TRACK+a.EDGE/2+1e-12),
               'primary_reference_capture_V': diff('rm', start+base.TRACK+a.EDGE/2+1e-12),
               'DUT_buffer_before_close_V': diff('df', before),
               'reference_buffer_before_close_V': diff('rf', before),
               'native_CDAC_before_close_V': diff('dh0', before),
               'native_CDAC_after_close_V': diff('dh0', after),
               'reference_10f_after_close_V': diff('rh0', after),
               'native_CDAC_common_mode_after_close_V': cm('dh0', after),
               'reference_common_mode_after_close_V': cm('rh0', after),
               'low_node_differential_after_main_close_V': diff('dl', after),
               'low_node_common_mode_after_main_close_V': cm('dl', after)}
        row['DUT_lag_before_close_V'] = row['native_CDAC_before_close_V']-row['DUT_buffer_before_close_V']
        row['reference_lag_before_close_V'] = diff('rh0', before)-row['reference_buffer_before_close_V']
        row['DUT_closing_edge_change_V'] = row['native_CDAC_after_close_V']-row['native_CDAC_before_close_V']
        row['DUT_minus_reference_after_close_V'] = row['native_CDAC_after_close_V']-row['reference_10f_after_close_V']
        row['DUT_buffer_change_last5ps_V'] = diff('df', before)-diff('df', before-5e-12)
        row['expected_CML_sign'] = -signed(row['source_differential_V'], 0.)
        for label, prefix in [('native_CDAC', 'dh0'), ('reference_10f', 'rh0')]:
            trace = [p-n for p, n in zip(v[prefix+'p'], v[prefix+'n'])]
            unused, values = a.window(t, trace, after, hold_end)
            row[label+'_held_drift_peak_V'] = max(abs(x-values[0]) for x in values)
            row[label+'_source_sign_agrees'] = signed(values[0]) == row['expected_CML_sign']
            row[label+'_held_differential_end_V'] = values[-1]
        for label, source in [('DUT_bank', 'VdDD:p'), ('reference_bank', 'VrDD:p'),
                              ('DUT_reset_comparator', 'VA:p'), ('reference_reset_comparator', 'VRAC:p')]:
            row[label+'_power_W'] = -.9*a.integral(t, v[source], start, start+base.SUPER)/base.SUPER
        rows.append(row)
    fields = ('DUT_lag_before_close_V', 'reference_lag_before_close_V', 'DUT_closing_edge_change_V',
              'DUT_minus_reference_after_close_V', 'DUT_buffer_change_last5ps_V',
              'native_CDAC_held_drift_peak_V', 'reference_10f_held_drift_peak_V')
    summary = {'branch0_captures': len(rows), 'errors': aggregate(rows, fields),
               'native_CDAC_source_sign_agrees': sum(row['native_CDAC_source_sign_agrees'] for row in rows),
               'reference_10f_source_sign_agrees': sum(row['reference_10f_source_sign_agrees'] for row in rows),
               'sign_deadband_V': 10e-6, 'noiseless_only': True,
               'interface_budget_half_100mVpp_LSB_V': .1/256,
               'native_CDAC_common_mode_range_V': [min(row['native_CDAC_common_mode_after_close_V'] for row in rows),
                                                  max(row['native_CDAC_common_mode_after_close_V'] for row in rows)]}
    for label in ('DUT_bank', 'reference_bank', 'DUT_reset_comparator', 'reference_reset_comparator'):
        summary[label+'_mean_power_W'] = sum(row[label+'_power_W'] for row in rows)/len(rows)
    summary['interpretation'] = ('Uncalibrated acquisition/hold loading diagnostic with reset comparators; '
                                 'no source-sign count is ADC resolution or BER qualification. '
                                 'Only branch0 has native CDAC; seven other branches retain10fF.')
    return rows, summary


def self_test():
    mos, capacitor = ng.mos, cap.capacitor
    def fake_mos(name, d, g, s, bulk, **kwargs):
        return '%s (%s %s %s %s) TESTMOS w=%.12g' % (name, d, g, s, bulk, kwargs.get('w', 3e-6))
    def fake_cap(name, plus, minus, bulk, key):
        return '%s (%s %s %s) TESTCAP key=%s' % (name, plus, minus, bulk, key)
    try:
        ng.mos, cap.capacitor = fake_mos, fake_cap
        unused, cfg = acq.configuration('cml2_late32_s10', .75686, 'in100_tail3')
        for width in (1e-6, 2e-6):
            lines = build(cfg, width)
            top, sub, inside = [], [], False
            for line in lines:
                if line.startswith('subckt '): inside = True
                elif line.startswith('ends '): inside = False
                elif '(' in line and not line.startswith('//'):
                    (sub if inside else top).append(line.split()[0])
            assert len(top) == len(set(top)) and len(sub) == len(set(sub))
            assert sum(' TESTCAP ' in x for x in lines) == 48
            assert 'CdH0p' not in top and 'CdH0n' not in top
            assert 'CrH0p' in top and 'CrH0n' in top
            assert 'COMPD' in top and 'COMPR' in top and 'VCMP' not in top
            assert any('LOWpN (dlp lowck dfp 0)' in x for x in lines)
            assert not any(' vsource ' in x and '(dlp ' in x for x in lines)
            assert any('dSN0p (dh0p s0ck dfp 0) TESTMOS w=%.12g' % width == x for x in lines)
    finally:
        ng.mos, cap.capacitor = mos, capacitor
    assert signed(10e-6) == 0 and signed(-11e-6) == -1
    stats = aggregate([{'e': 1.}, {'e': -1.}], ('e',))
    assert stats['e'] == {'rms_V': 1., 'peak_abs_V': 1., 'mean_V': 0.}
    print(json.dumps({'self_test': 'passed', 'cases': 2, 'simulator_executed': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--timeout', type=int, default=300)
    args = p.parse_args()
    if args.self_test: return self_test()
    if not 10 <= args.timeout <= 600: p.error('Timeout must be10..600 seconds')
    if not (PROJECT/'.codex_project6_owned').exists(): raise ValueError('Project marker absent')
    ng.install(); cap.install()
    for key, count in [(cdac.UNIT, 6), (cdac.BRIDGE, 8)]:
        if int(float(cap.CARDS[key]['saved_CDF_geometry']['Nfinger'])) != count:
            raise ValueError('Unexpected actual native capacitor geometry')
    original_path = PROJECT/'runs/adc_comparator_r3_tt/comparator_probe_summary.json'
    original = json.loads(original_path.read_text())
    unused, cfg = acq.configuration('cml2_late32_s10', original['configuration']['common_mode_V'], 'in100_tail3')
    root = PROJECT/'runs'/NAME
    root.mkdir(exist_ok=True)
    identity = {'script_sha256': a.digest(__file__), 'acquisition_helper_sha256': a.digest(acq.__file__),
                'isolation_helper_sha256': a.digest(base.__file__), 'native_mos_cards_sha256': a.digest(ng.CARD_PATH),
                'native_cap_cards_sha256': a.digest(cap.CARD_PATH), 'configuration': cfg,
                'unit_actual_Nfinger': 6, 'bridge_actual_Nfinger': 8,
                'low_node_release_before_main_s': LOW_EARLY}
    identity_path = root/'identity.json'
    if identity_path.exists() and json.loads(identity_path.read_text()) != identity:
        raise ValueError('Existing experiment identity differs')
    if not identity_path.exists(): a.atomic_json(identity_path, identity)
    result = {'identity': identity, 'status': 'running' if args.run else 'generating',
              'scope': 'One native split CDAC branch driven by physical CML, matched10fF control and reset comparator; no ADC conversion',
              'assumptions': ['Finite50ohm per-side source surrogate; actualr3 AFE absent in this block test.',
                              'Main andlow split nodes both sample same realCML output; low node releases10ps earlier.',
                              'This dual-node sampling increases input load versus main-node-only capacitance estimates.',
                              'Eight secondary branches switch; onlybranch0 has nativeCDAC, othersretain10fF.',
                              'Reset comparator included onbothDUT/reference branch0; no evaluation kickback.',
                              'AllCDAC bottomplates heldat.45V throughnativeTG; highreference switchesoff. NoSAR switching.',
                              'Ideal clocks/bias/reference supplies; noiselessTT25. Physicalclock, reference andlogic powerexcluded.',
                              'No thirteen-picosecond acquisition, directallcode linearity,112GS/s conversion orBERclaim.'], 'cases': []}
    for width in (1e-6, 2e-6):
        name = 'split_main_tg%d_low_tg1' % round(width*1e6)
        directory = root/name
        if directory.exists(): raise ValueError('Refuse to overwrite experiment '+name)
        directory.mkdir()
        lines = build(cfg, width)
        deck = '\n'.join(lines)+'\n'
        (directory/'bench.scs').write_text(deck)
        record = {'case': name, 'main_TG_width_m': width, 'low_sample_TG_width_m': 1e-6,
                  'deck_sha256': hashlib.sha256(deck.encode()).hexdigest(), 'status': 'generated_only'}
        if args.run:
            record['run_status'] = a.b.run(directory, lines, timeout=args.timeout)
            if record['run_status']['exit_code'] != 0:
                record['status'] = 'simulation_failed'
                a.atomic_json(directory/'summary.json', record)
                result['cases'].append(record); result['status'] = 'failed'
                a.atomic_json(root/'acquisition_summary.json', result)
                raise RuntimeError('NativeCDAC acquisition failed')
            raw = a.parse_file(a._raw_file(directory))
            record.update(status='complete', raw_sha256=raw.sha256)
            record['captures'], record['summary'] = analyze(raw, cfg)
        a.atomic_json(directory/'summary.json', record)
        result['cases'].append(record)
        a.atomic_json(root/'acquisition_summary.json', result)
        print(json.dumps({'case': name, 'status': record['status'], 'summary': record.get('summary')}), flush=True)
    result['status'] = 'complete' if args.run else 'generated_only'
    a.atomic_json(root/'acquisition_summary.json', result)


if __name__ == '__main__': main()
