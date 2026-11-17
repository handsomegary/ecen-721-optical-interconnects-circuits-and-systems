#!/usr/bin/env python3
"""Verify a new saved OA netlist against its selected native-card CML fixture."""
import argparse
import json
import math
import re
from pathlib import Path
import pam4_integration as integration
import native_baseline as baseline
from psf_ascii import parse_file


def run(revision, config):
    project = integration.PROJECT
    native_dir = Path((project / 'notes/latest_oa_run.txt').read_text().strip())
    sources = list(native_dir.rglob('input.scs'))
    expected_name = 'tb_p6_ctle_sampler_ac_' + revision
    if len(sources) != 1 or expected_name not in str(sources[0]):
        raise ValueError('Latest OA run does not match intended revision')
    source = sources[0]
    contents = source.read_text()
    flattened = contents.replace('\\\n', ' ')
    cards = json.loads((project / 'configs/native_device_cards.json').read_text())
    card_lookup = {}
    for key, name in [('n_l30', 'M1p0'), ('n_l60', 'T1p0'), ('p_l30', 'SP0p')]:
        match = re.search(r'^' + name + r'\s+\([^)]*\)\s+(\S+)\s+(.+)$', flattened, re.M)
        if not match:
            raise ValueError('Missing native representative ' + name)
        card_lookup[key] = {'model': match.group(1), 'parameters': ' '.join(match.group(2).split())}
        if card_lookup[key] != cards[key]:
            raise ValueError('Callback-derived native geometry changed for ' + key)
    allmos = re.findall(r'^\S+\s+\([^)]*\)\s+(?:nmos_lvt|pmos_lvt)\s+(.+)$', flattened, re.M)
    expected_count = 4 * (int(config['nc']) + int(config['nv'])) + 32
    if len(allmos) != expected_count:
        raise ValueError('Unexpected MOS count in new native netlist')
    for params in allmos:
        for flag in ['_ccoflag', '_rcoflag', '_rgflag']:
            if not re.search(r'\b' + flag + r'=1(?:\s|$)', params):
                raise ValueError('Native parasitic flag missing')
    integration.install_native_cards(project / 'configs/native_device_cards.json')
    directory = project / 'runs' / ('native_verification_' + revision)
    native_lines = contents.split('simulatorOptions options')[0].splitlines() + [
        'simulatorOptions options temp=25 tnom=25 reltol=1e-4 vabstol=1u iabstol=1p',
        'saveOptions options save=selected currents=selected',
        'save inp inn outp outn h0p h0n c_p c_n s1_p s2_p VDD:p', 'dcOp dc',
        'acResponse ac start=1K stop=150G dec=60',
        'noiseResponse (h0p h0n) noise start=1M stop=150G dec=60 iprobe=VIN']
    native_status = integration.b.run(directory / 'native', native_lines, 120)
    if native_status['exit_code'] != 0:
        raise ValueError(native_status)
    native = baseline.metrics(directory / 'native', ('inp', 'inn', 'outp', 'outn', 'h0p', 'h0n', 'VDD:p'), config.get('vdd', .9))
    circuit, saves = integration.b.circuit(config, 'X')
    lines = integration.b.header() + circuit + [
        'saveOptions options save=selected currents=selected', 'save ' + ' '.join(saves), 'dcOp dc',
        'acResponse ac start=1K stop=150G dec=60',
        'noiseResponse (X_h0p X_h0m) noise start=1M stop=150G dec=60 iprobe=XVin']
    fixture_status = integration.b.run(directory / 'fixture', lines, 120)
    if fixture_status['exit_code'] != 0:
        raise ValueError(fixture_status)
    fixture = baseline.metrics(directory / 'fixture', ('X_ip', 'X_im', 'X_o_p', 'X_o_m', 'X_h0p', 'X_h0m', 'XVs:p'), config.get('vdd', .9))
    errors = {key: abs(native[key] - fixture[key]) / max(abs(fixture[key]), 1e-20) for key in [
        'output_gain_56GHz_VV', 'held_track_gain_56GHz_VV', 'VDD_power_W', 'track_noise_1MHz_to_56GHz_Vrms']}
    native_ac = parse_file(directory / 'native/raw/acResponse.ac')
    fixture_ac = parse_file(directory / 'fixture/raw/acResponse.ac')
    if native_ac.values['freq'] != fixture_ac.values['freq']:
        raise ValueError('Native and fixture frequency grids differ')
    for label, np, nn, fp, fn in [('held_curve', 'h0p', 'h0n', 'X_h0p', 'X_h0m'),
                                  ('output_curve', 'outp', 'outn', 'X_o_p', 'X_o_m')]:
        left = [p - n for p, n in zip(native_ac.values[np], native_ac.values[nn])]
        right = [p - n for p, n in zip(fixture_ac.values[fp], fixture_ac.values[fn])]
        errors[label] = max(abs(a - b) / max(abs(b), 1e-12) for a, b in zip(left, right))
    native_dc = parse_file(directory / 'native/raw/dcOp.dc')
    fixture_dc = parse_file(directory / 'fixture/raw/dcOp.dc')
    for left, right in [('c_p', 'X_c_p'), ('outp', 'X_o_p'), ('s1_p', 'X_s1_p'), ('s2_p', 'X_s2_p')]:
        a, b = native_dc.values[left][0], fixture_dc.values[right][0]
        errors['DC_' + left] = abs(a - b) / max(abs(b), 1e-12)
    if max(errors.values()) > 1e-5:
        raise ValueError('New native fixture differs: ' + json.dumps(errors))
    result = {'revision': revision, 'native_cell': expected_name, 'config': config,
              'all_native_MOS_count': expected_count, 'native_cards_match_r2': True,
              'parasitic_flags_all_1': True, 'native_source_netlist_sha256': integration.file_hash(source),
              'source_run_directory': str(native_dir), 'native': native, 'fixture': fixture,
              'relative_errors': errors, 'native_run_status': native_status,
              'fixture_run_status': fixture_status, 'native_parity_verified': True}
    integration.atomic_json(project / 'results' / ('native_verification_' + revision + '.json'), result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    run(args.revision, json.loads(args.config.read_text()))
