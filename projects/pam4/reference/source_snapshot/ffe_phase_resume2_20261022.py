#!/usr/bin/env python3
"""One explicitly authorized post-reboot phase continuation; Python 3.6.

Both preceding run roots remain immutable. Eight successful cases are reused
through project-internal symlinks. Interrupted case08 gets one new attempt,
followed by each of the nine untouched noise cases once. No exit0 is inferred
from the interrupted case's log. Any new failure is terminal again.
No fitting, waveform export, GUI action, model edits, or automatic retries.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
PROJECT = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
SOURCE = PROJECT/'runs/ffe_phase_sweep_20261022'
RETIRED = PROJECT/'runs/ffe_phase_resume1_20261022'
ROOT = PROJECT/'runs/ffe_phase_resume2_20261022'
HELPER = PROJECT/'scripts/ffe_phase_sweep_20261022.py'
HELPER_SHA = '660a374e1da30b5fec84aed9e99a8ecba7de65466532767c83ff2e87ec172a8e'
PROTOCOL_SHA = '67f628995d6101c560a0d783901786166fc707d73e56ec5d82d5fb989c502b82'
RECEIPT = PROJECT/'notes/ffe_phase_sweep_terminal_20261022.json'
RECEIPT_SHA = '4cf257db32903e9485150e4ebaee8c9a6f937d652c194e1ae635d3d6d930115a'
SOURCE_REUSED = (
    ('noiseless_phase_00', 'de4f033b2070b79982f0f20ce4765d5a06700033214c5d18664fe1add82acba8'),
    ('noiseless_phase_01', 'b373861087913c5969b7ec7a011870ae5734cb58d08aa9c83d6a60c97868aed3'),
)
REUSED = SOURCE_REUSED + (
    ('noiseless_phase_02', '49ac94a67ec1d1d636b6194e5c572edda7a67563bd8e4a17764ac077e47d8a8d'),
    ('noiseless_phase_03', '4538e1aea36c1a1fad9f8cc53f77b978700dbbe11536d67a984136ec67d3b683'),
    ('noiseless_phase_04', '8a71aa427bedeca92a69adc3619e1d7e17b6fbe45eb05c4c2f60fb9f82d593cc'),
    ('noiseless_phase_05', '33c56a7765cc699001b6307969dd8f50c61b770e9bd9b6745e558342e27a8a9d'),
    ('noiseless_phase_06', '5e6b4dec253709ba4ad7d2c5c841045b8380adb3983b8f197ac56a50c5857fe4'),
    ('noiseless_phase_07', '71940df7033718aa3ba9cc9e402a376911af457ec442cd1118ffad58a65d7555'),
)
SOURCE_FAILED = 'noiseless_phase_02'
INTERRUPTED = 'noiseless_phase_08'
RETIRED_SCRIPT_SHA = '7cedd4fd32a8c69915dacf144bdcf40217fbfa98847dacd08ba19bdcd6cead71'
RETIRED_PROVENANCE_SHA = 'b627e84eb18b8c1fa09cc64dd599bde96fd49b980701c5615125586b4d5e5ebd'
CASE_TIMEOUT, WAIT_TIMEOUT, OUTER_TIMEOUT = 3600, 1800, 10*3600
MIN_FREE = 8*1024**3


def utc():
    return datetime.datetime.utcnow().isoformat()+'Z'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')
    temp.replace(path)


def checkpoint(state, status, **extra):
    state.update(status=status, updated_utc=utc(), **extra)
    write_json(ROOT/'status.json', state)


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def load_helper():
    if digest(HELPER) != HELPER_SHA:
        raise RuntimeError('Original phase helper changed')
    spec = importlib.util.spec_from_file_location('p6_fixed_phase_original', str(HELPER))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.ROOT = ROOT
    return helper


def classify_process(record):
    """Actual simulator executable, known shell launcher, or unknown identity."""
    executable = record.get('executable') or ''
    name = Path(executable).name
    if name in ('spectre', 'spectre (deleted)'):
        return 'actual'
    if record.get('comm') == 'spectre':
        if name in ('ksh', 'ksh93', 'bash', 'sh'):
            return 'launcher'
        return 'unknown'
    return 'other'


def inventory(helper):
    result = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        record = helper.process_record(path.name)
        if not record or record['state'] == 'Z':
            continue
        kind = classify_process(record)
        if kind in ('actual', 'unknown'):
            record['identity_class'] = kind
            result.append(record)
    return result


def capacity_available(records):
    if len(records) >= 2:
        return False
    for record in records:
        cwd = record.get('cwd')
        if record.get('identity_class') != 'actual' or not cwd:
            return False
        if cwd == str(PROJECT) or cwd.startswith(str(PROJECT)+'/'):
            return False
    return True


def await_capacity(helper, state, deadline):
    end = min(deadline, time.monotonic()+WAIT_TIMEOUT)
    while True:
        actual = inventory(helper)
        if capacity_available(actual):
            return actual
        checkpoint(state, 'waiting_capacity', actual_spectre=actual)
        if time.monotonic() >= end:
            raise RuntimeError('Capacity unavailable within bounded wait; nothing stopped')
        time.sleep(min(10., max(0., end-time.monotonic())))


def source_manifest():
    """All original result files stay put and are hash-pinned, including failure."""
    result = {}
    for path in sorted(SOURCE.rglob('*')):
        if path.is_symlink():
            raise RuntimeError('Unexpected symlink in original terminal study')
        if path.is_file():
            result[str(path.relative_to(SOURCE))] = dict(bytes=path.stat().st_size, sha256=digest(path))
    return result


def verify_original(protocol, helper, full=False, manifest=None):
    if (PROJECT.resolve() != PROJECT or SOURCE.resolve() != SOURCE or
            not (PROJECT/'.codex_project6_owned').is_file()):
        raise RuntimeError('Unexpected project/root or missing ownership marker')
    if digest(SOURCE/'protocol.json') != PROTOCOL_SHA or digest(RECEIPT) != RECEIPT_SHA:
        raise RuntimeError('Original protocol or terminal receipt changed')
    if digest(HELPER) != HELPER_SHA:
        raise RuntimeError('Original helper changed')
    helper.assert_unchanged(protocol)
    original = read_json(SOURCE/'status.json')
    expected = [dict(name=name, summary_sha256=sha) for name, sha in SOURCE_REUSED]
    if (original.get('status') != 'failed_terminal' or original.get('current_case') != SOURCE_FAILED or
            original.get('completed_cases') != expected):
        raise RuntimeError('Original terminal state is not the authorized two-complete/third-failed study')
    failed_status = read_json(SOURCE/SOURCE_FAILED/'run_status.json')
    if failed_status.get('exit_code') != -6 or 'SPECTRE-18' not in failed_status.get('issue_codes', []):
        raise RuntimeError('Original failure evidence differs')
    for name, expected_sha in SOURCE_REUSED:
        directory = SOURCE/name
        if digest(directory/'summary.json') != expected_sha:
            raise RuntimeError('Reused completed summary changed: '+name)
        summary = read_json(directory/'summary.json')
        if (summary.get('status') != 'analysis_complete' or
                summary.get('run_status', {}).get('exit_code') != 0 or
                summary.get('protocol_sha256') != PROTOCOL_SHA or
                summary.get('frozen_unchanged') is not True or
                summary.get('validation_fitting_performed') is not False):
            raise RuntimeError('Reused case is not a verified frozen result')
        for branch in ('primary', 'secondary'):
            info = summary['branches'][branch]
            filename = 'ffe_'+branch+'_decision_points.tsv'
            if (info['TSV_file'] != filename or info['input_sample_count'] != 512 or
                    info['FFE_output_count'] != 496 or digest(directory/filename) != info['TSV_sha256']):
                raise RuntimeError('Reused branch count or TSV hash changed')
    if full and source_manifest() != manifest:
        raise RuntimeError('An original terminal-run file changed')


def retired_manifest():
    """Pin every retired file and the two links, without walking link targets."""
    result = {}
    allowed_links = {str(RETIRED/name): str(SOURCE/name) for name, unused in SOURCE_REUSED}
    for parent, directories, files in os.walk(str(RETIRED), followlinks=False):
        for name in sorted(directories+files):
            path = Path(parent)/name
            relative = str(path.relative_to(RETIRED))
            if path.is_symlink():
                target = os.readlink(str(path))
                if str(path) not in allowed_links or target != allowed_links[str(path)]:
                    raise RuntimeError('Unexpected retired-run symlink: '+relative)
                result[relative] = dict(kind='symlink', target=target,
                    target_sha256=hashlib.sha256(target.encode('utf-8')).hexdigest())
                if name in directories:
                    directories.remove(name)
            elif path.is_file():
                result[relative] = dict(kind='file', bytes=path.stat().st_size, sha256=digest(path))
            elif not path.is_dir():
                raise RuntimeError('Unexpected retired-run entry: '+relative)
    if len([value for value in result.values() if value['kind'] == 'symlink']) != 2:
        raise RuntimeError('Retired root must contain exactly the two known reused-case links')
    return result


def verify_retired(helper, full=False, manifest=None, prepare_checks=False):
    if RETIRED.resolve() != RETIRED or not RETIRED.is_dir():
        raise RuntimeError('Unexpected retired root')
    if digest(PROJECT/'scripts/ffe_phase_resume1_20261022.py') != RETIRED_SCRIPT_SHA:
        raise RuntimeError('Retired dispatcher source changed')
    if digest(RETIRED/'resume_provenance.json') != RETIRED_PROVENANCE_SHA:
        raise RuntimeError('Retired provenance changed')
    if digest(RETIRED/'protocol.json') != PROTOCOL_SHA:
        raise RuntimeError('Retired protocol changed')
    old_state = read_json(RETIRED/'status.json')
    expected = [dict(name=name, summary_sha256=sha) for name, sha in REUSED]
    if (old_state.get('status') != 'simulating' or old_state.get('current_case') != INTERRUPTED or
            old_state.get('completed_cases') != expected):
        raise RuntimeError('Retired run is not the pinned eight-complete/case08-interrupted study')
    old_launch = read_json(RETIRED/'launch_receipt.json')
    pause = read_json(RETIRED/'travel_pause_20261022.json')
    if (old_launch['boot_id'] != old_state['boot_id'] or pause['boot_id'] != old_state['boot_id'] or
            pause.get('status') != 'paused_by_user_verified' or
            pause.get('current_case') != INTERRUPTED or pause.get('completed_cases') != expected or
            old_state['boot_id'] == boot_id()):
        raise RuntimeError('Retired boot/pause identity is inconsistent or old boot still active')
    if (RETIRED/INTERRUPTED/'run_status.json').exists() or (RETIRED/INTERRUPTED/'summary.json').exists():
        raise RuntimeError('Interrupted case now has an exit/summary; inspect instead of retrying')
    if prepare_checks:
        for reference in pause['stopped']:
            if (Path('/proc')/str(reference['pid'])).exists():
                raise RuntimeError('Old PID is present; inspect boot/PID reuse before preparation')
        records = inventory(helper)
        if any(record.get('identity_class') != 'actual' or not record.get('cwd') or
               record['cwd'] == str(PROJECT) or record['cwd'].startswith(str(PROJECT)+'/')
               for record in records):
            raise RuntimeError('Cannot prepare beside an owned or unidentified simulator')
    for name, expected_sha in REUSED:
        directory = RETIRED/name
        if name in dict(SOURCE_REUSED):
            if not directory.is_symlink() or os.readlink(str(directory)) != str(SOURCE/name):
                raise RuntimeError('Retired original-case link changed')
        elif directory.is_symlink() or directory.resolve() != directory:
            raise RuntimeError('Unexpected symlink in retired completed case')
        if digest(directory/'summary.json') != expected_sha:
            raise RuntimeError('Retired completed summary changed: '+name)
        summary = read_json(directory/'summary.json')
        prepared = read_json(directory/'prepared.json')
        if (summary.get('status') != 'analysis_complete' or
                summary.get('run_status', {}).get('exit_code') != 0 or
                summary.get('protocol_sha256') != PROTOCOL_SHA or
                summary.get('frozen_sha256') != helper.FROZEN_SHA or
                summary.get('frozen_unchanged') is not True or
                summary.get('validation_fitting_performed') is not False or
                summary.get('phase_selection_performed') is not False or
                summary.get('deck_sha256') != prepared['deck_sha256'] or
                digest(directory/'bench.scs') != prepared['deck_sha256'] or
                digest(directory/'bench.scs') != digest(SOURCE/name/'bench.scs')):
            raise RuntimeError('Retired case lacks a verified unchanged frozen result: '+name)
        for branch in ('primary', 'secondary'):
            info = summary['branches'][branch]
            filename = 'ffe_'+branch+'_decision_points.tsv'
            if (info['TSV_file'] != filename or info['input_sample_count'] != 512 or
                    info['FFE_output_count'] != 496 or digest(directory/filename) != info['TSV_sha256']):
                raise RuntimeError('Retired branch count or TSV changed: '+name)
    if full and retired_manifest() != manifest:
        raise RuntimeError('A retired run file or symlink changed')


def prepare(helper, protocol):
    if ROOT.exists() or ROOT.is_symlink():
        raise RuntimeError('Continuation root already exists; never overwrite')
    verify_original(protocol, helper)
    verify_retired(helper, prepare_checks=True)
    if shutil.disk_usage(str(SOURCE)).free < MIN_FREE:
        raise RuntimeError('Less than 8 GiB free before preparation')
    original_state = read_json(SOURCE/'status.json')
    manifest = source_manifest()
    retired_files = retired_manifest()
    ROOT.mkdir()
    state = dict(started_utc=utc(), boot_id=boot_id(), runner=helper.process_record(os.getpid()),
                 completed_cases=[dict(name=name, summary_sha256=sha) for name, sha in REUSED],
                 reused_completed_cases=[name for name, unused in REUSED],
                 original_terminal_root=str(SOURCE), retired_interrupted_root=str(RETIRED), automatic_retry=False,
                 protocol_sha256=PROTOCOL_SHA, scope=helper.SCOPE)
    checkpoint(state, 'preparing', current_case=None)
    try:
        shutil.copyfile(str(SOURCE/'protocol.json'), str(ROOT/'protocol.json'))
        for case in protocol['cases']:
            name = case['name']
            source, target = SOURCE/name, ROOT/name
            if name in state['reused_completed_cases']:
                target.symlink_to(RETIRED/name, target_is_directory=True)
                continue
            target.mkdir()
            expected = original_state['prepared_sha256'][name]
            if digest(source/'prepared.json') != expected:
                raise RuntimeError('Original prepared metadata changed: '+name)
            prepared = read_json(source/'prepared.json')
            if digest(source/'bench.scs') != prepared['deck_sha256']:
                raise RuntimeError('Original prepared deck changed: '+name)
            for filename in ('bench.scs', 'prepared.json'):
                shutil.copyfile(str(source/filename), str(target/filename))
                if digest(source/filename) != digest(target/filename):
                    raise RuntimeError('VM-only exact file copy failed')
        state['prepared_sha256'] = dict(original_state['prepared_sha256'])
        provenance = dict(created_utc=utc(), wrapper_sha256=digest(__file__),
                          original_helper_sha256=HELPER_SHA, original_protocol_sha256=PROTOCOL_SHA,
                          original_terminal_receipt=str(RECEIPT), original_terminal_receipt_sha256=RECEIPT_SHA,
                          original_source_manifest=manifest, original_root=str(SOURCE),
                          retired_root=str(RETIRED), retired_source_manifest=retired_files,
                          retired_provenance_sha256=RETIRED_PROVENANCE_SHA,
                          retired_script_sha256=RETIRED_SCRIPT_SHA,
                          retired_boot_id=read_json(RETIRED/'status.json')['boot_id'],
                          interrupted_case=INTERRUPTED, interrupted_exit_status_known=False,
                          interrupted_case_reused_as_success=False,
                          reused_cases=state['completed_cases'],
                          authorization='User said continue on 2026-10-22 after travel pause; verified VM reboot removed stopped processes.',
                          attempt_policy='Reuse eight verified complete cases; one new attempt of interrupted case08; nine untouched noise cases once; stop on any new failure.',
                          unchanged_experiment=True, fresh_independent_holdout=False,
                          automatic_retry=False, simulations_started_during_prepare=0,
                          changed_execution_only='New isolated simulator session, exact original simulator command and prepared decks.')
        write_json(ROOT/'resume_provenance.json', provenance)
        state['resume_provenance_sha256'] = digest(ROOT/'resume_provenance.json')
        verify_original(protocol, helper, full=True, manifest=manifest)
        verify_retired(helper, full=True, manifest=retired_files)
        checkpoint(state, 'prepared')
    except BaseException as error:
        checkpoint(state, 'preparation_failed', error=type(error).__name__+': '+str(error))
        raise
    return state


def session_members(helper, sid):
    members = []
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            record = helper.process_record(path.name)
            if record and record['state'] != 'Z' and record['sid'] == sid:
                members.append(record)
    return members


def stop_own_session(helper, child, identity, directory, expected_boot):
    """Only exact members of our newly-created case session may be signalled."""
    evidence = dict(sid=child.pid, signals=[], refused=[], remaining=[])
    if not identity or identity['sid'] != child.pid or boot_id() != expected_boot:
        evidence['refused'].append('Missing/mismatched launch identity or VM reboot')
        return evidence
    for sig in (signal.SIGTERM, signal.SIGKILL):
        members = session_members(helper, child.pid)
        for member in members:
            if (member['start_ticks'] < identity['start_ticks'] or member['cwd'] != str(directory) or
                    member['sid'] != identity['sid']):
                evidence['refused'].append(member)
                continue
            fresh = helper.process_record(member['pid'])
            if not fresh or fresh['state'] == 'Z':
                continue
            if any(fresh[key] != member[key] for key in ('pid', 'start_ticks', 'sid', 'cwd')):
                evidence['refused'].append(dict(identity_changed=member['pid']))
                continue
            try:
                os.kill(member['pid'], sig)
                evidence['signals'].append(dict(pid=member['pid'], start_ticks=member['start_ticks'], signal=int(sig)))
            except ProcessLookupError:
                pass
        end = time.monotonic()+3
        while time.monotonic() < end and session_members(helper, child.pid):
            time.sleep(.1)
    evidence['remaining'] = session_members(helper, child.pid)
    return evidence


def run_case(helper, backend, directory, timeout, state):
    # Preserve bench.scs byte for byte; the original helper would rewrite it.
    command = [backend.a.b.SPECTRE, '-64', 'bench.scs', '-format', 'psfascii',
               '-raw', 'raw', '+log', 'spectre.log', '+lqtimeout', '30']
    started = time.monotonic()
    launch_boot = boot_id()
    cleanup = None
    with (directory/'console.log').open('x') as output:
        child = subprocess.Popen(command, cwd=str(directory), stdout=output,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        identity = helper.process_record(child.pid)
        write_json(directory/'launch_identity.json', dict(utc=utc(), boot_id=launch_boot,
                   pid=child.pid, identity=identity, isolated_session=True,
                   simulator_command=command, timeout_s=timeout))
        checkpoint(state, 'simulating', case_process=identity, case_pid=child.pid,
                   case_session_id=child.pid)
        try:
            code = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            code = 'timeout'
            cleanup = stop_own_session(helper, child, identity, directory, launch_boot)
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        except BaseException:
            cleanup = stop_own_session(helper, child, identity, directory, launch_boot)
            write_json(directory/'interruption_cleanup.json', cleanup)
            raise
    text = (directory/'spectre.log').read_text(errors='replace') if (directory/'spectre.log').is_file() else ''
    result = dict(exit_code=code, seconds=round(time.monotonic()-started, 3),
                  issue_codes=sorted(set(re.findall(r'\b(?:SFE|SPECTRE)-\d+\b', text))),
                  audit=re.findall(r'spectre completes with.*', text)[-1:],
                  isolated_session=True, session_id=child.pid)
    if code != 0:
        result['error_lines'] = [line for line in text.splitlines() if 'ERROR' in line or 'Error' in line][-12:]
    if cleanup is not None:
        result['timeout_cleanup'] = cleanup
    write_json(directory/'run_status.json', result)
    return result


def verify_prepared(state, protocol, provenance, helper):
    if (state.get('status') != 'prepared' or state['completed_cases'] != provenance['reused_cases'] or
            state['protocol_sha256'] != PROTOCOL_SHA or digest(ROOT/'protocol.json') != PROTOCOL_SHA or
            digest(ROOT/'resume_provenance.json') != state['resume_provenance_sha256'] or
            digest(__file__) != provenance['wrapper_sha256']):
        raise RuntimeError('Continuation not pristine prepared state; no automatic resume/retry')
    verify_original(protocol, helper, full=True, manifest=provenance['original_source_manifest'])
    verify_retired(helper, full=True, manifest=provenance['retired_source_manifest'])
    for case in protocol['cases']:
        name, directory = case['name'], ROOT/case['name']
        if name in state['reused_completed_cases']:
            if (not directory.is_symlink() or os.readlink(str(directory)) != str(RETIRED/name) or
                    directory.resolve() != (RETIRED/name).resolve()):
                raise RuntimeError('Reused-case symlink target changed')
            continue
        if directory.is_symlink() or directory.resolve() != directory:
            raise RuntimeError('Unexpected writable case symlink')
        if set(p.name for p in directory.iterdir()) != {'bench.scs', 'prepared.json'}:
            raise RuntimeError('Remaining case already executed or altered: '+name)
        if digest(directory/'prepared.json') != state['prepared_sha256'][name]:
            raise RuntimeError('Copied prepared metadata changed')
        if digest(directory/'bench.scs') != read_json(directory/'prepared.json')['deck_sha256']:
            raise RuntimeError('Copied prepared deck changed')


def run(helper, protocol):
    state = read_json(ROOT/'status.json')
    provenance = read_json(ROOT/'resume_provenance.json')
    verify_prepared(state, protocol, provenance, helper)
    frozen, backend, ffe, metrics, psf_ascii = helper.load_verified()
    # Importing modules is allowed; generating/replacing decks is not.
    verify_original(protocol, helper)
    verify_retired(helper)
    rng = random.Random(helper.DATA_SEED)
    symbols = [rng.randrange(4) for unused in range(helper.WARMUP+helper.SCORE+helper.GUARD)]
    if helper.canonical_hash(symbols) != protocol['symbol_sequence_sha256']:
        raise RuntimeError('Original fixed symbol sequence does not match')
    deadline = time.monotonic()+OUTER_TIMEOUT
    state.update(run_started_utc=utc(), boot_id=boot_id(), runner=helper.process_record(os.getpid()))
    try:
        for case in protocol['cases'][len(REUSED):]:
            if digest(__file__) != provenance['wrapper_sha256']:
                raise RuntimeError('Continuation wrapper changed')
            verify_original(protocol, helper)
            verify_retired(helper)
            state['current_case'] = case['name']
            actual = await_capacity(helper, state, deadline)
            if shutil.disk_usage(str(ROOT)).free < MIN_FREE:
                raise RuntimeError('Less than 8 GiB free; case not started')
            remaining = int(deadline-time.monotonic())
            if remaining < 60:
                raise RuntimeError('Ten-hour dispatch deadline reached; case not started')
            directory = ROOT/case['name']
            prepared = read_json(directory/'prepared.json')
            if digest(directory/'prepared.json') != state['prepared_sha256'][case['name']]:
                raise RuntimeError('Copied metadata changed before launch')
            if digest(directory/'bench.scs') != prepared['deck_sha256']:
                raise RuntimeError('Copied deck changed before launch')
            checkpoint(state, 'launching', actual_spectre_before_case=actual,
                       effective_case_timeout_s=min(CASE_TIMEOUT, remaining))
            outcome = run_case(helper, backend, directory, min(CASE_TIMEOUT, remaining), state)
            if outcome['exit_code'] != 0 or 'SPECTRE-18' in outcome['issue_codes']:
                raise RuntimeError('Spectre failed in '+case['name']+'; exit='+str(outcome['exit_code']))
            if any((record.get('cwd') or '') == str(PROJECT) or
                   (record.get('cwd') or '').startswith(str(PROJECT)+'/') for record in inventory(helper)):
                raise RuntimeError('Owned simulator remains after exit; no further case dispatched')
            if digest(directory/'bench.scs') != prepared['deck_sha256']:
                raise RuntimeError('Deck changed while simulating')
            verify_original(protocol, helper)
            checkpoint(state, 'analyzing')
            result = helper.analyze(directory, case, frozen, backend, ffe, metrics, psf_ascii, symbols)
            result.update(case=case, run_status=outcome, frozen_sha256=helper.FROZEN_SHA,
                          frozen_unchanged=True, protocol_sha256=PROTOCOL_SHA,
                          deck_sha256=prepared['deck_sha256'], completed_utc=utc())
            verify_original(protocol, helper)
            write_json(directory/'summary.json', result)
            state['completed_cases'].append(dict(name=case['name'], summary_sha256=digest(directory/'summary.json')))
            checkpoint(state, 'case_complete')
        verify_original(protocol, helper, full=True, manifest=provenance['original_source_manifest'])
        verify_retired(helper, full=True, manifest=provenance['retired_source_manifest'])
        checkpoint(state, 'complete', current_case=None, automatic_retry=False,
                   full_ADC_verified=False, phase_selection_performed=False)
    except BaseException as error:
        checkpoint(state, 'failed_terminal', error=type(error).__name__+': '+str(error),
                   actual_spectre_at_failure=inventory(helper), automatic_retry=False)
        raise


def self_test():
    # Local synthetic checks only: no project/PDK, SSH, simulator, or GUI access.
    assert classify_process(dict(executable='/bin/ksh', comm='spectre')) == 'launcher'
    assert classify_process(dict(executable='/cadence/bin/spectre', comm='spectre')) == 'actual'
    assert classify_process(dict(executable=None, comm='spectre')) == 'unknown'
    assert classify_process(dict(executable='/cadence/bin/spectre (deleted)', comm='spectre')) == 'actual'
    assert capacity_available([])
    assert capacity_available([dict(executable='/x/spectre', identity_class='actual', cwd='/other/project')])
    assert not capacity_available([dict(identity_class='actual', cwd='/other/a'), dict(identity_class='actual', cwd='/other/b')])
    assert not capacity_available([dict(identity_class='actual', cwd=str(PROJECT)+'/runs/case')])
    assert not capacity_available([dict(identity_class='unknown', cwd='/other/project')])
    assert not capacity_available([dict(identity_class='actual', cwd=None)])
    names = ['%s_phase_%02d'%(kind, index) for kind in ('noiseless', 'noise') for index in range(9)]
    assert names[:2] == [name for name, unused in SOURCE_REUSED]
    assert names[:8] == [name for name, unused in REUSED]
    assert names[2] == SOURCE_FAILED and names[8] == INTERRUPTED
    assert len(names[8:]) == 10 and len(set(names[8:])) == 10
    assert names[9:] == ['noise_phase_%02d'%index for index in range(9)]
    original = Path(__file__).with_name('ffe_phase_sweep_20261022.py')
    if digest(original) != HELPER_SHA:
        raise AssertionError('Local original helper hash does not match reviewed VM source')
    spec = importlib.util.spec_from_file_location('p6_original_test_only', str(original))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    result = helper.self_test()
    assert result['status'] == 'passed' and result['simulations_started'] == 0
    return dict(status='passed', simulations_started=0, tests=[
        'actual executable distinguished from ksh launcher and unknown identity',
        'capacity gate permits at most one existing external simulator and no owned simulator',
        'original two-case provenance separate from eight post-reboot reused results',
        'eight complete cases reused; interrupted case08 and nine untouched noise cases attempted once',
        'immutable original helper self-tests including crossing-UI labels and496 FFE points'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--run', action='store_true')
    group.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test()), flush=True)
        return
    if os.name != 'posix' or not Path('/proc').is_dir():
        raise RuntimeError('Prepare/run restricted to designated Linux VM')
    if (PROJECT.resolve() != PROJECT or ROOT.resolve() != ROOT or
            Path(__file__).resolve().parent != PROJECT/'scripts' or
            not (PROJECT/'.codex_project6_owned').is_file()):
        raise RuntimeError('Wrong project, script location, or ownership marker')
    import fcntl
    # Both locks live outside the immutable original root. A restarted old
    # wrapper cannot overlap with this authorized continuation.
    with (PROJECT/'runs/.ffe_phase_sweep_20261022.lock').open('a') as old_lock:
        fcntl.flock(old_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (PROJECT/'runs/.ffe_phase_resume1_20261022.lock').open('a') as new_lock:
            fcntl.flock(new_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with (PROJECT/'runs/.ffe_phase_resume2_20261022.lock').open('a') as current_lock:
                fcntl.flock(current_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                helper = load_helper()
                protocol = read_json(SOURCE/'protocol.json')
                if args.prepare:
                    prepare(helper, protocol)
                else:
                    run(helper, protocol)
                print(json.dumps(dict(status=read_json(ROOT/'status.json')['status'],
                                      root=str(ROOT), automatic_retry=False)), flush=True)


if __name__ == '__main__':
    main()
