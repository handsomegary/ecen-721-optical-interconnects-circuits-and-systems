#!/usr/bin/env python3
"""Export only derived metrics, test conditions and hashes; no device cards/waves."""
import hashlib
import json
from pathlib import Path

PROJECT = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pick(data, names):
    return {name: data[name] for name in names if name in data}


def main():
    provenance = {}
    def read(relative):
        path = PROJECT / relative
        provenance[relative] = digest(path)
        return json.loads(path.read_text())
    frozen = read('configs/pam4_optimization_frozen.json')
    validation = read('results/pam4_optimization_validation.json')
    assert validation['status'] == 'complete'
    assert validation['frozen_file_unchanged_during_validation']
    result = {'schema_version': 1, 'scope': 'Derived Project6 CTLE/VGA optimization and initial comparator results',
              'project_directory': str(PROJECT),
              'conditions': {'data_rate_Gbps': 224, 'baud_rate_Gbaud': 112,
                  'synthetic_channel_loss_at_56GHz_dB': 20, 'TX_differential_Vpp': .4,
                  'temperature_C': 25, 'supply_V': .9, 'sampler_lanes': 8,
                  'sampler_per_lane_GHz': 14, 'hold_capacitance_per_side_fF': 5,
                  'transient_noise_cutoff_GHz': 150, 'noise_flattened_below_MHz': 500,
                  'ideal_FFE_taps': 17, 'FFE_decision_latency_UI': 8,
                  'ADC_model_nominal_bits': 7, 'ideal_clocks': True,
                  'training_symbols': frozen['training_symbol_count'],
                  'training_data_seed': frozen['training_data_seed'],
                  'training_noise_seed': frozen['training_noise_seed']},
              'native_cards_sha256': frozen['native_cards_sha256'],
              'frozen_choices_sha256': validation['frozen_choices_sha256'],
              'designs': [], 'comparison': validation['comparison'], 'validation_runs': [],
              'limits': validation['limits'], 'provenance_sha256': provenance}
    result['limits'].append('Raw three-threshold diagnostics use the FFE-selected alignment, not an independently optimized standalone slicer; headline improvement requires the stated ideal FFE.')
    for design in frozen['designs']:
        record = design['record']; selection = record['selection']
        entry = pick(record, ['candidate_id', 'config', 'clock_delay_offset_UI',
                             'measured_CK_half_fall_aperture_phase_UI', 'AC_metrics'])
        entry.update(role=design['role'], **pick(selection, ['integer_symbol_lag',
            'ADC_fullscale_differential_Vpp', 'raw_FFE_score', 'ADC_score']))
        result['designs'].append(entry)
    metric_keys = ['sample_count', 'symbol_errors', 'SER', 'gray_bit_errors', 'bit_count', 'gray_BER',
                   'prediction_RMSE_in_target_symbol_units', 'prediction_EVM_RMS_percent_of_target_RMS']
    for record in validation['runs']:
        entry = pick(record, ['role', 'candidate_id', 'final_data_seed', 'noise_seed',
                 'netlist_sha256', 'raw_transient_sha256', 'AFE_and_sampler_VDD_power_W',
                 'validation_held_min_V', 'validation_held_max_V', 'validation_held_Vppd'])
        entry['metrics'] = {key: pick(record['metrics'][key], metric_keys) for key in
            ['raw_held_FFE_before_ADC', 'ideal7bit_ADC_then_FFE', 'raw_three_threshold_same_centers']}
        entry.update(pick(record['metrics'], ['ADC_validation_input_clipped_count',
            'ADC_validation_input_count', 'ADC_fullscale_differential_Vpp']))
        result['validation_runs'].append(entry)
    if (PROJECT / 'results/native_verification_r3.json').exists():
        data = read('results/native_verification_r3.json')
        result['native_revision'] = pick(data, ['revision', 'native_cell', 'config',
            'all_native_MOS_count', 'native_cards_match_r2', 'parasitic_flags_all_1',
            'native_source_netlist_sha256', 'native_parity_verified', 'relative_errors'])
        keys = ['output_gain_56GHz_VV', 'held_track_gain_56GHz_VV', 'held_track_gain_56GHz_dB',
                'output_peaking_56_vs_1kHz_dB', 'response_peak_Hz', 'VDD_power_W',
                'output_common_mode_V', 'track_noise_1MHz_to_56GHz_Vrms', 'sha256']
        for label in ['native', 'fixture']:
            result['native_revision'][label] = pick(data[label], keys)
    if (PROJECT / 'results/noise_band_sensitivity.json').exists():
        data = read('results/noise_band_sensitivity.json')
        result['noise_band_sensitivity'] = pick(data, ['status', 'mode', 'frozen_choices_sha256',
            'source_final_validation_sha256', 'reused_final_data_seed', 'noise_seed',
            'noise_max_comparison_Hz', 'maxstep_s', 'noise_flattened_below_Hz',
            'errors', 'limits', 'protected_inputs_unchanged'])
        result['noise_band_sensitivity']['runs'] = [pick(row, ['role', 'candidate_id',
            'data_seed', 'noise_seed', 'noise_max_Hz', 'netlist_sha256', 'raw_transient_sha256',
            'validation_fitting_performed', 'result_300G', 'reference_150G', 'differences'])
            for row in data['runs']]
    probes = []
    for path in sorted((PROJECT / 'runs').glob('adc_comparator_r3*/comparator_probe_summary.json')):
        data = read(str(path.relative_to(PROJECT)))
        probe = pick(data, ['scope', 'configuration', 'winner', 'topology_reference',
                   'provisional_engineering_decision_budget_s', 'half_LSB_error_allocation_V',
                   'testbench_assumptions'])
        probe['cases'] = [pick(case, ['magnitude_LSB', 'polarities', 'deck_sha256',
                            'raw_sha256', 'summary', 'run_status']) for case in data['cases']]
        probes.append(probe)
    result['comparator_probes'] = probes
    diagnostic_path = PROJECT / 'results/adc_comparator_diagnostic.json'
    if diagnostic_path.exists():
        # The diagnostic producer emits conditions, scalar/timing statistics,
        # and hashes only. It never emits device cards or waveform arrays.
        result['comparator_diagnostic'] = read('results/adc_comparator_diagnostic.json')
    for name in ['optimize_pam4.py', 'pam4_integration.py', 'pam4_ffe_diagnostic.py',
                 'noise_band_check.py', 'adc_comparator_probe.py', 'verify_revision.py',
                 'export_optimization.py']:
        relative = 'scripts/' + name
        provenance[relative] = digest(PROJECT / relative)
    output = PROJECT / 'results/Project6_optimization_export.json'
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n'
    if len(encoded.encode('utf8')) > 70 * 1024:
        encoded = json.dumps(result, indent=1, sort_keys=True, allow_nan=False) + '\n'
    if len(encoded.encode('utf8')) > 70 * 1024:
        encoded = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'
    for forbidden in ['weights_on_normalized_input', 'equivalent_weights_per_input_V',
                      'simulator lang=spectre', 'nmos_lvt', 'pmos_lvt']:
        if forbidden in encoded:
            raise ValueError('Export boundary violation: ' + forbidden)
    output.write_text(encoded)
    print(json.dumps({'path': str(output), 'bytes': output.stat().st_size, 'sha256': digest(output)}))


if __name__ == '__main__':
    main()
