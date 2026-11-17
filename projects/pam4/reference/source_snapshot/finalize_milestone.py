#!/usr/bin/env python3
"""Save the first native Project6 milestone, derived statistics only."""
import datetime
import hashlib
import json
import pathlib
import re

P = pathlib.Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')


def sha(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf8')


def main():
    assert (P / '.codex_project6_owned').is_file()
    native = json.loads((P / 'results/native_baseline_summary.json').read_text())
    pam4_path = P / 'results/pam4_integration_summary.json'
    pam4 = json.loads(pam4_path.read_text())
    assert pam4['status'] == 'complete' and not pam4['errors']
    assert len(pam4['calibration']) == 12
    assert len(pam4['validation']) == 3 and len(pam4['PN_skew']) == 3
    assert len(pam4['noise_validation']) == 1
    assert native['reconstructed_same_cards_and_topology_verified']
    symbol_runs = [x for x in (P / 'runs').glob('symbols_*') if (x / 'SYMBOL_BUILD_VERIFIED').is_file()]
    assert symbol_runs
    receipt = json.loads((P / 'notes/reuse_receipt.json').read_text())
    preserved = {p: sha(p) == expected for p, expected in receipt['source_sha256'].items()}
    assert all(preserved.values())
    model = '<PDK_ROOT>/models/spectre/pdk_model.scs'
    model_hash = sha(model)
    assert model_hash == '002300afbc872cca7c0bab744740eb74ff2cc71e770832c6e6d97c447dbfff78'
    cards = json.loads((P / 'configs/native_device_cards.json').read_text())
    for value in cards.values():
        if isinstance(value, dict) and 'parameters' in value:
            for field in ['nf', 'multi']:
                found = re.search(r'(?<!\w)' + field + r'\s*=\s*([^\s()]+)', value['parameters'])
                assert found and float(found.group(1)) == 1.0
    active = {'library': 'p6_224g_lib', 'cells': {
        'p6_ctle2_lvt_r2': ['schematic', 'symbol'],
        'p6_sampler8_lvt_r2': ['schematic', 'symbol'],
        'tb_p6_ctle_sampler_ac_r2': ['schematic']},
        'history': 'r0 initial defaults; r1 failed intermediate; flag probe diagnostic; use r2 only'}
    save(P / 'notes/active_views.json', active)
    condensed = []
    for group in ['validation', 'PN_skew', 'noise_validation']:
        for record in pam4[group]:
            small = {k: record[k] for k in ['run_name', 'scenario', 'config',
                'loss_dB_at_56GHz', 'phase_UI', 'PN_skew_s', 'P_delay_s', 'N_delay_s',
                'transient_noise_enabled', 'AFE_and_sampler_VDD_power_W',
                'power_scope', 'output_common_mode_average_V', 'clock_audit',
                'netlist_sha256', 'raw_transient_sha256', 'run_status']}
            small.update(group=group, raw_slicer=record['metrics']['raw']['validation'],
                ideal_ADC=[{'fullscale_differential_Vpp': a['fullscale_differential_Vpp'],
                            'validation_clipped_count': a['validation_clipped_count'],
                            'validation': a['validation']} for a in record['metrics']['behavioral_ADC']])
            if 'PN_method' in record:
                small['PN_method'] = record['PN_method']
            if 'noise_conditions' in record:
                small['noise_conditions'] = record['noise_conditions']
            condensed.append(small)
    ffe_path = P / 'results/pam4_ffe_diagnostic.json'
    ffe = json.loads(ffe_path.read_text()) if ffe_path.exists() else None
    if ffe is not None:
        assert ffe['status'] == 'complete' and not ffe['errors']
        assert len(ffe['results']) == 4 and ffe['noise_case_count'] == 1
    report = {'milestone': 'native schematics, symbols, native-netlist parity and first PAM4 integration',
        'saved_UTC': datetime.datetime.utcnow().isoformat() + 'Z', 'project_directory': str(P),
        'active_views': active, 'full_Project6_verified': False,
        'native_baseline': native, 'PAM4_conditions': pam4['conditions'],
        'PAM4_simulation_status': pam4['status'], 'PAM4_results': condensed,
        'PAM4_original_summary_sha256': sha(pam4_path), 'FFE_diagnostic': ffe,
        'channel_shape_diagnostic': json.loads((P / 'results/channel_shape_diagnostic.json').read_text()),
        'verification': {'original_LA5_sources_unchanged': preserved,
            'PDK_main_file_sha256_unchanged': model_hash, 'native_nf_multi_both_1': True,
            'native_symbol_pin_count': 43, 'native_schematic_MOS_count_in_TB': 96,
            'pdk_probe_absent': not pathlib.Path('/path/to/local/cadence-home/pdk_probe').exists(),
            'PAM4': pam4['verification']},
        'limitations': pam4['limitations'] + [
            'Preset CTLE values and four phases are an initial screen, not a channel-optimized receiver.',
            'Direct three-threshold slicer errors do not establish the best ADC/DSP receiver performance.',
            'PN endpoint runs retain fixed timing; their comparison to oracle includes timing-recovery effects.',
            'Native CDF geometry differs from earlier minimal-geometry feasibility decks; use this native baseline.',
            'Three process/temperature/supply points are smoke checks, not full PVT signoff.']}
    save(P / 'results/Project6_started_summary.json', report)
    status = {'project': 'Sam Project6 224Gb/s PAM4 ADC-based receiver',
        'status': 'first_native_PAM4_milestone_complete_receiver_not_yet_validated',
        'full_project_verified': False, 'library': 'p6_224g_lib',
        'device': '28nm LVT', 'active_views': active,
        'completed': ['independent native Cadence project', 'CTLE and 8-lane sampler schematics and symbols',
            'save/reopen connectivity and CDF verification', 'native netlist equivalence',
            'three-corner AC/noise smoke checks', '12 training-only PAM4 phase calibrations',
            '3 independent PAM4 validation runs', '3 PN-skew/oracle diagnostic runs',
            '1 transient-noise PAM4 validation run'],
        'pending': ['channel-matched CTLE/VGA and training-only ADC/DSP optimization',
            'physical ADC architecture and transistor circuits', 'PN compensation circuit',
            'clock distribution and jitter', 'actual channel, full PVT, layout and extraction'],
        'summary': 'results/Project6_started_summary.json'}
    if ffe is not None:
        status['completed'].append('bounded behavioral FFE diagnostic')
    save(P / 'project_status.json', status)
    lines = ['Project 6 — first native Cadence milestone', '',
        'Project: ' + str(P), 'Library: p6_224g_lib', '',
        'Open manually: cd ' + str(P) + ' && ./start_virtuoso.sh',
        'Active cells: p6_ctle2_lvt_r2, p6_sampler8_lvt_r2, tb_p6_ctle_sampler_ac_r2',
        'CTLE and sampler have verified symbol views. Use r2; earlier revisions are history.', '',
        'Native TT/25C/0.9V: 56GHz held-track gain = -14.396dB; peaking relative to1kHz =21.829dB;',
        'response maximum is near22.387GHz, not56GHz. Frozen-clock DC VDD power =9.563mW.',
        'Three-corner results and differences from earlier minimal-geometry decks are in the summary.', '',
        'PAM4:112Gbaud,0.4Vpp differential source before synthetic channel;0/10/20dB loss at56GHz.',
        'Four phases calibrated using512 training symbols;2048 validation symbols use frozen settings.',
        'Current direct-slicer results are an initial diagnostic, not a complete ADC receiver result.']
    for record in condensed:
        raw = record['raw_slicer']
        lines.append('%s: symbol errors=%d/%d, SER=%.6g, GrayBER=%.6g, VDDpower=%.4fmW' % (
            record['run_name'], raw['symbol_errors'], raw['sample_count'], raw['SER'],
            raw['gray_BER'], record['AFE_and_sampler_VDD_power_W'] * 1e3))
    lines.extend(['', 'No physical7-bit ADC, clock network, physical PN deskew or extracted layout is complete.',
        'Next design focus: combined channel+CTLE impulse response, gain/bandwidth and ADC/DSP architecture.',
        'All model files and raw waves remain on the VM. Derived summary: results/Project6_started_summary.json',
        'Rerun integration: python3 scripts/pam4_integration.py --with-noise',
        'Native-card parity: python3 scripts/native_baseline.py',
        'Do not rerun native-view creation onto existing views; the builders intentionally refuse overwrites.'])
    (P / 'README.txt').write_text('\n'.join(lines) + '\n', encoding='utf8')
    print(json.dumps({'status': status['status'], 'summary': str(P / status['summary']),
        'summary_bytes': (P / status['summary']).stat().st_size, 'FFE_included': ffe is not None}))


if __name__ == '__main__':
    main()
