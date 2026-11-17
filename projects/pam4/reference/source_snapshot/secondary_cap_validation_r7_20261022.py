#!/usr/bin/env python3
"""Four-case independent fresh-data r7 validation; Python 3.6.

Original10fF/1um and selected25fF/2um only. Each candidate retains its exact
previously trained noiseless detector bytes. This program performs no fitting,
hardware search, phase search, lag selection, threshold or range tuning.
Two noiseless cases precede two noisy cases. A failure is terminal; no retries.
All native inputs, raw results, detectors and detailed outputs remain on VM.
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
import shutil
import sys
import time

sys.dont_write_bytecode = True
PROJECT = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
ROOT = PROJECT/'runs/secondary_cap_validation_r7_20261022'
TRAINING_ROOT = PROJECT/'runs/secondary_cap_training_r7_20261022'
TRAINING = PROJECT/'scripts/secondary_cap_training_r7_20261022.py'
TRAINING_SHA = 'a83a0795f0cfb341889649f9578cfd82dbf7ecf380d2cea799938dd84ce1bbac'
TRAINING_PROTOCOL_SHA = '52589424ae376221ffb488b3e1a92d5ca1e411768eed96825defa8f4cd3af1f0'
TRAINING_STATUS_SHA = 'b313c3ae8fdd84739cf381503161d2ba00c57034f599a3afecc5bcb850bd4a6c'
TRAINING_DETECTOR_SHA = {
    'baseline_r5': '650597e127ef2d86a5645e16ee8dd361915e41497fb1cd15a395e75ac67bc847',
    'secondary_c25_w2': '04298d537e246b4714d0037ab1ff044c705a695e804de041632ee1139de41b4f'}
FROZEN = PROJECT/'runs/adc_backend_pam4_r5_20261013/r5_late1/frozen.json'
FROZEN_SHA = '4cda4c9ec967f2af4bf4f89eacdd1beae372668877c358cf6aa26092597482eb'
HELPER = PROJECT/'scripts/ffe_phase_sweep_20261022.py'
HELPER_SHA = '660a374e1da30b5fec84aed9e99a8ecba7de65466532767c83ff2e87ec172a8e'
RUNNER = PROJECT/'scripts/ffe_phase_resume2_20261022.py'
RUNNER_SHA = '1a01d14b611f5e3cad372bb428d4768acad181fd723a84fe55a90c70bbf97b2b'
DATA_SEED, NOISE_SEED = 2026102301, 251
WARMUP, SCORE, GUARD, HALF = 256, 2048, 128, 8
FFE_COUNT = SCORE-2*HALF
LAGS = {'primary': 1, 'secondary': 3}
RANGES = {'primary': .100, 'secondary': .075}
CASE_TIMEOUT, WAIT_TIMEOUT, OUTER_TIMEOUT = 7200, 1800, 12*3600
MIN_FREE = 8*1024**3
CANDIDATES = ('baseline_r5', 'secondary_c25_w2')
SCOPE = ('Independent fresh-data comparison of original10fF/1um and selected25fF/2um '
         'secondary sampling branch, with each exact previously frozen detector. '
         'Numerical7bit quantizer and17tapFFE, reset comparators and ideal clocks '
         'remain; no full ADC certification or physical digital FFE verification.')


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
    training = verified_import(TRAINING, TRAINING_SHA, 'r7_verified_training_source')
    helper, runner, frozen, backend, ffe, metrics, psf = training.load_verified()
    # The verified training import sets runner.ROOT to its own root. Redirect only
    # this new module instance, deliberately, before safe run_case/await_capacity.
    runner.ROOT = ROOT
    runner.WAIT_TIMEOUT = WAIT_TIMEOUT
    if ffe.TAPS != 17 or ffe.HALF != HALF:
        raise RuntimeError('Unexpected FFE implementation')
    return training, helper, runner, frozen, backend, ffe, metrics, psf


def configurations(training, baseline):
    all_configs = training.configurations(baseline)
    return {name: all_configs[name] for name in CANDIDATES}


def case_specs():
    return [dict(name=kind+'_'+candidate, kind=kind, candidate=candidate,
                 noise_seed=None if kind == 'noiseless' else NOISE_SEED)
            for kind in ('noiseless', 'noise') for candidate in CANDIDATES]


def symbols_new():
    rng = random.Random(DATA_SEED)
    return [rng.randrange(4) for unused in range(WARMUP+SCORE+GUARD)]


def require_regular_inside(path, root):
    path, root = Path(path), Path(root)
    if (path.is_symlink() or not path.is_file() or
            root not in path.resolve().parents or path.resolve() != path):
        raise RuntimeError('Expected original regular project file: '+str(path))


def validate_detector(detectors, candidate):
    if (detectors.get('candidate') != candidate or detectors.get('data_seed') != 2026102202 or
            detectors.get('source_case') != 'noiseless_'+candidate or
            detectors.get('protocol_sha256') != TRAINING_PROTOCOL_SHA or
            detectors.get('fixed_lags') != LAGS or
            detectors.get('fit_target_indices') != [256, 511] or
            set(detectors.get('branches', {})) != set(LAGS)):
        raise RuntimeError('Frozen candidate detector lineage mismatch')
    for point, branch in detectors['branches'].items():
        if (branch.get('fit_input_count') != 256 or
                branch.get('fit_complete_window_count') != 240 or
                branch.get('fullscale_differential_Vpp') != RANGES[point] or
                branch.get('bits') != 7 or
                branch.get('threshold_target_units') != [-2., 0., 2.]):
            raise RuntimeError('Frozen branch detector policy mismatch: '+point)
        for kind in ('raw_FFE', 'ADC_FFE'):
            fit = branch[kind]
            if (fit.get('tap_count') != 17 or fit.get('tap_offsets_UI') != list(range(-8, 9)) or
                    fit.get('training_input_sample_count') != 256 or
                    fit.get('training_complete_window_count') != 240 or
                    len(fit.get('weights_on_normalized_input', [])) != 17 or
                    len(fit.get('equivalent_weights_per_input_V', [])) != 17 or
                    not math.isfinite(fit['normalization_training_centered_RMS_V']) or
                    fit['normalization_training_centered_RMS_V'] <= 0):
                raise RuntimeError('Frozen17tap detector structure mismatch')
    canonical(detectors)  # Strict finite JSON, including every stored coefficient.


def training_provenance():
    """Read only the completed training study; never any earlier holdout output."""
    paths = [TRAINING_ROOT/'status.json', TRAINING_ROOT/'protocol.json']
    for path in paths:
        require_regular_inside(path, TRAINING_ROOT)
    source_state, source_protocol = read_json(paths[0]), read_json(paths[1])
    if (source_state.get('status') != 'complete' or
            digest(paths[0]) != TRAINING_STATUS_SHA or
            source_state.get('protocol_sha256') != TRAINING_PROTOCOL_SHA or
            digest(paths[1]) != TRAINING_PROTOCOL_SHA or
            source_protocol.get('training_only') is not True or
            source_protocol.get('data_seed') != 2026102202 or
            source_protocol.get('noise_seed') != 223 or
            source_protocol.get('frozen_sha256') != FROZEN_SHA or
            source_protocol.get('script_sha256') != TRAINING_SHA):
        raise RuntimeError('Training source is not the verified completed study')
    expected = [kind+'_'+candidate for kind in ('noiseless', 'noise')
                for candidate in ('baseline_r5', 'secondary_c25_w1', 'secondary_c25_w2')]
    completed = source_state.get('completed_cases', [])
    if [item.get('name') for item in completed] != expected:
        raise RuntimeError('Training source lacks the exact six completed cases')
    hashes = {str(path.relative_to(PROJECT)): digest(path) for path in paths}
    summary_records = {}
    for item in completed:
        path = TRAINING_ROOT/item['name']/'summary.json'
        require_regular_inside(path, TRAINING_ROOT)
        sha, result = digest(path), read_json(path)
        if (sha != item['summary_sha256'] or result.get('status') != 'analysis_complete' or
                result.get('run_status', {}).get('exit_code') != 0 or
                'SPECTRE-18' in result.get('run_status', {}).get('issue_codes', []) or
                result.get('noise_fitting_performed') is not False or
                result.get('frozen_sha256') != FROZEN_SHA or
                result.get('frozen_unchanged') is not True or
                result.get('FFE_score_count') != 224):
            raise RuntimeError('Training summary integrity failure: '+item['name'])
        hashes[str(path.relative_to(PROJECT))] = sha
        summary_records[item['name']] = dict(summary_sha256=sha,
            raw_sha256=result['raw_transient_sha256'], deck_sha256=result['deck_sha256'],
            detector_sha256=result['detector_file_sha256'])
    detectors = {}
    for candidate in CANDIDATES:
        path = TRAINING_ROOT/(candidate+'_detectors.json')
        require_regular_inside(path, TRAINING_ROOT)
        sha, detector = digest(path), read_json(path)
        validate_detector(detector, candidate)
        if (sha != TRAINING_DETECTOR_SHA[candidate] or
                sha != source_state['detector_sha256'][candidate] or
                any(summary_records[kind+'_'+candidate]['detector_sha256'] != sha
                    for kind in ('noiseless', 'noise')) or
                detector['source_raw_sha256'] != summary_records['noiseless_'+candidate]['raw_sha256'] or
                detector['source_deck_sha256'] != summary_records['noiseless_'+candidate]['deck_sha256']):
            raise RuntimeError('Exact candidate detector lineage changed')
        hashes[str(path.relative_to(PROJECT))] = sha
        detectors[candidate] = dict(source_path=str(path.relative_to(PROJECT)),
            file_sha256=sha, content_sha256=canonical(detector))
    return dict(source_training_root=str(TRAINING_ROOT.relative_to(PROJECT)),
                source_protocol_sha256=TRAINING_PROTOCOL_SHA,
                source_files_sha256=hashes, detectors=detectors,
                source_summary_identity=summary_records, candidate_selection='completed training only',
                previous_holdout_outputs_read=False, original_r5_frozen_sha256=FROZEN_SHA)


def make_protocol(helper, frozen, configs, symbols, provenance):
    return dict(schema_version=1, created_utc=utc(), scope=SCOPE,
        independent_fresh_data_validation=True, training_only=False,
        script_sha256=digest(__file__), training_script_sha256=TRAINING_SHA,
        frozen_sha256=FROZEN_SHA, helper_sha256=HELPER_SHA, runner_sha256=RUNNER_SHA,
        dependency_hashes=dict(frozen['identity']['scripts']),
        additional_dependency_hashes=helper.loaded_project_sources(),
        data_seed=DATA_SEED, noise_seed=NOISE_SEED,
        symbol_sequence_sha256=canonical(symbols), generated_symbols=len(symbols),
        warmup_symbols=WARMUP, score_input_symbols=SCORE, end_guard_symbols=GUARD,
        score_complete_FFE_windows=FFE_COUNT,
        score_target_indices=[WARMUP, WARMUP+SCORE-1],
        score_FFE_center_indices=[WARMUP+HALF, WARMUP+SCORE-HALF-1],
        score_label_sha256=canonical(symbols[WARMUP:WARMUP+SCORE]),
        fixed_lags=LAGS, fixed_quantizer_fullscale_Vpp=RANGES,
        fixed_thresholds=[-2., 0., 2.], configurations=configs, cases=case_specs(),
        training_provenance=provenance,
        detector_policy='Exact bytes of each own trained candidate detector frozen before any new validation simulation; no fitting, phase/lag/range/threshold selection.',
        score_policy='2048 fresh held inputs;2032 centered full17tap outputs; entire fresh interval used only for validation.',
        noise_scope='Same declared seed251 is not proof of identical analog noise realization across hardware, or independent replicas.',
        independent_noise_replicates=False,
        limits_s=dict(per_case=CASE_TIMEOUT, capacity_wait=WAIT_TIMEOUT, whole=OUTER_TIMEOUT),
        minimum_free_bytes=MIN_FREE, automatic_retry=False, automatic_resume=False,
        validation_fitting_performed=False, complete_ADC_verified=False,
        physical_FFE_verified=False, previous_holdout_outputs_read=False,
        user_authorization='2026-10-22 explicit25fF/2um versus original fresh-data independent comparison, background30minute monitoring, report crash without retry',
        export_scope='Native/model/deck/raw/TSV/XY/detectors remain inside designated VM project.')


def assert_unchanged(protocol, state=None):
    expected = ((FROZEN, FROZEN_SHA), (TRAINING, TRAINING_SHA),
                (HELPER, HELPER_SHA), (RUNNER, RUNNER_SHA),
                (Path(__file__), protocol['script_sha256']))
    if any(digest(path) != sha for path, sha in expected):
        raise RuntimeError('Frozen/source identity changed')
    for name, sha in protocol['dependency_hashes'].items():
        if Path(name).name != name or digest(PROJECT/'scripts'/name) != sha:
            raise RuntimeError('Frozen dependency changed: '+name)
    for relative, sha in protocol['additional_dependency_hashes'].items():
        path = (PROJECT/relative).resolve()
        if PROJECT not in path.parents or digest(path) != sha:
            raise RuntimeError('Additional dependency changed: '+relative)
    provenance = protocol['training_provenance']
    for relative, sha in provenance['source_files_sha256'].items():
        path = PROJECT/relative
        require_regular_inside(path, TRAINING_ROOT)
        if digest(path) != sha:
            raise RuntimeError('Training provenance changed: '+relative)
    for candidate, identity in provenance['detectors'].items():
        path = ROOT/(candidate+'_detectors.json')
        require_regular_inside(path, ROOT)
        if digest(path) != identity['file_sha256']:
            raise RuntimeError('Copied exact detector bytes changed: '+candidate)
        validate_detector(read_json(path), candidate)
    if state is not None and (digest(ROOT/'protocol.json') != state['protocol_sha256'] or
            digest(ROOT/'symbols.json') != state['symbols_file_sha256'] or
            canonical(read_json(ROOT/'symbols.json')) != protocol['symbol_sequence_sha256'] or
            state['detector_sha256'] != {candidate: identity['file_sha256']
                for candidate, identity in provenance['detectors'].items()}):
        raise RuntimeError('Prepared protocol/symbol/detector manifest changed')


def prepare(training, helper, runner, frozen, backend):
    if ROOT.exists() or ROOT.is_symlink():
        raise RuntimeError('Validation root exists; never overwrite or reuse')
    if shutil.disk_usage(str(PROJECT)).free < MIN_FREE:
        raise RuntimeError('Less than8GiB free before preparation')
    configs, symbols = configurations(training, frozen['identity']['backend']), symbols_new()
    provenance = training_provenance()
    protocol = make_protocol(helper, frozen, configs, symbols, provenance)
    ROOT.mkdir()
    state = dict(started_utc=utc(), boot_id=runner.boot_id(), runner=helper.process_record(os.getpid()),
                 completed_cases=[], current_case=None, scope=SCOPE,
                 automatic_retry=False, automatic_resume=False,
                 independent_fresh_data_validation=True, validation_fitting_performed=False)
    try:
        # Exact bytes are copied before any validation simulations are possible.
        for candidate in CANDIDATES:
            identity = provenance['detectors'][candidate]
            source = PROJECT/identity['source_path']
            with (ROOT/(candidate+'_detectors.json')).open('xb') as output:
                output.write(source.read_bytes())
        write_json(ROOT/'symbols.json', symbols)
        write_json(ROOT/'protocol.json', protocol)
        state.update(protocol_sha256=digest(ROOT/'protocol.json'),
            symbols_file_sha256=digest(ROOT/'symbols.json'),
            detector_sha256={candidate: provenance['detectors'][candidate]['file_sha256']
                for candidate in CANDIDATES})
        checkpoint(state, 'preparing')
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
            audit = training.audit_deck(original, deck, base_clocks, clocks, case['candidate'])
            (directory/'bench.scs').write_text('\n'.join(deck)+'\n')
            write_json(directory/'prepared.json', dict(case=case, configuration=cfg,
                clock_specification=clocks, hardware_only_change_audit=audit,
                deck_sha256=digest(directory/'bench.scs'), symbol_sequence_sha256=canonical(symbols),
                detector_file_sha256=state['detector_sha256'][case['candidate']], status='prepared'))
        state['prepared_sha256'] = {case['name']: digest(ROOT/case['name']/'prepared.json')
                                    for case in protocol['cases']}
        assert_unchanged(protocol, state)
        checkpoint(state, 'prepared', simulations_started=0)
    except BaseException as error:
        checkpoint(state, 'preparation_failed', error=type(error).__name__+': '+str(error))
        raise
    return state


def align_fixed(records, symbols, lag):
    if len(symbols) != WARMUP+SCORE+GUARD or lag not in LAGS.values():
        raise ValueError('Unexpected fresh input sequence length or fixed lag')
    if any(not isinstance(symbol, int) or isinstance(symbol, bool) or symbol not in range(4)
           for symbol in symbols):
        raise ValueError('Invalid source PAM4 labels')
    lookup = {}
    for row in records:
        index = row[0]
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError('Sample reference indices must be integer ordinals')
        if index-lag in lookup:
            raise ValueError('Duplicate sample reference index')
        lookup[index-lag] = row
    indices = range(WARMUP, WARMUP+SCORE)
    if any(index not in lookup for index in indices):
        raise ValueError('Incomplete fixed2048symbol independent validation interval')
    chosen = [lookup[index] for index in indices]
    values, labels = [row[1] for row in chosen], [symbols[index] for index in indices]
    if len(chosen) != SCORE or not all(math.isfinite(value) for value in values):
        raise ValueError('Nonfinite or incomplete held sample vector')
    return values, labels, chosen


def evaluate_detector(samples, labels, detector, ffe, metrics, expected_labels):
    if len(samples) != SCORE or len(labels) != SCORE or labels != expected_labels:
        raise ValueError('Validation count or commanded fixed-lag label identity mismatch')
    if (detector.get('fit_input_count') != 256 or detector.get('fit_complete_window_count') != 240 or
            not all(math.isfinite(value) for value in samples)):
        raise ValueError('Frozen detector provenance or finite validation samples required')
    before = canonical(detector)
    quantized, clipped = metrics.quantize_symmetric(samples, detector['fullscale_differential_Vpp'], 7)
    if len(quantized) != SCORE:
        raise ValueError('Quantizer changed sample count')
    result = {}
    target = labels[HALF:-HALF]
    for kind, values in (('raw_FFE', samples), ('ADC_FFE', quantized)):
        predictions = ffe.predict_window(values, detector[kind])
        if len(predictions) != FFE_COUNT or not all(math.isfinite(x) for x in predictions):
            raise ValueError('Expected2032 finite centered17tap predictions')
        measured = ffe.prediction_metrics(predictions, target)
        if measured['sample_count'] != FFE_COUNT:
            raise ValueError('Expected2032 complete validation FFE windows')
        measured['MSE_target_units_squared'] = measured['prediction_RMSE_in_target_symbol_units']**2
        result[kind] = measured
    if canonical(detector) != before:
        raise RuntimeError('Validation evaluation modified frozen detector')
    average = math.fsum(samples)/SCORE
    result.update(score_input_count=SCORE, FFE_score_count=FFE_COUNT,
        score_ADC_clipped_count=clipped, held_min_V=min(samples), held_max_V=max(samples),
        held_centered_RMS_V=math.sqrt(math.fsum((x-average)**2 for x in samples)/SCORE),
        detector_content_sha256=before, fitting_performed=False)
    return result


def analyze(directory, case, state, protocol, backend, ffe, metrics, psf_ascii, symbols):
    prepared = read_json(directory/'prepared.json')
    psf_ascii.MAX_FILE_BYTES = 512*1024*1024
    raw = psf_ascii.parse_file(backend.a._raw_file(directory))
    records, audit = backend.extract_records(raw, prepared['clock_specification'])
    aligned = {point: align_fixed(records[point], symbols, LAGS[point]) for point in LAGS}
    expected_labels = symbols[WARMUP:WARMUP+SCORE]
    if canonical(expected_labels) != protocol['score_label_sha256']:
        raise RuntimeError('Independent score label identity changed')
    detector_path = ROOT/(case['candidate']+'_detectors.json')
    if digest(detector_path) != state['detector_sha256'][case['candidate']]:
        raise RuntimeError('Frozen detector identity changed before evaluation')
    detectors = read_json(detector_path)
    validate_detector(detectors, case['candidate'])
    branches = {}
    for point, (samples, labels, rows) in aligned.items():
        branches[point] = evaluate_detector(samples, labels, detectors['branches'][point],
            ffe, metrics, expected_labels)
        branches[point].update(integer_lag=LAGS[point], fullscale_Vpp=RANGES[point],
            target_index_first=WARMUP, target_index_last=WARMUP+SCORE-1,
            FFE_center_index_first=WARMUP+HALF, FFE_center_index_last=WARMUP+SCORE-HALF-1)
    all_rows = [row for samples, labels, rows in aligned.values() for row in rows]
    lo, hi = min(row[2] for row in all_rows), max(row[2] for row in all_rows)
    power = backend.power(raw, lo, hi)
    if digest(detector_path) != state['detector_sha256'][case['candidate']]:
        raise RuntimeError('Frozen detector bytes changed during evaluation')
    return dict(status='validation_complete', training_only=False,
        independent_fresh_data_validation=True, case=case, branches=branches,
        raw_transient_sha256=raw.sha256, clock_mapping_audit=audit,
        detector_file=detector_path.name, detector_file_sha256=digest(detector_path),
        detector_training_data_seed=2026102202, detector_training_protocol_sha256=TRAINING_PROTOCOL_SHA,
        new_fit_performed=False, noise_fitting_performed=False, validation_fitting_performed=False,
        previous_training_fit_input_count=256, validation_fit_input_count=0,
        score_input_count=SCORE, FFE_score_count=FFE_COUNT,
        data_seed=DATA_SEED, noise_seed=case['noise_seed'], modeled_power=power,
        complete_ADC_verified=False, independent_holdout=True, scope=SCOPE)


def verify_prepared(state, protocol):
    if (state.get('status') != 'prepared' or state.get('completed_cases') or
            state.get('simulations_started') != 0):
        raise RuntimeError('Study not pristine prepared; no automatic resume/retry')
    expected_files = {'status.json', 'protocol.json', 'symbols.json'} | {
        candidate+'_detectors.json' for candidate in CANDIDATES} | {
        case['name'] for case in protocol['cases']}
    if set(path.name for path in ROOT.iterdir()) != expected_files:
        raise RuntimeError('Prepared validation root contains unexpected files')
    for case in protocol['cases']:
        directory = ROOT/case['name']
        if directory.is_symlink() or directory.resolve() != directory:
            raise RuntimeError('Unexpected case symlink')
        if set(path.name for path in directory.iterdir()) != {'bench.scs', 'prepared.json'}:
            raise RuntimeError('Case was executed or altered already')
        prepared = read_json(directory/'prepared.json')
        if (digest(directory/'prepared.json') != state['prepared_sha256'][case['name']] or
                digest(directory/'bench.scs') != prepared['deck_sha256'] or
                prepared['case'] != case or
                prepared['symbol_sequence_sha256'] != protocol['symbol_sequence_sha256'] or
                prepared['detector_file_sha256'] != state['detector_sha256'][case['candidate']]):
            raise RuntimeError('Prepared metadata/deck/detector identity changed')


def run(training, helper, runner, frozen, backend, ffe, metrics, psf):
    state, protocol = read_json(ROOT/'status.json'), read_json(ROOT/'protocol.json')
    try:
        assert_unchanged(protocol, state)
        verify_prepared(state, protocol)
        if (protocol['cases'] != case_specs() or protocol['configurations'] !=
                configurations(training, frozen['identity']['backend']) or
                protocol['validation_fitting_performed'] is not False):
            raise RuntimeError('Finite fixed validation policy changed')
        symbols = symbols_new()
        if (canonical(symbols) != protocol['symbol_sequence_sha256'] or
                symbols != read_json(ROOT/'symbols.json')):
            raise RuntimeError('Fresh validation symbol identity mismatch')
        deadline = time.monotonic()+OUTER_TIMEOUT
        state.update(run_started_utc=utc(), boot_id=runner.boot_id(),
                     runner=helper.process_record(os.getpid()))
        for case in protocol['cases']:
            assert_unchanged(protocol, state)
            state['current_case'] = case['name']
            actual = runner.await_capacity(helper, state, deadline)
            remaining = int(deadline-time.monotonic())
            if remaining < 60 or shutil.disk_usage(str(ROOT)).free < MIN_FREE:
                raise RuntimeError('Dispatch deadline/free disk bound; case not launched')
            directory = ROOT/case['name']
            prepared = read_json(directory/'prepared.json')
            if (digest(directory/'prepared.json') != state['prepared_sha256'][case['name']] or
                    digest(directory/'bench.scs') != prepared['deck_sha256']):
                raise RuntimeError('Prepared identity changed before launch')
            assert_unchanged(protocol, state)
            checkpoint(state, 'launching', actual_spectre_before_case=actual,
                       effective_case_timeout_s=min(CASE_TIMEOUT, remaining))
            state['simulations_started'] += 1
            outcome = runner.run_case(helper, backend, directory, min(CASE_TIMEOUT, remaining), state)
            if outcome['exit_code'] != 0 or 'SPECTRE-18' in outcome['issue_codes']:
                raise RuntimeError('Spectre failed in '+case['name']+'; exit='+str(outcome['exit_code']))
            if any((record.get('cwd') or '') == str(PROJECT) or
                   (record.get('cwd') or '').startswith(str(PROJECT)+'/')
                   for record in runner.inventory(helper)):
                raise RuntimeError('Owned simulator remains after exit; stop dispatch')
            assert_unchanged(protocol, state)
            if digest(directory/'bench.scs') != prepared['deck_sha256']:
                raise RuntimeError('Deck changed during run')
            checkpoint(state, 'analyzing')
            result = analyze(directory, case, state, protocol, backend, ffe, metrics, psf, symbols)
            result.update(run_status=outcome, protocol_sha256=state['protocol_sha256'],
                deck_sha256=prepared['deck_sha256'], frozen_sha256=FROZEN_SHA,
                frozen_unchanged=True, completed_utc=utc())
            assert_unchanged(protocol, state)
            write_json(directory/'summary.json', result)
            state['completed_cases'].append(dict(name=case['name'],
                summary_sha256=digest(directory/'summary.json')))
            checkpoint(state, 'case_complete')
        if len(state['completed_cases']) != 4 or state['simulations_started'] != 4:
            raise RuntimeError('Expected exactly four successful validation simulations')
        assert_unchanged(protocol, state)
        checkpoint(state, 'complete', current_case=None, validation_fitting_performed=False,
            automatic_retry=False, independent_fresh_data_validation=True, complete_ADC_verified=False)
    except BaseException as error:
        try:
            actual = runner.inventory(helper)
        except Exception as inventory_error:
            actual = {'inventory_error': str(inventory_error)}
        checkpoint(state, 'failed_terminal', error=type(error).__name__+': '+str(error),
                   actual_spectre_at_failure=actual, automatic_retry=False, automatic_resume=False)
        raise


def self_test():
    """Real numerical predictor/metrics with predeclared synthetic frozen taps."""
    import ast
    import bisect
    import types
    metrics_path = Path(__file__).with_name('pam4_metrics.py')
    numerical_path = Path(__file__).with_name('pam4_ffe_diagnostic.py')
    numerical_metrics = verified_import(metrics_path, digest(metrics_path), 'r7_validation_test_metrics')
    tree = ast.parse(numerical_path.read_text())
    names = {'mean', 'predict_window', 'prediction_metrics'}
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if len(tree.body) != len(names):
        raise AssertionError('Missing existing numerical prediction API')
    namespace = dict(math=math, bisect=bisect, TAPS=17, HALF=8,
        TARGETS=(-3., -1., 1., 3.), THRESHOLDS=(-2., 0., 2.), metrics=numerical_metrics)
    exec(compile(tree, str(numerical_path), 'exec'), namespace)
    numerical_ffe = types.SimpleNamespace(**{name: namespace[name] for name in names})
    weights = [0.]*17
    weights[8] = 1.
    fit = dict(normalization_training_mean_V=0., normalization_training_centered_RMS_V=.01,
        weights_on_normalized_input=weights, bias_in_target_symbol_units=0.)
    detector = dict(raw_FFE=copy.deepcopy(fit), ADC_FFE=copy.deepcopy(fit),
        fullscale_differential_Vpp=.075, fit_input_count=256, fit_complete_window_count=240)
    symbols = symbols_new()
    rows = [(index+3, .01*(2*symbol-3), index*1e-12, 0., 0)
            for index, symbol in enumerate(symbols)]
    samples, labels, chosen = align_fixed(rows, symbols, 3)
    expected = symbols[WARMUP:WARMUP+SCORE]
    before = canonical(detector)
    result = evaluate_detector(samples, labels, detector, numerical_ffe, numerical_metrics, expected)
    assert canonical(detector) == before
    assert len(symbols) == 2432 and len(samples) == 2048 and len(chosen) == 2048
    assert chosen[0][0] == WARMUP+3 and chosen[-1][0] == WARMUP+SCORE-1+3
    assert result['FFE_score_count'] == 2032 and result['ADC_FFE']['sample_count'] == 2032
    assert result['raw_FFE']['symbol_errors'] == 0 and result['ADC_FFE']['symbol_errors'] == 0
    assert result['fitting_performed'] is False
    for bad_samples, bad_labels in ((samples[:-1], labels[:-1]),
                                    (samples, [(label+1)%4 for label in labels])):
        try:
            evaluate_detector(bad_samples, bad_labels, detector, numerical_ffe, numerical_metrics, expected)
            raise AssertionError('Invalid validation count or labels accepted')
        except ValueError:
            pass
    for invalid_rows in (rows[:-200], rows+[rows[300]]):
        try:
            align_fixed(invalid_rows, symbols, 3)
            raise AssertionError('Incomplete or duplicate ordinals accepted')
        except ValueError:
            pass
    class MutatingFfe:
        @staticmethod
        def predict_window(values, frozen_fit):
            answer = numerical_ffe.predict_window(values, frozen_fit)
            frozen_fit['bias_in_target_symbol_units'] += .01
            return answer
        prediction_metrics = staticmethod(numerical_ffe.prediction_metrics)
    try:
        evaluate_detector(samples, labels, copy.deepcopy(detector), MutatingFfe,
                          numerical_metrics, expected)
        raise AssertionError('Detector mutation accepted')
    except RuntimeError:
        pass
    assert len(case_specs()) == 4
    assert [case['kind'] for case in case_specs()] == ['noiseless']*2+['noise']*2
    assert set(case['candidate'] for case in case_specs()) == set(CANDIDATES)
    assert DATA_SEED not in (2026102201, 2026102202) and NOISE_SEED not in (197, 223)
    json.dumps(result, allow_nan=False)
    return dict(status='passed', simulations_started=0, checks=[
        'four fixed cases, baseline and selected25fF2um, new2432symbol identity',
        'actual existing prediction and metrics APIs only; predeclared frozen synthetic taps',
        'fixedlag2048 held inputs map to exact commanded labels and2032 full17tap outputs',
        'wrong labels, missing counts and duplicate ordinals are rejected',
        'frozen synthetic detector remains unchanged; deliberate mutation is detected',
        'no fitting or simulator launch in self-test'])


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
            ROOT.resolve() != ROOT or TRAINING_ROOT.resolve() != TRAINING_ROOT or
            Path(__file__).resolve().parent != PROJECT/'scripts' or
            not (PROJECT/'.codex_project6_owned').is_file()):
        raise RuntimeError('Restricted to designated Linux VM project and script location')
    import fcntl
    with (PROJECT/'runs/.secondary_cap_validation_r7_20261022.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        training, helper, runner, frozen, backend, ffe, metrics, psf = load_verified()
        if args.prepare:
            print(json.dumps(prepare(training, helper, runner, frozen, backend)), flush=True)
        else:
            run(training, helper, runner, frozen, backend, ffe, metrics, psf)


if __name__ == '__main__':
    main()
