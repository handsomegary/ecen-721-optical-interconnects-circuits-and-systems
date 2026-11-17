#!/usr/bin/env python3
"""Create native ViVA sampled-phase views after all 18 cases finish; Python 3.6.

This script performs no simulation, fitting, phase choice, plotting, networking,
or PDK access. Every real decision value and native plotting file stays in the
designated VM project. The --self-test uses synthetic values only.
"""
import argparse
import bisect
import csv
import datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile

PROJECT = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
ROOT = PROJECT/'runs/ffe_phase_sweep_20261022'
OUTPUT = ROOT/'viva_sampled_eye'
FROZEN = PROJECT/'runs/adc_backend_pam4_r5_20261013/r5_late1/frozen.json'
FROZEN_SHA = '4cda4c9ec967f2af4bf4f89eacdd1beae372668877c358cf6aa26092597482eb'
DELTAS = (-.5, -.375, -.25, -.125, 0., .125, .25, .375, .5)
INDICES = tuple(range(264, 760))
KINDS = ('noiseless', 'noise')
BRANCHES = ('primary', 'secondary')
SCOPE = ('Native ViVA scatter display of actual clock-phase simulation samples '
         'after ideal numerical 7-bit quantization and the frozen digital FFE. '
         'Nine tested phases, 496 fixed target symbols per phase. No interpolation, '
         'no physical continuous-time FFE waveform, no physical ADC/FFE verification.')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False)+'\n')


def checked_rows(content, expected_phase):
    rows = []
    for row in csv.DictReader(io.StringIO(content), delimiter='\t'):
        phase = float(row['delta_phase_UI'])
        index = int(row['target_symbol_index'])
        true = int(row['true_symbol'])
        amplitude = float(row['target_amplitude'])
        value = float(row['ADC_FFE_target_units'])
        decision = int(row['ADC_FFE_decision'])
        if not all(math.isfinite(v) for v in (phase, amplitude, value)):
            raise ValueError('Nonfinite sampled-eye point')
        if phase != expected_phase or true not in range(4) or amplitude != 2*true-3:
            raise ValueError('Unexpected phase or PAM4 target label')
        if decision != bisect.bisect_right((-2., 0., 2.), value):
            raise ValueError('TSV decision does not match fixed thresholds')
        rows.append(dict(index=index, true=true, target=amplitude, value=value,
                         decision=decision, phase=phase))
    if tuple(row['index'] for row in rows) != INDICES:
        raise ValueError('Require the exact same ordered 496 target indices 264..759')
    return rows


def collect(root):
    """Refuse partial, re-fitted, mismatched, or modified inputs before writing."""
    root = Path(root)
    protocol_path, status_path = root/'protocol.json', root/'status.json'
    protocol = json.loads(protocol_path.read_text())
    status = json.loads(status_path.read_text())
    expected_cases = [(kind, index, delta) for kind in KINDS for index, delta in enumerate(DELTAS)]
    expected_names = ['%s_phase_%02d'%(kind, index) for kind, index, delta in expected_cases]
    if status.get('status') != 'complete' or status.get('current_case') is not None:
        raise ValueError('All 18 cases must be complete before creating eye views')
    completed = status.get('completed_cases', [])
    if [x['name'] for x in completed] != expected_names:
        raise ValueError('Completed case list does not match fixed protocol')
    if status.get('protocol_sha256') != digest(protocol_path):
        raise ValueError('Protocol hash changed')
    expected = dict(frozen_sha256=FROZEN_SHA, data_seed=2026102201, noise_seed=197,
                    FFE_complete_windows=496, score_input_symbols=512,
                    validation_fitting_performed=False, phase_selection_performed=False,
                    delta_phase_UI=list(DELTAS), target_FFE_indices=[264, 759])
    for key, value in expected.items():
        if protocol.get(key) != value:
            raise ValueError('Unexpected protocol field: '+key)
    if [x['name'] for x in protocol['cases']] != expected_names:
        raise ValueError('Unexpected protocol case order')
    datasets = {(kind, branch): [] for kind in KINDS for branch in BRANCHES}
    provenance = dict(protocol_sha256=digest(protocol_path), status_sha256=digest(status_path),
                      frozen_sha256=FROZEN_SHA, cases={})
    all_labels = None
    for ordinal, (kind, index, phase) in enumerate(expected_cases):
        name = expected_names[ordinal]
        directory = root/name
        summary_path = directory/'summary.json'
        if digest(summary_path) != completed[ordinal]['summary_sha256']:
            raise ValueError('Case summary changed: '+name)
        summary = json.loads(summary_path.read_text())
        case = summary['case']
        if (case['name'] != name or case['kind'] != kind or
                case['delta_phase_UI'] != phase or
                case['noise_seed'] != (None if kind == 'noiseless' else 197)):
            raise ValueError('Case metadata mismatch: '+name)
        if (summary.get('status') != 'analysis_complete' or
                summary.get('run_status', {}).get('exit_code') != 0 or
                summary.get('frozen_sha256') != FROZEN_SHA or
                summary.get('frozen_unchanged') is not True or
                summary.get('validation_fitting_performed') is not False or
                summary.get('phase_selection_performed') is not False or
                summary.get('protocol_sha256') != provenance['protocol_sha256']):
            raise ValueError('Case is not a verified frozen completed run: '+name)
        source_hashes = {}
        for branch in BRANCHES:
            info = summary['branches'][branch]
            filename = 'ffe_'+branch+'_decision_points.tsv'
            if (info['TSV_file'] != filename or info['FFE_output_count'] != 496 or
                    info['input_sample_count'] != 512 or digest(directory/filename) != info['TSV_sha256']):
                raise ValueError('Decision TSV identity or point count changed')
            rows = checked_rows((directory/filename).read_text(), phase)
            labels = [(row['index'], row['true']) for row in rows]
            if all_labels is None:
                all_labels = labels
            if labels != all_labels:
                raise ValueError('Different symbol sequence across phases or branches')
            errors = sum(row['decision'] != row['true'] for row in rows)
            metric = info['metrics']['ideal7bit_ADC_then_FFE']
            if metric['sample_count'] != 496 or metric['symbol_errors'] != errors:
                raise ValueError('Independent TSV error count disagrees with summary')
            datasets[(kind, branch)].append(rows)
            source_hashes[filename] = info['TSV_sha256']
        provenance['cases'][name] = dict(summary_sha256=digest(summary_path), TSV_sha256=source_hashes,
                                        raw_transient_sha256=summary['raw_transient_sha256'],
                                        deck_sha256=summary['deck_sha256'])
    return datasets, provenance


def viewer_source(final_directory):
    # Loading this file only defines functions. Plotting occurs only when the
    # user calls p6FfePlot/p6FfePlotErrors in their existing CIW session.
    base = str(final_directory).replace('\\', '/').replace('"', '\\"')
    return r'''; Native ViVA helper; generated on VM from verified completed phase cases.
; Never use eyeDiagram() on this 1 sample/symbol numerical FFE output.
; X = commanded sampling clock offset in UI; Y = dimensionless target amplitude.
; Only nine measured phase points exist. Scatter style intentionally draws no lines.
p6FfeViewDirectory = "@BASE@"

procedure(p6FfeCheckChoice(kind branch)
  unless(member(kind list("noiseless" "noise")) && member(branch list("primary" "secondary"))
    error("Use kind noiseless/noise and branch primary/secondary.\n")
  )
  t
)

procedure(p6FfeWave(kind branch index)
  let((wave)
    p6FfeCheckChoice(kind branch)
    unless(fixp(index) && index >= 264 && index <= 759
      error("Target index must be an integer from 264 through 759.\n")
    )
    wave = getAsciiWave(sprintf(nil "%s/%s_%s/target_%04d.xy" p6FfeViewDirectory kind branch index)
      1 2 ?formatFloat t ?xName "sampling_phase_offset" ?xUnits "UI"
      ?yName "frozen_ADC_FFE_target_amplitude" ?yUnits "")
    unless(wave && drVectorLength(drGetWaveformXVec(wave)) == 9
      error("Missing or malformed nine-phase data for target %d.\n" index)
    )
    wave
  )
)

procedure(p6FfeFamily(kind branch)
  let((family index)
    p6FfeCheckChoice(kind branch)
    family = famCreateFamily("target_symbol_index" 'double)
    for(index 264 759
      famAddValue(family index p6FfeWave(kind branch index))
    )
    family
  )
)

procedure(p6FfeErrorWave(kind branch)
  p6FfeCheckChoice(kind branch)
  getAsciiWave(sprintf(nil "%s/%s_%s_errors.xy" p6FfeViewDirectory kind branch)
    1 2 ?formatFloat t ?xName "sampling_phase_offset" ?xUnits "UI"
    ?yName "observed_symbol_error_fraction_496" ?yUnits "")
)

procedure(p6FfeCheckAll()
  let((wave count kind branch index)
    count = 0
    foreach(kind list("noiseless" "noise")
      foreach(branch list("primary" "secondary")
        for(index 264 759
          wave = p6FfeWave(kind branch index)
          count = count + drVectorLength(drGetWaveformYVec(wave))
        )
        wave = p6FfeErrorWave(kind branch)
        unless(wave && drVectorLength(drGetWaveformYVec(wave)) == 9
          error("Missing error-vs-phase data.\n")
        )
      )
    )
    printf("P6_NATIVE_DATA_CHECK_OK %d sampled points; no windows opened.\n" count)
    count
  )
)

procedure(p6FfePlot(kind branch)
  let((wave window)
    wave = p6FfeFamily(kind branch)
    window = awvCreatePlotWindow()
    awvPlotWaveform(window list(wave)
      ?expr list(sprintf(nil "%s %s: sampled phase eye; ideal ADC + frozen FFE" kind branch))
      ?showSymbols t)
    unless(awvSetPlotStyle(window "scatterPlot")
      error("Set native plot style to Scatter before interpreting phase data.\n")
    )
    printf("Only nine tested phases. Y is target symbol amplitude, not volts. Thresholds: -2, 0, 2.\n")
    window
  )
)

procedure(p6FfePlotErrors()
  let((waves labels window kind branch)
    waves = nil
    labels = nil
    foreach(kind list("noiseless" "noise")
      foreach(branch list("primary" "secondary")
        waves = cons(p6FfeErrorWave(kind branch) waves)
        labels = cons(sprintf(nil "%s %s: observed SER, N=496" kind branch) labels)
      )
    )
    window = awvCreatePlotWindow()
    awvPlotWaveform(window reverse(waves) ?expr reverse(labels) ?showSymbols t)
    unless(awvSetPlotStyle(window "scatterPlot")
      error("Set native plot style to Scatter before interpreting phase data.\n")
    )
    window
  )
)

printf("P6 FFE helper loaded; no windows opened. Use p6FfePlot(\"noise\" \"secondary\") or p6FfePlotErrors().\n")
'''.replace('@BASE@', base)


def write_views(directory, datasets, provenance, final_directory):
    directory = Path(directory)
    directory.mkdir()
    report = []
    for kind in KINDS:
        for branch in BRANCHES:
            phases = datasets[(kind, branch)]
            if len(phases) != 9 or any(len(rows) != 496 for rows in phases):
                raise ValueError('Expected nine phases of 496 samples')
            subdir = directory/(kind+'_'+branch)
            subdir.mkdir()
            for position, index in enumerate(INDICES):
                # One symbol's values at nine ACTUALLY SIMULATED phases. No
                # synthesized intermediate points, resampling, fitting or delay.
                values = [(delta, rows[position]['value']) for delta, rows in zip(DELTAS, phases)]
                (subdir/('target_%04d.xy'%index)).write_text(''.join('%.17g %.17g\n'%p for p in values))
            errors = [sum(row['decision'] != row['true'] for row in rows) for rows in phases]
            (directory/(kind+'_'+branch+'_errors.xy')).write_text(''.join(
                '%.17g %.17g\n'%(phase, count/496.) for phase, count in zip(DELTAS, errors)))
            for phase, count in zip(DELTAS, errors):
                report.append(dict(kind=kind, branch=branch, delta_phase_UI=phase,
                                   symbol_errors=count, symbols=496, observed_SER=count/496.))
    (directory/'view_sampled_eye.il').write_text(viewer_source(final_directory))
    (directory/'check_native_data.ocn').write_text(
        'load("%s/view_sampled_eye.il")\n'%str(final_directory).replace('\\', '/')+
        'unless(p6FfeCheckAll() == 17856 error("Native point count mismatch.\\n"))\nexit()\n')
    write_json(directory/'sampled_eye_summary.json', dict(scope=SCOPE, results=report,
               data_seed=2026102201, noise_seed=197, points_per_view=4464,
               thresholds_target_units=[-2, 0, 2], target_amplitudes=[-3, -1, 1, 3],
               phase_selection_performed=False, validation_fitting_performed=False,
               statistical_scope='Observed 496-symbol fractions, correlated FFE errors; no BER certification.',
               noise_scope='Fixed noise seed, but phases are neither identical noise realizations nor independent repeats.'))
    write_json(directory/'provenance.json', dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
               script_sha256=digest(__file__), scope=SCOPE, input_provenance=provenance,
               file_sha256={str(path.relative_to(directory)).replace('\\', '/'):digest(path)
                            for path in sorted(directory.rglob('*')) if path.is_file()}))


def build():
    if os.name != 'posix' or not (PROJECT/'.codex_project6_owned').is_file():
        raise RuntimeError('Real data aggregation runs only in the designated VM project')
    if PROJECT.resolve() != PROJECT or ROOT.resolve() != ROOT or digest(FROZEN) != FROZEN_SHA:
        raise RuntimeError('Unexpected project path or modified frozen design')
    if OUTPUT.exists():
        raise RuntimeError('Native view directory already exists; refusing overwrite')
    datasets, provenance = collect(ROOT)
    pending = ROOT/('viva_sampled_eye_incomplete_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S'))
    write_views(pending, datasets, provenance, OUTPUT)
    if digest(FROZEN) != FROZEN_SHA:
        raise RuntimeError('Frozen design changed during aggregation')
    pending.rename(OUTPUT)
    print(json.dumps(dict(status='native_view_data_ready', path=str(OUTPUT),
                          GUI_opened=False, simulations_started=0, scope=SCOPE)))


def fixture_tsv(phase, corrupt=None):
    stream = io.StringIO()
    stream.write('delta_phase_UI\ttarget_symbol_index\ttrue_symbol\ttarget_amplitude\tADC_FFE_target_units\tADC_FFE_decision\n')
    for index in INDICES:
        label = index % 4
        value = 2*label-3+phase*.125
        if corrupt == 'nonfinite' and index == 264:
            value = float('nan')
        decision = bisect.bisect_right((-2., 0., 2.), value)
        stream.write('%s\t%d\t%d\t%d\t%s\t%d\n'%(phase, index, label, 2*label-3, value, decision))
    return stream.getvalue()


def fixture_complete(root):
    """Synthetic integrity fixture; no model, netlist or simulator access."""
    root.mkdir()
    cases = [dict(name='%s_phase_%02d'%(kind, index), kind=kind, delta_phase_UI=delta,
                  noise_seed=None if kind == 'noiseless' else 197)
             for kind in KINDS for index, delta in enumerate(DELTAS)]
    protocol = dict(frozen_sha256=FROZEN_SHA, data_seed=2026102201, noise_seed=197,
                    FFE_complete_windows=496, score_input_symbols=512,
                    validation_fitting_performed=False, phase_selection_performed=False,
                    delta_phase_UI=list(DELTAS), target_FFE_indices=[264, 759], cases=cases)
    write_json(root/'protocol.json', protocol)
    protocol_hash = digest(root/'protocol.json')
    completed = []
    for case in cases:
        directory = root/case['name']
        directory.mkdir()
        summary = dict(case=case, status='analysis_complete', run_status=dict(exit_code=0),
                       frozen_sha256=FROZEN_SHA, frozen_unchanged=True,
                       validation_fitting_performed=False, phase_selection_performed=False,
                       protocol_sha256=protocol_hash, raw_transient_sha256='synthetic-only',
                       deck_sha256='synthetic-only', branches={})
        for branch in BRANCHES:
            filename = 'ffe_'+branch+'_decision_points.tsv'
            (directory/filename).write_text(fixture_tsv(case['delta_phase_UI']))
            summary['branches'][branch] = dict(TSV_file=filename, TSV_sha256=digest(directory/filename),
                FFE_output_count=496, input_sample_count=512,
                metrics=dict(ideal7bit_ADC_then_FFE=dict(sample_count=496, symbol_errors=0)))
        write_json(directory/'summary.json', summary)
        completed.append(dict(name=case['name'], summary_sha256=digest(directory/'summary.json')))
    write_json(root/'status.json', dict(status='complete', current_case=None,
               protocol_sha256=protocol_hash, completed_cases=completed))


def self_test():
    datasets = {(kind, branch): [checked_rows(fixture_tsv(phase), phase) for phase in DELTAS]
                for kind in KINDS for branch in BRANCHES}
    for bad in (fixture_tsv(0, 'nonfinite'), fixture_tsv(.125), '\n'.join(fixture_tsv(0).splitlines()[:-1])):
        try:
            checked_rows(bad, 0.)
        except ValueError:
            pass
        else:
            raise AssertionError('Malformed input was accepted')
    # Temporary directory contains generated SYNTHETIC data only and is owned by
    # this context. No remote result or PDK file is involved in this test.
    with tempfile.TemporaryDirectory(prefix='p6_viva_synthetic_',
                                     dir=str(Path(__file__).resolve().parent)) as temporary:
        source = Path(temporary)/'synthetic_complete_study'
        fixture_complete(source)
        collected, provenance = collect(source)
        if collected != datasets or len(provenance['cases']) != 18:
            raise AssertionError('Complete integrity fixture differs from expected points')
        state_path = source/'status.json'
        state = json.loads(state_path.read_text())
        state['status'] = 'simulating'
        write_json(state_path, state)
        try:
            collect(source)
        except ValueError:
            pass
        else:
            raise AssertionError('Partial study was accepted')
        state['status'] = 'complete'
        write_json(state_path, state)
        tsv_path = source/'noise_phase_08/ffe_secondary_decision_points.tsv'
        tsv_path.write_text(tsv_path.read_text()+'\n')
        try:
            collect(source)
        except ValueError:
            pass
        else:
            raise AssertionError('Altered TSV hash was accepted')
        directory = Path(temporary)/'views'
        write_views(directory, datasets, dict(synthetic_fixture=True), directory)
        paths = list(directory.rglob('*.xy'))
        if len(paths) != 1988:
            raise AssertionError('Incorrect native XY trace count')
        first = directory/'noise_secondary/target_0264.xy'
        actual = [[float(v) for v in row.split()] for row in first.read_text().splitlines()]
        if [row[0] for row in actual] != list(DELTAS) or len(actual) != 9:
            raise AssertionError('Phase points changed')
        summary = json.loads((directory/'sampled_eye_summary.json').read_text())
        if len(summary['results']) != 36 or any(x['symbol_errors'] for x in summary['results']):
            raise AssertionError('Synthetic noiseless label accounting failed')
    return dict(status='passed', simulations_started=0, native_Cadence_execution=False,
                tests=['same 496 indices across nine phases', 'malformed/nonfinite/partial TSV rejected',
                       'complete 18-case provenance accepted; partial study and changed TSV rejected',
                       '1984 nine-point symbol XY traces plus four SER traces',
                       '36 independently counted phase/branch/mode error records'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--build', action='store_true')
    group.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test()))
    else:
        build()


if __name__ == '__main__':
    main()
