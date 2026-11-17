#!/usr/bin/env python3
"""Actual r3 AFE plus all-eight-lane frozen ADC input loading, Python 3.6.

Four DC/AC/noise cases, generate-only unless --run. Model-bearing decks and
raw traces remain in the VM project. Frozen linearization is not clocked ADC
performance and does not establish sampled/aliased noise, BER, or ENOB.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import adc_comparator_probe as a

PROJECT = a.PROJECT
NAME = 'adc_frontend_load_r4_20261013'
CASES = [('bare_5f_tg1', 5e-15, 1, False),
         ('loaded_5f_tg1', 5e-15, 1, True),
         ('loaded_25f_tg4', 25e-15, 4, True),
         ('loaded_50f_tg4', 50e-15, 4, True)]


def primary_sampler(config, tag, switch_copies, clocked=False, cap=None):
    if clocked:
        raise ValueError('This diagnostic supports frozen clocks only')
    node = lambda name: tag+'_'+name
    lines, saves = [], []
    for lane in range(8):
        ck, kb = (node('vdd'), '0') if lane < 4 else ('0', node('vdd'))
        for side in ('p', 'm'):
            hold, source = node('h%d%s' % (lane, side)), node('o_'+side)
            for j in range(switch_copies):
                lines += [a.b.mos(tag+'SN%d%s_%d' % (lane, side, j), hold, ck, source, '0'),
                          a.b.mos(tag+'SP%d%s_%d' % (lane, side, j), hold, kb, source, node('vdd'), pmos=True)]
            lines += ['%sCH%d%s (%s 0) capacitor c=%.15g' % (tag, lane, side, hold, cap),
                      '%sRH%d%s (%s %s) resistor r=1T' % (tag, lane, side, hold, source)]
            saves.append(hold)
    return lines, saves


def make_deck(config, case, comparator_load):
    case_name, primary_cap, switch_copies, loaded = case
    cfg = copy.deepcopy(config)
    cfg.update(ch=primary_cap, vdd=.9)
    old_sampler = a.b.sampler
    try:
        a.b.sampler = lambda c, t, clocked=False, cap=None: primary_sampler(c, t, switch_copies, clocked, cap)
        body, saves = a.b.circuit(cfg, 'X', cap=primary_cap)
    finally:
        a.b.sampler = old_sampler
    lines = a.b.header(temp=25)+['// '+case_name+': frozen four master tracking / four holding.']+body
    if loaded:
        lines += ['VBANK (bankvdd 0) vsource dc=.9', 'VBBIAS (bankbias 0) vsource dc=.58']
        saves += ['VBANK:p', 'VBBIAS:p']
        if comparator_load == 'reset':
            lines += ['VCOMP (compvdd 0) vsource dc=.9', 'VLOGIC (logicvdd 0) vsource dc=.9',
                      'subckt COMPLOAD (inp inn avdd bvdd)']
            lines += a.strongarm(clk='0', inp='inp', inn='inn', copies={'precharge': 4, 'tail': 4})
            lines += ['CBX (bx 0) capacitor c=1f', 'CBY (by 0) capacitor c=1f', 'ends COMPLOAD']
            saves += ['VCOMP:p', 'VLOGIC:p']
        for bank in range(8):
            tag = 'B%d' % bank
            for side in ('p', 'm'):
                gate, out, source = 'X_h%d%s' % (bank, side), tag+'_f'+side, tag+'_s'+side
                lines.append('%sRL%s (bankvdd %s) resistor r=75' % (tag, side, out))
                for j in range(8):
                    lines += [a.b.mos(tag+'F%s%d' % (side, j), out, gate, source, '0'),
                              a.b.mos(tag+'T%s%d' % (side, j), source, 'bankbias', '0', '0', l=60e-9)]
                saves += [out, source]
                for lane in range(8):
                    hold = tag+'_h%d%s' % (lane, side)
                    ck, kb = ('bankvdd', '0') if lane == 0 else ('0', 'bankvdd')
                    lines += [a.b.mos(tag+'SN%d%s' % (lane, side), hold, ck, out, '0'),
                              a.b.mos(tag+'SP%d%s' % (lane, side), hold, kb, out, 'bankvdd', pmos=True),
                              '%sCH%d%s (%s 0) capacitor c=25f' % (tag, lane, side, hold),
                              '%sRH%d%s (%s %s) resistor r=1T' % (tag, lane, side, hold, out)]
                    if lane in (0, 1):
                        saves.append(hold)
            lines.append('%sRDEG (%s_sp %s_sm) resistor r=25' % (tag, tag, tag))
            if comparator_load == 'reset':
                for lane in range(8):
                    lines.append('%sCOMP%d (%s_h%dp %s_h%dm compvdd logicvdd) COMPLOAD' %
                                 (tag, lane, tag, lane, tag, lane))
    lines += ['saveOptions options save=selected currents=selected', 'save '+' '.join(dict.fromkeys(saves)),
              'dcOp dc', 'acResponse ac start=100M stop=150G dec=60',
              'noisePrimary (X_h0p X_h0m) noise start=1M stop=150G dec=40 iprobe=XVin']
    if loaded:
        lines.append('noiseSecondary (B0_h0p B0_h0m) noise start=1M stop=150G dec=40 iprobe=XVin')
    return lines


def complex_point(value):
    return {'real_VV': value.real, 'imaginary_VV': value.imag,
            'magnitude_VV': abs(value), 'magnitude_dB': 20*math.log10(max(abs(value), 1e-300)),
            'phase_degrees': math.degrees(math.atan2(value.imag, value.real))}


def metrics(directory, loaded, comparator_load):
    ac = a.parse_file(directory/'raw/acResponse.ac')
    dc = a.parse_file(directory/'raw/dcOp.dc')
    freq = ac.values['freq']
    vin = [p-m for p, m in zip(ac.values['X_ip'], ac.values['X_im'])]
    if max(abs(v-1.) for v in vin) > 1e-8:
        raise ValueError('AC differential input must be normalized to one volt')
    pairs = {'AFE_output': ('X_o_p', 'X_o_m'), 'primary_track_lane0': ('X_h0p', 'X_h0m'),
             'primary_hold_lane4': ('X_h4p', 'X_h4m')}
    if loaded:
        pairs.update(buffer_lane0=('B0_fp', 'B0_fm'), secondary_track_bank0=('B0_h0p', 'B0_h0m'),
                     secondary_hold_bank0=('B0_h1p', 'B0_h1m'))
    result = {'transfer': {}, 'raw_sha256': {'ac': ac.sha256, 'dc': dc.sha256}, 'noise': {}}
    for label, nodes in pairs.items():
        hp, hm = nodes
        curve = [(p-m)/v for p, m, v in zip(ac.values[hp], ac.values[hm], vin)]
        h1, h56 = a.b.at(freq, curve, 1e9), a.b.at(freq, curve, 56e9)
        result['transfer'][label] = {'H1GHz': complex_point(h1), 'H56GHz': complex_point(h56),
                                    'gain_56_vs_1GHz_dB': 20*math.log10(max(abs(h56), 1e-300)/max(abs(h1), 1e-300)),
                                    'DC_common_mode_V': (dc.values[hp][0]+dc.values[hm][0])/2,
                                    'DC_differential_V': dc.values[hp][0]-dc.values[hm][0]}
    power = {'AFE_and_primary_sampler_W': -.9*dc.values['XVs:p'][0],
             'all_eight_CML_buffer_banks_W': -.9*dc.values['VBANK:p'][0] if loaded else 0.,
             'all_64_reset_comparators_W': -.9*dc.values['VCOMP:p'][0] if loaded and comparator_load == 'reset' else 0.,
             'all_64_reset_output_inverters_W': -.9*dc.values['VLOGIC:p'][0] if loaded and comparator_load == 'reset' else 0.}
    power['total_static_W'] = sum(power.values())
    result['DC_power'] = power
    if loaded:
        result['DC_per_bank'] = [{'bank': bank,
                                  'primary_common_mode_V': (dc.values['X_h%dp' % bank][0]+dc.values['X_h%dm' % bank][0])/2,
                                  'buffer_common_mode_V': (dc.values['B%d_fp' % bank][0]+dc.values['B%d_fm' % bank][0])/2,
                                  'secondary_track_common_mode_V': (dc.values['B%d_h0p' % bank][0]+dc.values['B%d_h0m' % bank][0])/2}
                                 for bank in range(8)]
    for label, analysis in [('primary_track_lane0', 'noisePrimary'), ('secondary_track_bank0', 'noiseSecondary')]:
        path = directory/('raw/'+analysis+'.noise')
        if not path.exists():
            if label == 'secondary_track_bank0' and not loaded:
                continue
            raise ValueError('Missing requested noise analysis')
        noise = a.parse_file(path)
        if noise.unit('out') != 'V/sqrt(Hz)':
            raise ValueError('Unexpected noise density units')
        result['noise'][label] = {'integrated_1MHz_to_56GHz_Vrms': a.b.noise_band(noise.values['freq'], noise.values['out'], 1e6, 56e9),
                                  'integrated_1MHz_to_150GHz_Vrms': a.b.noise_band(noise.values['freq'], noise.values['out'], 1e6, 150e9)}
        result['raw_sha256'][analysis] = noise.sha256
    return result


def self_test():
    cfg = dict(arch='cml', nc=8, nv=8, rc=50, rv=50, vb=.58, cm=.7, vdd=.9,
               rdeg=250, rdeg2=250, cdeg=100e-15, cdeg2=100e-15, ch=5e-15)
    for case in CASES:
        for comparator in ('reset', 'none'):
            lines = make_deck(cfg, case, comparator)
            top, sub = [], []
            inside = False
            for line in lines:
                if line.startswith('subckt '):
                    inside = True
                    continue
                if line.startswith('ends '):
                    inside = False
                    continue
                if '(' in line and not line.startswith('//'):
                    (sub if inside else top).append(line.split()[0])
            assert len(top) == len(set(top))
            assert len(sub) == len(set(sub))
            primary_n = [x for x in top if x.startswith('XSN')]
            primary_p = [x for x in top if x.startswith('XSP')]
            assert len(primary_n) == len(primary_p) == 16*case[2]
            assert sum(x.startswith('BR') for x in top) == 0
            if case[3]:
                assert sum(x.startswith('B') and 'COMP' in x for x in top) == (64 if comparator == 'reset' else 0)
                assert sum(x.startswith('B') and 'SN' in x for x in top) == 128
                assert sum(x.startswith('B') and 'SP' in x for x in top) == 128
            assert a.b.sampler.__name__ == 'sampler'
    assert abs(complex_point(1j)['phase_degrees']-90) < 1e-12
    print(json.dumps({'self_test': 'passed', 'four_cases': True, 'simulator_executed': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--timeout', type=int, default=240)
    p.add_argument('--comparator-load', choices=('reset', 'none'), default='reset')
    p.add_argument('--config', type=Path, default=PROJECT/'configs/ctle_selected_r3.json')
    p.add_argument('--cards', type=Path, default=PROJECT/'configs/native_device_cards.json')
    p.add_argument('--output-dir', type=Path, default=PROJECT/'runs'/NAME)
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if not 10 <= args.timeout <= 600:
        p.error('Timeout must be 10..600 seconds per case')
    out, allowed = args.output_dir.resolve(), (PROJECT/'runs').resolve()
    if allowed not in out.parents or out.name != NAME:
        p.error('Output must be '+NAME+' under project runs')
    cfg = json.loads(args.config.read_text())
    required = ('nc', 'nv', 'rc', 'rv', 'vb', 'cm', 'rdeg', 'rdeg2', 'cdeg', 'cdeg2')
    if not isinstance(cfg, dict) or any(x not in cfg for x in required) or cfg.get('arch', 'cml') != 'cml':
        raise ValueError('Expected flat selected r3 CML configuration')
    a.validate_card_identity(args.cards)
    native = a.install_native_cards(args.cards)
    original = json.loads((PROJECT/'runs/adc_comparator_r3_tt/comparator_probe_summary.json').read_text())
    if native['native_cards_sha256'] != original['native_cards']['native_cards_sha256']:
        raise ValueError('Native cards differ from original verified probe')
    identity = {'script_sha256': a.digest(__file__), 'config_sha256': a.digest(args.config),
                'native_cards_sha256': native['native_cards_sha256'], 'selected_r3_configuration': cfg,
                'comparator_load': args.comparator_load, 'temperature_C': 25., 'supply_V': .9,
                'buffer_per_bank': {'native_copies_per_input_and_tail': 8, 'load_ohm': 75., 'degeneration_ohm': 25., 'bias_V': .58},
                'secondary_capacitance_per_side_F': 25e-15}
    out.mkdir(parents=True, exist_ok=True)
    identity_path = out/'load_identity.json'
    if identity_path.exists():
        if json.loads(identity_path.read_text()) != identity:
            raise ValueError('Existing experiment identity differs; refusing mutation')
    else:
        a.atomic_json(identity_path, identity)
    result = {'schema_version': 1, 'identity': identity, 'scope': 'Actual r3 AFE with all eight frozen primary/buffer/secondary banks',
              'status': 'running' if args.run else 'generating',
              'assumptions': ['Four primary lanes track; four hold. One secondary TG tracks and seven hold in each of eight banks.',
                              'DC operating points of held nodes settle through 1T leakage resistors; no sampled history.',
                              'All comparators, when enabled, remain reset; evaluation kickback and conversion energy are absent.',
                              'CML signal polarity is inverted. Complex gains are normalized to 1V differential AFE input.',
                              'Frozen small-signal output noise is not sampled/aliased noise or comparator decision noise.',
                              'Static power excludes clock transitions, bias generators, reference/CDAC/SAR logic and DSP.',
                              'Ideal lumped hold capacitors and wiring; native MOS parasitic options enabled; no PEX/PVT/mismatch proof.'],
              'cases': []}
    for case in CASES:
        name, cap, copies, loaded = case
        directory = out/name
        directory.mkdir(exist_ok=True)
        lines = make_deck(cfg, case, args.comparator_load)
        deck = '\n'.join(lines)+'\n'
        deck_sha = hashlib.sha256(deck.encode()).hexdigest()
        deck_path, summary_path = directory/'bench.scs', directory/'load_case_summary.json'
        if deck_path.exists() and a.digest(deck_path) != deck_sha:
            raise ValueError('Existing deck differs: '+name)
        if summary_path.exists():
            prior = json.loads(summary_path.read_text())
            if prior.get('status') == 'complete':
                if prior['deck_sha256'] != deck_sha:
                    raise ValueError('Completed deck provenance differs: '+name)
                current = metrics(directory, loaded, args.comparator_load)
                if current['raw_sha256'] != prior['metrics']['raw_sha256']:
                    raise ValueError('Completed raw provenance differs: '+name)
                result['cases'].append(prior)
                continue
        if (directory/'raw').exists():
            raise ValueError('Unbound raw directory exists; refusing overwrite: '+name)
        deck_path.write_text(deck)
        record = {'case': name, 'primary_cap_per_side_F': cap, 'primary_TG_copies': copies,
                  'eight_buffer_banks_present': loaded, 'deck_sha256': deck_sha, 'status': 'generated_only'}
        if args.run:
            record['run_status'] = a.b.run(directory, lines, timeout=args.timeout)
            if record['run_status']['exit_code'] != 0:
                record['status'] = 'simulation_failed'
                a.atomic_json(summary_path, record)
                result['cases'].append(record)
                result['status'] = 'failed'
                a.atomic_json(out/'frontend_load_summary.json', result)
                raise RuntimeError('Frontend loading case failed: '+name)
            record.update(status='complete', metrics=metrics(directory, loaded, args.comparator_load))
        a.atomic_json(summary_path, record)
        result['cases'].append(record)
        a.atomic_json(out/'frontend_load_summary.json', result)
        print(json.dumps({'case': name, 'status': record['status'], 'metrics': record.get('metrics')}), flush=True)
    result['status'] = 'complete' if all(x['status'] == 'complete' for x in result['cases']) else 'generated_only'
    if result['status'] == 'complete':
        base = result['cases'][0]['metrics']['transfer']['primary_track_lane0']['H56GHz']['magnitude_VV']
        result['baseline_H56GHz_relative_error_vs_verified_r3_0p1892565'] = abs(base-.1892565)/.1892565
        for record in result['cases']:
            h = record['metrics']['transfer']['primary_track_lane0']['H56GHz']['magnitude_VV']
            record['primary_H56GHz_change_vs_bare_dB'] = 20*math.log10(h/base)
    a.atomic_json(out/'frontend_load_summary.json', result)


if __name__ == '__main__':
    main()
