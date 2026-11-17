#!/usr/bin/env python3
"""Native-card CTLE AC/DC/noise optimization for the synthetic 20 dB channel.

Python 3.6 standard library. Run from the native project's scripts directory.
This writes only a separate optimization simulation tree and derived summaries;
it does not edit existing OA cells, native-card configuration, PDKs or baseline.
Frozen four-track/four-hold loading is a screening approximation. Shortlisted
candidates require actual clocked PAM4 and sampled-noise validation.
"""

import argparse
import bisect
import concurrent.futures
import hashlib
import json
import math
import time
from pathlib import Path

import pam4_integration as integration
import p6_bench as b
from psf_ascii import parse_file


PROJECT = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
NYQUIST = 56e9
CHANNEL_POLE = NYQUIST / math.sqrt(10 ** (20.0 / 20.0) - 1.0)
SOURCE_VPPD = 0.4
GRID = [1e3] + [NYQUIST * i / 112.0 for i in range(1, 113)]


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(path)


def interpolate(frequencies, values, frequency):
    index = bisect.bisect_left(frequencies, frequency)
    if index == 0:
        return values[0]
    if index == len(frequencies):
        return values[-1]
    fraction = math.log(frequency / frequencies[index - 1]) / math.log(
        frequencies[index] / frequencies[index - 1])
    return values[index - 1] + fraction * (values[index] - values[index - 1])


def channel(frequency):
    return (1.0 + 1j * frequency / CHANNEL_POLE) ** -2


def db(value):
    value = abs(value)
    if value <= 0 or not math.isfinite(value):
        raise ValueError('Gain or noise must be finite and positive')
    return 20.0 * math.log10(value)


def phase_linearity(frequencies, transfer):
    phases = []
    for value in transfer:
        phase = math.atan2(value.imag, value.real)
        if phases:
            while phase - phases[-1] > math.pi:
                phase -= 2 * math.pi
            while phase - phases[-1] < -math.pi:
                phase += 2 * math.pi
        phases.append(phase)
    # Uniform-frequency sampling avoids over-weighting a low-frequency decade.
    # Remove the best affine phase; this diagnoses dispersive phase, not BER.
    count = len(frequencies)
    mean_x = sum(frequencies) / count
    mean_y = sum(phases) / count
    variance = sum((frequency - mean_x) ** 2 for frequency in frequencies)
    slope = sum((frequency - mean_x) * (phase - mean_y)
                for frequency, phase in zip(frequencies, phases)) / variance
    intercept = mean_y - slope * mean_x
    residual = math.sqrt(sum((phase - intercept - slope * frequency) ** 2
                             for frequency, phase in zip(frequencies, phases)) / count)
    return {'affine_phase_residual_rms_degrees': residual * 180.0 / math.pi,
            'affine_phase_delay_s': -slope / (2.0 * math.pi),
            'affine_phase_intercept_degrees': intercept * 180.0 / math.pi,
            'phase_metric_note': 'best affine phase removed; waveform screen only, not a sampled eye'}


def make_configs(project):
    baseline = integration.base_config(project)
    result = [('baseline_native_r2', dict(baseline))]
    # Keep useful gain-bandwidth tradeoffs and both stage-size asymmetries.
    geometries = [(4, 4, 50, 50), (4, 4, 75, 75),
                  (8, 8, 25, 25), (8, 8, 35, 35), (8, 8, 50, 50),
                  (16, 16, 25, 25), (16, 8, 25, 35), (8, 4, 35, 75)]
    symmetric = [(0, 0.0)]
    symmetric += [(resistance, capacitance) for resistance in [500, 1000, 2000]
                  for capacitance in [5e-15, 10e-15, 20e-15]]
    symmetric += [(250, 20e-15), (8000, 10e-15), (64000, 10e-15)]
    equalizers = [(resistance, capacitance, resistance, capacitance)
                 for resistance, capacitance in symmetric]
    equalizers += [(1000, 5e-15, 2000, 10e-15),
                   (2000, 10e-15, 1000, 5e-15),
                   (500, 10e-15, 2000, 5e-15),
                   (2000, 5e-15, 500, 10e-15)]
    seen = {json.dumps(baseline, sort_keys=True)}
    for nc, nv, rc, rv in geometries:
        # Native OP probes showed improved tail saturation for these pairs.
        # The old .58/.60 setup is retained as the explicit baseline control.
        for bias, input_cm in [(.58, .70), (.50, .60)]:
            # Include unequal zero-placement estimates from the native OP probe.
            # These are additional hypotheses; the measured full transfer ranks them.
            physical_pair = ((1600, 18.4e-15, 1600, 15.0e-15) if bias == .58
                             else (1600, 11.6e-15, 1600, 8.9e-15))
            for r1, c1, r2, c2 in equalizers + [physical_pair]:
                config = dict(baseline, arch='cml', nc=nc, nv=nv, rc=rc, rv=rv,
                              vb=bias, cm=input_cm, rdeg=r1, cdeg=c1,
                              rdeg2=r2, cdeg2=c2, ch=5e-15, vdd=.9)
                key = json.dumps(config, sort_keys=True)
                if key in seen:
                    continue
                seen.add(key)
                result.append(('ac%03d' % (len(result) - 1), config))
    return result


def load_explicit_configs(path):
    value = json.loads(path.read_text())
    if isinstance(value, dict):
        value = value.get('configs', value.get('shortlist', value.get('candidates')))
    if not isinstance(value, list) or not value:
        raise ValueError('--configs-file must contain a nonempty config list')
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError('Each configuration must be an object')
        config = dict(item.get('config', item))
        config.pop('id', None)
        for key in ['nc', 'nv', 'rc', 'rv', 'vb', 'rdeg', 'cdeg']:
            if key not in config:
                raise ValueError('Configuration is missing ' + key)
        if config.get('arch', 'cml') != 'cml':
            raise ValueError('Native W=3um-card screening supports CML only')
        config.setdefault('rdeg2', 0)
        config.setdefault('cdeg2', 0.0)
        config.setdefault('ch', 5e-15)
        config.setdefault('cm', .6)
        config.setdefault('vdd', .9)
        result.append((str(item.get('id', 'custom%03d' % index)), config))
    ids = [identifier for identifier, unused in result]
    if len(ids) != len(set(ids)):
        raise ValueError('Configuration IDs must be unique')
    if any(not identifier or any(character not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for character in identifier)
           for identifier in ids):
        raise ValueError('Configuration IDs must be simple file-safe names')
    return result


def analyze(directory, config):
    ac = parse_file(directory / 'raw/acResponse.ac')
    dc = parse_file(directory / 'raw/dcOp.dc')
    noise = parse_file(directory / 'raw/noiseResponse.noise')
    frequency = ac.values[ac.sweep_names[0]]
    vin = [positive - negative for positive, negative in zip(ac.values['X_ip'], ac.values['X_im'])]
    if max(abs(value - 1.0) for value in vin) > 1e-7:
        raise ValueError('Differential AC stimulus normalization is incorrect')
    held = [(positive - negative) / source for positive, negative, source in
            zip(ac.values['X_h0p'], ac.values['X_h0m'], vin)]
    output = [(positive - negative) / source for positive, negative, source in
              zip(ac.values['X_o_p'], ac.values['X_o_m'], vin)]
    combined = [interpolate(frequency, held, value) * channel(value) for value in GRID]
    gains = [db(value) for value in combined]
    peak = max(range(len(GRID)), key=lambda index: abs(combined[index]))
    h56 = interpolate(frequency, held, NYQUIST)
    low = interpolate(frequency, held, 1e3)
    g56 = h56 * channel(NYQUIST)
    g1 = interpolate(frequency, held, 1e9) * channel(1e9)
    if noise.unit('out') != 'V/sqrt(Hz)':
        raise ValueError('Differential output-noise density unit is unverified')
    nf = noise.values[noise.sweep_names[0]]
    density = noise.values['out']
    nrms = b.noise_band(nf, density, 1e6, NYQUIST)
    snr56 = db(SOURCE_VPPD * abs(g56) / (2 * math.sqrt(2) * nrms))
    minimum_gain = min(abs(value) for value in combined)
    worst_snr = db(SOURCE_VPPD * minimum_gain / (2 * math.sqrt(2) * nrms))
    point = lambda node: dc.values['X_' + node][0]
    cm1 = (point('c_p') + point('c_m')) / 2
    cm2 = (point('o_p') + point('o_m')) / 2
    supply = config.get('vdd', .9)
    power = -supply * dc.values['XVs:p'][0]
    if not math.isfinite(power) or power <= 0:
        raise ValueError('Supply power is nonpositive or invalid')
    nodes = ['c_p', 'c_m', 'o_p', 'o_m', 's1_p', 's1_m', 's2_p', 's2_m']
    clearances = {node: min(point(node), supply - point(node)) for node in nodes}
    minimum_clearance = min(clearances.values())
    headroom = minimum_clearance > .08
    op = parse_file(directory / 'raw/dcOpInfo.info')
    tails = {}
    for key, copies in [('XT1p0', config['nc']), ('XT2p0', config['nv'])]:
        value = op.values.get(key)
        if not value or not isinstance(value[0], dict):
            value = next((value for name, value in op.values.items()
                          if name.startswith(key + '.') and value and isinstance(value[0], dict)), None)
        if not value or not isinstance(value[0], dict):
            continue
        primitive = value[0]
        record = {name: primitive[name] for name in ['gm', 'gds', 'vgs', 'vds', 'vdsat', 'ids', 'region']
                  if name in primitive}
        if 'vds' in primitive and 'vdsat' in primitive:
            record['vds_minus_vdsat_V'] = primitive['vds'] - primitive['vdsat']
        if primitive.get('gds', 0) > 0:
            record['parallel_tail_gds_S'] = primitive['gds'] * copies
            record['parallel_tail_ro_ohm'] = 1.0 / record['parallel_tail_gds_S']
        tails[key] = record
    metrics = {'combined_gain_56GHz_VV': abs(g56),
               'combined_gain_56GHz_dB': db(g56),
               'combined_gain_1GHz_VV': abs(g1),
               'combined_gain_1GHz_dB': db(g1),
               'combined_gain_1kHz_VV': abs(combined[0]),
               'combined_minimum_passband_gain_VV': minimum_gain,
               'combined_passband_ripple_dB': max(gains) - min(gains),
               'combined_midband_hump_vs_56GHz_dB': max(gains) - db(g56),
               'combined_peak_Hz': GRID[peak],
               'combined_peak_gain_dB': gains[peak],
               'held_gain_56GHz_VV': abs(h56),
               'held_gain_56GHz_dB': db(h56),
               'held_boost_56GHz_vs_1kHz_dB': db(h56 / low),
               'output_boost_56GHz_vs_1kHz_dB': db(interpolate(frequency, output, NYQUIST) / output[0]),
               'output_noise_1MHz_to_56GHz_Vrms': nrms,
               'noise_measurement_node': 'differential held node h0p-h0m, frozen tracking',
               'power_W': power,
               'ctle_common_mode_V': cm1,
               'output_common_mode_V': cm2,
               'source1_V': point('s1_p'),
               'source2_V': point('s2_p'),
               'static_headroom_heuristic_ok': headroom,
               'static_nodes_within_supply_rails': minimum_clearance > 0,
               'static_node_rail_clearances_V': clearances,
               'static_minimum_rail_clearance_V': minimum_clearance,
               'representative_tail_primitive_OP': tails,
               'sinusoidal_SNR_56GHz_proxy_dB': snr56,
               'worst_passband_sinusoidal_SNR_proxy_dB': worst_snr,
               'source_sinusoid_Vppd_for_proxy': SOURCE_VPPD,
               'predicted_output_56GHz_sinusoid_Vppd': SOURCE_VPPD * abs(g56)}
    metrics.update(phase_linearity(GRID, combined))
    # Comparative score only. No course noise, gain or power limit is invented.
    rail_penalty = 5.0 * max(0.0, (.08 - minimum_clearance) / .08)
    metrics['headroom_soft_ranking_penalty'] = rail_penalty
    metrics['ranking_score'] = (snr56 - .85 * metrics['combined_passband_ripple_dB']
                                - .025 * metrics['affine_phase_residual_rms_degrees']
                                - rail_penalty)
    metrics['transfer_samples'] = [{'frequency_Hz': value,
                                   'held_gain_VV': abs(interpolate(frequency, held, value)),
                                   'combined_gain_VV': abs(interpolate(frequency, held, value) * channel(value)),
                                   'combined_gain_dB': db(interpolate(frequency, held, value) * channel(value))}
                                  for value in [1e9, 5e9, 10e9, 20e9, 28e9, 40e9, 56e9]]
    return metrics, {'ac': ac.sha256, 'dc': dc.sha256, 'noise': noise.sha256}


def run_case(project, identifier, config):
    directory = project / 'simulations/ctle_ac_optimization' / identifier
    lines, saves = b.circuit(config, 'X')
    deck = b.header(temp=25) + lines + [
        'saveOptions options save=selected currents=selected',
        'save ' + ' '.join(dict.fromkeys(saves)), 'dcOp dc',
        'dcOpInfo info what=oppoint where=rawfile',
        'acResponse ac start=1K stop=150G dec=50',
        'noiseResponse (X_h0p X_h0m) noise start=1M stop=56G dec=40 iprobe=XVin']
    netlist_hash = hashlib.sha256(('\n'.join(deck) + '\n').encode('utf-8')).hexdigest()
    cached = False
    audit_file = directory / 'optimization_record.json'
    if audit_file.exists():
        prior = json.loads(audit_file.read_text())
        if prior.get('netlist_sha256') == netlist_hash and prior.get('run_status', {}).get('exit_code') == 0:
            return dict(prior, reused_identical_cached_deck=True)
    status = b.run(directory, deck, timeout=120)
    result = {'id': identifier, 'config': config, 'run_status': status,
              'netlist_sha256': netlist_hash, 'reused_identical_cached_deck': cached}
    if status.get('exit_code') == 0:
        try:
            metrics, hashes = analyze(directory, config)
            result.update(metrics=metrics, result_sha256=hashes)
        except Exception as error:
            result['analysis_error'] = repr(error)
    atomic_json(audit_file, result)
    return result


def select_shortlist(records, count):
    valid = [record for record in records if record.get('metrics', {}).get('static_nodes_within_supply_rails')
             and record.get('run_status', {}).get('exit_code') == 0]
    candidates = [record for record in valid if record['id'] != 'baseline_native_r2']
    if not candidates:
        return []
    best_snr = max(record['metrics']['sinusoidal_SNR_56GHz_proxy_dB'] for record in candidates)
    less_extreme = [record for record in candidates
                    if record['metrics']['sinusoidal_SNR_56GHz_proxy_dB'] >= best_snr - 12.0]
    selectors = [
        ('balanced transfer and noise score', candidates,
         lambda record: record['metrics']['ranking_score']),
        ('flatter combined transfer within12dB of best noise proxy', less_extreme,
         lambda record: -record['metrics']['combined_passband_ripple_dB']
         - .01 * record['metrics']['affine_phase_residual_rms_degrees']),
        ('best56GHz signal-to-noise proxy', candidates,
         lambda record: record['metrics']['sinusoidal_SNR_56GHz_proxy_dB']),
        ('higher absolute56GHz gain', candidates,
         lambda record: record['metrics']['combined_gain_56GHz_VV'])]
    chosen = []
    seen = set()
    def signature(record):
        config = record['config']
        return (config['nc'], config['nv'], config['rc'], config['rv'],
                config['rdeg'], config['cdeg'], config.get('rdeg2'), config.get('cdeg2'))
    signatures = set()
    for reason, subset, score in selectors:
        ordered = sorted(subset, key=score, reverse=True)
        record = next((item for item in ordered
                       if item['id'] not in seen and signature(item) not in signatures), None)
        if record is None:
            record = next((item for item in ordered if item['id'] not in seen), None)
        if record is not None:
            chosen.append(dict(record, ranking_reason=reason))
            seen.add(record['id'])
            signatures.add(signature(record))
    ranked = sorted(candidates, key=lambda record: record['metrics']['ranking_score'], reverse=True)
    # Prefer a different stage geometry or EQ shape before nearly identical cases.
    for diverse in [True, False]:
        for record in ranked:
            if len(chosen) >= count:
                return chosen[:count]
            config_signature = signature(record)
            if record['id'] in seen or (diverse and config_signature in signatures):
                continue
            chosen.append(dict(record, ranking_reason='diverse balanced-score candidate' if diverse else 'balanced-score reserve'))
            signatures.add(config_signature)
            seen.add(record['id'])
    return chosen[:count]


def run(project, configs_file=None, limit=None, workers=2, shortlist_count=10):
    native = integration.install_native_cards(project / 'configs/native_device_cards.json')
    configs = load_explicit_configs(configs_file) if configs_file else make_configs(project)
    if limit is not None:
        configs = configs[:limit]
    ids = [identifier for identifier, unused in configs]
    order = {identifier: index for index, identifier in enumerate(ids)}
    destination = project / 'results/ctle_ac_optimization.json'
    summary = {'schema_version': 1, 'status': 'running',
               'scope': 'native-card CML AC/DC/noise screening, frozen four-track/four-hold eight-lane sampler',
               'native_metadata': native,
               'conditions': {'model_section': 'tt', 'temperature_C': 25,
                              'channel_loss_dB_at_56GHz': 20, 'channel_poles_Hz': [CHANNEL_POLE, CHANNEL_POLE],
                              'sampling_rate_per_s': 112e9, 'hold_capacitance_per_lane_per_side_F': 5e-15,
                              'combined_transfer_grid': '1kHz plus uniform0.5GHz steps through56GHz',
                              'interpolation': 'complex linear against logarithmic frequency',
                              'noise_integration_Hz': [1e6, 56e9],
                              'noise_scope': 'held differential frozen-track MOS/resistor noise; no synthetic-channel thermal noise or sampled folding',
                              'power_scope': 'AFE/TG DC VDD only; no ideal-clock energy, physical clocks/bias generator or ADC',
                              'ranking_note': 'comparative score, not a course pass/fail threshold; SNR proxy uses0.4Vppd pre-channel sine',
                              'shortlist_note': 'first4 balance score, flatness, noise proxy and absolute gain; actual PAM4/noise must select the final candidate'},
               'configuration_count': len(configs), 'results': [], 'shortlist': [], 'errors': []}
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        pending = {executor.submit(run_case, project, identifier, config): identifier
                   for identifier, config in configs}
        for future in concurrent.futures.as_completed(pending):
            identifier = pending[future]
            try:
                record = future.result()
            except Exception as error:
                record = {'id': identifier, 'error': repr(error)}
            summary['results'].append(record)
            summary['results'].sort(key=lambda item: order[item['id']])
            if record.get('error') or record.get('analysis_error') or record.get('run_status', {}).get('exit_code') != 0:
                summary['errors'].append({'id': identifier, 'error': record.get('error', record.get('analysis_error', record.get('run_status')))})
            summary['shortlist'] = select_shortlist(summary['results'], shortlist_count)
            summary['preferred_top4_ids'] = [item['id'] for item in summary['shortlist'][:4]]
            summary['baseline'] = next((item for item in summary['results'] if item['id'] == 'baseline_native_r2'), None)
            summary['elapsed_s'] = time.time() - started
            atomic_json(destination, summary)
            print(json.dumps({'event': 'AC_case_complete', 'id': identifier,
                              'completed': len(summary['results']), 'total': len(configs),
                              'shortlist_ids': summary['preferred_top4_ids'],
                              'metrics': {key: record['metrics'][key] for key in [
                                  'combined_gain_56GHz_VV', 'combined_passband_ripple_dB',
                                  'sinusoidal_SNR_56GHz_proxy_dB', 'power_W']}
                              if record.get('metrics') else None}), flush=True)
    summary['status'] = 'complete' if not summary['errors'] else 'complete_with_errors'
    summary['elapsed_s'] = time.time() - started
    summary['script_sha256'] = integration.file_hash(Path(__file__))
    atomic_json(destination, summary)
    print(json.dumps({'event': 'AC_optimization_finished', 'status': summary['status'],
                      'completed': len(summary['results']), 'shortlist_ids': summary['preferred_top4_ids']}), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=PROJECT)
    parser.add_argument('--configs-file', type=Path, help='optional focused follow-up grid; list of configs or{configs:[...]}')
    parser.add_argument('--limit', type=int, help='small smoke subset')
    parser.add_argument('--workers', type=int, default=2, choices=[1, 2])
    parser.add_argument('--shortlist-count', type=int, default=10)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    if args.shortlist_count < 4:
        parser.error('--shortlist-count must be at least4')
    summary = run(args.project, args.configs_file, args.limit, args.workers, args.shortlist_count)
    return 0 if summary['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
