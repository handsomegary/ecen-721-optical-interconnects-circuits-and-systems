#!/usr/bin/env python3
"""Bounded native CTLE optimization with strictly separate final validation.

--screen selects analog configuration, phase, lag and ADC range on a split
training sequence, then refits and freezes FIR coefficients using training.
--validate reads that frozen file and runs old/new analog designs on identical
fresh data/noise-seed pairs. No validation fitting or automatic redesign occurs.
"""

import argparse
import concurrent.futures
import hashlib
import json
import math
import random
import re
import sys
import time
from pathlib import Path

import pam4_integration as integration
import pam4_ffe_diagnostic as ffe
import pam4_metrics as metrics
import psf_ascii


TRAIN_SEED = 721202610
SCREEN_NOISE_SEED = 71
VALIDATION_DATA_SEEDS = (20261103, 20261207)
VALIDATION_NOISE_SEEDS = (11, 29)
ADC_RANGES = (.025, .035, .05, .075, .1, .15, .2, .25, .3, .4)
SPLIT_GUARD = 16
FINAL_SYMBOLS = 2048


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode('utf-8')).hexdigest()


def read_json_snapshot(path):
    data = path.read_bytes()
    return json.loads(data.decode('utf-8')), hashlib.sha256(data).hexdigest()


def choice_identity(frozen):
    """Hash actual frozen choices, ignoring timing/cache/progress metadata."""
    choices = {'training_data_seed': frozen['training_data_seed'],
               'training_noise_seed': frozen['training_noise_seed'],
               'training_symbol_count': frozen['training_symbol_count'],
               'native_cards_sha256': frozen['native_cards_sha256'], 'designs': []}
    for design in frozen['designs']:
        record = design['record']
        choices['designs'].append({'role': design['role'], 'config': record['config'],
                                   'phase_UI': record['phase_UI'],
                                   'integer_symbol_lag': record['selection']['integer_symbol_lag'],
                                   'frozen_detectors': record['selection']['frozen_detectors']})
    choices['designs'].sort(key=lambda design: design['role'])
    return canonical_hash(choices)


def random_symbols(seed, count):
    generator = random.Random(seed)
    return [generator.randrange(4) for unused in range(count)]


def training_sequence(train_count):
    return random_symbols(TRAIN_SEED, integration.WARMUP + train_count + integration.GUARD)


def validation_sequence(train_count, fresh_data_seed):
    if fresh_data_seed == TRAIN_SEED:
        raise ValueError('Final data seed must differ from training seed')
    prefix = random_symbols(TRAIN_SEED, integration.WARMUP + train_count)
    fresh = random_symbols(fresh_data_seed, FINAL_SYMBOLS + integration.GUARD)
    return prefix + fresh


def split_training(samples, symbols):
    fit_stop = len(samples) // 2
    selection_start = fit_stop + SPLIT_GUARD
    if len(samples) != len(symbols) or len(samples) < 256:
        raise ValueError('Expected matched training arrays of at least256 symbols')
    if len(samples) - selection_start <= ffe.TAPS:
        raise ValueError('Training selection block is too short')
    return (samples[:fit_stop], symbols[:fit_stop],
            samples[selection_start:], symbols[selection_start:],
            {'fit_input_symbols': fit_stop, 'guard_symbols': SPLIT_GUARD,
             'selection_input_symbols': len(samples) - selection_start,
             'fit_complete_windows': fit_stop - 2 * ffe.HALF,
             'selection_complete_windows': len(samples) - selection_start - 2 * ffe.HALF})


def score_split(samples, symbols, fullscale=None):
    first, first_labels, second, second_labels, split = split_training(samples, symbols)
    clipped_fit = clipped_selection = 0
    if fullscale is not None:
        first, clipped_fit = metrics.quantize_symmetric(first, fullscale, 7)
        second, clipped_selection = metrics.quantize_symmetric(second, fullscale, 7)
    fit = ffe.fit_ffe(first, first_labels, ridge=1e-3)
    predicted = ffe.predict_window(second, fit)
    targets = second_labels[ffe.HALF:len(second_labels) - ffe.HALF]
    measured = ffe.prediction_metrics(predicted, targets)
    return {'selection_symbol_errors': measured['symbol_errors'],
            'selection_symbol_count': measured['sample_count'],
            'selection_SER': measured['SER'],
            'selection_gray_BER': measured['gray_BER'],
            'selection_MSE_target_units_squared': measured['prediction_RMSE_in_target_symbol_units'] ** 2,
            'fit_input_clipped_count': clipped_fit,
            'selection_input_clipped_count': clipped_selection,
            'fullscale_differential_Vpp': fullscale, 'split': split}


def score_key(score):
    return (score['selection_SER'], score['selection_MSE_target_units_squared'])


def freeze_detectors(samples, labels, fullscale):
    quantized, clipped = metrics.quantize_symmetric(samples, fullscale, 7)
    return {'raw_FFE': ffe.fit_ffe(samples, labels, ridge=1e-3),
            'ADC_FFE': ffe.fit_ffe(quantized, labels, ridge=1e-3),
            'raw_three_threshold': metrics.fit_training(samples, labels),
            'ADC_three_threshold': metrics.fit_training(quantized, labels),
            'ADC_fullscale_differential_Vpp': fullscale,
            'all_training_ADC_clipped_count': clipped,
            'freeze_rule': 'phase/lag/ADC range selected with split training; FIRs then refit once using all training; no final validation samples'}


def select_training_alignment(held_records, transmitted_symbols, train_count):
    searches = []
    best = None
    for lag in integration.LAGS:
        try:
            samples, labels, unused = integration.aligned_window(
                held_records, transmitted_symbols, lag, train_count, 0)
            score = score_split(samples, labels)
            candidate = {'integer_symbol_lag': lag, 'raw_FFE_score': score}
            searches.append(candidate)
            if best is None or score_key(score) < score_key(best['raw_FFE_score']):
                best = candidate
        except ValueError as error:
            searches.append({'integer_symbol_lag': lag, 'error': str(error)})
    if best is None:
        raise ValueError('No valid training-only FFE alignment')
    samples, labels, unused = integration.aligned_window(
        held_records, transmitted_symbols, best['integer_symbol_lag'], train_count, 0)
    adc_search = []
    for fullscale in ADC_RANGES:
        try:
            adc_search.append(score_split(samples, labels, fullscale))
        except ValueError as error:
            adc_search.append({'fullscale_differential_Vpp': fullscale, 'error': str(error)})
    valid_adc = [score for score in adc_search if 'error' not in score]
    if not valid_adc:
        raise ValueError('Every requested ADC range produces unusable training data')
    selected_adc = min(valid_adc, key=score_key)
    return {'integer_symbol_lag': best['integer_symbol_lag'],
            'raw_FFE_score': best['raw_FFE_score'], 'ADC_score': selected_adc,
            'ADC_fullscale_differential_Vpp': selected_adc['fullscale_differential_Vpp'],
            'lag_search': searches, 'ADC_range_search': adc_search,
            'frozen_detectors': freeze_detectors(samples, labels, selected_adc['fullscale_differential_Vpp']),
            'selection_rule': 'raw-held FFE split-training SER then MSE selects timing; conditional quantized split-training SER then MSE selects ADC range'}


def validate_config(candidate):
    identifier = str(candidate['id'])
    if not re.match(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$', identifier):
        raise ValueError('Unsafe candidate identifier')
    config = dict(candidate['config'])
    if config.get('arch', 'cml') != 'cml':
        raise ValueError('Optimization supports native CML candidates only')
    if not math.isclose(config.get('ch', 5e-15), 5e-15, rel_tol=1e-9):
        raise ValueError('All comparisons must keep5fF per sampler side')
    if not math.isclose(config.get('vdd', .9), .9, rel_tol=1e-9):
        raise ValueError('All comparisons must keep0.9V supply')
    for parameter in ['nc', 'nv']:
        if int(config[parameter]) != config[parameter] or config[parameter] < 1:
            raise ValueError('MOS copy counts must be positive integers')
    return {'id': identifier, 'config': config,
            'AC_metrics': candidate.get('metrics', {}),
            'AC_ranking_reason': candidate.get('ranking_reason')}


def load_candidates(path, limit=4, requested_ids=None):
    source, source_hash = read_json_snapshot(path)
    baseline = validate_config(source['baseline'])
    pool = source.get('shortlist', source.get('candidates', []))
    wanted = set(requested_ids or [])
    candidates = []
    seen = {canonical_hash(baseline['config'])}
    for record in pool:
        if wanted and record['id'] not in wanted:
            continue
        candidate = validate_config(record)
        fingerprint = canonical_hash(candidate['config'])
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        candidates.append(candidate)
        if limit and len(candidates) >= limit:
            break
    if not candidates:
        raise ValueError('No new nonduplicate candidates found in shortlist')
    found_ids = set(candidate['id'] for candidate in candidates)
    if wanted - found_ids:
        raise ValueError('Requested candidate IDs absent, duplicated, or beyondlimit: ' + repr(sorted(wanted - found_ids)))
    return baseline, candidates, source_hash


def build_noise_deck(config, symbols, phase_ui, noise_seed):
    deck, stop = integration.build_deck(config, symbols, 20, phase_ui=phase_ui, noise=True)
    found = 0
    for index, line in enumerate(deck):
        if line.startswith('tranResponse '):
            deck[index], replacements = re.subn(r'\bnoiseseed=\d+', 'noiseseed=%d' % noise_seed, line)
            found += replacements
    if found != 1:
        raise ValueError('Expected exactly one transient noise seed')
    return deck, stop


def measured_aperture_phase(held):
    """Clock half-fall phase relative to a transmitted-symbol boundary.

    Use the first observed held record after warmup, rather than equating the
    requested clock delay increment with the actual aperture phase.
    """
    record = next((record for record in held if record[0] >= integration.WARMUP), None)
    if record is None:
        raise ValueError('No observed held record after warmup for aperture audit')
    close = record[3]
    return {'phase_UI': ((close - integration.T0) / integration.UI) % 1.0,
            'CK_half_fall_time_s': close,
            'observed_symbol_time_index': record[0], 'lane': record[4],
            'reference': 'transmitted-symbol boundaries T0 + integer*UI',
            'method': 'first observed CK half-fall after warmup, modulo UI; not the requested clock delay increment'}


def simulate(project, candidate, run_name, symbols, phase_ui, noise_seed):
    deck, stop = build_noise_deck(candidate['config'], symbols, phase_ui, noise_seed)
    directory, status, deck_hash, cached = integration.execute_deck(project, run_name, deck)
    raw = integration._raw_file(directory)
    parsed = psf_ascii.parse_file(raw)
    held, clock_audit = integration.held_records(parsed)
    if clock_audit['saved_last_time_s'] < stop - integration.UI / 16 * 1.01:
        raise ValueError('Saved data does not cover requested transient')
    aperture = measured_aperture_phase(held)
    metadata = {'run_name': run_name, 'candidate_id': candidate['id'],
                'config': candidate['config'], 'phase_UI': phase_ui,
                'phase_UI_definition': 'requested clock delay offset in UI, not actual aperture phase',
                'clock_delay_offset_UI': phase_ui,
                'measured_CK_half_fall_aperture_phase_UI': aperture['phase_UI'],
                'aperture_phase_measurement': aperture,
                'noise_seed': noise_seed, 'transient_noise_enabled': True,
                'noise_max_Hz': 150e9, 'noise_flattened_below_Hz': 500e6,
                'synthetic_channel_resistor_thermal_noise_included': True,
                'run_status': status, 'cached_identical_deck': cached,
                'netlist_sha256': deck_hash, 'raw_transient_sha256': parsed.sha256,
                'clock_audit': clock_audit}
    return parsed, held, metadata


def screen_one(project, candidate, phase_index, phase_count, train_count, noise_seed):
    phase_ui = phase_index / phase_count
    symbols = training_sequence(train_count)
    name = 'opt_train_%s_p%03d_t%d_n%d' % (candidate['id'], int(round(phase_ui * 1000)), train_count, noise_seed)
    parsed, held, result = simulate(project, candidate, name, symbols, phase_ui, noise_seed)
    selection = select_training_alignment(held, symbols, train_count)
    result['selection'] = selection
    result['training_data_seed'] = TRAIN_SEED
    result['training_symbol_count'] = train_count
    result['AC_metrics'] = candidate.get('AC_metrics', {})
    samples, labels, times = integration.aligned_window(held, symbols,
        selection['integer_symbol_lag'], train_count, 0)
    lo, hi = times[0], times[-1] + integration.UI
    waveform_times = parsed.values[parsed.sweep_names[0]]
    result['AFE_and_sampler_VDD_power_W'] = -candidate['config'].get('vdd', .9) * integration.dynamic.mean_time(
        waveform_times, parsed.values['XVs:p'], lo, hi)
    result['training_held_min_V'] = min(samples)
    result['training_held_max_V'] = max(samples)
    return result


def screen(project, candidate_path, candidate_limit=4, requested_ids=None,
           train_count=512, phase_count=4, noise_seed=SCREEN_NOISE_SEED, workers_count=2,
           final_data_seeds=VALIDATION_DATA_SEEDS):
    if train_count not in (512, 1024) or phase_count not in (4, 8):
        raise ValueError('Choose512/1024 training symbols and4/8 phases')
    if noise_seed in VALIDATION_NOISE_SEEDS:
        raise ValueError('Training noise seed must differ from predefined final seeds')
    if len(set(final_data_seeds)) != 2 or TRAIN_SEED in final_data_seeds:
        raise ValueError('Predeclare two distinct final data seeds different from training')
    native = integration.install_native_cards(project / 'configs' / 'native_device_cards.json')
    baseline, candidates, source_hash = load_candidates(candidate_path, candidate_limit, requested_ids)
    all_candidates = [baseline] + candidates
    summary = {'schema_version': 1, 'status': 'running', 'mode': 'training_screen',
               'source_AC_shortlist_sha256': source_hash, 'native_cards': native,
               'training_data_seed': TRAIN_SEED, 'training_noise_seed': noise_seed,
               'training_symbol_count': train_count, 'phase_count': phase_count,
               'phases_UI': [index / phase_count for index in range(phase_count)],
               'ADC_ranges_Vppd': list(ADC_RANGES),
               'baseline_id': baseline['id'], 'candidate_ids': [candidate['id'] for candidate in candidates],
               'criterion': 'minimize split-training raw-held FFE SER then MSE before ADC; ADC range selected conditionally on same training split',
               'scope': 'native candidate CTLE gain/noise changes only; no ideal analog VGA added;20dB synthetic channel,0.4Vppd TX,5fF native TG',
               'runs': [], 'errors': []}
    destination = project / 'results' / 'pam4_optimization_screen.json'
    started = time.time()

    def checkpoint(event):
        summary['elapsed_seconds'] = round(time.time() - started, 3)
        integration.atomic_json(destination, summary)
        print(json.dumps(event, sort_keys=True), flush=True)

    checkpoint({'event': 'optimization_screen_started', 'candidate_count_with_control': len(all_candidates)})
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers_count) as workers:
        futures = {}
        for candidate in all_candidates:
            for phase_index in range(phase_count):
                future = workers.submit(screen_one, project, candidate, phase_index,
                                        phase_count, train_count, noise_seed)
                futures[future] = (candidate['id'], phase_index)
        for future in concurrent.futures.as_completed(futures):
            identifier, phase_index = futures[future]
            try:
                record = future.result()
                summary['runs'].append(record)
                checkpoint({'event': 'optimization_training_complete', 'candidate': identifier,
                            'phase_UI': record['phase_UI'],
                            'raw_FFE_selection_SER': record['selection']['raw_FFE_score']['selection_SER'],
                            'ADC_range_Vppd': record['selection']['ADC_fullscale_differential_Vpp']})
            except Exception as error:
                summary['errors'].append({'candidate_id': identifier, 'phase_index': phase_index,
                                          'error': repr(error)})
                checkpoint({'event': 'optimization_training_failed', 'candidate': identifier,
                            'phase_index': phase_index, 'error': repr(error)})

    best_per_candidate = []
    for candidate in all_candidates:
        available = [record for record in summary['runs'] if record['candidate_id'] == candidate['id']]
        if len(available) != phase_count:
            continue
        best = min(available, key=lambda record: score_key(record['selection']['raw_FFE_score']) + (record['phase_UI'],))
        best_per_candidate.append(best)
    baseline_runs = [record for record in best_per_candidate if record['candidate_id'] == baseline['id']]
    new_runs = [record for record in best_per_candidate if record['candidate_id'] != baseline['id']]
    summary['eligible_candidate_count'] = len(best_per_candidate)
    if len(baseline_runs) != 1 or not new_runs:
        summary['status'] = 'failed_no_valid_control_or_candidate'
        checkpoint({'event': 'optimization_screen_failed', 'reason': summary['status']})
        return summary
    old = baseline_runs[0]
    new = min(new_runs, key=lambda record: score_key(record['selection']['raw_FFE_score']))
    summary['selected_baseline'] = old
    summary['selected_new_candidate'] = new
    summary['baseline_better_or_equal_on_training'] = score_key(old['selection']['raw_FFE_score']) <= score_key(new['selection']['raw_FFE_score'])
    summary['status'] = 'complete' if not summary['errors'] else 'complete_with_excluded_failed_candidates'
    checkpoint({'event': 'optimization_screen_selected', 'baseline': old['candidate_id'],
                'new_candidate': new['candidate_id'],
                'baseline_training_SER': old['selection']['raw_FFE_score']['selection_SER'],
                'new_training_SER': new['selection']['raw_FFE_score']['selection_SER']})
    frozen = {'schema_version': 1, 'purpose': 'frozen train-only choices for independent final validation',
              'screen_summary_sha256': integration.file_hash(destination),
              'training_data_seed': TRAIN_SEED, 'training_noise_seed': noise_seed,
              'training_symbol_count': train_count,
              'final_data_seeds': list(final_data_seeds),
              'final_noise_seeds': list(VALIDATION_NOISE_SEEDS),
              'validation_symbol_count': FINAL_SYMBOLS,
              'native_cards_sha256': native['native_cards_sha256'],
              'designs': [{'role': 'baseline', 'record': old}, {'role': 'optimized', 'record': new}],
              'freeze_statement': 'Analog configuration,phase,lag,ADC range,input normalization,FIR weights,bias and thresholds fixed before any final validation'}
    integration.atomic_json(project / 'configs' / 'pam4_optimization_frozen.json', frozen)
    return summary


def evaluate_frozen(samples, labels, frozen_detectors):
    target_labels = labels[ffe.HALF:len(labels) - ffe.HALF]
    raw_predictions = ffe.predict_window(samples, frozen_detectors['raw_FFE'])
    fullscale = frozen_detectors['ADC_fullscale_differential_Vpp']
    quantized, clipped = metrics.quantize_symmetric(samples, fullscale, 7)
    adc_predictions = ffe.predict_window(quantized, frozen_detectors['ADC_FFE'])
    return {'raw_held_FFE_before_ADC': ffe.prediction_metrics(raw_predictions, target_labels),
            'ideal7bit_ADC_then_FFE': ffe.prediction_metrics(adc_predictions, target_labels),
            'raw_three_threshold_same_centers': metrics._validation_metrics(
                samples[ffe.HALF:len(samples) - ffe.HALF], target_labels, frozen_detectors['raw_three_threshold']),
            'ADC_three_threshold_same_centers': metrics._validation_metrics(
                quantized[ffe.HALF:len(samples) - ffe.HALF], target_labels, frozen_detectors['ADC_three_threshold']),
            'ADC_fullscale_differential_Vpp': fullscale,
            'ADC_validation_input_clipped_count': clipped,
            'ADC_validation_input_count': len(samples),
            'ADC_validation_input_clipped_fraction': clipped / len(samples),
            'FFE_validation_output_count': len(raw_predictions),
            'feature_rule': 'FFE features lie wholly within independent validation slice;8 symbols excluded at each edge',
            'validation_fitting_performed': False}


def validate_one(project, design, train_count, data_seed, noise_seed, frozen_hash):
    record = design['record']
    candidate = {'id': record['candidate_id'], 'config': record['config']}
    symbols = validation_sequence(train_count, data_seed)
    run_name = 'opt_final_%s_%s_d%d_n%d_%s' % (
        design['role'], candidate['id'], data_seed, noise_seed, frozen_hash[:10])
    parsed, held, result = simulate(project, candidate, run_name, symbols, record['phase_UI'], noise_seed)
    selected = record['selection']
    samples, labels, held_times = integration.aligned_window(
        held, symbols, selected['integer_symbol_lag'], train_count, FINAL_SYMBOLS)
    validation_samples = samples[train_count:]
    validation_labels = labels[train_count:]
    if len(validation_samples) != FINAL_SYMBOLS:
        raise ValueError('Final validation must contain exactly2048 aligned held samples')
    result.update(role=design['role'], final_data_seed=data_seed,
                  frozen_choices_sha256=frozen_hash,
                  integer_symbol_lag=selected['integer_symbol_lag'],
                  metrics=evaluate_frozen(validation_samples, validation_labels, selected['frozen_detectors']))
    result['validation_held_min_V'] = min(validation_samples)
    result['validation_held_max_V'] = max(validation_samples)
    result['validation_held_Vppd'] = max(validation_samples) - min(validation_samples)
    result['validation_symbol_index_range_after_FFE_edge_exclusion'] = [
        integration.WARMUP + train_count + ffe.HALF,
        integration.WARMUP + train_count + FINAL_SYMBOLS - ffe.HALF - 1]
    lo = held_times[train_count]
    hi = held_times[-1] + integration.UI
    times = parsed.values[parsed.sweep_names[0]]
    result['AFE_and_sampler_VDD_power_W'] = -candidate['config'].get('vdd', .9) * integration.dynamic.mean_time(
        times, parsed.values['XVs:p'], lo, hi)
    result['power_scope'] = 'CTLE/native TG VDD only; excludes clock-source energy, physical clock/bias generation,ADC andDSP'
    return result


def aggregate_validation(results):
    roles = ('baseline', 'optimized')
    grouped = {}
    for record in results:
        key = (record['final_data_seed'], record['noise_seed'])
        grouped.setdefault(key, {}).setdefault(record['role'], []).append(record)
    complete = {}
    unmatched = []
    for key, group in sorted(grouped.items()):
        if set(group) == set(roles) and all(len(group[role]) == 1 for role in roles):
            complete[key] = {role: group[role][0] for role in roles}
        else:
            unmatched.append({'data_seed': key[0], 'noise_seed': key[1],
                              'available_run_counts_by_role': {role: len(records) for role, records in group.items()},
                              'reason': 'missing counterpart or duplicate role; excluded from headline pools'})
    matched_records = [record for group in complete.values() for record in group.values()]
    matched_ids = set(id(record) for record in matched_records)
    unmatched_records = [record for record in results if id(record) not in matched_ids]
    aggregate = {}
    for role in roles:
        records = [record for record in matched_records if record['role'] == role]
        if not records:
            continue
        groups = {}
        for path in ['raw_held_FFE_before_ADC', 'ideal7bit_ADC_then_FFE']:
            count = sum(record['metrics'][path]['sample_count'] for record in records)
            errors = sum(record['metrics'][path]['symbol_errors'] for record in records)
            bits = sum(record['metrics'][path]['bit_count'] for record in records)
            bit_errors = sum(record['metrics'][path]['gray_bit_errors'] for record in records)
            groups[path] = {'symbol_count': count, 'symbol_errors': errors,
                            'observed_SER': errors / count, 'bit_count': bits,
                            'gray_bit_errors': bit_errors, 'observed_gray_BER': bit_errors / bits,
                            'confidence_note': 'Descriptive pooled counts; two repeated data sequences and filtered errors are not assumed independent'}
        aggregate[role] = {'run_count': len(records), 'paths': groups,
                           'mean_AFE_and_sampler_VDD_power_W': sum(record['AFE_and_sampler_VDD_power_W'] for record in records) / len(records),
                           'ADC_total_clipped_input_count': sum(record['metrics']['ADC_validation_input_clipped_count'] for record in records),
                           'ADC_fullscale_differential_Vpp': records[0]['metrics']['ADC_fullscale_differential_Vpp']}
    pairs = []
    for (data_seed, noise_seed), matching in sorted(complete.items()):
        pair = {'data_seed': data_seed, 'noise_seed': noise_seed}
        for path in ['raw_held_FFE_before_ADC', 'ideal7bit_ADC_then_FFE']:
            old = matching['baseline']['metrics'][path]['SER']
            new = matching['optimized']['metrics'][path]['SER']
            pair[path] = {'baseline_SER': old, 'optimized_SER': new,
                          'SER_absolute_reduction': old - new,
                          'SER_relative_reduction_fraction': (old - new) / old if old else None}
        pairs.append(pair)
    return {'designs': aggregate, 'matched_fresh_data_noise_pairs': pairs,
            'headline_pool_rule': 'only one baseline and one optimized run on each complete matched data/noise-seed pair',
            'comparison_status': ('complete_matched_pairs' if len(complete) == 4 and not unmatched_records
                                  else 'partial_matched_pairs_only' if complete else 'no_complete_matched_pairs'),
            'expected_matched_pair_count': 4, 'matched_pair_count': len(complete),
            'input_run_count': len(results), 'matched_run_count': len(matched_records),
            'unmatched_run_count': len(unmatched_records),
            'unmatched_run_count_by_role': {role: sum(record['role'] == role for record in unmatched_records)
                                            for role in roles},
            'unmatched_pairs': unmatched,
            'before_ADC_definition': 'ideal17tapFFE applied directly to actual held voltages; raw three-threshold metrics also reported perrun'}


def validate(project, workers_count=2):
    path = project / 'configs' / 'pam4_optimization_frozen.json'
    frozen, frozen_hash = read_json_snapshot(path)
    data_seeds = tuple(frozen['final_data_seeds'])
    if len(set(data_seeds)) != 2 or TRAIN_SEED in data_seeds or tuple(frozen['final_noise_seeds']) != VALIDATION_NOISE_SEEDS:
        raise ValueError('Frozen final seeds do not define the predeclared independent test suite')
    if frozen['training_data_seed'] != TRAIN_SEED or frozen['validation_symbol_count'] != FINAL_SYMBOLS:
        raise ValueError('Frozen training prefix or validation size differs from this driver')
    if sorted(design['role'] for design in frozen['designs']) != ['baseline', 'optimized']:
        raise ValueError('Final comparison requires exactly baseline and optimized designs')
    if frozen['training_noise_seed'] in VALIDATION_NOISE_SEEDS:
        raise ValueError('Training and final noise seeds overlap')
    native = integration.install_native_cards(project / 'configs' / 'native_device_cards.json')
    if native['native_cards_sha256'] != frozen['native_cards_sha256']:
        raise ValueError('Native cards changed after training choices were frozen')
    # Prevent a later redesign from silently treating previously inspected
    # final data as a fresh holdout. Re-running exactly the same choices is OK.
    identity = choice_identity(frozen)
    ledger_path = project / 'results' / 'pam4_validation_usage.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {'schema_version': 1, 'reservations': []}
    for reservation in ledger['reservations']:
        if reservation['choice_identity'] != identity and set(reservation['data_seeds']) & set(data_seeds):
            raise ValueError('These final data seeds were already reserved for different frozen choices; '
                             'predeclare two unused --final-data-seeds during a new screen')
    reservation = {'choice_identity': identity, 'data_seeds': list(data_seeds),
                   'noise_seeds': list(VALIDATION_NOISE_SEEDS)}
    if reservation not in ledger['reservations']:
        ledger['reservations'].append(reservation)
        integration.atomic_json(ledger_path, ledger)
    summary = {'schema_version': 1, 'status': 'running', 'mode': 'independent_final_validation',
               'frozen_choices_sha256': frozen_hash,
               'training_data_seed': frozen['training_data_seed'],
               'training_noise_seed': frozen['training_noise_seed'],
               'final_data_seeds': list(data_seeds),
               'frozen_choice_identity': identity,
               'final_noise_seeds': list(VALIDATION_NOISE_SEEDS),
               'validation_symbols_per_run_before_FFE_edges': FINAL_SYMBOLS,
               'validation_FFE_symbols_per_run': FINAL_SYMBOLS - 2 * ffe.HALF,
               'expected_run_count': 8, 'runs': [], 'errors': [],
               'fair_comparison': 'old and new native analog configurations use identical fresh data-seed/noise-seed pairs; each has its own train-only frozen timing,FIRs andADC range',
               'limits': ['Noise seed equality does not imply identical device noise realizations across different transistor topologies.',
                          'Only two fresh data sequences and two noise seeds; finite-screen evidence, not targetBER certification.',
                          'Synthetic20dB channel, ideal zero-impedance source andidealclocks; noPVT/PEX.',
                          '17tapFFE and7bitquantization are idealDSP/ADC models without hardware speed,power orload claims.',
                          'AFEpower omits physicalclock/bias generation,ADC andDSP.',
                          'No final validation samples select or refit any analog,digital,normalization ordecision parameter.']}
    destination = project / 'results' / 'pam4_optimization_validation.json'
    started = time.time()

    def checkpoint(event):
        summary['elapsed_seconds'] = round(time.time() - started, 3)
        summary['comparison'] = aggregate_validation(summary['runs'])
        integration.atomic_json(destination, summary)
        print(json.dumps(event, sort_keys=True), flush=True)

    checkpoint({'event': 'independent_validation_started', 'frozen_sha256': frozen_hash})
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers_count) as workers:
        futures = {}
        for design in frozen['designs']:
            for data_seed in data_seeds:
                for noise_seed in VALIDATION_NOISE_SEEDS:
                    future = workers.submit(validate_one, project, design, frozen['training_symbol_count'],
                                            data_seed, noise_seed, frozen_hash)
                    futures[future] = (design['role'], data_seed, noise_seed)
        for future in concurrent.futures.as_completed(futures):
            role, data_seed, noise_seed = futures[future]
            try:
                record = future.result()
                summary['runs'].append(record)
                checkpoint({'event': 'independent_validation_complete', 'role': role,
                            'data_seed': data_seed, 'noise_seed': noise_seed,
                            'raw_FFE_SER': record['metrics']['raw_held_FFE_before_ADC']['SER'],
                            'ADC_FFE_SER': record['metrics']['ideal7bit_ADC_then_FFE']['SER']})
            except Exception as error:
                summary['errors'].append({'role': role, 'data_seed': data_seed,
                                          'noise_seed': noise_seed, 'error': repr(error)})
                checkpoint({'event': 'independent_validation_failed', 'role': role,
                            'data_seed': data_seed, 'noise_seed': noise_seed, 'error': repr(error)})
    summary['status'] = 'complete' if len(summary['runs']) == 8 and not summary['errors'] else 'partial_or_errors'
    summary['frozen_file_unchanged_during_validation'] = integration.file_hash(path) == frozen_hash
    if not summary['frozen_file_unchanged_during_validation']:
        summary['status'] = 'frozen_file_changed_during_validation'
    checkpoint({'event': 'independent_validation_finished', 'status': summary['status']})
    return summary


def self_check():
    generator = random.Random(448)
    labels = [generator.randrange(4) for unused in range(512 + FINAL_SYMBOLS)]
    amplitude = [ffe.TARGETS[label] for label in labels]
    samples = [.015 * (.55 * value + .3 * amplitude[max(0, index - 1)] +
                       .12 * amplitude[max(0, index - 2)])
               for index, value in enumerate(amplitude)]
    score = score_split(samples[:512], labels[:512])
    assert score['selection_SER'] == 0
    assert score['split']['fit_input_symbols'] == 256
    assert score['split']['guard_symbols'] == 16
    assert score['selection_symbol_count'] == 224
    frozen = freeze_detectors(samples[:512], labels[:512], .1)
    before = canonical_hash(frozen)
    first = evaluate_frozen(samples[512:], labels[512:], frozen)
    changed_labels = [(value + 1) % 4 for value in labels[512:]]
    changed = evaluate_frozen(samples[512:], changed_labels, frozen)
    assert canonical_hash(frozen) == before
    assert first['raw_held_FFE_before_ADC']['symbol_errors'] == 0
    assert changed['raw_held_FFE_before_ADC']['symbol_errors'] > 100
    a = validation_sequence(512, VALIDATION_DATA_SEEDS[0])
    b = validation_sequence(512, VALIDATION_DATA_SEEDS[1])
    prefix_length = integration.WARMUP + 512
    assert a[:prefix_length] == b[:prefix_length] == training_sequence(512)[:prefix_length]
    assert a[prefix_length:] != b[prefix_length:]
    close = integration.T0 + (integration.WARMUP + .856) * integration.UI
    aperture = measured_aperture_phase([(integration.WARMUP, 0.0, close + 1.5e-12, close, 0)])
    assert math.isclose(aperture['phase_UI'], .856, abs_tol=1e-10)

    def mock_run(role, data_seed, noise_seed, errors):
        path = {'sample_count': 100, 'symbol_errors': errors, 'SER': errors / 100,
                'bit_count': 200, 'gray_bit_errors': errors}
        return {'role': role, 'final_data_seed': data_seed, 'noise_seed': noise_seed,
                'AFE_and_sampler_VDD_power_W': .01,
                'metrics': {'raw_held_FFE_before_ADC': path, 'ideal7bit_ADC_then_FFE': path,
                            'ADC_validation_input_clipped_count': 0,
                            'ADC_fullscale_differential_Vpp': .1}}

    paired = [mock_run('baseline', 1, 11, 10), mock_run('optimized', 1, 11, 5)]
    incomplete = aggregate_validation(paired + [mock_run('baseline', 2, 29, 90)])
    assert incomplete['matched_pair_count'] == 1 and incomplete['unmatched_run_count'] == 1
    assert incomplete['unmatched_run_count_by_role'] == {'baseline': 1, 'optimized': 0}
    assert incomplete['comparison_status'] == 'partial_matched_pairs_only'
    assert incomplete['designs']['baseline']['run_count'] == incomplete['designs']['optimized']['run_count'] == 1
    assert incomplete['designs']['baseline']['paths']['raw_held_FFE_before_ADC']['observed_SER'] == .1
    assert aggregate_validation(paired[:1])['designs'] == {}
    complete_runs = [mock_run(role, data_seed, noise_seed, 10 if role == 'baseline' else 5)
                     for role in ['baseline', 'optimized'] for data_seed in [1, 2] for noise_seed in [11, 29]]
    assert aggregate_validation(complete_runs)['comparison_status'] == 'complete_matched_pairs'
    json.dumps([score, first, changed], allow_nan=False)
    return {'status': 'passed', 'checks': ['256fit/16guard/240selection split with224 complete selection windows',
            'knownISI corrected by fixed17tapFFE', 'final labels cannot change frozen coefficients',
            'same training prefix and independent final sequences',
            'clock delay offset distinguished from measured aperture phase',
            'headline pools exclude unmatched seed-pair runs', 'strictJSON']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--screen', action='store_true')
    actions.add_argument('--validate', action='store_true')
    actions.add_argument('--self-check', action='store_true')
    parser.add_argument('--project', type=Path, default=integration.PROJECT)
    parser.add_argument('--candidates', type=Path, help='ACshortlist JSON,defaultresults/ctle_ac_optimization.json')
    parser.add_argument('--candidate-limit', type=int, default=4, help='number of new candidates,plusoldcontrol;0usesall')
    parser.add_argument('--candidate-id', action='append', default=[])
    parser.add_argument('--train-count', type=int, choices=[512, 1024], default=512)
    parser.add_argument('--phases', type=int, choices=[4, 8], default=4)
    parser.add_argument('--screen-noise-seed', type=int, default=SCREEN_NOISE_SEED)
    parser.add_argument('--final-data-seeds', type=int, nargs=2, default=VALIDATION_DATA_SEEDS,
                        help='predeclare two fresh final data seeds when screening; validate reads frozen choices')
    parser.add_argument('--workers', type=int, choices=[1, 2], default=2)
    arguments = parser.parse_args()
    if arguments.self_check:
        print(json.dumps(self_check(), sort_keys=True))
        return 0
    if arguments.screen:
        path = arguments.candidates or arguments.project / 'results' / 'ctle_ac_optimization.json'
        result = screen(arguments.project, path, arguments.candidate_limit, arguments.candidate_id,
                        arguments.train_count, arguments.phases, arguments.screen_noise_seed, arguments.workers,
                        tuple(arguments.final_data_seeds))
        return 0 if result['status'].startswith('complete') else 1
    result = validate(arguments.project, arguments.workers)
    return 0 if result['status'] == 'complete' else 1


if __name__ == '__main__':
    sys.exit(main())
