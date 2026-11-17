#!/usr/bin/env python3
"""Measure admitted small-signal time-domain modal probes. Never fits an FFE."""
import argparse
import cmath
import csv
import json
import math
import re
from pathlib import Path
import admit
import collect_r5 as C
import pn_stage


def solve3(matrix, vector):
    a = [list(row) + [value] for row, value in zip(matrix, vector)]
    for j in range(3):
        pivot = max(range(j, 3), key=lambda k: abs(a[k][j]))
        admit.require(abs(a[pivot][j]) > 1e-12, 'Tone least-squares basis is singular')
        a[j], a[pivot] = a[pivot], a[j]
        v = a[j][j]
        a[j] = [x / v for x in a[j]]
        for k in range(3):
            if k != j:
                v = a[k][j]
                a[k] = [x - v * y for x, y in zip(a[k], a[j])]
    return [a[j][3] for j in range(3)]


def fit_tone(times, values, frequency):
    admit.require(len(times) == len(values) >= 20, 'Too few tone samples')
    admit.require(all(math.isfinite(x) for x in times + values) and
                  all(b > a for a, b in zip(times, times[1:])), 'Nonfinite/unordered tone data')
    width = times[-1] - times[0]
    admit.require(width * frequency >= 19.9, 'Insufficient tone observation')
    weights = [(times[1] - times[0]) / 2] + [(times[k+1] - times[k-1]) / 2 for k in range(1, len(times)-1)] + [(times[-1] - times[-2]) / 2]
    weights = [w / width for w in weights]
    features = [[math.sin(2 * math.pi * frequency * t), math.cos(2 * math.pi * frequency * t), 1.] for t in times]
    matrix = [[sum(w * f[j] * f[k] for w, f in zip(weights, features)) for k in range(3)] for j in range(3)]
    vector = [sum(w * f[j] * v for w, f, v in zip(weights, features, values)) for j in range(3)]
    sine, cosine, dc = solve3(matrix, vector)
    residual = math.sqrt(sum(w * (v - sine*f[0] - cosine*f[1] - dc)**2 for w, f, v in zip(weights, features, values)))
    phasor = complex(cosine, -sine)  # Re{phasor * exp(jwt)}
    return {'phasor_real_V': phasor.real, 'phasor_imag_V': phasor.imag,
            'amplitude_peak_V': abs(phasor), 'phase_rad': cmath.phase(phasor),
            'dc_V': dc, 'residual_rms_V': residual, 'sample_count': len(times),
            'coverage_s': [times[0], times[-1]], 'method': 'Trapezoid-time-weighted sin/cos/DC least squares; no phase or window selection'}


def collect(admission_path, run_dir, output):
    root = Path(run_dir).resolve()
    profile = pn_stage.verify_stage(admission_path, root)
    admission = admit.read_admission(admission_path, verify=True)
    case = profile['case']
    admit.require(case['kind'] in ('tone_dm', 'tone_cm'), 'Tone collector only')
    functions = C.original_functions(admission['source_dir'])
    raw_path = C.ensure_end(functions.a._raw_file(root))
    raw_before = C.file_snapshot(raw_path)
    raw = functions.a.parse_file(raw_path)
    t = C.validate_raw(raw, profile['stop_s'])
    status, status_sha = C.verify_run_status(root, raw_path, profile, case, raw.sha256)
    log = admit.regular_file(root / 'spectre.log')
    admit.require(log.stat().st_size <= 32 * 1024 * 1024, 'Spectre log exceeds bound')
    log_before, log_sha = C.file_snapshot(log), admit.sha256_file(log)
    admit.require(re.search(r'spectre completes with\s+0\s+errors\b',
                  log.read_text(encoding='utf-8', errors='replace'), re.I),
                  'Completed zero-error Spectre log required; no pass inferred')
    required = ('X_ip', 'X_im', 'X_o_p', 'X_o_m')
    admit.require(all(n in raw.values for n in required), 'Missing saved native AFE modal nodes')
    lo, hi = case['measurement_window_s']
    chosen = [j for j, value in enumerate(t) if lo <= value <= hi]
    admit.require(chosen and t[chosen[0]] - lo <= C.STROBE * 1.01 and hi - t[chosen[-1]] <= C.STROBE * 1.01,
                  'Requested tone window is not fully sampled')
    times = [t[j] for j in chosen]
    v = raw.values
    series = {
        'AFE_input_differential': [v['X_ip'][j] - v['X_im'][j] for j in chosen],
        'AFE_input_common': [(v['X_ip'][j] + v['X_im'][j]) / 2 for j in chosen],
        'AFE_output_differential': [v['X_o_p'][j] - v['X_o_m'][j] for j in chosen],
        'AFE_output_common': [(v['X_o_p'][j] + v['X_o_m'][j]) / 2 for j in chosen],
    }
    fits = {name: fit_tone(times, data, case['frequency_Hz']) for name, data in series.items()}
    reference = complex(0., -case['tone_peak_V'])
    transfer = {}
    for name, fit in fits.items():
        value = complex(fit['phasor_real_V'], fit['phasor_imag_V']) / reference
        transfer[name] = {'real': value.real, 'imag': value.imag, 'magnitude_V_per_V': abs(value),
                          'phase_rad': cmath.phase(value)}
    admit.require(pn_stage.verify_stage(admission_path, root) == profile and
                  C.verify_run_status(root, raw_path, profile, case, raw.sha256)[1] == status_sha,
                  'Stage/runner changed during tone measurement')
    admit.require(C.file_snapshot(raw_path) == raw_before and admit.sha256_file(raw_path) == raw.sha256 and
                  C.file_snapshot(log) == log_before and admit.sha256_file(log) == log_sha,
                  'Raw/log changed during tone measurement')
    output = Path(output).resolve()
    admit.require(admit.inside(output, root) and not output.exists(), 'New result inside own run-dir required')
    result = {'format': 'pn_skew_native_modal_probe_v1', 'measurement_complete': True, 'case': case,
              'fits': fits, 'normalized_to_TX_modal_peak': transfer,
              'units': {'voltage': 'V', 'frequency': 'Hz', 'time': 's', 'phase': 'rad', 'transfer': 'V/V'},
              'profile_sha256': admit.sha256_file(root / 'profile.json'),
              'input_deck_sha256': admit.sha256_file(root / 'bench.scs'), 'raw_sha256': raw.sha256,
              'run_status_sha256': status_sha, 'complete_ADC_verified': False,
              'raw': {'path': str(raw_path), 'relative_path': raw_path.relative_to(root).as_posix(),
                      'bytes': raw_before[2], 'sha256': raw.sha256, 'time_sample_count': len(t),
                      'first_time_s': t[0], 'last_time_s': t[-1], 'requested_stop_s': profile['stop_s']},
              'provenance': {'admission_sha256': admit.sha256_file(admission_path),
                  'profile_sha256': admit.sha256_file(root / 'profile.json'),
                  'case_json_sha256': admit.sha256_file(root / 'case.json'),
                  'input_deck_sha256': admit.sha256_file(root / 'bench.scs'),
                  'source_deck_sha256': profile['source_deck_sha256'],
                  'frozen_r5_sha256': admission['frozen_r5']['sha256'],
                  'source_scripts': admission['source_scripts'], 'auxiliary_scripts': admission['auxiliary_scripts'],
                  'model_files': admission['model_files'], 'run_status_sha256': status_sha,
                  'spectre_log_sha256': log_sha, 'collector_sha256': admit.sha256_file(__file__),
                  'raw_input_binding': 'New exclusive-run runner attestation checked; not cryptographic proof of simulator execution.'},
              'signal_definition': 'Vd=Vp-Vn; Vcm=(Vp+Vn)/2. DM stimulus peak is total differential; CM stimulus peak is per-leg common.',
              'reference_path': 'TX modal source through synthetic channel and native AFE, before primary sampler',
              'linearity': 'Compare predeclared 0.5mV and1mV zero-skew cases before interpreting as small-signal transfer.',
              'limitations': ['Time-domain small-signal probe, not an ADC timing or BER qualification.',
                              'P/N skew is inserted before the channel; clocks and mean source delay remain unchanged.',
                              'PWL source uses128 points/tone cycle; repeat at256 before final sub-0.01dB claims.',
                              'No measured physical PN compensator exists in this experiment.']}
    clip_path = output.with_name(output.stem + '.short_waveform.csv')
    admit.require(not clip_path.exists(), 'Short-clip output exists')
    view = [k for k, value in enumerate(times) if value <= times[0] + 8 / case['frequency_Hz']]
    view = view[::max(1, int(math.ceil(len(view) / 512.)))]
    with clip_path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        keys = ['AFE_input_differential', 'AFE_input_common', 'AFE_output_differential', 'AFE_output_common']
        writer.writerow(['time_s'] + [k + '_V' for k in keys])
        writer.writerows([[times[j]] + [series[k][j] for k in keys] for j in view])
    result['short_waveform_csv'] = {'path': str(clip_path), 'rows': len(view),
        'bytes': clip_path.stat().st_size, 'window_s': [times[view[0]], times[view[-1]]],
        'sha256': admit.sha256_file(clip_path), 'units': 's, V',
        'selection': 'Fixed first8tone cycles of the predeclared observation window; atmost512 original samples, no data-selected window.'}
    admit.write_new_json(output, result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--admission', required=True); p.add_argument('--run-dir', required=True); p.add_argument('--output', required=True)
    a = p.parse_args(); r = collect(a.admission, a.run_dir, a.output)
    print(json.dumps({'measurement_complete': r['measurement_complete'], 'output': a.output}))
