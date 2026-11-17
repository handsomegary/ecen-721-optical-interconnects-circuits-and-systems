#!/usr/bin/env python3
"""Dependency-free PAM4 held-sample metrics (Python 3.6 or later).

Samples must already be aligned one-to-one with transmitted symbols. Training
sets polarity and thresholds; validation never changes either. The optional
ADC is a symmetric ideal quantizer, not a transistor ADC: it adds no physical
input load, comparator noise, kickback, latency, or power.
"""

import bisect
import json
import math


GRAY_CODES = (0, 1, 3, 2)


def _mean(values):
    return math.fsum(values) / len(values)


def _percentile(values, probability):
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _level_stats(values, symbols):
    result = []
    for level in range(4):
        group = [value for value, symbol in zip(values, symbols)
                 if symbol == level]
        if not group:
            result.append({'symbol': level, 'gray_code': GRAY_CODES[level],
                           'count': 0, 'mean_V': None, 'std_V': None,
                           'min_V': None, 'max_V': None,
                           'p05_V': None, 'p95_V': None})
            continue
        average = _mean(group)
        # Population standard deviation of the observed samples, not an
        # inferred thermal-noise standard deviation (ISI is included).
        variance = math.fsum((value - average) ** 2 for value in group) / len(group)
        result.append({'symbol': level, 'gray_code': GRAY_CODES[level],
                       'count': len(group), 'mean_V': average,
                       'std_V': math.sqrt(variance), 'min_V': min(group),
                       'max_V': max(group), 'p05_V': _percentile(group, .05),
                       'p95_V': _percentile(group, .95)})
    return result


def _eye_gaps(levels, low_key, high_key):
    return [(levels[level + 1][low_key] - levels[level][high_key])
            if levels[level + 1]['count'] and levels[level]['count'] else None
            for level in range(3)]


def _decide(value, thresholds):
    return bisect.bisect_right(thresholds, value)


def _validate_input(samples, symbols):
    if len(samples) != len(symbols):
        raise ValueError('samples and symbols must have equal lengths')
    values = [float(value) for value in samples]
    if any(not math.isfinite(value) for value in values):
        raise ValueError('samples must all be finite')
    labels = []
    for symbol in symbols:
        integer = int(symbol)
        if integer != symbol or integer not in range(4):
            raise ValueError('symbols must be integers 0, 1, 2, or 3')
        labels.append(integer)
    return values, labels


def fit_training(samples, symbols):
    """Return a JSON-serializable detector fitted to this training slice only.

    A larger quality_score is better for phase search. It combines the worst
    normalized 5/95-percentile eye gap with a four-times symbol-error penalty.
    It is a comparative engineering score, not a course specification.
    """
    values, labels = _validate_input(samples, symbols)
    if not values or set(labels) != set(range(4)):
        raise ValueError('training must contain all four PAM4 symbols')
    raw_levels = _level_stats(values, labels)
    # Equal class weighting prevents an imbalanced training sequence from
    # choosing a polarity merely because one symbol is more frequent.
    covariance = math.fsum((level - 1.5) * raw_levels[level]['mean_V']
                           for level in range(4))
    polarity = 1 if covariance >= 0 else -1
    oriented = [polarity * value for value in values]
    levels = _level_stats(oriented, labels)
    means = [level['mean_V'] for level in levels]
    thresholds = [(means[level] + means[level + 1]) / 2.0
                  for level in range(3)]
    ordered = all(means[level + 1] > means[level] for level in range(3))
    # Failed class ordering is explicitly marked. Sorting thresholds gives a
    # deterministic diagnostic slicer without silently re-labelling classes.
    decision_thresholds = sorted(thresholds)
    errors = sum(_decide(value, decision_thresholds) != symbol
                 for value, symbol in zip(oriented, labels))
    robust_gaps = _eye_gaps(levels, 'p05_V', 'p95_V')
    span = max(means) - min(means)
    score = (min(robust_gaps) / span if span > 0 else -1.0) - 4.0 * errors / len(values)
    if not ordered:
        score -= 1.0
    return {'sample_count': len(values), 'polarity': polarity,
            'thresholds_V': decision_thresholds,
            'unreordered_midpoint_thresholds_V': thresholds,
            'class_means_strictly_ordered': ordered,
            'levels_in_polarity_corrected_V': levels,
            'empirical_eye_gaps_V': _eye_gaps(levels, 'min_V', 'max_V'),
            'p05_p95_eye_gaps_V': robust_gaps,
            'symbol_errors': errors, 'SER': errors / len(values),
            'quality_score': score,
            'quality_score_definition':
                'min(p05_next-p95_previous)/class_mean_span - 4*training_SER; '
                'minus1 if class means not strictly ordered; larger is better'}


def training_quality_score(samples, symbols):
    """Convenient scalar for phase search; inputs must be training only."""
    return fit_training(samples, symbols)['quality_score']


def _validation_metrics(values, symbols, fit):
    oriented = [fit['polarity'] * value for value in values]
    predictions = [_decide(value, fit['thresholds_V']) for value in oriented]
    symbol_errors = sum(guess != truth for guess, truth in zip(predictions, symbols))
    bit_errors = 0
    confusion = [[0 for unused in range(4)] for unused in range(4)]
    for guess, truth in zip(predictions, symbols):
        difference = GRAY_CODES[guess] ^ GRAY_CODES[truth]
        bit_errors += (difference & 1) + ((difference >> 1) & 1)
        confusion[truth][guess] += 1
    count = len(values)
    levels = _level_stats(oriented, symbols)
    zero_upper = -math.expm1(math.log(.05) / count) if symbol_errors == 0 else None
    return {'sample_count': count, 'bit_count': 2 * count,
            'symbol_errors': symbol_errors, 'SER': symbol_errors / count,
            'gray_bit_errors': bit_errors, 'gray_BER': bit_errors / (2 * count),
            'zero_error_SER_95pct_upper_if_independent_symbols': zero_upper,
            'SER_bound_note':
                'Exact one-sided zero-error binomial bound assuming independent '
                'symbol errors; finite correlated samples do not establish a target BER.',
            'BER_note': 'Observed Gray-bit error fraction only; no independent-bit '
                        'confidence bound is assigned to the paired bits.',
            'confusion_rows_true_cols_decided': confusion,
            'levels_in_polarity_corrected_V': levels,
            'empirical_eye_gaps_V': _eye_gaps(levels, 'min_V', 'max_V'),
            'p05_p95_eye_gaps_V': _eye_gaps(levels, 'p05_V', 'p95_V'),
            'sample_min_V': min(values), 'sample_max_V': max(values),
            'observed_peak_to_peak_V': max(values) - min(values),
            'detector_training_class_order_valid': fit['class_means_strictly_ordered']}


def quantize_symmetric(samples, fullscale, bits=7):
    """Return reconstructed midrise samples and a clipping count.

    fullscale is total differential Vpp, centered at zero. End points are
    accepted; values outside [-fullscale/2, +fullscale/2] count as clipped.
    """
    fullscale = float(fullscale)
    if not math.isfinite(fullscale) or fullscale <= 0:
        raise ValueError('fullscale must be positive and finite')
    if not isinstance(bits, int) or isinstance(bits, bool) or bits < 1 or bits > 24:
        raise ValueError('bits must be an integer from 1 through 24')
    count = 1 << bits
    step = fullscale / count
    half = fullscale / 2.0
    result = []
    clipped = 0
    for sample in samples:
        value = float(sample)
        if not math.isfinite(value):
            raise ValueError('samples must all be finite')
        clipped += value < -half or value > half
        code = max(0, min(count - 1, int(math.floor((value + half) / step))))
        result.append(-half + (code + .5) * step)
    return result, clipped


def evaluate_samples(samples, symbols, train_count=512, validation_count=2048,
                     adc_fullscales=(.05, .1, .2, .4), bits=7):
    """Evaluate aligned held samples and return derived statistics only.

    The first train_count samples train the detector; the next validation_count
    samples validate it. Extra samples are explicitly ignored. Quantizer ranges
    are fixed arguments, not adapted using validation data.
    """
    for name, count in [('train_count', train_count), ('validation_count', validation_count)]:
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError(name + ' must be a positive integer')
    values, labels = _validate_input(samples, symbols)
    needed = train_count + validation_count
    if len(values) < needed:
        raise ValueError('not enough samples for the requested training and validation windows')
    training = values[:train_count]
    train_labels = labels[:train_count]
    validation = values[train_count:needed]
    validation_labels = labels[train_count:needed]
    raw_fit = fit_training(training, train_labels)
    result = {'schema_version': 1, 'alignment': 'caller-provided; one held sample per symbol',
              'gray_codes_for_ascending_symbols': list(GRAY_CODES),
              'train_count': train_count, 'validation_count': validation_count,
              'ignored_trailing_sample_count': len(values) - needed,
              'raw': {'training': raw_fit,
                      'validation': _validation_metrics(validation, validation_labels, raw_fit)},
              'behavioral_ADC': []}
    for fullscale in adc_fullscales:
        quant_train, clipped_train = quantize_symmetric(training, fullscale, bits)
        quant_validation, clipped_validation = quantize_symmetric(validation, fullscale, bits)
        quant_fit = fit_training(quant_train, train_labels)
        result['behavioral_ADC'].append({
            'bits': bits, 'fullscale_differential_Vpp': float(fullscale),
            'LSB_V': float(fullscale) / (1 << bits),
            'input_center_V': 0.0, 'reconstruction': 'uniform midrise, saturating',
            'training_clipped_count': clipped_train,
            'validation_clipped_count': clipped_validation,
            'validation_clipped_fraction': clipped_validation / validation_count,
            'training': quant_fit,
            'validation': _validation_metrics(quant_validation, validation_labels, quant_fit),
            'physical_scope': 'behavioral quantization only; no added physical input load, '
                              'comparator noise, kickback, mismatch, latency, or ADC power'})
    return result


def self_check():
    labels = [0, 1, 2, 3] * 24
    amplitudes = (-.03, -.01, .01, .03)
    samples = [amplitudes[label] for label in labels]
    plain = evaluate_samples(samples, labels, 32, 64, (.1,))
    assert plain['raw']['validation']['symbol_errors'] == 0
    assert plain['behavioral_ADC'][0]['validation']['symbol_errors'] == 0
    inverted = evaluate_samples([-value for value in samples], labels, 32, 64, (.1,))
    assert inverted['raw']['training']['polarity'] == -1
    assert inverted['raw']['validation']['gray_bit_errors'] == 0
    clipped = evaluate_samples(samples, labels, 32, 64, (.02,))
    assert clipped['behavioral_ADC'][0]['validation_clipped_count'] == 32
    assert clipped['behavioral_ADC'][0]['validation']['symbol_errors'] > 0
    shifted = samples[:32] + [value + .08 for value in samples[32:]]
    contaminated = evaluate_samples(shifted, labels, 32, 64, (.1,))
    assert contaminated['raw']['training'] == plain['raw']['training']
    assert contaminated['behavioral_ADC'][0]['training'] == plain['behavioral_ADC'][0]['training']
    assert contaminated['raw']['validation']['symbol_errors'] > 0
    assert math.isclose(plain['raw']['validation']['zero_error_SER_95pct_upper_if_independent_symbols'],
                        1 - .05 ** (1.0 / 64), rel_tol=1e-12)
    json.dumps(contaminated, allow_nan=False)
    return {'self_check': 'passed', 'checks': ['identity recovery', 'polarity inversion',
            'clipping detection and loss of levels', 'training-only threshold fit',
            'zero-error conditional bound', 'strict JSON serialization']}


if __name__ == '__main__':
    print(json.dumps(self_check(), sort_keys=True))
