#!/usr/bin/env python3
"""Read-only integrity checks for new native measurements and retired outputs.

Checks runner-attested provenance, not cryptographic proof of execution. No
private modules are imported, simulator is run, or file is changed/deleted.
"""
import csv
import math
from pathlib import Path
import re

import admit
import collect_r5 as C

TONE_KEYS = ('AFE_input_differential', 'AFE_input_common',
             'AFE_output_differential', 'AFE_output_common')
TONE_FIELDS = ('time_s',) + tuple(key + '_V' for key in TONE_KEYS)


def owned_file(root, path):
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    admit.require(admit.inside(path, root), 'Keeper escaped this case: ' + str(path))
    current = path.absolute()
    while current != root:
        admit.require(not current.is_symlink(), 'Symlink keeper/ancestor refused')
        admit.require(current != current.parent, 'Keeper escaped case root')
        current = current.parent
    return admit.regular_file(path)


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def csv_readback(root, descriptor, fields):
    admit.require(isinstance(descriptor, dict) and descriptor.get('available', True) is True,
                  'Required compact CSV is unavailable')
    path = owned_file(root, descriptor['path'])
    admit.require(not admit.inside(path, root / 'raw'), 'Retained compact evidence cannot be inside disposable raw')
    admit.require(admit.sha256_file(path) == descriptor['sha256'], 'Compact CSV SHA mismatch')
    admit.require(path.stat().st_size == descriptor.get('bytes', path.stat().st_size), 'Compact CSV byte count mismatch')
    admit.require(path.stat().st_size <= 16 * 1024 * 1024, 'Compact CSV exceeds bound')
    with path.open('r', encoding='utf-8', newline='') as stream:
        reader = csv.reader(stream)
        admit.require(next(reader, None) == list(fields), 'Compact CSV columns mismatch')
        rows = list(reader)
    admit.require(len(rows) == descriptor['rows'] and len(rows) > 0 and
                  all(len(row) == len(fields) for row in rows), 'Compact CSV actual rows mismatch')
    return path, rows


def check_scores(score, count):
    admit.require(score.get('sample_count') == count and score.get('bit_count') == 2 * count,
                  'Measured scored-symbol/bit count mismatch')
    for name, limit in [('symbol_errors', count), ('gray_bit_errors', 2 * count)]:
        admit.require(type(score.get(name)) is int and 0 <= score[name] <= limit,
                      'Invalid measured error count')
    for key, expected in [('SER', score['symbol_errors'] / count),
                          ('gray_BER', score['gray_bit_errors'] / (2 * count))]:
        admit.require(finite_number(score.get(key)) and abs(score[key] - expected) <= 1e-14,
                      'Measured error fraction inconsistent with count')


def check_pam4(root, result):
    admit.require(result.get('format') == 'pn_skew_native_r5_collection_v1' and
                  result.get('validation_fitting_performed') is False and
                  result.get('validation_input_symbols') == 2048 and result.get('FFE_complete_windows') == 2032 and
                  result.get('historical_validation_data_seed') == 2026101302 and
                  result.get('new_independent_holdout') is False, 'Original r5 measured protocol missing')
    admit.require(result['units'].get('time') == 's' and result['units'].get('held_voltage') == 'V differential',
                  'PAM4 SI voltage/time units missing')
    for point, lag, scale in [('primary', 1, .1), ('secondary', 3, .075)]:
        branch = result['results'][point]
        metrics = branch['metrics']
        admit.require(branch.get('sample_count') == 2048 and branch.get('integer_symbol_lag') == lag and
                      metrics.get('ADC_fullscale_differential_Vpp') == scale and
                      metrics.get('ADC_validation_input_count') == 2048 and
                      metrics.get('FFE_validation_output_count') == 2032 and
                      metrics.get('validation_fitting_performed') is False, 'Missing/inconsistent r5 branch measurement')
        for name in ('raw_held_FFE_before_ADC', 'ideal7bit_ADC_then_FFE'):
            check_scores(metrics[name], 2032)
    path, rows = csv_readback(root, result.get('held_sample_csv'), C.CSV_FIELDS)
    admit.require(len(rows) == 4096, 'Both complete 2048-sample held slices are required')
    seen = {'primary': set(), 'secondary': set()}
    for row in rows:
        point = row[0]
        admit.require(point in seen, 'Unknown held branch')
        index, label_index, capture_index = [int(x) for x in row[1:4]]
        admit.require(index not in seen[point] and 0 <= index < 2048 and label_index == 1152 + index and
                      capture_index == label_index + (1 if point == 'primary' else 3), 'Held labels/lag/index mismatch')
        seen[point].add(index)
        admit.require(all(math.isfinite(float(row[j])) for j in (4, 5, 7, 9)) and
                      int(row[6]) in range(8) and int(row[8]) in range(4), 'Invalid held CSV numeric sample')
    admit.require(all(len(indices) == 2048 for indices in seen.values()), 'Missing held branch samples')
    clip = result['short_waveform_csv']
    clip_path, clip_rows = csv_readback(root, clip, C.SHORT_FIELDS)
    window = clip['window_s']
    admit.require(clip.get('duration_UI') == 64 and len(window) == 2 and
                  abs((window[1] - window[0]) - 64 * C.UI) <= 1e-20,
                  'Fixed64UI short waveform required')
    check_wave_rows(clip_rows, window, exact_endpoints=True)
    return [path, clip_path]


def check_wave_rows(rows, window, exact_endpoints=False):
    numeric = [[float(value) for value in row] for row in rows]
    admit.require(len(numeric) >= 2 and all(math.isfinite(value) for row in numeric for value in row),
                  'Finite short waveform samples required')
    times = [row[0] for row in numeric]
    admit.require(all(b > a for a, b in zip(times, times[1:])) and
                  window[0] - 1e-20 <= times[0] <= times[-1] <= window[1] + 1e-20,
                  'Short waveform time/window mismatch')
    if exact_endpoints:
        admit.require(abs(times[0] - window[0]) <= 1e-20 and abs(times[-1] - window[1]) <= 1e-20,
                      'Fixed short waveform endpoints missing')


def check_tone(root, result, case):
    admit.require(result.get('format') == 'pn_skew_native_modal_probe_v1', 'Native tone measurements missing')
    admit.require(result['units'].get('time') == 's' and result['units'].get('voltage') == 'V' and
                  result['units'].get('frequency') == 'Hz', 'Modal SI voltage/time/frequency units missing')
    lo, hi = case['measurement_window_s']
    counts = []
    for name in TONE_KEYS:
        fit = result['fits'][name]
        admit.require(all(finite_number(fit.get(key)) for key in
                      ('phasor_real_V', 'phasor_imag_V', 'amplitude_peak_V', 'phase_rad', 'dc_V', 'residual_rms_V')),
                      'Missing/nonfinite modal fit')
        admit.require(fit['amplitude_peak_V'] >= 0 and fit['residual_rms_V'] >= 0 and
                      type(fit.get('sample_count')) is int and fit['sample_count'] >= 20,
                      'Invalid modal sample count/amplitude')
        coverage = fit['coverage_s']
        admit.require(abs(coverage[0] - lo) <= C.STROBE * 1.01 and
                      abs(coverage[1] - hi) <= C.STROBE * 1.01 and
                      (coverage[1] - coverage[0]) * case['frequency_Hz'] >= 19.9, 'Incomplete modal observation')
        transfer = result['normalized_to_TX_modal_peak'][name]
        admit.require(all(finite_number(transfer.get(key)) for key in ('real', 'imag', 'magnitude_V_per_V', 'phase_rad')),
                      'Missing/nonfinite modal transfer')
        counts.append(fit['sample_count'])
    admit.require(len(set(counts)) == 1, 'Modal fit sample counts disagree')
    clip = result['short_waveform_csv']
    path, rows = csv_readback(root, clip, TONE_FIELDS)
    admit.require(len(rows) <= 512, 'Tone compact clip exceeds declared bound')
    check_wave_rows(rows, [lo, min(hi, lo + 8 / case['frequency_Hz']) + C.STROBE * 1.01])
    return [path]


def inventory_rows(status):
    rows = status['raw_inventory']
    admit.require(isinstance(rows, list) and rows, 'Runner raw inventory missing')
    found = {}
    for row in rows:
        rel = Path(row['path'])
        admit.require(not rel.is_absolute() and '..' not in rel.parts and rel.parts and rel.parts[0] == 'raw' and
                      rel.as_posix() not in found, 'Unsafe/duplicate runner raw inventory path')
        admit.require(admit.is_sha(row['sha256']) and type(row['bytes']) is int and row['bytes'] >= 0 and
                      all(type(row[key]) is int and row[key] >= 0 for key in ('device', 'inode', 'mtime_ns')),
                      'Invalid runner raw inventory metadata')
        found[rel.as_posix()] = row
    return found


def check_retirement_paths(receipt, absent, inventory):
    """Accept legacy complete receipts and explicit proof of partial retirement."""
    removed = receipt['removed']
    by_path = {row['path']: row for row in removed}
    missing_paths = set(absent)
    inventory_paths = set(inventory)
    status = receipt.get('status')
    admit.require(receipt.get('VM_or_original_study_deletion') is False and
                  len(by_path) == len(removed) and set(by_path) == missing_paths and
                  missing_paths <= inventory_paths, 'Retirement receipt does not match missing raw')
    if status == 'completed':
        admit.require(missing_paths == inventory_paths, 'Complete raw retirement receipt required')
    else:
        remaining = receipt.get('remaining_raw_paths')
        admit.require(status == 'deferred' and isinstance(receipt.get('reason'), str) and receipt['reason'] and
                      isinstance(remaining, list) and len(remaining) == len(set(remaining)) and
                      bool(remaining) and set(remaining) == inventory_paths - missing_paths,
                      'Incomplete partial retirement proof')
    return by_path


def verify_run(root, expected_case=None, expected_plan_sha256=None, admission_path=None, require_raw=False):
    root = Path(root).resolve()
    result_path = owned_file(root, root / 'measurements.json')
    result, profile, case, status, completion = [admit.read_json(owned_file(root, root / name)) for name in
        ('measurements.json', 'profile.json', 'case.json', 'run_status.json', 'completion.json')]
    admit.require(result.get('measurement_complete') is True and result.get('complete_ADC_verified') is False and
                  completion.get('measurement_complete') is True and
                  completion.get('measurement_sha256') == admit.sha256_file(result_path), 'Incomplete/stale measurement completion')
    admit.require(case == profile['case'] == result['case'] and
                  (expected_case is None or case == expected_case), 'Cross-case measurement/profile mismatch')
    admit.require(case.get('kind') in ('pam4_noiseless', 'pam4_noise', 'tone_dm', 'tone_cm'), 'Unknown case kind')
    admit.require(status.get('format') == 'pn_skew_native_run_v1' and status.get('status') == 'spectre_completed' and
                  status.get('exit_code') == 0 and status.get('case_id') == case['case_id'], 'Incomplete/cross-case runner')
    plan_sha = profile['plan_sha256']
    admit.require(admit.is_sha(plan_sha) and status['plan_sha256'] == plan_sha and
                  (expected_plan_sha256 is None or expected_plan_sha256 == plan_sha), 'Plan binding mismatch')
    prov = result['provenance']
    input_sha = admit.sha256_file(owned_file(root, root / 'bench.scs'))
    admit.require(input_sha == profile['staged_deck_sha256'] == status['input_deck_sha256_before'] ==
                  status['input_deck_sha256_after'] == prov['input_deck_sha256'], 'Input deck binding mismatch')
    admit.require(prov['profile_sha256'] == admit.sha256_file(root / 'profile.json') and
                  prov['case_json_sha256'] == admit.sha256_file(root / 'case.json') and
                  prov['run_status_sha256'] == admit.sha256_file(root / 'run_status.json'), 'Retained provenance hash mismatch')
    admit.require(admit.is_sha(profile['admission_sha256']) and
                  profile['admission_sha256'] == status['admission_sha256'] == prov['admission_sha256'] and
                  prov['frozen_r5_sha256'] == admit.FROZEN_SHA256 and
                  prov['source_deck_sha256'] == profile['source_deck_sha256'], 'Admission/frozen/source binding mismatch')
    source_kind = 'noise' if case['kind'] == 'pam4_noise' else 'noiseless'
    admit.require(profile['source_kind'] == source_kind and
                  profile['normalized_original_vm_sha256'] == admit.DECK_SHA256[source_kind], 'Original r5 source lineage mismatch')
    admit.require(set(prov['source_scripts']) == set(admit.SCRIPT_NAMES) and
                  all(admit.is_sha(value) for value in prov['source_scripts'].values()) and
                  prov['model_files'] == admit.MODEL_FILES, 'Original source/model metadata missing')
    if admission_path is not None:
        document = admit.read_admission(admission_path, verify=False)
        admit.require(admit.sha256_file(admission_path) == profile['admission_sha256'] and
                      document['frozen_r5']['sha256'] == prov['frozen_r5_sha256'] and
                      document['source_scripts'] == prov['source_scripts'] and document['model_files'] == prov['model_files'],
                      'Admission file differs from measurement provenance')
    log = owned_file(root, root / 'spectre.log')
    admit.require(log.stat().st_size <= 32 * 1024 * 1024 and admit.sha256_file(log) == prov['spectre_log_sha256'] and
                  re.search(r'spectre completes with\s+0\s+errors\b', log.read_text(encoding='utf-8', errors='replace'), re.I),
                  'Zero-error Spectre log proof missing/changed')
    keepers = check_pam4(root, result) if case['kind'].startswith('pam4_') else check_tone(root, result, case)
    inventory = inventory_rows(status)
    raw = result['raw']
    relative = raw['relative_path']
    admit.require(relative in inventory and raw['sha256'] == inventory[relative]['sha256'] and
                  raw['bytes'] == inventory[relative]['bytes'], 'Measured raw not bound to runner inventory')
    absent = []
    for relative, row in inventory.items():
        path = root / relative
        if not path.exists():
            absent.append(relative)
            continue
        path = owned_file(root, path)
        stat = path.stat()
        admit.require(stat.st_size == row['bytes'] and admit.sha256_file(path) == row['sha256'],
                      'Current raw inventory hash/bytes changed')
    if absent:
        admit.require(not require_raw, 'Current raw required before retirement')
        receipt = admit.read_json(owned_file(root, root / 'raw_retirement.json'))
        by_path = check_retirement_paths(receipt, absent, inventory)
        for relative in absent:
            row, event = inventory[relative], by_path[relative]
            admit.require(all(event[key] == row[key] for key in ('sha256', 'bytes', 'device', 'inode', 'mtime_ns')) and
                          event['retained_measurement_sha256'] == admit.sha256_file(result_path), 'Retired raw proof mismatch')
        required = keepers + [root / name for name in ('bench.scs', 'profile.json', 'case.json',
                    'run_status.json', 'spectre.log', 'completion.json', 'measurements.json')]
        for path in required:
            matches = [value for name, value in receipt['retained'].items() if Path(name).name == path.name]
            admit.require(matches == [admit.sha256_file(path)], 'Retirement retained-keeper proof mismatch')
    return result
