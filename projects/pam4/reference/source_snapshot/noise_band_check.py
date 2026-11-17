#!/usr/bin/env python3
"""Frozen 150-versus-300 GHz noise-band sensitivity diagnostic (Python 3.6).

Default: verify a completed final validation and generate two owned decks only.
--run: execute baseline/winner serially and apply their existing frozen fits.
This repeats one inspected data/noise pair; it is not another fresh holdout.
"""

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import optimize_pam4 as optimization
import pam4_integration as integration
import psf_ascii


NOISE_SEED = 11
NOISE_MAX_HZ = 300e9
PATHS = ('raw_held_FFE_before_ADC', 'ideal7bit_ADC_then_FFE')


def deck_hash(deck):
    return hashlib.sha256(('\n'.join(deck) + '\n').encode('utf-8')).hexdigest()


def widen_noise_band(deck):
    """Change precisely one noisefmax token; retain all solver/sample options."""
    changed = list(deck)
    indices = [index for index, line in enumerate(deck)
               if line.startswith('tranResponse ')]
    if len(indices) != 1:
        raise ValueError('Expected exactly one transient analysis')
    index = indices[0]
    line = deck[index]
    for parameter, expected in [('maxstep', 200e-15), ('noisefmax', 150e9),
                                ('noisefmin', 500e6), ('noiseseed', NOISE_SEED)]:
        found = re.findall(r'\b' + parameter + r'=([^\s]+)', line)
        if len(found) != 1 or not math.isclose(integration._spectre_number(found[0]),
                                              expected, rel_tol=1e-12):
            raise ValueError('Unexpected existing transient ' + parameter)
    changed[index], count = re.subn(r'\bnoisefmax=150G\b', 'noisefmax=300G', line)
    if count != 1:
        raise ValueError('Noise-band substitution was not unique')
    if changed[index].replace('noisefmax=300G', 'noisefmax=150G') != line:
        raise ValueError('An option besides noisefmax changed')
    return changed


def compact(record):
    measured = record['metrics']
    return {'paths': {name: {key: measured[name][key] for key in
                            ['sample_count', 'symbol_errors', 'SER', 'gray_bit_errors',
                             'gray_BER', 'prediction_RMSE_in_target_symbol_units',
                             'prediction_EVM_RMS_percent_of_target_RMS']}
                       for name in PATHS},
            'ADC_fullscale_differential_Vpp': measured['ADC_fullscale_differential_Vpp'],
            'ADC_input_clipped_count': measured['ADC_validation_input_clipped_count'],
            'ADC_input_count': measured['ADC_validation_input_count'],
            'held_min_V': record['validation_held_min_V'],
            'held_max_V': record['validation_held_max_V'],
            'held_Vppd': record['validation_held_Vppd'],
            'AFE_and_sampler_VDD_power_W': record['AFE_and_sampler_VDD_power_W']}


def evaluate(project, item, frozen, frozen_hash, symbols):
    directory, status, fingerprint, cached = integration.execute_deck(
        project, item['run_name'], item['deck'])
    if fingerprint != item['netlist_300G_sha256']:
        raise ValueError('Executed deck does not match generated deck')
    parsed = psf_ascii.parse_file(integration._raw_file(directory))
    held, clock_audit = integration.held_records(parsed)
    if clock_audit['saved_last_time_s'] < item['stop_s'] - integration.UI / 16 * 1.01:
        raise ValueError('Saved data does not cover requested transient')
    design = item['design']
    record = design['record']
    selection = record['selection']
    train_count = frozen['training_symbol_count']
    samples, labels, held_times = integration.aligned_window(
        held, symbols, selection['integer_symbol_lag'], train_count,
        optimization.FINAL_SYMBOLS)
    values = samples[train_count:]
    labels = labels[train_count:]
    if len(values) != optimization.FINAL_SYMBOLS:
        raise ValueError('Expected exactly2048 aligned diagnostic held samples')
    detectors_before = optimization.canonical_hash(selection['frozen_detectors'])
    measured = optimization.evaluate_frozen(values, labels, selection['frozen_detectors'])
    if optimization.canonical_hash(selection['frozen_detectors']) != detectors_before:
        raise ValueError('Frozen detectors changed during diagnostic evaluation')
    times = parsed.values[parsed.sweep_names[0]]
    result = {'role': design['role'], 'candidate_id': record['candidate_id'],
              'run_name': item['run_name'], 'data_seed': item['data_seed'],
              'noise_seed': NOISE_SEED, 'noise_max_Hz': NOISE_MAX_HZ,
              'maxstep_s': 200e-15, 'noise_flattened_below_Hz': 500e6,
              'frozen_choices_sha256': frozen_hash,
              'frozen_detector_sha256': detectors_before,
              'netlist_sha256': fingerprint, 'raw_transient_sha256': parsed.sha256,
              'run_status': status, 'cached_identical_deck': cached,
              'clock_audit': clock_audit,
              'measured_aperture': optimization.measured_aperture_phase(held),
              'metrics': measured, 'validation_held_min_V': min(values),
              'validation_held_max_V': max(values),
              'validation_held_Vppd': max(values) - min(values),
              'AFE_and_sampler_VDD_power_W': -record['config'].get('vdd', .9) *
              integration.dynamic.mean_time(times, parsed.values['XVs:p'],
                                            held_times[train_count], held_times[-1] + integration.UI),
              'validation_fitting_performed': False}
    # Keep the derived report compact; raw waveforms remain in their run folder.
    return {key: value for key, value in result.items() if key not in
            ['metrics', 'validation_held_min_V', 'validation_held_max_V',
             'validation_held_Vppd', 'AFE_and_sampler_VDD_power_W']}, compact(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=integration.PROJECT)
    parser.add_argument('--data-seed', type=int,
                        help='one existing final data seed; default first frozen seed')
    parser.add_argument('--run', action='store_true', help='execute two diagnostic runs serially')
    args = parser.parse_args()
    project = args.project
    frozen_path = project / 'configs' / 'pam4_optimization_frozen.json'
    validation_path = project / 'results' / 'pam4_optimization_validation.json'
    cards_path = project / 'configs' / 'native_device_cards.json'
    frozen, frozen_hash = optimization.read_json_snapshot(frozen_path)
    validation, validation_hash = optimization.read_json_snapshot(validation_path)
    cards_hash = integration.file_hash(cards_path)
    if validation.get('status') != 'complete' or validation.get('frozen_choices_sha256') != frozen_hash:
        raise ValueError('Requires completed final validation of exactly these frozen choices')
    comparison = validation.get('comparison', {})
    if comparison.get('comparison_status') != 'complete_matched_pairs' or comparison.get('matched_pair_count') != 4:
        raise ValueError('Requires all four completed baseline/winner final seed pairs')
    if cards_hash != frozen['native_cards_sha256']:
        raise ValueError('Native cards changed after training')
    if sorted(design['role'] for design in frozen['designs']) != ['baseline', 'optimized']:
        raise ValueError('Expected exactly baseline and optimized frozen designs')
    if (frozen['training_data_seed'] != optimization.TRAIN_SEED or
            frozen['validation_symbol_count'] != optimization.FINAL_SYMBOLS or
            NOISE_SEED not in frozen['final_noise_seeds']):
        raise ValueError('Frozen sequence conditions differ from the original validation driver')
    data_seed = args.data_seed if args.data_seed is not None else frozen['final_data_seeds'][0]
    if data_seed not in frozen['final_data_seeds']:
        raise ValueError('This diagnostic must reuse an existing final data seed')
    native = integration.install_native_cards(cards_path)
    symbols = optimization.validation_sequence(frozen['training_symbol_count'], data_seed)
    prepared = []
    plans = []
    for design in frozen['designs']:
        record = design['record']
        candidate = optimization.validate_config({'id': record['candidate_id'], 'config': record['config']})
        original = [run for run in validation['runs'] if run['role'] == design['role'] and
                    run['final_data_seed'] == data_seed and run['noise_seed'] == NOISE_SEED]
        if len(original) != 1:
            raise ValueError('Missing unique150GHz reference for ' + design['role'])
        original = original[0]
        if (original.get('frozen_choices_sha256') != frozen_hash or
                original.get('config') != record['config'] or
                original.get('phase_UI') != record['phase_UI'] or
                original.get('integer_symbol_lag') != record['selection']['integer_symbol_lag'] or
                original.get('noise_max_Hz') != 150e9):
            raise ValueError('150GHz reference does not match frozen design conditions')
        deck150, stop = optimization.build_noise_deck(record['config'], symbols, record['phase_UI'], NOISE_SEED)
        if deck_hash(deck150) != original['netlist_sha256']:
            raise ValueError('Regenerated150GHz deck differs from actual reference; driver may have changed')
        deck300 = widen_noise_band(deck150)
        name = 'noise_band_300G_%s_%s_d%d_n%d_%s' % (
            design['role'], candidate['id'], data_seed, NOISE_SEED, frozen_hash[:16])
        directory = project / 'simulations' / 'pam4_integration' / name
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / 'bench.scs'
        contents = '\n'.join(deck300) + '\n'
        if destination.exists() and destination.read_text() != contents:
            raise ValueError('Owned diagnostic directory contains a different deck')
        destination.write_text(contents)
        plan = {'role': design['role'], 'candidate_id': candidate['id'],
                'config': record['config'], 'phase_UI': record['phase_UI'],
                'integer_symbol_lag': record['selection']['integer_symbol_lag'],
                'run_name': name, 'generated_deck_path': str(destination),
                'reference_run_name': original['run_name'],
                'netlist_150G_sha256': original['netlist_sha256'],
                'netlist_300G_sha256': deck_hash(deck300),
                'raw_150G_transient_sha256': original['raw_transient_sha256'],
                'frozen_detector_sha256': optimization.canonical_hash(record['selection']['frozen_detectors']),
                'reference_150G': compact(original)}
        plans.append(plan)
        prepared.append(dict(plan, design=design, deck=deck300, stop_s=stop, data_seed=data_seed))

    def assert_preserved():
        for path, expected in [(frozen_path, frozen_hash), (validation_path, validation_hash),
                               (cards_path, cards_hash)]:
            if integration.file_hash(path) != expected:
                raise ValueError('Protected input changed during diagnostic: ' + str(path))

    assert_preserved()
    report = {'schema_version': 1, 'status': 'decks_generated_not_run',
              'mode': 'postvalidation_noise_band_sensitivity',
              'frozen_choices_sha256': frozen_hash,
              'frozen_choice_identity': optimization.choice_identity(frozen),
              'source_final_validation_sha256': validation_hash, 'native_cards': native,
              'reused_final_data_seed': data_seed, 'noise_seed': NOISE_SEED,
              'noise_max_comparison_Hz': [150e9, NOISE_MAX_HZ], 'maxstep_s': 200e-15,
              'noise_flattened_below_Hz': 500e6, 'expected_new_run_count': 2,
              'plans': plans, 'runs': [], 'errors': [],
              'limits': ['One previously inspected data/noise-seed pair; sensitivity diagnostic, not fresh holdout.',
                         'Changing noisefmax may change the stochastic realization despite retaining noise seed11.',
                         'No selection, normalization change, FIR/threshold refit, or ADC-range adjustment.',
                         '300GHz and200fs are one frequency-band sensitivity point, not convergence or RF-model signoff.',
                         'Synthetic20dB channel, ideal source and clocks; ideal7bitADC/17tapFFE; noPVT/PEX.',
                         'Reported power covers CTLE/native TG VDD only; excludes clock/bias generation,ADC andDSP.']}
    stem = 'noise_band_check_%s_d%d_n%d_300G' % (frozen_hash[:16], data_seed, NOISE_SEED)
    integration.atomic_json(project / 'results' / (stem + '_plan.json'), report)
    if args.run:
        report['status'] = 'running'
        output = project / 'results' / (stem + '_results.json')
        for item in prepared:
            assert_preserved()
            try:
                metadata, measured = evaluate(project, item, frozen, frozen_hash, symbols)
                differences = {}
                for name in PATHS:
                    old = item['reference_150G']['paths'][name]
                    new = measured['paths'][name]
                    differences[name] = {'SER_300G_minus_150G': new['SER'] - old['SER'],
                        'symbol_errors_300G_minus_150G': new['symbol_errors'] - old['symbol_errors'],
                        'MSE_target_units_squared_300G_minus_150G':
                        new['prediction_RMSE_in_target_symbol_units'] ** 2 - old['prediction_RMSE_in_target_symbol_units'] ** 2}
                report['runs'].append(dict(metadata, result_300G=measured,
                                           reference_150G=item['reference_150G'], differences=differences))
                print(json.dumps({'event': 'noise_band_run_complete', 'role': item['role'],
                                  'SER_300G': {name: measured['paths'][name]['SER'] for name in PATHS},
                                  'differences': differences}, sort_keys=True), flush=True)
            except Exception as error:
                report['errors'].append({'role': item['role'], 'run_name': item['run_name'], 'error': repr(error)})
            assert_preserved()
            integration.atomic_json(output, report)
        report['status'] = 'complete' if len(report['runs']) == 2 and not report['errors'] else 'partial_or_errors'
        report['protected_inputs_unchanged'] = True
        integration.atomic_json(output, report)
    print(json.dumps({'status': report['status'], 'generated_run_names': [item['run_name'] for item in plans],
                      'new_runs_completed': len(report['runs']), 'errors': report['errors'],
                      'frozen_choices_sha256': frozen_hash}, sort_keys=True), flush=True)
    return 0 if report['status'] in ('decks_generated_not_run', 'complete') else 1


if __name__ == '__main__':
    sys.exit(main())
