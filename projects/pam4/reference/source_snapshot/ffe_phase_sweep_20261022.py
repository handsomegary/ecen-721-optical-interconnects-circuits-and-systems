#!/usr/bin/env python3
"""Bounded real-clock aperture sweep with the immutable r5 FFE; Python 3.6.

This is a sampled-eye learning experiment, not a continuous analog FFE output
or a complete physical ADC. Native cards, decks, TSV points and raw traces stay
in the existing VM project. --prepare never starts Spectre; only --run does.
An interrupted/failed run is terminal: no resume, retry, fitting or phase choice.
"""
import argparse
import bisect
import copy
import datetime
import hashlib
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
ROOT = PROJECT/'runs/ffe_phase_sweep_20261022'
FROZEN_PATH = PROJECT/'runs/adc_backend_pam4_r5_20261013/r5_late1/frozen.json'
FROZEN_SHA = '4cda4c9ec967f2af4bf4f89eacdd1beae372668877c358cf6aa26092597482eb'
DELTAS = (-.5, -.375, -.25, -.125, 0., .125, .25, .375, .5)
DATA_SEED, NOISE_SEED = 2026102201, 197
WARMUP, SCORE, GUARD, HALF = 256, 512, 128, 8
UI, T0 = 1.0/112e9, 200e-12
CASE_TIMEOUT, WAIT_TIMEOUT, OUTER_TIMEOUT = 3600, 1800, 10*3600
MIN_FREE_BYTES = 8*1024**3
SCOPE = ('Real-clock phase-swept sampled eye of native AFE and two sampler stages, '
         'followed by an ideal numerical 7-bit quantizer and frozen 17-tap FFE; '
         'not a continuous analog FFE waveform, physical ADC, DSP implementation '
         'or BER certification. Phase is swept for observation, never optimized.')


def utc():
    return datetime.datetime.utcnow().isoformat()+'Z'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')
    temporary.replace(path)


def reference_symbol_index(close, delta_ui, ui=UI, t0=T0):
    # Remove the deliberate clock translation BEFORE assigning the symbol index.
    # Otherwise a half-UI sweep across a TX boundary silently changes labels.
    return int(math.floor((close-delta_ui*ui-t0)/ui+1e-7))


def align_score(records, symbols, lag):
    lookup = {row[0]-lag: row for row in records}
    if len(lookup) != len(records):
        raise ValueError('Duplicate reference symbol index')
    indices = list(range(WARMUP, WARMUP+SCORE))
    if any(index not in lookup for index in indices):
        raise ValueError('Incomplete 512-symbol score interval')
    chosen = [lookup[index] for index in indices]
    return ([row[1] for row in chosen], [symbols[index] for index in indices], chosen)


def process_record(pid):
    p = Path('/proc')/str(pid)
    try:
        fields = (p/'stat').read_text().rsplit(')', 1)[1].split()
        command = (p/'comm').read_text().strip()
        try:
            executable = os.readlink(str(p/'exe'))
        except OSError:
            executable = None
        try:
            cwd = os.readlink(str(p/'cwd'))
        except OSError:
            cwd = None
        return dict(pid=int(pid), state=fields[0], start_ticks=int(fields[19]),
                    pgid=int(fields[2]), sid=int(fields[3]), cwd=cwd,
                    executable=executable, comm=command)
    except (OSError, ValueError, IndexError):
        return None


def spectre_inventory():
    actual = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        record = process_record(p.name)
        if not record or record['state'] == 'Z':
            continue
        exe = Path(record['executable']).name if record['executable'] else ''
        if exe == 'spectre' or record['comm'] == 'spectre':
            actual.append(record)
    return actual


def owned_process(record):
    cwd = record.get('cwd')
    return bool(cwd and (cwd == str(PROJECT) or cwd.startswith(str(PROJECT)+'/')))


def capacity_available(actual):
    return len(actual) < 2 and not any(owned_process(x) for x in actual) and all(x['cwd'] for x in actual)


def checkpoint(state, status, **extra):
    state.update(status=status, updated_utc=utc(), **extra)
    atomic_json(ROOT/'status.json', state)


def await_capacity(state, deadline):
    wait_deadline = min(deadline, time.monotonic()+WAIT_TIMEOUT)
    while True:
        actual = spectre_inventory()
        # Fail closed if an actual simulator's ownership cannot be determined.
        if capacity_available(actual):
            return actual
        checkpoint(state, 'waiting_capacity', actual_spectre=actual)
        if time.monotonic() >= wait_deadline:
            raise RuntimeError('Capacity unavailable within bounded wait; no process stopped')
        time.sleep(min(10., max(0., wait_deadline-time.monotonic())))


def load_verified():
    if PROJECT.resolve() != PROJECT or not (PROJECT/'.codex_project6_owned').is_file():
        raise RuntimeError('Unexpected VM project or missing ownership marker')
    if digest(FROZEN_PATH) != FROZEN_SHA:
        raise RuntimeError('Frozen r5 identity changed')
    frozen = json.loads(FROZEN_PATH.read_text())
    scripts = PROJECT/'scripts'
    for name, expected in frozen['identity']['scripts'].items():
        if Path(name).name != name or digest(scripts/name) != expected:
            raise RuntimeError('Frozen dependency changed: '+name)
    # Imports are deliberately lazy: --self-test needs no PDK or VM modules.
    sys.path.insert(0, str(scripts))
    import adc_backend_pam4_r5 as backend
    import native_geometry_r5 as ng
    import pam4_ffe_diagnostic as ffe
    import pam4_metrics as metrics
    import psf_ascii
    native = ng.install()
    if native != frozen['identity']['native_geometry_metadata']:
        raise RuntimeError('Native geometry metadata differs from frozen design')
    for point in ('primary', 'secondary'):
        choice = frozen['selections'][point]
        for mode in ('raw_FFE', 'ADC_FFE'):
            fit = choice['frozen_detectors'][mode]
            if fit['tap_count'] != 17 or fit['tap_offsets_UI'] != list(range(-8, 9)):
                raise RuntimeError('Unexpected frozen FIR shape')
    return frozen, backend, ffe, metrics, psf_ascii


def case_specs():
    return [dict(name='%s_phase_%02d'%(kind, index), kind=kind,
                 delta_phase_UI=delta, noise_seed=None if kind == 'noiseless' else NOISE_SEED)
            for kind in ('noiseless', 'noise') for index, delta in enumerate(DELTAS)]


def loaded_project_sources():
    """Pin also the recursively imported project helpers outside frozen.identity."""
    result = {}
    for module in list(sys.modules.values()):
        source = getattr(module, '__file__', None)
        if not source:
            continue
        path = Path(source).resolve()
        try:
            relative = path.relative_to(PROJECT)
        except ValueError:
            continue
        if path.suffix == '.py':
            result[str(relative)] = digest(path)
    for required in ('adc_comparator_probe.py', 'p6_bench.py', 'p6_dynamic.py', 'psf_ascii.py'):
        if 'scripts/'+required not in result:
            raise RuntimeError('Required helper not imported from this project: '+required)
    return result


def audit_clock_translation(baseline_lines, shifted_lines, baseline, shifted, delta, parse_pulse):
    """Every pulse changes only delay; every nonpulse line must be identical."""
    shift = delta*UI
    if len(baseline_lines) != len(shifted_lines):
        raise ValueError('Phase sweep changed netlist length')
    pulse_count = 0
    for before, after in zip(baseline_lines, shifted_lines):
        if 'type=pulse' not in before:
            if before != after:
                raise ValueError('Phase sweep changed a nonclock statement')
            continue
        pulse_count += 1
        bp, ap = parse_pulse(before), parse_pulse(after)
        for name, value in bp.items():
            expected = value+shift if name in ('delay', 'first_rise_midpoint_s', 'first_fall_midpoint_s') else value
            if not math.isclose(ap[name], expected, rel_tol=1e-12, abs_tol=1e-23):
                raise ValueError('Clock pulse changed beyond common phase: '+name)
        # Derived widths may differ at the final printed floating-point digit.
        # Numerical checks above cover their values; this checks connectivity and
        # all unparsed text without imposing bitwise equality on harmless roundoff.
        pattern = r'\b(delay|rise|fall|width|period|val0|val1)=\S+'
        normalized_before = re.sub(pattern, lambda m: m.group(1)+'=CHECKED', before)
        normalized_after = re.sub(pattern, lambda m: m.group(1)+'=CHECKED', after)
        if normalized_before != normalized_after:
            raise ValueError('Clock connectivity or another pulse parameter changed')
    if pulse_count != 144:
        raise ValueError('Expected 16 primary and 128 secondary complementary clock sources')
    if len(baseline['primary_clocks']) != 8 or len(shifted['secondary_clocks']) != 64:
        raise ValueError('Clock metadata lane count changed')
    for before, after in zip(baseline['secondary_clocks'], shifted['secondary_clocks']):
        for name, value in before.items():
            expected = value+shift if name in ('first_open_midpoint_s', 'first_close_midpoint_s') else value
            if not math.isclose(after[name], expected, rel_tol=1e-12, abs_tol=1e-23):
                raise ValueError('Secondary clock ordinal or relative timing changed: '+name)
    return dict(pulse_sources_checked=pulse_count, primary_lanes=8, secondary_branches=64,
                common_translation_s=shift, all_nonclock_statements_unchanged=True,
                all_pulse_parameters_except_delay_unchanged=True, bank_branch_ordinals_unchanged=True)


def make_protocol(frozen, symbols):
    return dict(schema_version=1, scope=SCOPE, complete_ADC_verified=False,
                physical_FFE_verified=False, validation_fitting_performed=False,
                phase_selection_performed=False, independent_phase_noise_replicates=False,
                frozen_sha256=FROZEN_SHA, script_sha256=digest(__file__),
                frozen_choice_sha256=canonical_hash(frozen['selections']),
                baseline_hardware_sha256=canonical_hash(frozen['identity']),
                dependency_hashes=dict(frozen['identity']['scripts']),
                additional_dependency_hashes=loaded_project_sources(),
                simulator_runner_sha256=digest(PROJECT/'scripts/p6_bench.py'),
                data_seed=DATA_SEED, noise_seed=NOISE_SEED, symbol_sequence_sha256=canonical_hash(symbols),
                generated_symbols=len(symbols), warmup_symbols=WARMUP, score_input_symbols=SCORE,
                end_guard_symbols=GUARD, FFE_complete_windows=SCORE-2*HALF,
                target_score_indices=[WARMUP, WARMUP+SCORE-1],
                target_FFE_indices=[WARMUP+HALF, WARMUP+SCORE-HALF-1],
                nominal_requested_clock_offset_UI=frozen['identity']['backend']['phase_UI'],
                delta_phase_UI=list(DELTAS), cases=case_specs(),
                phase_index_rule='floor((actual primary close - delta_phase_UI*UI - T0)/UI); fixed lag; bank/branch clock ordinal unchanged',
                noise_scope='Same data and fixed noise seed at all phases; adaptive integration means phase cases are not identical noise realizations or independent replicates.',
                timeouts_s=dict(per_case=CASE_TIMEOUT, capacity_wait=WAIT_TIMEOUT, outer=OUTER_TIMEOUT),
                free_space_gate_bytes=MIN_FREE_BYTES,
                timeout_scope='Per-case subprocess timeout and outer dispatch deadline; failures are terminal. Any surviving owned process is recorded, never broadly killed or automatically retried.',
                user_authorization='2026-10-22 bounded real sampling-phase sweep and frozen FFE learning experiment',
                export_scope='All decks, raw traces, coefficients and decision TSVs stay in this VM project.')


def prepare(protocol, frozen, backend, symbols):
    # Refuse all pre-existing directories; --run can separately consume a fully
    # prepared directory after verifying every generated deck and metadata hash.
    if ROOT.exists():
        raise RuntimeError('Study already exists; preparation never overwrites')
    ROOT.mkdir()
    atomic_json(ROOT/'protocol.json', protocol)  # Written before any deck/simulation.
    state = dict(started_utc=utc(), boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                 runner=process_record(os.getpid()), completed_cases=[], automatic_retry=False,
                 protocol_sha256=digest(ROOT/'protocol.json'), scope=SCOPE)
    checkpoint(state, 'preparing')
    try:
        baselines = {}
        for kind, seed in (('noiseless', None), ('noise', NOISE_SEED)):
            baselines[kind] = backend.build_deck(copy.deepcopy(frozen['identity']['frontend']),
                                               copy.deepcopy(frozen['identity']['backend']), symbols, seed)
        for case in protocol['cases']:
            directory = ROOT/case['name']
            directory.mkdir()
            cfg = copy.deepcopy(frozen['identity']['backend'])
            cfg['phase_UI'] += case['delta_phase_UI']
            deck, clocks = backend.build_deck(copy.deepcopy(frozen['identity']['frontend']), cfg,
                                               symbols, case['noise_seed'])
            base_deck, base_clocks = baselines[case['kind']]
            clock_audit = audit_clock_translation(base_deck, deck, base_clocks, clocks,
                                                  case['delta_phase_UI'], backend.pulse_parameters)
            (directory/'bench.scs').write_text('\n'.join(deck)+'\n')
            metadata = dict(case, clock_specification=clocks,
                            deck_sha256=digest(directory/'bench.scs'),
                            backend_only_change=dict(phase_UI=cfg['phase_UI']),
                            common_clock_translation_audit=clock_audit,
                            status='prepared', symbol_sequence_sha256=protocol['symbol_sequence_sha256'])
            atomic_json(directory/'prepared.json', metadata)
        state['prepared_sha256'] = {case['name']: digest(ROOT/case['name']/'prepared.json') for case in protocol['cases']}
        checkpoint(state, 'prepared')
    except BaseException as error:
        checkpoint(state, 'preparation_failed', error=type(error).__name__+': '+str(error))
        raise
    return state


def assert_unchanged(protocol):
    if digest(FROZEN_PATH) != FROZEN_SHA or digest(__file__) != protocol['script_sha256']:
        raise RuntimeError('Frozen choices or sweep script changed')
    for name, expected in protocol['dependency_hashes'].items():
        if digest(PROJECT/'scripts'/name) != expected:
            raise RuntimeError('Frozen dependency changed during sweep: '+name)
    for relative, expected in protocol['additional_dependency_hashes'].items():
        path = (PROJECT/relative).resolve()
        if PROJECT not in path.parents or digest(path) != expected:
            raise RuntimeError('Additional project helper changed during sweep: '+relative)
    if digest(PROJECT/'scripts/p6_bench.py') != protocol['simulator_runner_sha256']:
        raise RuntimeError('Simulator runner changed during sweep')


def analyze(directory, case, frozen, backend, ffe, metrics, psf_ascii, symbols):
    prepared = json.loads((directory/'prepared.json').read_text())
    psf_ascii.MAX_FILE_BYTES = 512*1024*1024
    raw = psf_ascii.parse_file(backend.a._raw_file(directory))
    records, audit = backend.extract_records(raw, prepared['clock_specification'])
    delta = case['delta_phase_UI']
    corrected = {}
    for point, rows in records.items():
        corrected[point] = [(reference_symbol_index(row[3], delta),)+tuple(row[1:]) for row in rows]
        if any(y[0]-x[0] != 1 for x, y in zip(corrected[point], corrected[point][1:])):
            raise ValueError('Reference symbol indices are not contiguous')
    audit['original_extractor_symbol_indices_discarded'] = True
    audit['phase_reference_correction_UI'] = delta
    audit['reference_index_rule'] = 'subtract commanded phase translation before floor; preserve bank/branch ordinal'
    aperture = backend.opt.measured_aperture_phase(corrected['primary'])
    audit['actual_measured_aperture_relative_TX_UI'] = aperture['phase_UI']
    audit['nominal_reference_aperture_after_subtract_delta_UI'] = (aperture['phase_UI']-delta) % 1.0
    audit['commanded_clock_translation_UI'] = delta
    audit['aperture_definition'] = 'Actual half-fall modulo TX UI; nominal reference subtracts commanded delta; neither is the requested baseline phase offset.'
    result = dict(status='analysis_complete', raw_transient_sha256=raw.sha256,
                  clock_mapping_audit=audit, branches={}, scope=SCOPE,
                  validation_fitting_performed=False, phase_selection_performed=False,
                  complete_ADC_verified=False, physical_FFE_verified=False)
    for point in ('primary', 'secondary'):
        choice = frozen['selections'][point]
        samples, labels, rows = align_score(corrected[point], symbols, choice['integer_symbol_lag'])
        detectors = choice['frozen_detectors']
        scores = backend.opt.evaluate_frozen(samples, labels, detectors)
        quantized, clipped = metrics.quantize_symmetric(samples, detectors['ADC_fullscale_differential_Vpp'], 7)
        predictions = ffe.predict_window(quantized, detectors['ADC_FFE'])
        raw_predictions = ffe.predict_window(samples, detectors['raw_FFE'])
        if len(predictions) != 496 or len(raw_predictions) != 496 or len(samples) != 512:
            raise ValueError('Unexpected input/FFE point counts')
        columns = ('delta_phase_UI', 'target_symbol_index', 'true_symbol', 'target_amplitude',
                   'ADC_FFE_target_units', 'raw_FFE_target_units', 'ADC_FFE_decision',
                   'center_held_V', 'center_quantized_V', 'primary_close_s', 'center_read_s',
                   'earliest_last_tap_read_s', 'bank', 'master_cycle', 'secondary_branch')
        tsv = directory/('ffe_'+point+'_decision_points.tsv')
        with tsv.open('w') as output:
            output.write('\t'.join(columns)+'\n')
            for i, prediction in enumerate(predictions):
                center = i+HALF
                row = rows[center]
                master = prepared['clock_specification']['primary_clocks'][row[4]]
                master_cycle = int(round((row[3]-master['first_fall_midpoint_s'])/master['period']))
                values = (delta, WARMUP+center, labels[center], 2*labels[center]-3,
                          prediction, raw_predictions[i], bisect.bisect_right((-2., 0., 2.), prediction),
                          samples[center], quantized[center], row[3], row[2], rows[center+HALF][2],
                          row[4], master_cycle, master_cycle % 8)
                output.write('\t'.join('%.17g'%v if isinstance(v, float) else str(v) for v in values)+'\n')
        result['branches'][point] = dict(metrics=scores, input_sample_count=512, FFE_output_count=496,
                                         integer_lag=choice['integer_symbol_lag'], clipped_count=clipped,
                                         held_min_V=min(samples), held_max_V=max(samples),
                                         TSV_sha256=digest(tsv), TSV_file=tsv.name,
                                         TSV_scope='VM-only numerical sampled decisions; not an analog eye waveform')
    return result


def run(protocol, frozen, backend, ffe, metrics, psf_ascii, symbols):
    state = json.loads((ROOT/'status.json').read_text())
    if state['status'] != 'prepared' or state['completed_cases']:
        raise RuntimeError('Only pristine prepared studies may run; no automatic resume/retry')
    if json.loads((ROOT/'protocol.json').read_text()) != protocol or digest(ROOT/'protocol.json') != state['protocol_sha256']:
        raise RuntimeError('Prepared protocol changed')
    # Verify all cases before launching the first one; nothing can be silently replaced.
    for case in protocol['cases']:
        directory = ROOT/case['name']
        if digest(directory/'prepared.json') != state['prepared_sha256'][case['name']]:
            raise RuntimeError('Prepared metadata changed')
        prepared = json.loads((directory/'prepared.json').read_text())
        if digest(directory/'bench.scs') != prepared['deck_sha256'] or set(x.name for x in directory.iterdir()) != {'bench.scs', 'prepared.json'}:
            raise RuntimeError('Prepared case changed or already executed')
    deadline = time.monotonic()+OUTER_TIMEOUT
    state.update(run_started_utc=utc(), runner=process_record(os.getpid()), boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    try:
        for case in protocol['cases']:
            assert_unchanged(protocol)
            state['current_case'] = case['name']
            actual = await_capacity(state, deadline)
            free_bytes = shutil.disk_usage(str(ROOT)).free
            if free_bytes < MIN_FREE_BYTES:
                raise RuntimeError('Less than 8 GiB free before case; no simulation started')
            remaining = int(deadline-time.monotonic())
            if remaining < 60:
                raise RuntimeError('Ten-hour outer deadline reached; remaining cases not started')
            directory = ROOT/case['name']
            prepared = json.loads((directory/'prepared.json').read_text())
            lines = (directory/'bench.scs').read_text().splitlines()
            checkpoint(state, 'simulating', actual_spectre_before_case=actual,
                       free_space_bytes_before_case=free_bytes,
                       effective_case_timeout_s=min(CASE_TIMEOUT, remaining))
            outcome = backend.a.b.run(directory, lines, timeout=min(CASE_TIMEOUT, remaining))
            atomic_json(directory/'run_status.json', outcome)
            if outcome['exit_code'] != 0:
                raise RuntimeError('Spectre failed in '+case['name']+'; exit='+str(outcome['exit_code']))
            if any(owned_process(x) for x in spectre_inventory()):
                raise RuntimeError('Owned Spectre remains after case exit; refusing further work')
            if digest(directory/'bench.scs') != prepared['deck_sha256']:
                raise RuntimeError('Deck changed while running')
            assert_unchanged(protocol)
            checkpoint(state, 'analyzing')
            result = analyze(directory, case, frozen, backend, ffe, metrics, psf_ascii, symbols)
            result.update(case=case, run_status=outcome, frozen_sha256=FROZEN_SHA,
                          frozen_unchanged=True, protocol_sha256=state['protocol_sha256'],
                          deck_sha256=prepared['deck_sha256'], completed_utc=utc())
            assert_unchanged(protocol)
            atomic_json(directory/'summary.json', result)
            state['completed_cases'].append(dict(name=case['name'], summary_sha256=digest(directory/'summary.json')))
            checkpoint(state, 'case_complete')
        checkpoint(state, 'complete', current_case=None, automatic_retry=False,
                   full_ADC_verified=False, phase_selection_performed=False)
    except BaseException as error:
        checkpoint(state, 'failed_terminal', error=type(error).__name__+': '+str(error),
                   actual_spectre_at_failure=spectre_inventory(), automatic_retry=False)
        raise


def self_test():
    # Synthetic, model-free tests exercise wrap, fixed lag and full FIR windows.
    for base_fraction in (.12, .87):
        for delta in DELTAS:
            for index in (0, 255, 256, 767, 895):
                close = T0+(index+base_fraction+delta)*UI
                if reference_symbol_index(close, delta) != index:
                    raise AssertionError('Phase wrap relabelled a symbol')
    if reference_symbol_index(T0+(256+.12-.5)*UI, -.5) != 256:
        raise AssertionError('Negative half-UI wrap test failed')
    generator = random.Random(DATA_SEED)
    symbols = [generator.randrange(4) for unused in range(WARMUP+SCORE+GUARD)]
    for lag in (1, 3):
        records = [(i+lag, float(i), float(i), T0+(i+lag+.87)*UI, i%8)
                   for i in range(len(symbols))]
        samples, labels, rows = align_score(records, symbols, lag)
        assert len(samples) == 512 and labels == symbols[256:768]
        assert samples[0] == 256 and samples[-1] == 767
        assert len([samples[i-8:i+9] for i in range(8, len(samples)-8)]) == 496
        assert all(len(samples[i-8:i+9]) == 17 for i in range(8, len(samples)-8))
        assert rows[8+8][2] > rows[8][2]  # Full features precede causal availability.
    cases = case_specs()
    assert len(cases) == 18 and all(x['kind'] == 'noiseless' for x in cases[:9])
    assert all(x['kind'] == 'noise' for x in cases[9:])
    assert capacity_available([])
    assert capacity_available([dict(cwd='/other/project')])
    assert not capacity_available([dict(cwd='/other/a'), dict(cwd='/other/b')])
    assert not capacity_available([dict(cwd=str(PROJECT)+'/runs/a')])
    assert not capacity_available([dict(cwd=None)])
    assert capacity_available([dict(cwd=str(PROJECT)+'_another_project')])
    # Exercise the all-clock audit without importing any circuit or PDK module.
    def test_pulse(text):
        fields = {name: float(value) for name, value in re.findall(
            r'\b(delay|rise|fall|width|period|val0|val1)=([^\s]+)', text)}
        fields['first_rise_midpoint_s'] = fields['delay']+fields['rise']/2
        fields['first_fall_midpoint_s'] = fields['delay']+fields['rise']+fields['width']+fields['fall']/2
        return fields
    base_lines = ['V%d (ck%d 0) vsource type=pulse val0=0 val1=.9 delay=%.17g rise=1e-12 fall=1e-12 width=3e-11 period=7e-11'%(i, i, 1e-10) for i in range(144)]
    delta = -.5
    shifted_lines = [re.sub(r'\bdelay=\S+', 'delay=%.17g'%(1e-10+delta*UI), line) for line in base_lines]
    base_clocks = dict(primary_clocks=[{} for unused in range(8)], secondary_clocks=[
        dict(bank=i//8, branch=i%8, first_open_midpoint_s=1e-10,
             first_close_midpoint_s=1.5e-10, period_s=8*8*UI,
             nonoverlap_to_next_primary_begin_s=2e-12) for i in range(64)])
    shifted_clocks = copy.deepcopy(base_clocks)
    for clock in shifted_clocks['secondary_clocks']:
        for name in ('first_open_midpoint_s', 'first_close_midpoint_s'):
            clock[name] += delta*UI
    assert audit_clock_translation(base_lines, shifted_lines, base_clocks, shifted_clocks,
                                   delta, test_pulse)['pulse_sources_checked'] == 144
    shifted_lines[0] = shifted_lines[0].replace('width=3e-11', 'width=4e-11')
    try:
        audit_clock_translation(base_lines, shifted_lines, base_clocks, shifted_clocks, delta, test_pulse)
    except ValueError:
        pass
    else:
        raise AssertionError('Clock proof failed to reject pulse-width change')
    assert 'not a continuous analog FFE waveform' in SCOPE and 'physical ADC' in SCOPE
    return dict(status='passed', tests=['phase wrap preserves reference labels', 'fixed lag aligns 512 inputs',
                                       '17-tap windows yield 496 centers', 'nine noiseless precede nine noise cases',
                                       'capacity blocks owned, two global or unknown simulators without stopping any',
                                       'all-clock audit accepts common translation and rejects width mutation',
                                       'scope excludes analog FFE and complete ADC'], simulations_started=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--run', action='store_true')
    action.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test()), flush=True)
        return
    if os.name != 'posix' or not Path('/proc').is_dir():
        raise RuntimeError('Prepare/run is restricted to the designated Linux VM')
    import fcntl
    if not (PROJECT/'.codex_project6_owned').is_file():
        raise RuntimeError('Missing project ownership marker')
    # Cross-process lock prevents concurrent invocations of this new sweep.
    with (PROJECT/'runs/.ffe_phase_sweep_20261022.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        frozen, backend, ffe, metrics, psf_ascii = load_verified()
        generator = random.Random(DATA_SEED)
        symbols = [generator.randrange(4) for unused in range(WARMUP+SCORE+GUARD)]
        protocol = make_protocol(frozen, symbols)
        if args.prepare or not ROOT.exists():
            prepare(protocol, frozen, backend, symbols)
        if args.run:
            run(protocol, frozen, backend, ffe, metrics, psf_ascii, symbols)
        print(json.dumps({'status': json.loads((ROOT/'status.json').read_text())['status'],
                          'study': str(ROOT), 'scope': SCOPE}), flush=True)


if __name__ == '__main__':
    main()
