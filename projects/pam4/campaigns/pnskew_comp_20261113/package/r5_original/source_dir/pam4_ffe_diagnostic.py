#!/usr/bin/env python3
"""Read-only waveform analysis for a bounded, training-only linear FFE screen.

No Spectre runs, native design changes, or waveform export. The 17 centered taps
represent ideal DSP with eight UI of decision latency. The quantized paths use
fixed100/400mVppd ideal7-bit ADCs; they prove neither physical ADC nor DSP speed or
power. Only derived JSON statistics, fit coefficients, and hashes are saved.
"""

import argparse
import bisect
import hashlib
import json
import math
import random
import sys
from pathlib import Path

import pam4_integration as integration
import pam4_metrics as metrics
import psf_ascii


TAPS = 17
HALF = 8
RIDGE = 1e-3
ADC_FULLSCALES = (.1, .4)
TARGETS = (-3.0, -1.0, 1.0, 3.0)
THRESHOLDS = (-2.0, 0.0, 2.0)


def mean(values):
    return math.fsum(values) / len(values)


def cholesky_solve(matrix, rhs):
    """Solve the small ridge-positive-definite normal equations without NumPy."""
    count = len(rhs)
    lower = [[0.0] * count for unused in range(count)]
    for row in range(count):
        for column in range(row + 1):
            value = matrix[row][column] - math.fsum(
                lower[row][k] * lower[column][k] for k in range(column))
            if row == column:
                if value <= 0 or not math.isfinite(value):
                    raise ValueError('Ridge normal equation is not positive definite')
                lower[row][column] = math.sqrt(value)
            else:
                lower[row][column] = value / lower[column][column]
    forward = []
    for row in range(count):
        forward.append((rhs[row] - math.fsum(lower[row][k] * forward[k]
                                            for k in range(row))) / lower[row][row])
    result = [0.0] * count
    for row in range(count - 1, -1, -1):
        result[row] = (forward[row] - math.fsum(lower[k][row] * result[k]
                                               for k in range(row + 1, count))) / lower[row][row]
    return result


def fit_ffe(training_samples, training_symbols, ridge=RIDGE):
    """Fit using training only; complete17-sample features stay in this slice."""
    samples, symbols = metrics._validate_input(training_samples, training_symbols)
    if len(samples) <= TAPS or set(symbols) != set(range(4)):
        raise ValueError('FFE training needs all four symbols and more than17 samples')
    if not math.isfinite(ridge) or ridge <= 0:
        raise ValueError('ridge must be positive and finite')
    center = mean(samples)
    rms = math.sqrt(mean([(value - center) ** 2 for value in samples]))
    if rms < 1e-20:
        raise ValueError('Input has no usable training variation, including possible ADC level collapse')
    normalized = [(value - center) / rms for value in samples]
    rows = [normalized[index - HALF:index + HALF + 1] + [1.0]
            for index in range(HALF, len(samples) - HALF)]
    targets = [TARGETS[symbol] for symbol in symbols[HALF:len(symbols) - HALF]]
    size = TAPS + 1
    normal = [[0.0] * size for unused in range(size)]
    rhs = [math.fsum(row[column] * target for row, target in zip(rows, targets))
           for column in range(size)]
    for first in range(size):
        for second in range(first + 1):
            value = math.fsum(row[first] * row[second] for row in rows)
            normal[first][second] = value
            normal[second][first] = value
    # Objective: mean((prediction-target)^2) + ridge*sum(tap_weight^2).
    # The intercept is intentionally not regularized.
    for index in range(TAPS):
        normal[index][index] += ridge * len(rows)
    coefficients = cholesky_solve(normal, rhs)
    residual = [math.fsum(a * w for a, w in zip(row, coefficients)) - target
                for row, target in zip(rows, targets)]
    solve_residual = [math.fsum(a * w for a, w in zip(row, coefficients)) - target
                      for row, target in zip(normal, rhs)]
    rhs_norm = math.sqrt(math.fsum(value * value for value in rhs))
    return {'tap_count': TAPS, 'tap_offsets_UI': list(range(-HALF, HALF + 1)),
            'decision_latency_UI': HALF, 'decision_latency_s': HALF * integration.UI,
            'training_input_sample_count': len(samples),
            'training_complete_window_count': len(rows),
            'normalization_training_mean_V': center,
            'normalization_training_centered_RMS_V': rms,
            'weights_on_normalized_input': coefficients[:TAPS],
            'bias_in_target_symbol_units': coefficients[-1],
            'equivalent_weights_per_input_V': [weight / rms for weight in coefficients[:TAPS]],
            'equivalent_intercept_in_target_symbol_units': coefficients[-1] -
                math.fsum(coefficients[:TAPS]) * center / rms,
            'ridge_lambda': ridge,
            'ridge_selection': 'fixed a priori, no search or validation tuning',
            'objective': 'mean squared target-amplitude error pluslambda*sum(normalized-input tap weights squared); unregularized bias',
            'training_MSE_in_target_symbol_units_squared': mean([value * value for value in residual]),
            'normal_equation_relative_residual': math.sqrt(math.fsum(value * value for value in solve_residual)) /
                max(rhs_norm, 1e-30)}


def predict_window(samples, fit):
    """Only emit outputs whose full17-sample features lie inside this slice."""
    center = fit['normalization_training_mean_V']
    rms = fit['normalization_training_centered_RMS_V']
    normalized = [(float(value) - center) / rms for value in samples]
    weights = fit['weights_on_normalized_input']
    bias = fit['bias_in_target_symbol_units']
    return [bias + math.fsum(weight * value for weight, value in
                             zip(weights, normalized[index - HALF:index + HALF + 1]))
            for index in range(HALF, len(samples) - HALF)]


def prediction_metrics(predictions, symbols):
    if len(predictions) != len(symbols) or not predictions:
        raise ValueError('Predictions and labels must have equal nonzero lengths')
    decisions = [bisect.bisect_right(THRESHOLDS, prediction) for prediction in predictions]
    symbol_errors = sum(prediction != symbol for prediction, symbol in zip(decisions, symbols))
    gray_bit_errors = 0
    confusion = [[0] * 4 for unused in range(4)]
    for decision, symbol in zip(decisions, symbols):
        difference = metrics.GRAY_CODES[decision] ^ metrics.GRAY_CODES[symbol]
        gray_bit_errors += (difference & 1) + ((difference >> 1) & 1)
        confusion[symbol][decision] += 1
    errors = [prediction - TARGETS[symbol] for prediction, symbol in zip(predictions, symbols)]
    target_rms = math.sqrt(mean([TARGETS[symbol] ** 2 for symbol in symbols]))
    rmse = math.sqrt(mean([error * error for error in errors]))
    classes = []
    for symbol in range(4):
        values = [prediction for prediction, label in zip(predictions, symbols) if label == symbol]
        if not values:
            classes.append({'symbol': symbol, 'count': 0, 'mean': None, 'std': None,
                            'min': None, 'max': None, 'p05': None, 'p95': None})
            continue
        average = mean(values)
        classes.append({'symbol': symbol, 'count': len(values), 'mean': average,
                        'std': math.sqrt(mean([(value - average) ** 2 for value in values])),
                        'min': min(values), 'max': max(values),
                        'p05': metrics._percentile(values, .05),
                        'p95': metrics._percentile(values, .95)})
    count = len(predictions)
    return {'sample_count': count, 'symbol_errors': symbol_errors,
            'SER': symbol_errors / count, 'gray_bit_errors': gray_bit_errors,
            'bit_count': 2 * count, 'gray_BER': gray_bit_errors / (2 * count),
            'zero_error_SER_95pct_upper_if_independent_symbols':
                -math.expm1(math.log(.05) / count) if symbol_errors == 0 else None,
            'SER_bound_note': 'Conditional zero-error binomial bound assuming independent symbol errors; FFE output errors can be correlated.',
            'BER_note': 'Observed Gray-bit error fraction; no independent-bit confidence bound.',
            'decision_thresholds_in_target_symbol_units': list(THRESHOLDS),
            'target_amplitudes_for_symbols_0_through_3': list(TARGETS),
            'prediction_units': 'dimensionless target PAM4 amplitude units, not volts',
            'prediction_RMSE_in_target_symbol_units': rmse,
            'prediction_EVM_RMS_percent_of_target_RMS': 100.0 * rmse / target_rms,
            'confusion_rows_true_cols_decided': confusion,
            'class_predictions_in_target_symbol_units': classes,
            'empirical_eye_gaps_in_target_symbol_units': [
                classes[index + 1]['min'] - classes[index]['max']
                if classes[index + 1]['count'] and classes[index]['count'] else None
                for index in range(3)],
            'p05_p95_eye_gaps_in_target_symbol_units': [
                classes[index + 1]['p05'] - classes[index]['p95']
                if classes[index + 1]['count'] and classes[index]['count'] else None
                for index in range(3)]}


def diagnose_path(samples, symbols, train_count=512, validation_count=2048,
                  fullscale=None, baseline_fit=None):
    """Fit training-only weights, then score untouched validation with fixed thresholds."""
    if len(samples) < train_count + validation_count or len(symbols) < train_count + validation_count:
        raise ValueError('Not enough aligned samples for diagnostic windows')
    training_samples = list(samples[:train_count])
    training_symbols = list(symbols[:train_count])
    validation_samples = list(samples[train_count:train_count + validation_count])
    validation_symbols = list(symbols[train_count:train_count + validation_count])
    clipping = None
    if fullscale is not None:
        training_samples, training_clipped = metrics.quantize_symmetric(training_samples, fullscale, 7)
        validation_samples, validation_clipped = metrics.quantize_symmetric(validation_samples, fullscale, 7)
        clipping = {'bits': 7, 'fullscale_differential_Vpp': fullscale,
                    'LSB_V': fullscale / 128, 'input_center_V': 0,
                    'training_clipped_count': training_clipped,
                    'training_input_count': train_count,
                    'validation_clipped_count': validation_clipped,
                    'validation_input_count': validation_count,
                    'validation_clipped_fraction': validation_clipped / validation_count,
                    'fullscale_selection': 'fixed diagnostic range, both100and400mVppd reported; no validation-driven range selection',
                    'physical_scope': 'ideal7-bit quantization only; no additional ADC noise, physical load, kickback, latency, power or speed claim'}
    fit = fit_ffe(training_samples, training_symbols)
    train_predictions = predict_window(training_samples, fit)
    validation_predictions = predict_window(validation_samples, fit)
    train_targets = training_symbols[HALF:train_count - HALF]
    validation_targets = validation_symbols[HALF:validation_count - HALF]
    if baseline_fit is None:
        baseline_fit = metrics.fit_training(training_samples, training_symbols)
        threshold_source = 'diagnostic training slice only'
    else:
        threshold_source = 'original short-calibration detector frozen by PAM4 integration'
    baseline = metrics._validation_metrics(validation_samples[HALF:validation_count - HALF],
                                            validation_targets, baseline_fit)
    return {'path': 'raw_held_samples' if fullscale is None else 'ideal7bit_ADC_%gmVppd_before_FFE' % (fullscale * 1000),
            'input_representation': 'differential held volts',
            'quantizer': clipping, 'FFE': fit,
            'training_predictions': prediction_metrics(train_predictions, train_targets),
            'validation_predictions': prediction_metrics(validation_predictions, validation_targets),
            'three_threshold_baseline_on_same_validation_centers': baseline,
            'baseline_threshold_source': threshold_source,
            'feature_isolation': 'training and validation are separately windowed; no17tap feature crosses their boundary',
            'excluded_validation_symbols_at_each_edge': HALF,
            'validation_complete_window_count': len(validation_predictions),
            'scope': 'ideal linear DSP feasibility diagnostic; phase and lag inherited unchanged; fixed symbol-unit thresholds[-2,0,2]'}


def analyze_record(project, record, train_count, validation_count):
    run_name = record['run_name']
    # run_name originates in our own integration summary. Keep analysis inside
    # its assigned project simulation directory even if a file is edited.
    base = (project / 'simulations' / 'pam4_integration').resolve()
    directory = (base / run_name).resolve()
    if directory.parent != base:
        raise ValueError('Unexpected run path outside PAM4 integration directory')
    raw_path = integration._raw_file(directory)
    psf = psf_ascii.parse_file(raw_path)
    if psf.sha256 != record['raw_transient_sha256']:
        raise ValueError('Existing waveform hash disagrees with original integration summary')
    reference_delay = record.get('clock_audit', {}).get('reference_common_delay_s', 0.0)
    held, clock_audit = integration.held_records(psf, reference_delay)
    symbols = integration.symbol_sequence(integration.WARMUP + train_count + validation_count + integration.GUARD)
    selection = record['selection']
    samples, labels, unused_times = integration.aligned_window(
        held, symbols, selection['integer_symbol_lag'], train_count, validation_count)
    raw_fit = selection['frozen_detectors']['raw']
    path_inputs = [(None, raw_fit)]
    for fullscale in ADC_FULLSCALES:
        adc_candidates = [adc for adc in selection['frozen_detectors']['ADC']
                          if math.isclose(adc['fullscale_differential_Vpp'], fullscale, rel_tol=1e-12)]
        if len(adc_candidates) != 1:
            raise ValueError('Original calibration lacks exactly one requested fullscale ADC detector')
        path_inputs.append((fullscale, adc_candidates[0]['fit']))
    paths = []
    for fullscale, detector in path_inputs:
        try:
            paths.append(diagnose_path(samples, labels, train_count, validation_count,
                                       fullscale, detector))
        except ValueError as error:
            paths.append({'path': 'raw_held_samples' if fullscale is None else 'ideal7bit_ADC_%gmVppd_before_FFE' % (fullscale * 1000),
                          'status': 'unusable_input_or_fit_failure', 'error': str(error)})
    return {'run_name': run_name, 'scenario': record['scenario'],
            'loss_dB_at_56GHz': record['loss_dB_at_56GHz'],
            'transient_noise_enabled': record.get('transient_noise_enabled', False),
            'waveform_sha256_matches_original_summary': True,
            'raw_transient_sha256': psf.sha256,
            'inherited_phase_UI': record['phase_UI'],
            'inherited_integer_symbol_lag': selection['integer_symbol_lag'],
            'phase_lag_scope': 'selected by prior three-threshold training score; not reoptimized for FFE',
            'FFE_training_source': 'first512 aligned training symbols from this full run; validation never used',
            'validation_symbol_index_range_after_edge_exclusion': [
                integration.WARMUP + train_count + HALF,
                integration.WARMUP + train_count + validation_count - HALF - 1],
            'clock_audit': clock_audit, 'paths': paths}


def self_check():
    generator = random.Random(9926)
    symbols = [generator.randrange(4) for unused in range(512 + 2048)]
    amplitudes = [TARGETS[symbol] for symbol in symbols]
    # Known causal linear ISI, with distinct eye overlap but an invertible
    # short channel. The first two edge terms stay within the training slice.
    samples = [.015 * (.55 * amplitudes[index] +
                       .30 * amplitudes[max(0, index - 1)] +
                       .12 * amplitudes[max(0, index - 2)])
               for index in range(len(symbols))]
    first = diagnose_path(samples, symbols)
    baseline_errors = first['three_threshold_baseline_on_same_validation_centers']['symbol_errors']
    equalized_errors = first['validation_predictions']['symbol_errors']
    assert baseline_errors > 100
    assert equalized_errors == 0
    changed_labels = symbols[:512] + [(symbol + 1) % 4 for symbol in symbols[512:]]
    changed = diagnose_path(samples, changed_labels)
    assert first['FFE'] == changed['FFE']
    assert changed['validation_predictions']['symbol_errors'] > equalized_errors
    assert first['validation_complete_window_count'] == 2032
    assert first['FFE']['normal_equation_relative_residual'] < 1e-10
    quantized = diagnose_path(samples, symbols, fullscale=ADC_FULLSCALES[0])
    assert quantized['validation_predictions']['symbol_errors'] < baseline_errors
    json.dumps([first, changed, quantized], allow_nan=False)
    return {'status': 'passed', 'checks': ['known linear ISI substantially improved',
            'FFE weights unchanged when validation labels change',
            '2032 independently windowed validation outputs',
            'small normal-equation residual', 'fixed7bit input path', 'strictJSON'],
            'known_ISI_baseline_errors': baseline_errors,
            'known_ISI_FFE_errors': equalized_errors}


def run(project=integration.PROJECT):
    psf_ascii.MAX_FILE_BYTES = 256 * 1024 * 1024
    source = project / 'results' / 'pam4_integration_summary.json'
    source_bytes = source.read_bytes()
    summary = json.loads(source_bytes.decode('utf-8'))
    if summary.get('smoke_test'):
        raise ValueError('Diagnostic requires full integration results, not the smoke summary')
    train_count = summary.get('conditions', {}).get('training_symbols', 512)
    validation_count = summary.get('conditions', {}).get('validation_symbols', 2048)
    if (train_count, validation_count) != (512, 2048):
        raise ValueError('This bounded diagnostic expects512 training and2048 validation symbols')
    records = list(summary.get('validation', [])) + list(summary.get('noise_validation', []))
    result = {'schema_version': 1, 'status': 'running',
              'source_summary_sha256': hashlib.sha256(source_bytes).hexdigest(),
              'source_integration_status': summary.get('status'),
              'scope': '17tap ideal linear FFE feasibility diagnostic on existing actual MOS held samples; no new simulations',
              'settings': {'tap_count': TAPS, 'centered_taps_each_side': HALF,
                           'decision_latency_UI': HALF, 'fixed_ridge_lambda': RIDGE,
                           'ADC_bits': 7, 'ADC_fullscales_differential_Vpp': list(ADC_FULLSCALES),
                           'training_symbols': train_count,
                           'validation_input_symbols': validation_count,
                           'validation_complete_windows': validation_count - 2 * HALF,
                           'thresholds_target_symbol_units': list(THRESHOLDS)},
              'self_check': self_check(), 'results': [], 'errors': [],
              'limitations': [
                  'Ideal DSP arithmetic and ideal quantizer; no transistor ADC or DSP timing/power claim.',
                  'Phase and integer lag inherited from three-threshold calibration, not reoptimized for FFE.',
                  'One fixed17tap length and ridge1e-3; failure is not a proof all equalizers or architectures fail.',
                  'Training mean/RMS, weights and bias use only512 training samples; fixed output thresholds[-2,0,2].',
                  'Validation excludes8 symbols at each end and never contributes features to training.',
                  'Synthetic channel and ideal clocks retain the original integration limitations.',
                  'FFE output error correlation limits the meaning of conditional finite-sample binomial bounds.']}
    destination = project / 'results' / 'pam4_ffe_diagnostic.json'
    integration.atomic_json(destination, result)
    for record in records:
        try:
            analysis = analyze_record(project, record, train_count, validation_count)
            result['results'].append(analysis)
            print(json.dumps({'event': 'FFE_diagnostic_complete', 'run_name': record['run_name'],
                              'paths': [{'path': path['path'], 'SER': path.get('validation_predictions', {}).get('SER'),
                                         'status': path.get('status', 'complete')}
                                        for path in analysis['paths']]}), flush=True)
        except Exception as error:
            result['errors'].append({'run_name': record.get('run_name'), 'error': repr(error)})
            print(json.dumps({'event': 'FFE_diagnostic_error', 'run_name': record.get('run_name'),
                              'error': repr(error)}), flush=True)
        integration.atomic_json(destination, result)
    completed_names = sorted(record.get('scenario') for record in summary.get('validation', []))
    expected = ['bypass', 'synthetic_10dB', 'synthetic_20dB']
    result['all_three_main_scenarios_present'] = completed_names == expected
    result['noise_case_count'] = len(summary.get('noise_validation', []))
    result['status'] = ('complete' if result['all_three_main_scenarios_present'] and not result['errors']
                        and summary.get('status') in ('complete', 'complete_with_errors') else 'partial_or_errors')
    result['script_sha256'] = integration.file_hash(Path(__file__))
    integration.atomic_json(destination, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=integration.PROJECT)
    parser.add_argument('--self-check', action='store_true')
    arguments = parser.parse_args()
    if arguments.self_check:
        print(json.dumps(self_check(), sort_keys=True))
        return 0
    result = run(arguments.project)
    return 0 if result['status'] == 'complete' else 1


if __name__ == '__main__':
    sys.exit(main())
