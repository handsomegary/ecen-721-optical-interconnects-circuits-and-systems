#!/usr/bin/env python3
"""Collect completed native r5 PSF ASCII using frozen original pure functions.

Python 3.6+, standard library only. Writes a small result JSON and held-sample
CSV IN the existing run directory. Does not simulate, fit, update a usage
ledger, delete raw data, connect remotely, or download private files.
"""
import argparse
import ast
import bisect
import csv
import hashlib
import json
import math
import random
import re
from pathlib import Path
from types import SimpleNamespace

import admit

MAX_RAW_BYTES = 512 * 1024 * 1024
UI = 1.0 / 112e9
STROBE = UI / 8


def load_definitions(path, names, namespace, assignments=()):
    """Compile only explicitly named definitions; no module imports/main/body.

    Source files have already passed admission hashes. In particular, train,
    validate, run_deck, fit_training, fit_ffe and all simulator functions are
    never loaded into this execution namespace.
    """
    source = Path(path).read_text(encoding='utf-8')
    tree = ast.parse(source, filename=str(path))
    selected, found, assigned = [], set(), set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            admit.require(not node.decorator_list, 'Unexpected decorated original definition')
            selected.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if len(targets) == 1 and targets[0] in assignments:
                selected.append(node)
                assigned.add(targets[0])
    admit.require(found == set(names) and assigned == set(assignments),
                  'Original pure-function API missing: ' + str(path))
    module = ast.Module(body=selected)
    if 'type_ignores' in ast.Module._fields:
        module.type_ignores = []
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), 'exec'), namespace)
    return SimpleNamespace(**namespace)


def original_functions(source_dir):
    source = Path(source_dir)
    parser = load_definitions(source / 'psf_ascii.py', {
        'PsfError', 'Tokens', 'text_value', 'numeric_value', 'parse_properties',
        'parse_descriptor', 'parse_datum', 'PsfData', 'split_sections',
        'parse_text', 'parse_file'},
        {'hashlib': hashlib, 'json': json, 'math': math, 're': re, 'Path': Path},
        assignments=('MAX_FILE_BYTES', 'SECTIONS', 'TOKEN'))
    # The function's globals are the same dict used by load_definitions.
    parser.parse_file.__globals__['MAX_FILE_BYTES'] = MAX_RAW_BYTES
    metrics = load_definitions(source / 'pam4_metrics.py', {
        '_mean', '_percentile', '_level_stats', '_eye_gaps', '_decide',
        '_validate_input', '_validation_metrics', 'quantize_symmetric'},
        {'math': math, 'bisect': bisect, 'GRAY_CODES': (0, 1, 3, 2)})
    pi = load_definitions(source / 'pam4_integration.py', {'aligned_window', '_raw_file', '_spectre_number'},
                          {'WARMUP': 128, 'T0': 200e-12, 'UI': UI, 'GUARD': 64, 're': re})
    ffe = load_definitions(source / 'pam4_ffe_diagnostic.py', {
        'mean', 'predict_window', 'prediction_metrics'},
        {'math': math, 'bisect': bisect, 'metrics': metrics, 'HALF': 8,
         'TAPS': 17, 'TARGETS': (-3., -1., 1., 3.), 'THRESHOLDS': (-2., 0., 2.)})
    opt = load_definitions(source / 'optimize_pam4.py', {
        'random_symbols', 'canonical_hash', 'evaluate_frozen', 'measured_aperture_phase'},
        {'random': random, 'math': math, 'hashlib': hashlib, 'json': json,
         'integration': pi, 'ffe': ffe, 'metrics': metrics})
    a = load_definitions(source / 'adc_comparator_probe.py', {
        'interpolate', 'window', 'integral', 'crossings'},
        {'bisect': bisect, 'math': math})
    a.parse_file, a._raw_file = parser.parse_file, pi._raw_file
    r5 = load_definitions(source / 'adc_backend_pam4_r5.py', {
        'extract_records', 'validation_symbols', 'power'},
        {'a': a, 'opt': opt, 'pi': pi, 'math': math, 'STROBE': STROBE,
         'TRAIN_SEED': 2026101301, 'VALID_SEED': 2026101302,
         'TRAIN_COUNT': 1024, 'VALID_COUNT': 2048})
    return SimpleNamespace(a=a, r5=r5, pi=pi, opt=opt, metrics=metrics)


def file_snapshot(path):
    stat = Path(path).stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def validate_raw(raw, stop_s):
    admit.require(len(raw.sweep_names) == 1, 'Exactly one time sweep required')
    axis = raw.sweep_names[0]
    admit.require(axis.lower() == 'time', 'PSF sweep must be time')
    t = raw.values[axis]
    admit.require(len(t) >= 2 and all(isinstance(x, (float, int)) and math.isfinite(x) for x in t),
                  'Finite time samples required')
    admit.require(all(b > a for a, b in zip(t, t[1:])), 'Time must be strictly increasing')
    admit.require(0 <= t[0] <= STROBE and t[-1] >= stop_s - STROBE * 1.01,
                  'Raw transient does not cover original requested STOP')
    for name, values in raw.values.items():
        admit.require(len(values) == len(t), 'Trace sample count mismatch: ' + name)
        admit.require(all(isinstance(x, (float, int)) and math.isfinite(x) for x in values),
                      'Nonfinite/non-real trace: ' + name)
    required = {'X_ck0'}
    for bank in range(8):
        required.update(('X_h%dp' % bank, 'X_h%dm' % bank))
        for branch in range(8):
            required.update(('B%d_h%dp' % (bank, branch), 'B%d_h%dm' % (bank, branch)))
    required.update(('B0_ck0', 'B0_ck7', 'B7_ck7', 'XVs:p', 'VBANK:p', 'VCOMP:p', 'VLOGIC:p'))
    admit.require(required.issubset(raw.values),
                  'Missing original native clock/64-secondary/power signals: ' + repr(sorted(required - set(raw.values))))
    return t


def validate_case(case):
    admit.require(isinstance(case, dict), 'Case must be one JSON object')
    admit.require(isinstance(case.get('case_id'), str) and
                  re.match(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$', case['case_id']), 'Safe case_id required')
    kind = case.get('kind')
    admit.require(kind in ('pam4_noiseless', 'pam4_noise'), 'This collector accepts PAM4 cases only')
    delta = case.get('delta_ui')
    admit.require(isinstance(delta, (float, int)) and not isinstance(delta, bool) and math.isfinite(delta),
                  'Finite delta_ui required')
    if kind == 'pam4_noiseless':
        admit.require(case.get('noise_seed') is None, 'Noiseless case cannot contain a noise seed')
    else:
        seed = case.get('noise_seed')
        admit.require(isinstance(seed, int) and not isinstance(seed, bool) and 1 <= seed < 2147483648,
                      'Explicit positive Spectre noise seed required')
    admit.require(case.get('validation_data_seed', 2026101302) == 2026101302,
                  'The original r5 data/labels must remain unchanged')
    return case


def ensure_end(path):
    path = admit.regular_file(path)
    admit.require(path.stat().st_size <= MAX_RAW_BYTES, 'Raw exceeds 512 MiB collector bound')
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - 65536))
        tail = stream.read()
    admit.require(tail.rstrip().endswith(b'\nEND') or tail.rstrip() == b'END',
                  'Incomplete or unsupported raw PSF: final END required')
    return path


def validation_stop(deck, functions):
    # Training's clock-spec STOP is shorter than the full validation run.
    # The admitted/staged deck, whose STOP is unchanged, is authoritative here.
    text = Path(deck).read_text(encoding='utf-8')
    lines = [line for line in text.splitlines() if re.match(r'^tranResponse\s+tran\s', line)]
    admit.require(len(lines) == 1, 'Exactly one original validation transient required')
    stops = re.findall(r'\bstop=([^\s]+)', lines[0])
    admit.require(len(stops) == 1, 'Unique validation STOP required')
    value = functions.pi._spectre_number(stops[0])
    admit.require(math.isfinite(value) and value > 0, 'Finite positive validation STOP required')
    return value


def verify_run_status(run_dir, raw_path, profile, case, raw_sha256):
    """Check the fresh runner's attestation; this is not cryptographic proof."""
    path = admit.regular_file(Path(run_dir) / 'run_status.json')
    status = admit.read_json(path)
    admit.require(status.get('format') == 'pn_skew_native_run_v1' and
                  status.get('status') == 'spectre_completed' and status.get('exit_code') == 0,
                  'A completed new-run runner attestation is required; old raw cannot be admitted directly')
    for key, expected in [('case_id', case['case_id']),
                          ('input_deck_sha256_before', profile['staged_deck_sha256']),
                          ('input_deck_sha256_after', profile['staged_deck_sha256']),
                          ('admission_sha256', profile['admission_sha256']),
                          ('plan_sha256', profile['plan_sha256'])]:
        admit.require(status.get(key) == expected, 'Runner attestation mismatch: ' + key)
    for key in ('simulator_build', 'started_utc', 'finished_utc'):
        admit.require(isinstance(status.get(key), str) and status[key].strip(), 'Runner metadata missing: ' + key)
    cpus = status.get('cpus_allocated')
    admit.require(isinstance(cpus, int) and not isinstance(cpus, bool) and cpus > 0, 'Runner CPU allocation missing')
    argv = status.get('actual_argv')
    admit.require(isinstance(argv, list) and argv and all(isinstance(x, str) for x in argv),
                  'Runner actual argv required')
    admit.require(any(Path(x).name == 'bench.scs' for x in argv), 'Runner must use this staged bench.scs')
    relative = Path(raw_path).resolve().relative_to(Path(run_dir).resolve()).as_posix()
    inventory = status.get('raw_inventory')
    admit.require(isinstance(inventory, list), 'Runner raw inventory required')
    entries = [entry for entry in inventory if isinstance(entry, dict) and entry.get('path') == relative]
    admit.require(len(entries) == 1, 'Exactly one matching runner raw inventory entry required')
    stat = Path(raw_path).stat()
    for key, expected in [('sha256', raw_sha256), ('bytes', stat.st_size),
                          ('mtime_ns', stat.st_mtime_ns), ('inode', stat.st_ino), ('device', stat.st_dev)]:
        admit.require(entries[0].get(key) == expected, 'Runner raw inventory mismatch: ' + key)
    return status, admit.sha256_file(path)


def evaluate_records(functions, raw, frozen):
    r5, pi, opt = functions.r5, functions.pi, functions.opt
    records, audit = r5.extract_records(raw, frozen['training_run']['clock_specification'])
    symbols = r5.validation_symbols()
    results, rows = {}, []
    for point in ('primary', 'secondary'):
        choice = frozen['selections'][point]
        samples, labels, times = pi.aligned_window(records[point], symbols,
            choice['integer_symbol_lag'], 1024, 2048)
        ss, ll, tt = samples[1024:], labels[1024:], times[1024:]
        admit.require(len(ss) == len(ll) == len(tt) == 2048, 'Full 2048 held holdout samples required')
        metrics = opt.evaluate_frozen(ss, ll, choice['frozen_detectors'])
        admit.require(metrics['validation_fitting_performed'] is False and
                      metrics['FFE_validation_output_count'] == 2032 and
                      metrics['ADC_validation_input_count'] == 2048, 'Original no-refit protocol mismatch')
        quantized, unused = functions.metrics.quantize_symmetric(ss,
            choice['ADC_fullscale_differential_Vpp'], 7)
        results[point] = {'metrics': metrics, 'integer_symbol_lag': choice['integer_symbol_lag'],
            'sample_count': 2048, 'held_min_V': min(ss), 'held_max_V': max(ss),
            'held_Vppd': max(ss) - min(ss), 'first_read_s': tt[0], 'last_read_s': tt[-1]}
        by_index = {row[0]: row for row in records[point]}
        for index, (sample, label, time, q) in enumerate(zip(ss, ll, tt, quantized)):
            label_index = 128 + 1024 + index
            capture_index = label_index + choice['integer_symbol_lag']
            row = by_index[capture_index]
            rows.append((point, index, label_index, capture_index, time, row[3], row[4], sample, label, q))
    lo = results['primary']['first_read_s']
    hi = results['primary']['last_read_s'] + UI
    return {'results': results, 'clock_mapping_audit': audit,
            'VDD_power': r5.power(raw, lo, hi),
            'symbol_sequence_sha256': opt.canonical_hash(symbols)}, rows


CSV_FIELDS = ('point', 'holdout_index', 'transmitted_symbol_index', 'held_symbol_index',
              'read_s', 'primary_close_s', 'bank', 'held_differential_V', 'symbol', 'ideal7bit_reconstructed_V')
SHORT_FIELDS = ('time_s', 'AFE_differential_V', 'AFE_commonmode_V', 'AFE_input_differential_V', 'CK0_V')
SHORT_NODES = ('X_o_p', 'X_o_m', 'X_ip', 'X_im', 'X_ck0')


def fixed_validation_clip_window(frozen):
    """Predeclare first64UI at the first validation primary read, without data.

    Uses frozen EXPECTED clocks, not observed noise/skew waveforms or eye
    quality. Primary label1152 and frozen lag1 imply capture index1153.
    """
    target = 128 + 1024 + frozen['selections']['primary']['integer_symbol_lag']
    candidates = []
    for bank, clock in enumerate(frozen['training_run']['clock_specification']['primary_clocks']):
        base, period = clock['first_fall_midpoint_s'], clock['period']
        admit.require(math.isfinite(base) and math.isfinite(period) and period > 0,
                      'Valid frozen primary clocks required for fixed clip')
        approximate = int(math.floor((200e-12 + target * UI - base) / period))
        for cycle in range(max(0, approximate - 2), approximate + 3):
            close = base + cycle * period
            if int(math.floor((close - 200e-12) / UI + 1e-7)) == target:
                candidates.append((close + 1.5e-12, bank, cycle))
    admit.require(len(candidates) == 1, 'Fixed validation first primary read must be unambiguous')
    start, bank, cycle = candidates[0]
    return {'window_s': [start, start + 64 * UI], 'duration_UI': 64,
            'reference_transmitted_symbol_index': 1152, 'reference_capture_index': target,
            'reference_bank': bank, 'reference_master_cycle': cycle,
            'selection': 'Predeclared first64UI from frozen expected validation primary read; identical for every delta/noise seed.',
            'endpoint_method': 'Original linear interpolation only at fixed endpoints; all native saved strobes inside are retained.',
            'scope': 'Native saved/strobed AFE waveform, not full adaptive raw or a continuous post-FFE eye.'}


def short_waveform(raw, frozen, functions):
    metadata = {'columns': list(SHORT_FIELDS)}
    metadata['units'] = {'time_s': 's', 'AFE_differential_V': 'V differential',
        'AFE_commonmode_V': 'V', 'AFE_input_differential_V': 'V differential', 'CK0_V': 'V'}
    missing = [name for name in SHORT_NODES if name not in raw.values]
    if missing:
        metadata.update(available=False, reason='Required saved AFE/clock traces unavailable', missing_signals=missing)
        return metadata, []
    metadata.update(fixed_validation_clip_window(frozen))
    t = raw.values[raw.sweep_names[0]]
    lo, hi = metadata['window_s']
    admit.require(t[0] <= lo < hi <= t[-1], 'Fixed native short-waveform window is not actually covered')
    admit.require(all(math.isfinite(x) for x in t) and all(b > a for a, b in zip(t, t[1:])),
                  'Short waveform requires finite monotonic time')
    for name in SHORT_NODES:
        admit.require(len(raw.values[name]) == len(t) and all(math.isfinite(x) for x in raw.values[name]),
                      'Short waveform requires finite complete native traces: ' + name)
    first, last = bisect.bisect_right(t, lo), bisect.bisect_left(t, hi)
    times = [lo] + t[first:last] + [hi]
    rows = []
    for time in times:
        op, om, ip, im, ck = [functions.a.interpolate(t, raw.values[name], time) for name in SHORT_NODES]
        rows.append((time, op - om, (op + om) / 2., ip - im, ck))
    admit.require(all(math.isfinite(value) for row in rows for value in row), 'Nonfinite derived short waveform')
    metadata.update(available=True, rows=len(rows), native_interior_strobe_rows=last - first,
                    source_signals=list(SHORT_NODES))
    return metadata, rows


def collect(admission_path, run_dir, case_json, output):
    # Delayed import of our local stager only; never imports private source modules.
    import pn_stage
    run_dir = Path(run_dir).resolve()
    output = Path(output).absolute()
    admit.require(run_dir.is_dir() and admit.inside(output, run_dir), 'Output must remain inside run-dir')
    admit.require(output.parent.is_dir(), 'Output parent must already exist')
    csv_path = output.with_name(output.stem + '.held_samples.csv')
    short_path = output.with_name(output.stem + '.short_waveform.csv')
    admit.require(not output.exists() and not csv_path.exists() and not short_path.exists(),
                  'Refuse to overwrite collected evidence')
    admission_path, case_json = admit.regular_file(admission_path), admit.regular_file(case_json)
    document = admit.read_admission(admission_path, verify=True)
    frozen = admit.read_json(document['frozen_r5']['path'])
    case = validate_case(admit.read_json(case_json))
    profile = pn_stage.verify_stage(admission_path, run_dir)
    admit.require(profile['case'] == case, 'Case JSON differs from staged profile')
    admit.require(profile['mean_input_delay_s'] == 0 and profile['clock_shift_s'] == 0,
                  'Symmetric PN skew must preserve mean delay and all clocks')
    admit.require(profile['admission_sha256'] == admit.sha256_file(admission_path), 'Wrong admission binding')
    deck = admit.regular_file(run_dir / 'bench.scs')
    admit.require(admit.sha256_file(deck) == profile['staged_deck_sha256'], 'Staged deck changed')
    functions = original_functions(document['source_dir'])
    raw_path = ensure_end(functions.a._raw_file(run_dir))
    admit.require(admit.inside(raw_path, run_dir / 'raw'), 'Raw escaped run/raw')
    before = file_snapshot(raw_path)
    raw = functions.a.parse_file(raw_path)
    run_status, run_status_sha = verify_run_status(run_dir, raw_path, profile, case, raw.sha256)
    stop_s = validation_stop(deck, functions)
    t = validate_raw(raw, stop_s)
    log = admit.regular_file(run_dir / 'spectre.log')
    admit.require(log.stat().st_size <= 32 * 1024 * 1024, 'Spectre log exceeds bound')
    log_before, log_sha = file_snapshot(log), admit.sha256_file(log)
    log_text = log.read_text(encoding='utf-8', errors='replace')
    admit.require(re.search(r'spectre completes with\s+0\s+errors\b', log_text, re.I),
                  'A completed zero-error Spectre log is required; no pass inferred')
    numeric, rows = evaluate_records(functions, raw, frozen)
    short_metadata, short_rows = short_waveform(raw, frozen, functions)
    # Fresh guards before any output; active/incomplete/changing evidence is refused.
    admit.require(file_snapshot(raw_path) == before and admit.sha256_file(raw_path) == raw.sha256,
                  'Raw changed during collection')
    admit.require(file_snapshot(log) == log_before and admit.sha256_file(log) == log_sha,
                  'Spectre log changed during collection')
    admit.require(verify_run_status(run_dir, raw_path, profile, case, raw.sha256)[1] == run_status_sha,
                  'Runner attestation changed during collection')
    admit.read_admission(admission_path, verify=True)
    admit.require(pn_stage.verify_stage(admission_path, run_dir) == profile, 'Stage changed during collection')
    result = dict(numeric, format='pn_skew_native_r5_collection_v1',
        status='completed_frozen_numerical_diagnostic', measurement_complete=True, case=case,
        complete_ADC_verified=False, validation_fitting_performed=False,
        frozen_file_unchanged=True, validation_input_symbols=2048, FFE_complete_windows=2032,
        historical_validation_data_seed=2026101302,
        historical_reference=True, new_independent_holdout=False,
        validation_label_index_range=[1152, 3199],
        noise_conditions={'noise_seed': case['noise_seed'],
            'noisefmin_Hz': 500e6 if case['kind'] == 'pam4_noise' else None,
            'noisefmax_Hz': 150e9 if case['kind'] == 'pam4_noise' else None},
        skew_protocol={'delta_UI': case['delta_ui'], 'mean_input_delay_s': 0., 'clock_shift_s': 0.,
                       'fixed_original_lags_and_labels': True},
        units={'held_voltage': 'V differential', 'time': 's', 'power': 'W',
               'ADC_fullscale': 'V peak-to-peak differential', 'SER': 'errors/symbols',
               'gray_BER': 'Gray bit errors/observed bits', 'FFE_prediction': 'dimensionless target PAM4 amplitude'},
        raw={'path': str(raw_path), 'bytes': before[2], 'sha256': raw.sha256,
             'relative_path': raw_path.relative_to(run_dir).as_posix(),
             'time_sample_count': len(t), 'trace_count_including_time': len(raw.values),
             'first_time_s': t[0], 'last_time_s': t[-1], 'requested_stop_s': stop_s},
        provenance={'admission_sha256': admit.sha256_file(admission_path),
            'profile_sha256': admit.sha256_file(run_dir / 'profile.json'),
            'case_json_sha256': admit.sha256_file(case_json), 'input_deck_sha256': admit.sha256_file(deck),
            'source_deck_sha256': profile['source_deck_sha256'],
            'run_status_sha256': run_status_sha,
            'raw_input_binding': 'New exclusive-run runner attestation checked; not cryptographic proof of simulator execution.',
            'frozen_r5_sha256': document['frozen_r5']['sha256'],
            'source_scripts': document['source_scripts'], 'auxiliary_scripts': document['auxiliary_scripts'],
            'model_files': document['model_files'], 'spectre_log_sha256': log_sha,
            'collector_sha256': admit.sha256_file(__file__)},
        runtime={'simulator_build': run_status['simulator_build'],
                 'started_utc': run_status['started_utc'], 'finished_utc': run_status['finished_utc'],
                 'cpus_allocated': run_status['cpus_allocated'], 'source': 'runner-attested run_status.json'},
        limitations=['Native r5 reset-comparator loads are retained; not a complete ADC.',
                     'Ideal numerical 7-bit quantizer and frozen 17-tap FFE; no refitting.',
                     'Finite correlated sample errors do not establish a target BER.',
                     'No PVT, mismatch, physical deskew circuit, jitter, PEX or ENOB proof.'])
    # Exclusive creation prevents accidental replacement of previous evidence.
    with csv_path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(CSV_FIELDS)
        writer.writerows(rows)
    result['held_sample_csv'] = {'path': str(csv_path), 'rows': len(rows),
        'bytes': csv_path.stat().st_size, 'sha256': admit.sha256_file(csv_path),
        'units': 'voltage V differential; time s; integer symbol indices'}
    if short_metadata['available']:
        with short_path.open('x', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(SHORT_FIELDS)
            writer.writerows(short_rows)
        short_metadata.update(path=str(short_path), bytes=short_path.stat().st_size,
                              sha256=admit.sha256_file(short_path))
    result['short_waveform_csv'] = short_metadata
    admit.write_new_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('admission', 'run-dir', 'case-json', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    try:
        result = collect(args.admission, args.run_dir, args.case_json, args.output)
    except (ValueError, KeyError, TypeError, OSError, ImportError) as error:
        parser.exit(2, 'Collection refused: ' + str(error) + '\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output),
                      'complete_ADC_verified': False}, sort_keys=True))


if __name__ == '__main__':
    main()
