#!/usr/bin/env python3
"""Native-card PAM4/CTLE/TG integration screen; Python 3.6, standard library.

Run from the project's scripts directory. Only this project's simulations and
derived summaries are written. Channel, source, clocks, ADC quantization, and
oracle deskew are explicitly behavioral; CTLE and TG devices are native MOS.
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

import p6_bench as b
import p6_dynamic as dynamic
import psf_ascii
import pam4_metrics as metrics


PROJECT = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
UI = 1.0 / 112e9
T0 = 200e-12
EDGE = 1e-12
WARMUP = 128
GUARD = 64
SEED = 7212026
FULLSCALES = (.05, .1, .2, .4)
PHASES_UI = (0.0, .25, .5, .75)
LAGS = tuple(range(17))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(path)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _spectre_number(text):
    match = re.match(r'^([+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?)([a-zA-Z]*)$', text)
    if not match:
        raise ValueError('Native geometry is not a literal number: ' + text)
    scale = {'': 1.0, 'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12,
             'f': 1e-15, 'a': 1e-18, 'k': 1e3, 'K': 1e3, 'M': 1e6, 'G': 1e9}
    if match.group(2) not in scale:
        raise ValueError('Unsupported native geometry suffix: ' + text)
    return float(match.group(1)) * scale[match.group(2)]


def install_native_cards(path):
    """Install the verified native instance tails once, before worker threads."""
    cards = json.loads(path.read_text())
    for key, length in [('n_l30', 30e-9), ('n_l60', 60e-9), ('p_l30', 30e-9)]:
        card = cards[key]
        if not isinstance(card.get('model'), str) or not isinstance(card.get('parameters'), str):
            raise ValueError('Native card must provide model and full parameter-tail strings')
        parameters = card['parameters']
        for parameter, expected in [('w', 3e-6), ('l', length)]:
            match = re.search(r'(?<!\w)' + parameter + r'\s*=\s*([^\s()]+)', parameters)
            if not match or not math.isclose(_spectre_number(match.group(1)), expected, rel_tol=1e-7):
                raise ValueError('Native geometry does not match expected ' + key + ' ' + parameter)
        for flag in ['_ccoflag', '_rcoflag', '_rgflag']:
            match = re.search(re.escape(flag) + r'\s*=\s*\(?([0-9.eE+\-]+)', parameters)
            if not match or float(match.group(1)) != 1.0:
                raise ValueError('Native parasitic flag must equal 1: ' + key + ' ' + flag)

    def native_mos(name, drain, gate, source, bulk, pmos=False, w=3e-6, l=30e-9):
        if not math.isclose(w, 3e-6, rel_tol=1e-9):
            raise ValueError('Native integration only supports W=3um copies')
        if math.isclose(l, 30e-9, rel_tol=1e-9):
            key = 'p_l30' if pmos else 'n_l30'
        elif not pmos and math.isclose(l, 60e-9, rel_tol=1e-9):
            key = 'n_l60'
        else:
            raise ValueError('Unsupported native integration channel length')
        card = cards[key]
        return '%s (%s %s %s %s) %s %s' % (
            name, drain, gate, source, bulk, card['model'], card['parameters'])

    b.mos = native_mos
    # This only expands the reader's bound for our own transient result files.
    psf_ascii.MAX_FILE_BYTES = 256 * 1024 * 1024
    return {'native_cards_sha256': file_hash(path),
            'native_geometry': 'W=3um, input/TG L=30nm, NMOS tail L=60nm',
            'native_parasitic_flags': {'_ccoflag': 1, '_rcoflag': 1, '_rgflag': 1}}


def base_config(project):
    baseline = json.loads((project / 'baseline' / 'feasibility_results.json').read_text())
    record = baseline['CTLE_adjustable_peaking_range_confirmation']['results'][0]
    config = dict(record['config'])
    if config.get('arch', 'cml') != 'cml':
        raise ValueError('Expected the equalized CML baseline')
    config.update(cdeg=100e-15, cdeg2=100e-15, ch=5e-15)
    return config


def symbol_sequence(count):
    generator = random.Random(SEED)
    return [generator.randrange(4) for unused in range(count)]


def pwl_source(name, output, symbols, polarity, delay_s=0.0):
    # Differential levels are -0.2,-0.0667,+0.0667,+0.2V (0.4Vppd).
    values = [polarity * (symbol - 1.5) * (.4 / 6.0) for symbol in symbols]
    points = [(0.0, values[0])]
    for index in range(1, len(values)):
        boundary = T0 + index * UI + delay_s
        points.extend([(boundary, values[index - 1]), (boundary + EDGE, values[index])])
    # Spectre continuation uses a trailing backslash, not SPICE's leading '+'.
    lines = ['%s (%s X_cm) vsource type=pwl wave=[ \\' % (name, output)]
    lines.extend(' %.16g %.16g \\' % point for point in points)
    lines.append(' ]')
    return lines


def stimulus_and_channel(symbols, loss_db, p_delay=0.0, n_delay=0.0):
    lines = []
    for side, polarity, delay in [('p', 1, p_delay), ('m', -1, n_delay)]:
        input_node = 'X_i' + side
        source_node = 'PAM4_src_' + side if loss_db else input_node
        lines.extend(pwl_source('PAM4V' + side, source_node, symbols, polarity, delay))
        if loss_db:
            pole_hz = 56e9 / math.sqrt(10 ** (loss_db / 20.0) - 1)
            capacitance = 1.0 / (2 * math.pi * 100.0 * pole_hz)
            # Unity-DC two-pole lowpass. Buffers isolate both poles and present
            # zero output impedance to the native CTLE input gate network.
            lines.extend([
                'CHR1%s (%s CH1_%s) resistor r=100' % (side, source_node, side),
                'CHC1%s (CH1_%s X_cm) capacitor c=%.16g' % (side, side, capacitance),
                'CHB1%s (CHB_%s X_cm CH1_%s X_cm) vcvs gain=1' % (side, side, side),
                'CHR2%s (CHB_%s CH2_%s) resistor r=100' % (side, side, side),
                'CHC2%s (CH2_%s X_cm) capacitor c=%.16g' % (side, side, capacitance),
                'CHB2%s (%s X_cm CH2_%s X_cm) vcvs gain=1' % (side, input_node, side)])
    return lines


def shift_clock(line, phase_s):
    if not re.match(r'^X(?:CK|KB)\d+\s', line):
        return line
    match = re.search(r'\bdelay=([^\s]+)', line)
    if not match:
        raise ValueError('Clock source missing delay')
    value = _spectre_number(match.group(1)) + phase_s
    return line[:match.start(1)] + ('%.16g' % value) + line[match.end(1):]


def build_deck(config, symbols, loss_db, phase_ui=0.0, p_delay=0.0,
               n_delay=0.0, common_clock_delay=0.0, noise=False):
    stop = T0 + (len(symbols) + 2) * UI + max(p_delay, n_delay, common_clock_delay)
    lines = b.header(temp=25)
    circuit, unused = b.circuit(config, 'X', mode='tran', vinpp=.4, clocked=True)
    for line in circuit:
        if re.match(r'^X(?:Vin|Ein)\s', line):
            continue
        lines.append(shift_clock(line, phase_ui * UI + common_clock_delay))
    lines.extend(stimulus_and_channel(symbols, loss_db, p_delay, n_delay))
    saves = ['X_o_p', 'X_o_m', 'X_ip', 'X_im', 'X_ck0', 'X_kb0', 'XVs:p']
    saves.extend('X_h%d%s' % (lane, side) for lane in range(8) for side in ['p', 'm'])
    lines.extend(['saveOptions options save=selected currents=selected',
                  'save ' + ' '.join(saves), 'dcOp dc'])
    transient = ('tranResponse tran stop=%.16g maxstep=200f errpreset=conservative '
                 'strobeperiod=%.16g strobeoutput=strobeonly') % (stop, UI / 16)
    if noise:
        transient += ' noisefmax=150G noisefmin=500M noiseseed=11'
    lines.append(transient)
    return lines, stop


def _raw_file(directory):
    files = list((directory / 'raw').glob('tranResponse.tran*'))
    if len(files) != 1:
        raise ValueError('Expected exactly one transient result file')
    return files[0]


def execute_deck(project, run_name, deck):
    directory = project / 'simulations' / 'pam4_integration' / run_name
    netlist_hash = hashlib.sha256(('\n'.join(deck) + '\n').encode('utf-8')).hexdigest()
    prior_hash = directory / 'integration_netlist.sha256'
    prior_status = directory / 'run_status.json'
    cached = False
    status = None
    if prior_hash.exists() and prior_status.exists() and prior_hash.read_text().strip() == netlist_hash:
        status = json.loads(prior_status.read_text())
        if status.get('exit_code') == 0:
            try:
                _raw_file(directory)
                cached = True
            except ValueError:
                pass
    if not cached:
        status = b.run(directory, deck, timeout=240)
        if status.get('exit_code') == 0:
            prior_hash.write_text(netlist_hash + '\n')
    if status.get('exit_code') != 0:
        raise RuntimeError('Spectre run failed: %s: %s' % (run_name, json.dumps(status)))
    return directory, status, netlist_hash, cached


def held_records(psf, reference_delay=0.0):
    """Read CK0 falling midpoint, then each lane's held value 1.5ps later."""
    times = psf.values[psf.sweep_names[0]]
    clock = psf.values['X_ck0']
    half = (max(clock) + min(clock)) / 2.0
    falls = []
    for index in range(1, len(times)):
        if clock[index - 1] >= half > clock[index]:
            fraction = (clock[index - 1] - half) / (clock[index - 1] - clock[index])
            falls.append(times[index - 1] + fraction * (times[index] - times[index - 1]))
    if len(falls) < 2:
        raise ValueError('Not enough saved CK0 falling transitions')
    records = []
    for falling in falls:
        for lane in range(8):
            close = falling + lane * UI
            held_at = close + 1.5e-12
            if held_at > times[-1] or close < T0 + reference_delay:
                continue
            symbol_time_index = int(math.floor((close - T0 - reference_delay) / UI + 1e-7))
            sample = (dynamic.interp(times, psf.values['X_h%dp' % lane], held_at) -
                      dynamic.interp(times, psf.values['X_h%dm' % lane], held_at))
            records.append((symbol_time_index, sample, held_at, close, lane))
    records.sort(key=lambda record: record[0])
    if len(set(record[0] for record in records)) != len(records):
        raise ValueError('Duplicate symbol indices from clock-to-symbol mapping')
    period_errors = [abs((second - first) - 8 * UI) for first, second in zip(falls, falls[1:])]
    audit = {'clock_fall_count': len(falls), 'sample_after_actual_fall_midpoint_s': 1.5e-12,
             'clock_fall_period_max_error_s': max(period_errors),
             'strobe_period_s': UI / 16, 'saved_first_time_s': times[0],
             'saved_last_time_s': times[-1], 'reference_common_delay_s': reference_delay,
             'method': 'CK0 half-falling crossings interpolated from strobed output; '
                       'lane k closes k*UI later; held voltage read after1.5ps'}
    return records, audit


def aligned_window(records, symbols, lag, train_count, validation_count):
    by_symbol = {record[0] - lag: record for record in records}
    indices = list(range(WARMUP, WARMUP + train_count + validation_count))
    missing = [index for index in indices if index not in by_symbol]
    if missing:
        raise ValueError('Held output does not cover required symbol indices: ' + repr(missing[:8]))
    if indices[-1] >= len(symbols):
        raise ValueError('Insufficient generated symbols')
    chosen = [by_symbol[index] for index in indices]
    return ([record[1] for record in chosen], [symbols[index] for index in indices],
            [record[2] for record in chosen])


def detector_bundle(samples, labels):
    result = {'raw': metrics.fit_training(samples, labels), 'ADC': []}
    for fullscale in FULLSCALES:
        quantized, clipped = metrics.quantize_symmetric(samples, fullscale, 7)
        result['ADC'].append({'fullscale_differential_Vpp': fullscale,
                              'training_clipped_count': clipped,
                              'fit': metrics.fit_training(quantized, labels)})
    return result


def select_alignment(records, symbols, train_count):
    candidates = []
    best = None
    for lag in LAGS:
        try:
            samples, labels, unused = aligned_window(records, symbols, lag, train_count, 0)
            fit = metrics.fit_training(samples, labels)
        except ValueError:
            continue
        candidate = {'integer_symbol_lag': lag, 'quality_score': fit['quality_score'],
                     'training_SER': fit['SER'],
                     'class_means_strictly_ordered': fit['class_means_strictly_ordered']}
        candidates.append(candidate)
        if best is None or candidate['quality_score'] > best['quality_score']:
            best = dict(candidate)
            best['frozen_detectors'] = detector_bundle(samples, labels)
    if best is None:
        raise ValueError('No lag has enough held training samples')
    best['lag_search'] = candidates
    best['selection_data'] = 'training symbols only; no validation samples used'
    return best


def frozen_metrics(samples, symbols, train_count, validation_count, frozen):
    """Apply calibration-run detectors verbatim to the independent full run."""
    values = samples[train_count:train_count + validation_count]
    labels = symbols[train_count:train_count + validation_count]
    if len(values) != validation_count or len(labels) != validation_count:
        raise ValueError('Incorrect validation window length')
    result = {'schema_version': 1, 'train_count': train_count,
              'validation_count': validation_count,
              'threshold_source': 'frozen from selected short calibration run; no validation fitting',
              'gray_codes_for_ascending_symbols': list(metrics.GRAY_CODES),
              'raw': {'training': frozen['raw'],
                      'validation': metrics._validation_metrics(values, labels, frozen['raw'])},
              'behavioral_ADC': []}
    for adc in frozen['ADC']:
        fullscale = adc['fullscale_differential_Vpp']
        quantized, clipped = metrics.quantize_symmetric(values, fullscale, 7)
        result['behavioral_ADC'].append({
            'bits': 7, 'fullscale_differential_Vpp': fullscale,
            'LSB_V': fullscale / 128, 'input_center_V': 0.0,
            'reconstruction': 'uniform midrise, saturating',
            'training_clipped_count': adc['training_clipped_count'],
            'validation_clipped_count': clipped,
            'validation_clipped_fraction': clipped / validation_count,
            'training': adc['fit'],
            'validation': metrics._validation_metrics(quantized, labels, adc['fit']),
            'physical_scope': 'behavioral quantization only; no added physical input load, '
                              'comparator noise, kickback, mismatch, latency, or ADC power'})
    return result


def simulate_and_analyze(project, scenario, run_name, symbols, train_count,
                         validation_count, phase_ui, frozen_selection=None,
                         p_delay=0.0, n_delay=0.0, common_clock_delay=0.0,
                         reference_delay=0.0, noise=False):
    deck, stop = build_deck(scenario['config'], symbols, scenario['loss_dB_at_56GHz'],
                            phase_ui, p_delay, n_delay, common_clock_delay, noise)
    directory, status, netlist_hash, cached = execute_deck(project, run_name, deck)
    raw = _raw_file(directory)
    psf = psf_ascii.parse_file(raw)
    records, clock_audit = held_records(psf, reference_delay)
    if clock_audit['saved_last_time_s'] < stop - UI / 16 * 1.01:
        raise ValueError('Strobed data ends before the requested simulation window')
    selection = frozen_selection or select_alignment(records, symbols, train_count)
    selection = dict(selection, phase_UI=phase_ui)
    samples, labels, held_times = aligned_window(records, symbols,
                                                selection['integer_symbol_lag'],
                                                train_count, validation_count)
    result = {'run_name': run_name, 'scenario': scenario['name'],
              'loss_dB_at_56GHz': scenario['loss_dB_at_56GHz'],
              'config': scenario['config'], 'phase_UI': phase_ui,
              'PN_skew_s': p_delay - n_delay,
              'P_delay_s': p_delay, 'N_delay_s': n_delay,
              'common_clock_delay_s': common_clock_delay,
              'transient_noise_enabled': noise,
              'run_status': status, 'reused_identical_cached_deck': cached,
              'netlist_sha256': netlist_hash, 'raw_transient_sha256': psf.sha256,
              'clock_audit': clock_audit, 'selection': selection,
              'train_symbol_index_range': [WARMUP, WARMUP + train_count - 1]}
    if validation_count:
        result['validation_symbol_index_range'] = [WARMUP + train_count,
                                                   WARMUP + train_count + validation_count - 1]
        result['metrics'] = frozen_metrics(samples, labels, train_count, validation_count,
                                          selection['frozen_detectors'])
        t = psf.values[psf.sweep_names[0]]
        lo = held_times[train_count]
        hi = held_times[train_count + validation_count - 1] + UI
        if hi > t[-1]:
            raise ValueError('Missing data for full-symbol power integration')
        result['AFE_and_sampler_VDD_power_W'] = -scenario['config'].get('vdd', .9) * dynamic.mean_time(
            t, psf.values['XVs:p'], lo, hi)
        result['power_average_interval_s'] = [lo, hi]
        result['power_scope'] = ('CTLE and native TG VDD source only; excludes ideal clock-source '
                                 'energy, physical clocks, channel/source, bias generator and ADC')
        common_mode = [(p + n) / 2 for p, n in zip(psf.values['X_o_p'], psf.values['X_o_m'])]
        result['output_common_mode_average_V'] = dynamic.mean_time(t, common_mode, lo, hi)
    if noise:
        result['noise_conditions'] = {'noisefmax_Hz': 150e9, 'noisefmin_Hz': 500e6,
                                      'noiseseed': 11,
                                      'low_frequency_note': 'PSD flattened below500MHz; finite-band screen',
                                      'synthetic_channel_resistor_thermal_noise_included':
                                          scenario['loss_dB_at_56GHz'] > 0}
    return result


def make_scenarios(config):
    scenarios = []
    for name, loss, resistance in [('bypass', 0, 0), ('synthetic_10dB', 10, 1000),
                                    ('synthetic_20dB', 20, 64000)]:
        scenarios.append({'name': name, 'loss_dB_at_56GHz': loss,
                          'config': dict(config, rdeg=resistance, rdeg2=resistance,
                                         cdeg=100e-15, cdeg2=100e-15)})
    return scenarios


def initial_summary(native_metadata, smoke):
    return {'schema_version': 1, 'status': 'running', 'smoke_test': smoke,
            'scope': 'native MOS CTLE and 8-lane TG PAM4 integration; behavioral channel, '
                     'ideal clocks, behavioral ADC and oracle deskew; not full Project6 signoff',
            'conditions': {'symbol_rate_Baud': 112e9, 'bit_rate_bps': 224e9,
                           'UI_s': UI, 'temperature_C': 25, 'supply_V': .9,
                           'source_differential_Vpp_before_channel': .4,
                           'PAM4_level_order_Gray_codes': list(metrics.GRAY_CODES),
                           'edge_s': EDGE, 'warmup_symbols': WARMUP,
                           'end_guard_symbols': GUARD, 'seed': SEED,
                           'source_impedance': 'ideal zero impedance at CTLE input after channel buffer',
                           'channel': 'declared synthetic unity-DC two identical isolated RC poles per leg; '
                                      'R=100ohm; fc=56GHz/sqrt(10^(loss_dB/20)-1); loss0 bypasses channel',
                           'actual_channel_model_available': False,
                           'clock': 'eight ideal complementary14GHz lanes,1ps edges,zero jitter',
                           'phase_candidates_UI': list(PHASES_UI),
                           'integer_lag_candidates_UI': list(LAGS),
                           'sampler': 'eight native differential TG lanes;5fF per lane per side',
                           'ADC': '7-bit symmetric ideal midrise quantization only; input fullscales50/100/200/400mVppd',
                           'timing': 'phase,integer lag,polarity and thresholds selected on training only and frozen',
                           'native_cards': native_metadata},
            'calibration': [], 'selected_calibration': {}, 'validation': [],
            'PN_skew': [], 'noise_validation': [], 'errors': [],
            'limitations': [
                'No actual board/package channel model; synthetic losses are explicit assumptions.',
                'No transistor ADC, comparator noise, ADC kickback, ADC power or calibrated ENOB.',
                'Eight sampling lanes do not establish a14GS/s seven-bit converter per lane.',
                'No physical PN deskew circuitry; oracle branch is an ideal compensation bound.',
                'No clock jitter/distribution, PVT, extracted parasitics, or model-RF validity certification.',
                'No fullscale or threshold is fitted using validation data.',
                'Finite sequence errors and conditional bounds cannot establish very low BER.']}


def run(project=PROJECT, smoke=False, with_noise=False):
    native = install_native_cards(project / 'configs' / 'native_device_cards.json')
    config = base_config(project)
    scenarios = make_scenarios(config)
    summary = initial_summary(native, smoke)
    destination = project / 'results' / ('pam4_smoke_summary.json' if smoke else 'pam4_integration_summary.json')
    started = time.time()

    def checkpoint(event):
        summary['elapsed_seconds'] = round(time.time() - started, 3)
        atomic_json(destination, summary)
        print(json.dumps(event, sort_keys=True), flush=True)

    checkpoint({'event': 'started', 'smoke': smoke})
    if smoke:
        train_count, validation_count = 64, 128
        symbols = symbol_sequence(WARMUP + train_count + validation_count + GUARD)
        result = simulate_and_analyze(project, scenarios[0], 'smoke_bypass', symbols,
                                      train_count, validation_count, .25)
        summary['validation'].append(result)
        summary['status'] = 'complete'
        checkpoint({'event': 'smoke_complete',
                    'SER': result['metrics']['raw']['validation']['SER'],
                    'lag_UI': result['selection']['integer_symbol_lag']})
        return summary

    train_count, validation_count = 512, 2048
    summary['conditions'].update(training_symbols=train_count, validation_symbols=validation_count)
    calibration_symbols = symbol_sequence(WARMUP + train_count + GUARD)
    full_symbols = symbol_sequence(WARMUP + train_count + validation_count + GUARD)
    assert calibration_symbols == full_symbols[:len(calibration_symbols)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
        futures = {}
        for scenario in scenarios:
            for phase_index, phase_ui in enumerate(PHASES_UI):
                name = 'cal_%s_p%d' % (scenario['name'], phase_index)
                future = workers.submit(simulate_and_analyze, project, scenario, name,
                                        calibration_symbols, train_count, 0, phase_ui)
                futures[future] = name
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                summary['calibration'].append(result)
                checkpoint({'event': 'calibration_complete', 'run': name,
                            'score': result['selection']['quality_score'],
                            'training_SER': result['selection']['training_SER']})
            except Exception as error:
                summary['errors'].append({'run': name, 'error': repr(error)})
                checkpoint({'event': 'calibration_failed', 'run': name, 'error': repr(error)})

    for scenario in scenarios:
        available = [record for record in summary['calibration'] if record['scenario'] == scenario['name']]
        if len(available) != len(PHASES_UI):
            summary['status'] = 'failed_calibration'
            checkpoint({'event': 'stopped', 'reason': 'incomplete phase calibration'})
            return summary
        best = max(available, key=lambda record: record['selection']['quality_score'])
        summary['selected_calibration'][scenario['name']] = best['selection']
    checkpoint({'event': 'calibration_selected', 'selections': {
        name: {'phase_UI': selection['phase_UI'], 'lag_UI': selection['integer_symbol_lag'],
               'quality_score': selection['quality_score']}
        for name, selection in summary['selected_calibration'].items()}})

    validation_jobs = []
    for scenario in scenarios:
        selection = summary['selected_calibration'][scenario['name']]
        validation_jobs.append(('validation', scenario, 'full_' + scenario['name'],
                                selection, {}))
    high_loss = scenarios[2]
    selection = summary['selected_calibration'][high_loss['name']]
    half_ui = .5 * UI
    for suffix, p_delay, n_delay in [('positive', half_ui, 0.0), ('negative', 0.0, half_ui)]:
        validation_jobs.append(('PN_skew', high_loss, 'pn_' + suffix, selection,
                                {'p_delay': p_delay, 'n_delay': n_delay}))
    validation_jobs.append(('PN_skew', high_loss, 'pn_oracle_aligned', selection,
                            {'p_delay': half_ui, 'n_delay': half_ui,
                             'common_clock_delay': half_ui, 'reference_delay': half_ui}))
    if with_noise:
        validation_jobs.append(('noise_validation', high_loss, 'noise_synthetic_20dB',
                                selection, {'noise': True}))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
        futures = {}
        for group, scenario, name, selection, extra in validation_jobs:
            future = workers.submit(simulate_and_analyze, project, scenario, name,
                                    full_symbols, train_count, validation_count,
                                    selection['phase_UI'], frozen_selection=selection, **extra)
            futures[future] = (group, name)
        for future in concurrent.futures.as_completed(futures):
            group, name = futures[future]
            try:
                result = future.result()
                if group == 'PN_skew':
                    result['PN_method'] = ('oracle delay: both P/N delayed0.5UI; sample clocks and '
                        'label time reference shifted by the same common delay; frozen baseline detector; '
                        'identical ideal bound for correcting either endpoint, not physical deskew or estimation'
                        if name == 'pn_oracle_aligned' else
                        'uncorrected endpoint; one input leg delayed0.5UI; baseline sampling phase and '
                        'detector frozen; no CDR recentering')
                summary[group].append(result)
                checkpoint({'event': 'validation_complete', 'run': name,
                            'SER': result['metrics']['raw']['validation']['SER'],
                            'symbol_errors': result['metrics']['raw']['validation']['symbol_errors']})
            except Exception as error:
                summary['errors'].append({'run': name, 'error': repr(error)})
                checkpoint({'event': 'validation_failed', 'run': name, 'error': repr(error)})

    summary['status'] = 'complete' if not summary['errors'] else 'complete_with_errors'
    summary['verification'] = {'expected_calibration_runs': 12,
                               'actual_calibration_runs': len(summary['calibration']),
                               'expected_noiseless_validation_runs': 6,
                               'actual_noiseless_validation_runs': len(summary['validation']) + len(summary['PN_skew']),
                               'metrics_self_check': metrics.self_check(),
                               'script_sha256': file_hash(Path(__file__))}
    checkpoint({'event': 'finished', 'status': summary['status']})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=PROJECT)
    parser.add_argument('--smoke', action='store_true', help='one native bypass run,64 training+128 validation symbols')
    parser.add_argument('--with-noise', action='store_true', help='add one actual transient-noise20dB validation run')
    arguments = parser.parse_args()
    result = run(arguments.project, arguments.smoke, arguments.with_noise)
    return 0 if result['status'] == 'complete' else 1


if __name__ == '__main__':
    sys.exit(main())
