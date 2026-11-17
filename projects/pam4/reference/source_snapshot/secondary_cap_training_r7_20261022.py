#!/usr/bin/env python3
"""Six-case secondary capacitor/switch TRAINING screen; Python 3.6.

New data2026102202/noise223. Three predeclared hardware candidates, no phase,
lag, range, current, resistance or architecture search. Each candidate gets a
noiseless first256-only raw/ideal7bit 17-tap fit, frozen before its paired
noise run. The disjoint remaining240 inputs give224 complete FFE scores.
All results stay in the designated VM project. No holdout is read or run.
Any simulator, analysis or integrity failure terminates this finite study.
"""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import sys
import time

sys.dont_write_bytecode = True
PROJECT = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
ROOT = PROJECT/'runs/secondary_cap_training_r7_20261022'
FROZEN = PROJECT/'runs/adc_backend_pam4_r5_20261013/r5_late1/frozen.json'
FROZEN_SHA = '4cda4c9ec967f2af4bf4f89eacdd1beae372668877c358cf6aa26092597482eb'
HELPER = PROJECT/'scripts/ffe_phase_sweep_20261022.py'
HELPER_SHA = '660a374e1da30b5fec84aed9e99a8ecba7de65466532767c83ff2e87ec172a8e'
RUNNER = PROJECT/'scripts/ffe_phase_resume2_20261022.py'
RUNNER_SHA = '1a01d14b611f5e3cad372bb428d4768acad181fd723a84fe55a90c70bbf97b2b'
DATA_SEED, NOISE_SEED = 2026102202, 223
WARMUP, TRAIN, GUARD = 256, 512, 128
FIT, SPLIT_GUARD, SCORE, HALF = 256, 16, 240, 8
LAGS = {'primary': 1, 'secondary': 3}
RANGES = {'primary': .100, 'secondary': .075}
CASE_TIMEOUT, WAIT_TIMEOUT, OUTER_TIMEOUT = 3600, 1800, 10*3600
MIN_FREE = 8*1024**3
CANDIDATES = ('baseline_r5', 'secondary_c25_w1', 'secondary_c25_w2')
SCOPE = ('Training-only native r5 AFE/primary/CML/secondary TG-cap screen; '
         'numerical7bit quantizer and17tapFFE, reset comparators, ideal clocks; '
         'no full ADC or final BER certification. No previous holdout is read.')


def utc():
    return datetime.datetime.utcnow().isoformat()+'Z'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode('utf-8')).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n')
    temp.replace(path)


def checkpoint(state, status, **extra):
    state.update(status=status, updated_utc=utc(), **extra)
    write_json(ROOT/'status.json', state)


def verified_import(path, expected, name):
    if digest(path) != expected:
        raise RuntimeError('Reviewed dependency SHA mismatch: '+Path(path).name)
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_verified():
    if digest(FROZEN) != FROZEN_SHA:
        raise RuntimeError('Original r5 frozen identity changed')
    helper = verified_import(HELPER, HELPER_SHA, 'r7_original_phase_helper')
    runner = verified_import(RUNNER, RUNNER_SHA, 'r7_reviewed_session_runner')
    # run_case and await_capacity use this module variable for checkpoints.
    runner.ROOT = ROOT
    frozen, backend, ffe, metrics, psf = helper.load_verified()
    if ffe.TAPS != 17 or ffe.HALF != HALF:
        raise RuntimeError('Unexpected FFE implementation')
    return helper, runner, frozen, backend, ffe, metrics, psf


def configurations(baseline):
    if (baseline['secondary_cap_F'] != 10e-15 or
            baseline['secondary_switch_width_m'] != 1e-6):
        raise RuntimeError('Expected original r5_late1 secondary10fF/1um')
    result = {name: copy.deepcopy(baseline) for name in CANDIDATES}
    result['secondary_c25_w1'].update(secondary_cap_F=25e-15, secondary_switch_width_m=1e-6)
    result['secondary_c25_w2'].update(secondary_cap_F=25e-15, secondary_switch_width_m=2e-6)
    for name, cfg in result.items():
        allowed = {'secondary_cap_F', 'secondary_switch_width_m'}
        if any(cfg[key] != baseline[key] for key in baseline if key not in allowed):
            raise RuntimeError('Unexpected hardware change: '+name)
    return result


def case_specs():
    return [dict(name=kind+'_'+candidate, kind=kind, candidate=candidate,
                 noise_seed=None if kind == 'noiseless' else NOISE_SEED)
            for kind in ('noiseless', 'noise') for candidate in CANDIDATES]


def symbols_new():
    rng = random.Random(DATA_SEED)
    return [rng.randrange(4) for unused in range(WARMUP+TRAIN+GUARD)]


def audit_deck(base, deck, clocks_base, clocks, candidate):
    if clocks_base != clocks or len(base) != len(deck):
        raise RuntimeError('Candidate clock/mapping or deck shape changed')
    changed = []
    for old, new in zip(base, deck):
        if old == new:
            continue
        token = old.split()[0]
        if token != new.split()[0]:
            raise RuntimeError('Deck instance identity changed')
        cap = re.fullmatch(r'B[0-7]_CH[0-7][pm]', token)
        switch = re.fullmatch(r'B[0-7]_S[NP][0-7][pm]', token)
        if not cap and not (switch and candidate == 'secondary_c25_w2'):
            raise RuntimeError('Unexpected changed instance: '+token)
        changed.append(token)
    expect = 0 if candidate == 'baseline_r5' else (384 if candidate.endswith('w2') else 128)
    if len(changed) != expect:
        raise RuntimeError('Expected only128 secondary caps and optionally256 TG devices to change')
    pulse_sources = sum('vsource type=pulse ' in line for line in deck)
    if pulse_sources != 144:
        raise RuntimeError('Expected144 unchanged complementary clock sources')
    return dict(changed_instance_count=len(changed), changed_instances=changed,
                clock_specifications_unchanged=True, pulse_sources_unchanged=pulse_sources)


def make_protocol(helper, frozen, configs, symbols):
    return dict(schema_version=1, created_utc=utc(), scope=SCOPE, training_only=True,
                script_sha256=digest(__file__), frozen_sha256=FROZEN_SHA,
                helper_sha256=HELPER_SHA, runner_sha256=RUNNER_SHA,
                dependency_hashes=dict(frozen['identity']['scripts']),
                additional_dependency_hashes=helper.loaded_project_sources(),
                data_seed=DATA_SEED, noise_seed=NOISE_SEED,
                symbol_sequence_sha256=canonical(symbols), generated_symbols=len(symbols),
                warmup_symbols=WARMUP, training_input_symbols=TRAIN, end_guard_symbols=GUARD,
                first_fit_input_symbols=FIT, internal_guard_symbols=SPLIT_GUARD,
                score_input_symbols=SCORE, fit_complete_FFE_windows=FIT-2*HALF,
                score_complete_FFE_windows=SCORE-2*HALF,
                fit_target_indices=[WARMUP, WARMUP+FIT-1],
                score_target_indices=[WARMUP+FIT+SPLIT_GUARD, WARMUP+TRAIN-1],
                score_FFE_center_indices=[WARMUP+FIT+SPLIT_GUARD+HALF, WARMUP+TRAIN-HALF-1],
                fixed_lags=LAGS, fixed_quantizer_fullscale_Vpp=RANGES,
                fixed_ridge=1e-3, fixed_thresholds=[-2., 0., 2.],
                configurations=configs, cases=case_specs(),
                detector_policy='Per candidate fit raw/ADC FFE on first256 noiseless inputs only; freeze before paired noise. No refit for noise, no lag/phase/range selection.',
                score_policy='240 later inputs after16symbol guard; independently windowed224 centered17tap outputs; all training screen, no fresh holdout.',
                candidate_ranking_scope='Training-only comparison; no automatic hardware adoption or fresh holdout launch.',
                independent_noise_replicates=False,
                noise_scope='Fixed seed223 does not make analog noise realization identical across changed hardware.',
                limits_s=dict(per_case=CASE_TIMEOUT, capacity_wait=WAIT_TIMEOUT, whole=OUTER_TIMEOUT),
                minimum_free_bytes=MIN_FREE, automatic_retry=False,
                complete_ADC_verified=False, physical_FFE_verified=False,
                holdout_read=False, holdout_launched=False,
                user_authorization='2026-10-22 explicit continue background improvement of secondary sampling branch',
                export_scope='Native/model/deck/raw/TSV/fits remain inside designated VM project.')


def assert_unchanged(protocol):
    if (digest(FROZEN) != FROZEN_SHA or digest(__file__) != protocol['script_sha256'] or
            digest(HELPER) != HELPER_SHA or digest(RUNNER) != RUNNER_SHA):
        raise RuntimeError('Frozen/source identity changed')
    for name, sha in protocol['dependency_hashes'].items():
        if Path(name).name != name or digest(PROJECT/'scripts'/name) != sha:
            raise RuntimeError('Frozen dependency changed: '+name)
    for relative, sha in protocol['additional_dependency_hashes'].items():
        path = (PROJECT/relative).resolve()
        if PROJECT not in path.parents or digest(path) != sha:
            raise RuntimeError('Additional dependency changed: '+relative)


def prepare(helper, runner, frozen, backend):
    if ROOT.exists() or ROOT.is_symlink():
        raise RuntimeError('Training root exists; never overwrite or reuse')
    configs = configurations(frozen['identity']['backend'])
    symbols = symbols_new()
    protocol = make_protocol(helper, frozen, configs, symbols)
    if shutil.disk_usage(str(PROJECT)).free < MIN_FREE:
        raise RuntimeError('Less than8GiB free before preparation')
    ROOT.mkdir()
    write_json(ROOT/'protocol.json', protocol)
    state = dict(started_utc=utc(), boot_id=runner.boot_id(), runner=helper.process_record(os.getpid()),
                 completed_cases=[], detector_sha256={}, current_case=None,
                 protocol_sha256=digest(ROOT/'protocol.json'), scope=SCOPE,
                 automatic_retry=False, training_only=True)
    checkpoint(state, 'preparing')
    try:
        baselines = {}
        for kind, seed in (('noiseless', None), ('noise', NOISE_SEED)):
            baselines[kind] = backend.build_deck(copy.deepcopy(frozen['identity']['frontend']),
                                               copy.deepcopy(configs['baseline_r5']), symbols, seed)
        for case in protocol['cases']:
            directory = ROOT/case['name']
            directory.mkdir()
            cfg = configs[case['candidate']]
            deck, clocks = backend.build_deck(copy.deepcopy(frozen['identity']['frontend']),
                                             copy.deepcopy(cfg), symbols, case['noise_seed'])
            original, base_clocks = baselines[case['kind']]
            audit = audit_deck(original, deck, base_clocks, clocks, case['candidate'])
            (directory/'bench.scs').write_text('\n'.join(deck)+'\n')
            write_json(directory/'prepared.json', dict(case=case, configuration=cfg,
                clock_specification=clocks, hardware_only_change_audit=audit,
                deck_sha256=digest(directory/'bench.scs'), symbol_sequence_sha256=canonical(symbols),
                status='prepared'))
        state['prepared_sha256'] = {case['name']: digest(ROOT/case['name']/'prepared.json')
                                    for case in protocol['cases']}
        assert_unchanged(protocol)
        checkpoint(state, 'prepared', simulations_started=0)
    except BaseException as error:
        checkpoint(state, 'preparation_failed', error=type(error).__name__+': '+str(error))
        raise
    return state


def align_fixed(records, symbols, lag):
    lookup = {row[0]-lag: row for row in records}
    if len(lookup) != len(records):
        raise ValueError('Duplicate sample reference index')
    indices = range(WARMUP, WARMUP+TRAIN)
    if any(index not in lookup for index in indices):
        raise ValueError('Incomplete fixed512symbol training interval')
    chosen = [lookup[index] for index in indices]
    return [row[1] for row in chosen], [symbols[index] for index in indices], chosen


def split_arrays(samples, labels):
    if len(samples) != TRAIN or len(labels) != TRAIN:
        raise ValueError('Expected512 aligned training samples')
    return (samples[:FIT], labels[:FIT],
            samples[FIT+SPLIT_GUARD:], labels[FIT+SPLIT_GUARD:])


def fit_detector(samples, labels, fullscale, ffe, metrics):
    first, first_labels, unused_samples, unused_labels = split_arrays(samples, labels)
    quantized, clipped = metrics.quantize_symmetric(first, fullscale, 7)
    fits = dict(raw_FFE=ffe.fit_ffe(first, first_labels, ridge=1e-3),
                ADC_FFE=ffe.fit_ffe(quantized, first_labels, ridge=1e-3))
    for fit in fits.values():
        if 'weights_on_normalized_input' in fit:
            fit['normalized_input_tap_L2'] = math.sqrt(math.fsum(x*x for x in fit['weights_on_normalized_input']))
            fit['equivalent_per_V_tap_L2'] = math.sqrt(math.fsum(x*x for x in fit['equivalent_weights_per_input_V']))
    return dict(raw_FFE=fits['raw_FFE'], ADC_FFE=fits['ADC_FFE'],
                fit_input_count=FIT, fit_complete_window_count=FIT-2*HALF,
                fullscale_differential_Vpp=fullscale, bits=7,
                noiseless_fit_clipped_count=clipped,
                fit_source='first256 noiseless training samples only',
                threshold_target_units=[-2., 0., 2.])


def evaluate_detector(samples, labels, detector, ffe, metrics):
    unused_first, unused_labels, score, target = split_arrays(samples, labels)
    if len(score) != SCORE:
        raise ValueError('Expected240 independently windowed score inputs')
    before = canonical(detector)
    unused_first_q, first_clipped = metrics.quantize_symmetric(samples[:FIT], detector['fullscale_differential_Vpp'], 7)
    quantized, clipped = metrics.quantize_symmetric(score, detector['fullscale_differential_Vpp'], 7)
    result = {}
    for key, values in (('raw_FFE', score), ('ADC_FFE', quantized)):
        predictions = ffe.predict_window(values, detector[key])
        measured = ffe.prediction_metrics(predictions, target[HALF:-HALF])
        if len(predictions) != 224 or measured['sample_count'] != 224:
            raise ValueError('Expected224 complete score FFE windows')
        measured['MSE_target_units_squared'] = measured['prediction_RMSE_in_target_symbol_units']**2
        result[key] = measured
    if canonical(detector) != before:
        raise RuntimeError('Evaluation modified frozen detector')
    result.update(score_input_count=SCORE, FFE_score_count=224, score_ADC_clipped_count=clipped,
                  first256_ADC_clipped_count=first_clipped,
                  held_min_V=min(score), held_max_V=max(score),
                  held_centered_RMS_V=math.sqrt(sum((x-sum(score)/len(score))**2 for x in score)/len(score)),
                  detector_sha256=before, fitting_performed=False)
    return result


def analyze(directory, case, state, protocol, backend, ffe, metrics, psf_ascii, symbols):
    prepared = read_json(directory/'prepared.json')
    psf_ascii.MAX_FILE_BYTES = 512*1024*1024
    raw = psf_ascii.parse_file(backend.a._raw_file(directory))
    records, audit = backend.extract_records(raw, prepared['clock_specification'])
    aligned = {point: align_fixed(records[point], symbols, LAGS[point]) for point in LAGS}
    detector_path = ROOT/(case['candidate']+'_detectors.json')
    fitted = case['kind'] == 'noiseless'
    if fitted:
        if detector_path.exists():
            raise RuntimeError('Detector exists; never refit/reuse candidate')
        detectors = dict(candidate=case['candidate'], data_seed=DATA_SEED,
            source_case=case['name'], source_raw_sha256=raw.sha256,
            protocol_sha256=state['protocol_sha256'], source_deck_sha256=prepared['deck_sha256'],
            fixed_lags=LAGS, fit_target_indices=protocol['fit_target_indices'], branches={})
        for point, (samples, labels, rows) in aligned.items():
            detectors['branches'][point] = fit_detector(samples, labels, RANGES[point], ffe, metrics)
        write_json(detector_path, detectors)
        state['detector_sha256'][case['candidate']] = digest(detector_path)
    else:
        if digest(detector_path) != state['detector_sha256'][case['candidate']]:
            raise RuntimeError('Frozen noiseless detector file changed')
        detectors = read_json(detector_path)
    if (detectors['candidate'] != case['candidate'] or detectors['data_seed'] != DATA_SEED or
            detectors['protocol_sha256'] != state['protocol_sha256']):
        raise RuntimeError('Candidate detector identity mismatch')
    branches = {}
    for point, (samples, labels, rows) in aligned.items():
        branches[point] = evaluate_detector(samples, labels, detectors['branches'][point], ffe, metrics)
        branches[point]['integer_lag'] = LAGS[point]
        branches[point]['fullscale_Vpp'] = RANGES[point]
    all_rows = [row for sample, labels, rows in aligned.values() for row in rows[FIT+SPLIT_GUARD:]]
    lo, hi = min(row[2] for row in all_rows), max(row[2] for row in all_rows)
    power = backend.power(raw, lo, hi)
    if digest(detector_path) != state['detector_sha256'][case['candidate']]:
        raise RuntimeError('Frozen detector mutated during score evaluation')
    return dict(status='analysis_complete', training_only=True, case=case, branches=branches,
                raw_transient_sha256=raw.sha256, clock_mapping_audit=audit,
                detector_file=detector_path.name, detector_file_sha256=digest(detector_path),
                new_fit_performed=fitted, noise_fitting_performed=False,
                fit_input_count=FIT, score_input_count=SCORE, FFE_score_count=224,
                data_seed=DATA_SEED, noise_seed=case['noise_seed'], modeled_power=power,
                complete_ADC_verified=False, independent_holdout=False, scope=SCOPE)


def verify_prepared(state, protocol):
    if state.get('status') != 'prepared' or state['completed_cases'] or state['detector_sha256']:
        raise RuntimeError('Study not pristine prepared; no automatic resume/retry')
    if digest(ROOT/'protocol.json') != state['protocol_sha256']:
        raise RuntimeError('Protocol changed')
    for case in protocol['cases']:
        directory = ROOT/case['name']
        if directory.is_symlink() or directory.resolve() != directory:
            raise RuntimeError('Unexpected case symlink')
        if set(p.name for p in directory.iterdir()) != {'bench.scs', 'prepared.json'}:
            raise RuntimeError('Case was executed or altered already')
        if digest(directory/'prepared.json') != state['prepared_sha256'][case['name']]:
            raise RuntimeError('Prepared metadata changed')
        if digest(directory/'bench.scs') != read_json(directory/'prepared.json')['deck_sha256']:
            raise RuntimeError('Prepared deck changed')


def run(helper, runner, frozen, backend, ffe, metrics, psf):
    state, protocol = read_json(ROOT/'status.json'), read_json(ROOT/'protocol.json')
    assert_unchanged(protocol)
    verify_prepared(state, protocol)
    if protocol['cases'] != case_specs() or protocol['configurations'] != configurations(frozen['identity']['backend']):
        raise RuntimeError('Finite candidate policy changed')
    symbols = symbols_new()
    if canonical(symbols) != protocol['symbol_sequence_sha256']:
        raise RuntimeError('Fresh training symbol identity mismatch')
    deadline = time.monotonic()+OUTER_TIMEOUT
    state.update(run_started_utc=utc(), boot_id=runner.boot_id(), runner=helper.process_record(os.getpid()))
    try:
        for case in protocol['cases']:
            assert_unchanged(protocol)
            state['current_case'] = case['name']
            actual = runner.await_capacity(helper, state, deadline)
            remaining = int(deadline-time.monotonic())
            if remaining < 60 or shutil.disk_usage(str(ROOT)).free < MIN_FREE:
                raise RuntimeError('Dispatch deadline/free disk bound; case not launched')
            directory = ROOT/case['name']
            prepared = read_json(directory/'prepared.json')
            if (digest(ROOT/'protocol.json') != state['protocol_sha256'] or
                    digest(directory/'prepared.json') != state['prepared_sha256'][case['name']] or
                    digest(directory/'bench.scs') != prepared['deck_sha256']):
                raise RuntimeError('Prepared identity changed before launch')
            if case['kind'] == 'noise':
                for candidate, sha in state['detector_sha256'].items():
                    if digest(ROOT/(candidate+'_detectors.json')) != sha:
                        raise RuntimeError('Noiseless frozen detector changed before noise')
                if len(state['detector_sha256']) != 3:
                    raise RuntimeError('All3detectors must freeze before any noise run')
            checkpoint(state, 'launching', actual_spectre_before_case=actual,
                       effective_case_timeout_s=min(CASE_TIMEOUT, remaining))
            outcome = runner.run_case(helper, backend, directory, min(CASE_TIMEOUT, remaining), state)
            if outcome['exit_code'] != 0 or 'SPECTRE-18' in outcome['issue_codes']:
                raise RuntimeError('Spectre failed in '+case['name']+'; exit='+str(outcome['exit_code']))
            if any((r.get('cwd') or '') == str(PROJECT) or
                   (r.get('cwd') or '').startswith(str(PROJECT)+'/') for r in runner.inventory(helper)):
                raise RuntimeError('Owned simulator remains after exit; stop dispatch')
            assert_unchanged(protocol)
            if digest(directory/'bench.scs') != prepared['deck_sha256']:
                raise RuntimeError('Deck changed during run')
            checkpoint(state, 'analyzing')
            result = analyze(directory, case, state, protocol, backend, ffe, metrics, psf, symbols)
            result.update(run_status=outcome, protocol_sha256=state['protocol_sha256'],
                          deck_sha256=prepared['deck_sha256'], frozen_sha256=FROZEN_SHA,
                          frozen_unchanged=True, completed_utc=utc())
            assert_unchanged(protocol)
            write_json(directory/'summary.json', result)
            state['completed_cases'].append(dict(name=case['name'], summary_sha256=digest(directory/'summary.json')))
            checkpoint(state, 'case_complete')
        checkpoint(state, 'complete', current_case=None, training_only=True,
                   automatic_retry=False, holdout_launched=False, complete_ADC_verified=False)
    except BaseException as error:
        checkpoint(state, 'failed_terminal', error=type(error).__name__+': '+str(error),
                   actual_spectre_at_failure=runner.inventory(helper), automatic_retry=False)
        raise


def self_test():
    # Pure synthetic numerical API doubles. No VM, PDK, imports or processes.
    class FakeMetrics:
        @staticmethod
        def quantize_symmetric(values, fullscale, bits):
            clip = sum(abs(x) > fullscale/2 for x in values)
            step = fullscale/(2**bits)
            return [max(-fullscale/2, min(fullscale/2-step, round(x/step)*step)) for x in values], clip
    class FakeFfe:
        @staticmethod
        def fit_ffe(values, labels, ridge):
            return dict(mean=sum(values)/len(values), label_sum=sum(labels), samples=len(values), ridge=ridge)
        @staticmethod
        def predict_window(values, fit):
            return [x*100+fit['mean'] for x in values[HALF:-HALF]]
        @staticmethod
        def prediction_metrics(predictions, labels):
            rmse=math.sqrt(sum((x-(2*y-3))**2 for x,y in zip(predictions, labels))/len(labels))
            return dict(sample_count=len(predictions), prediction_RMSE_in_target_symbol_units=rmse,
                        symbol_errors=sum(abs(x-(2*y-3))>1 for x,y in zip(predictions, labels)))
    baseline = dict(secondary_cap_F=10e-15, secondary_switch_width_m=1e-6,
                    phase_UI=.25, n_bias_V=.5, resistor_ohm=350)
    cfg = configurations(baseline)
    assert tuple(cfg) == CANDIDATES and len(case_specs()) == 6
    assert [x['kind'] for x in case_specs()] == ['noiseless']*3+['noise']*3
    assert cfg['baseline_r5'] == baseline and baseline['secondary_cap_F'] == 10e-15
    assert cfg['secondary_c25_w1']['secondary_cap_F'] == 25e-15
    assert cfg['secondary_c25_w2']['secondary_switch_width_m'] == 2e-6
    labels = [i%4 for i in range(TRAIN)]
    samples = [(2*x-3)*.01 for x in labels]
    detector = fit_detector(samples, labels, .1, FakeFfe, FakeMetrics)
    encoded = canonical(detector)
    altered = [(x+1)%4 if i >= FIT+SPLIT_GUARD else x for i,x in enumerate(labels)]
    assert fit_detector(samples, altered, .1, FakeFfe, FakeMetrics) == detector
    original_score = evaluate_detector(samples, labels, detector, FakeFfe, FakeMetrics)
    changed_score = evaluate_detector(samples, altered, detector, FakeFfe, FakeMetrics)
    assert canonical(detector) == encoded
    assert original_score['ADC_FFE']['symbol_errors'] != changed_score['ADC_FFE']['symbol_errors']
    assert detector['fit_input_count'] == 256 and detector['fit_complete_window_count'] == 240
    assert original_score['score_input_count'] == 240 and original_score['FFE_score_count'] == 224
    assert len(symbols_new()) == 896 and DATA_SEED != 2026102201 and NOISE_SEED != 197
    rows = [(i+3, float(i), 0., 0., 0) for i in range(896)]
    ss, ll, chosen = align_fixed(rows, symbols_new(), 3)
    assert len(ss) == 512 and ss[0] == 256 and ss[-1] == 767
    assert ll == symbols_new()[256:768]
    try:
        align_fixed(rows[:-200], symbols_new(), 3)
        raise AssertionError('Missing512input coverage accepted')
    except ValueError:
        pass
    json.dumps([detector, original_score, changed_score], allow_nan=False)
    # Run the actual existing numerical FFE functions in an isolated namespace.
    # AST extraction excludes their unrelated VM/PDK imports and all run entrypoints.
    import ast
    import bisect
    import types
    numerical_path = Path(__file__).with_name('pam4_ffe_diagnostic.py')
    metrics_path = Path(__file__).with_name('pam4_metrics.py')
    numerical_metrics = verified_import(metrics_path, digest(metrics_path), 'r7_test_metrics_only')
    tree = ast.parse(numerical_path.read_text())
    names = {'mean', 'cholesky_solve', 'fit_ffe', 'predict_window', 'prediction_metrics'}
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if len(tree.body) != len(names):
        raise AssertionError('Missing existing numerical FFE API for synthetic test')
    namespace = dict(math=math, bisect=bisect, TAPS=17, HALF=8, RIDGE=1e-3,
                     TARGETS=(-3., -1., 1., 3.), THRESHOLDS=(-2., 0., 2.),
                     metrics=numerical_metrics, integration=types.SimpleNamespace(UI=1./112e9))
    exec(compile(tree, str(numerical_path), 'exec'), namespace)
    numerical_ffe = types.SimpleNamespace(**{name: namespace[name] for name in names})
    rng = random.Random(7022)
    actual_labels = [rng.randrange(4) for unused in range(TRAIN)]
    amplitudes = [2*x-3 for x in actual_labels]
    actual_samples = [.008*(.7*x+.2*amplitudes[max(0, i-1)]) for i, x in enumerate(amplitudes)]
    actual_detector = fit_detector(actual_samples, actual_labels, .075, numerical_ffe, numerical_metrics)
    noise_samples = [x+rng.gauss(0, .0008) for x in actual_samples]
    noise_labels_changed = [(x+1)%4 for x in actual_labels]
    real_before = canonical(actual_detector)
    actual_score = evaluate_detector(noise_samples, actual_labels, actual_detector, numerical_ffe, numerical_metrics)
    perturbed_score = evaluate_detector(noise_samples, noise_labels_changed, actual_detector, numerical_ffe, numerical_metrics)
    assert canonical(actual_detector) == real_before
    assert actual_score['ADC_FFE']['symbol_errors'] < perturbed_score['ADC_FFE']['symbol_errors']
    assert actual_detector['ADC_FFE']['training_input_sample_count'] == 256
    assert actual_detector['ADC_FFE']['training_complete_window_count'] == 240
    assert actual_score['ADC_FFE']['sample_count'] == 224
    assert actual_detector['ADC_FFE']['normal_equation_relative_residual'] < 1e-10
    return dict(status='passed', simulations_started=0, checks=[
        'exact3fixedconfigs, onlyC/widthchanges, originalnotmutated',
        'sixcases:3noiseless then3noise; fresh896symbolseed',
        'fixedlag mapping returns exact512traininglabels',
        'fit256 ->240FFEfitwindows;16guard;240score ->224FFEoutputs',
        'changing later/noise score labels does not change frozenfit',
        'evaluation alters scores but never detector; strictJSON',
        'actual existing numerical FFE functions:256fit/240fitwindows/224scores, frozen noisy evaluation and small normal residual'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--run', action='store_true')
    group.add_argument('--selftest', '--self-test', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        print(json.dumps(self_test()), flush=True)
        return
    if (os.name != 'posix' or not Path('/proc').is_dir() or PROJECT.resolve() != PROJECT or
            ROOT.resolve() != ROOT or Path(__file__).resolve().parent != PROJECT/'scripts' or
            not (PROJECT/'.codex_project6_owned').is_file()):
        raise RuntimeError('Restricted to designated Linux VM project and script location')
    import fcntl
    with (PROJECT/'runs/.secondary_cap_training_r7_20261022.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        helper, runner, frozen, backend, ffe, metrics, psf = load_verified()
        if args.prepare:
            print(json.dumps(prepare(helper, runner, frozen, backend)), flush=True)
        else:
            run(helper, runner, frozen, backend, ffe, metrics, psf)


if __name__ == '__main__':
    main()
