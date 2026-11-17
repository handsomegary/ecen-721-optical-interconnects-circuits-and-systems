#!/usr/bin/env python3
"""One bounded retry of the unchanged r5 noise holdout; Python 3.6 compatible.

No fitting, new candidate, noiseless rerun, automatic replay, or unrelated signal.
All archive manifests, decks, native cards and raw results stay in the VM project.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import types

P = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R = P/'runs/project6_noise_retry2_20261020'
STUDY = P/'runs/adc_backend_pam4_r5_20261013/r5_late1'
BOOT = '3490e49c-4bfb-400c-a537-9a5d936e2e6d'
HELPER_SHA = '0c02120d0a049f22b52f5fa08392cb1498f13718c6a6a410f35c263416b25b16'
NOISELESS_SHA = 'ff8a466c80549cc476e8c768e56aea64cdab4ed4abb8a6b5d2709769519f716f'
PARTIAL_SHA = '282aa605d96b7b65c9a8e2e918189af2f082bd22c53b145460d45437311c55f0'
DECK_SHA = '3109f222211963fe5fcadbbb96b6605f8c4c7a8d32aa35bae178678f1d927fa2'
SYMBOL_SHA = '67fa287fe82d08414b207177bf915c50e4b61692cc1fde0d4b9dbf4774f54633'
CHOICE_SHA = '7fb7dbcbe76fa94857d80fea75b9b47db81761b69ac2a4efd5698332a1daff4e'
ARCHIVE = STUDY/'validation_noise_failed_readin_20261020_archived_retry2'
MIN_FREE = 8*1024**3
DIAG_ROOT = P/'runs/project6_readin_diagnostic_20261020'
DIAG_SHA = '7ecbcfa75c135d15593363141997e73a310fc18e835498bf53454dbde5e35e90'
DIAG_SCRIPT_SHA = '4e9251e8ba4c30cb0d2b298136188c6b59ecbd32fb222f18bead5a1d7b816ff6'
PRIOR_STATE_SHA = '4d6bef1ea9a56a9cca84a7aadc3e5b1e94511b9a399a597e707dffa6dc20231e'
FAILED_FILES = {
    'bench.scs': DECK_SHA,
    'run_summary.json': PARTIAL_SHA,
    'console.log': '23c261337d56f8e22926f200d4bd4c3b80b88e5f019982295ce8fd4b80c93437',
    'spectre.log': '1a87bbeaa04eadcfa862869fefea319706eb4f4d298ea367671b872248e2c0ea',
    'run_status.json': '2240c1bcae051ce687b5e216eae812ef0542397f0bc48168c2acd0557a0a1685',
}
PROTECTED_FILES = {
    P/'configs/native_device_cards.json': '8d05bd62f3e668c64569459e90373024ca76998f510ec5d2b7a23cd3f5749b9a',
    P/'configs/pam4_optimization_frozen.json': '2eef7e17f3e51248f82d8f2ff7b643905f2e906c040ffb18b4e8d24a3f7f0309',
    Path('<PDK_ROOT>/models/spectre/pdk_model.scs'):
        '002300afbc872cca7c0bab744740eb74ff2cc71e770832c6e6d97c447dbfff78',
}
ENV_KEYS = ('PATH', 'LD_LIBRARY_PATH', 'LD_PRELOAD', 'SPECTRE_DEFAULTS',
            'CDS_AUTO_64BIT', 'CDS_Netlisting_Mode', 'LANG', 'LC_ALL',
            'CDS_LIC_FILE', 'LM_LICENSE_FILE')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_helper():
    path = Path(__file__).with_name('run_r5_reboot_resume.py')
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != HELPER_SHA:
        raise RuntimeError('Immutable helper identity changed')
    module = types.ModuleType('immutable_r5_helper')
    module.__file__ = str(path)
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def verify_sources(helper):
    result = helper.verify_sources()
    for path, expected in PROTECTED_FILES.items():
        if digest(path) != expected:
            raise RuntimeError('Protected file identity changed: '+str(path))
        result[str(path)] = expected
    return result


def original_environment():
    env = os.environ.copy()
    env['CDS_LIC_FILE'] = '<LICENSE_FILE>'
    env['LM_LICENSE_FILE'] = env['CDS_LIC_FILE']
    return env


def acceptable_diagnostic(record, env):
    cases = record.get('cases', [])
    if (record.get('status') != 'complete' or record.get('stage') != 'diagnostics_complete' or
            record.get('boot_id') != BOOT or record.get('wrapper_sha256') != DIAG_SCRIPT_SHA or len(cases) != 1):
        return False
    case = cases[0]
    phase = case.get('phases', {})
    cleanup = case.get('cleanup')
    return (case.get('name') == 'A_original' and case.get('deck_sha256') == DECK_SHA and
            case.get('removed_environment_keys') == [] and case.get('runner_error') is None and
            case.get('cleanup_error') is None and isinstance(cleanup, dict) and cleanup.get('remaining') == [] and
            case.get('cutoff_reached') is True and case.get('exit_code') == 3 and
            case.get('readin_progressed') is True and phase.get('spectre18') is False and
            all(phase.get(k) is True for k in ('edb_visiting', 'circuit_inventory', 'transient_started')) and
            phase.get('error_codes') == ['SFE-1131'] and
            case.get('env_allowlist') == {k: env.get(k) for k in ENV_KEYS})


def verify_diagnostic(env):
    summary = DIAG_ROOT/'summary.json'
    state = DIAG_ROOT/'status.json'
    script = P/'scripts/diagnose_readin_20261020.py'
    if digest(summary) != DIAG_SHA or digest(state) != DIAG_SHA or digest(script) != DIAG_SCRIPT_SHA:
        raise RuntimeError('Reviewed diagnostic evidence changed or is not terminal')
    record = json.loads(summary.read_text())
    if not acceptable_diagnostic(record, env):
        raise RuntimeError('Diagnostic outcome/environment differs from reviewed original-environment progress')
    for path, expected in record['cases'][0].get('dependency_sha256', {}).items():
        if not Path(path).is_absolute() or digest(path) != expected:
            raise RuntimeError('Diagnostic direct dependency identity changed')
    return dict(summary_sha256=DIAG_SHA, script_sha256=DIAG_SCRIPT_SHA,
                selected_environment='A_original', env_allowlist={k: env.get(k) for k in ENV_KEYS},
                interpretation='Original environment progressed into transient under 30-second cutoff; historical fault not reproduced; root cause unknown')


def require_startup_memory():
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0])*1024
    if available < 2*1024**3:
        raise RuntimeError('Startup MemAvailable below 2 GiB')
    return available


def write_new(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def save(state, stage, **values):
    state.update(stage=stage, updated_UTC=datetime.datetime.utcnow().isoformat()+'Z', **values)
    temporary = R/'status.tmp'
    with temporary.open('w') as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(R/'status.json')
    with (R/'events.jsonl').open('a') as handle:
        handle.write(json.dumps(state, sort_keys=True)+'\n')
        handle.flush()
        os.fsync(handle.fileno())


def owned_cwd(cwd):
    if not cwd:
        return False
    path = Path(cwd).resolve()
    return path == P.resolve() or P.resolve() in path.parents


def process_rows():
    rows = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            stat = (path/'stat').read_text()
            fields = stat[stat.rfind(')')+2:].split()
            if fields[0] == 'Z':
                continue
            try:
                cwd = os.readlink(str(path/'cwd'))
            except (OSError, PermissionError):
                cwd = None
            try:
                exe = os.readlink(str(path/'exe'))
            except (OSError, PermissionError):
                exe = None
            args = [s.decode('utf8', 'replace') for s in (path/'cmdline').read_bytes().split(b'\0') if s]
            rows.append(dict(pid=int(path.name), ppid=int(fields[1]), pgid=int(fields[2]),
                             sid=int(fields[3]), start=fields[19], cwd=cwd, exe=exe, args=args))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return rows


def capacity_rows(helper, rows, self_pid):
    jobs = [r for r in rows if r.get('exe') and Path(r['exe']).name.lower() in ('spectre', 'spectre.exe')]
    for row in rows:
        if row['pid'] == self_pid:
            continue
        if row.get('exe') is None and any(Path(a).name == 'spectre' for a in row.get('args', [])[:2]):
            raise RuntimeError('Unclassifiable possible Spectre process')
        script = helper.script_path(row)
        if script and ((P/'scripts').resolve() in Path(script).resolve().parents):
            raise RuntimeError('Owned script worker already exists')
        if row in jobs and owned_cwd(row.get('cwd')):
            raise RuntimeError('Owned Spectre already exists')
        if owned_cwd(row.get('cwd')) and row.get('exe') and 'python' in Path(row['exe']).name.lower():
            raise RuntimeError('Unclassified project Python worker already exists')
    return len(jobs) < 2, len(jobs)


def capacity(helper):
    return capacity_rows(helper, process_rows(), os.getpid())


def session_members(rows, identity, current_boot):
    """Fail closed before signaling any member of the session we created."""
    if current_boot != identity['boot_id'] or not identity.get('start'):
        raise RuntimeError('Cannot verify created session boot/leader start')
    members = [r for r in rows if r['sid'] == identity['sid'] or r['pgid'] == identity['pgid']]
    for row in members:
        if (row['sid'] != identity['sid'] or row['pgid'] != identity['pgid'] or
                not owned_cwd(row.get('cwd'))):
            raise RuntimeError('Unclassifiable session member; no signal permitted')
        if int(row['start']) < int(identity['start']):
            raise RuntimeError('Session member predates created leader; no signal permitted')
        if row['pid'] == identity['pid'] and row['start'] != identity['start']:
            raise RuntimeError('Session leader PID reused; no signal permitted')
    return members


def cleanup_session(helper, identity):
    """Only the new isolated session can be signaled; keep a full receipt."""
    receipt = dict(signals=[], remaining=[], scope='Verified newly created session only')
    if identity is None:
        return receipt
    for signum, grace in ((signal.SIGINT, 3), (signal.SIGTERM, 8), (signal.SIGKILL, 3)):
        members = session_members(process_rows(), identity, helper.boot_id())
        if not members:
            return receipt
        # Recheck all members and their start times immediately before the signal.
        fresh = session_members(process_rows(), identity, helper.boot_id())
        old_starts = {r['pid']: r['start'] for r in members}
        if any(r['pid'] in old_starts and r['start'] != old_starts[r['pid']] for r in fresh):
            raise RuntimeError('Session membership identity changed; no signal permitted')
        if not fresh:
            return receipt
        os.killpg(identity['pgid'], signum)
        receipt['signals'].append(dict(signal=int(signum), verified_members=fresh))
        end = time.monotonic()+grace
        while time.monotonic() < end:
            if not session_members(process_rows(), identity, helper.boot_id()):
                return receipt
            time.sleep(.25)
    receipt['remaining'] = session_members(process_rows(), identity, helper.boot_id())
    return receipt


def check_environment(helper):
    helper.require_stable_boot(BOOT)
    free = shutil.disk_usage(str(P)).free
    if free < MIN_FREE:
        raise RuntimeError('Guest project filesystem has less than 8 GiB free')
    return free


def verify_noiseless(helper):
    path = STUDY/'validation_noiseless/run_summary.json'
    if digest(path) != NOISELESS_SHA or not helper.complete(json.loads(path.read_text()), 'noiseless', 0):
        raise RuntimeError('Completed noiseless reference changed or is incomplete')


def check_generated(record):
    if (record.get('deck_sha256') != DECK_SHA or record.get('symbol_sequence_sha256') != SYMBOL_SHA or
            record.get('symbol_count') != 3264 or record.get('noise_seed') != 173):
        raise RuntimeError('Retry deck, symbol sequence, count or noise seed differs')


def manifest(directory):
    if directory.is_symlink() or directory.parent.resolve() != STUDY.resolve() or not directory.is_dir():
        raise RuntimeError('Unexpected archive source/destination path')
    files = []
    directories = []
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise RuntimeError('Symlink in partial results; refusing archive')
        name = str(path.relative_to(directory))
        if path.is_file():
            files.append(dict(path=name, bytes=path.stat().st_size, sha256=digest(path)))
        elif path.is_dir():
            directories.append(name)
        else:
            raise RuntimeError('Unexpected special file in partial results')
    return dict(files=files, directories=directories)


def verify_failed_manifest(before):
    files = before['files']
    if len(files) != len(FAILED_FILES) or {f['path'] for f in files} != set(FAILED_FILES):
        raise RuntimeError('Failed directory does not contain exactly the five reviewed files')
    for entry in files:
        if entry['sha256'] != FAILED_FILES[entry['path']]:
            raise RuntimeError('Failed evidence bytes changed: '+entry['path'])


def archive_partial(helper, state):
    source = STUDY/'validation_noise'
    if ARCHIVE.exists() or ARCHIVE.is_symlink():
        raise RuntimeError('Archive already exists; refusing replay')
    if digest(source/'run_summary.json') != PARTIAL_SHA:
        raise RuntimeError('Partial noise summary identity changed; inspect before retry')
    old = json.loads((source/'run_summary.json').read_text())
    if old.get('status') == 'validation_complete':
        raise RuntimeError('Noise already completed; no retry permitted')
    check_generated(old)
    before = manifest(source)
    verify_failed_manifest(before)
    failure = json.loads((source/'run_status.json').read_text())
    if old.get('status') != 'simulation_failed' or failure.get('exit_code') != -6 or 'SPECTRE-18' not in failure.get('issue_codes', []):
        raise RuntimeError('Expected read-in failure evidence differs')
    prior_state = P/'runs/project6_noise_retry_20261020/status.json'
    if digest(prior_state) != PRIOR_STATE_SHA:
        raise RuntimeError('Prior retry terminal state changed')
    snapshot = dict(source=str(source), archive=str(ARCHIVE), manifest=before,
                    partial_summary_sha256=PARTIAL_SHA, observed_boot_id=BOOT,
                    prior_runner_status=json.loads(prior_state.read_text()),
                    prior_runner_status_sha256=digest(prior_state),
                    reason='User explicitly requested one immediate unchanged retry on 2026-10-20 with immediate crash notification; prior failure preserved, root cause unknown, no automatic replay')
    write_new(R/'archive_receipt_before.json', snapshot)
    check_environment(helper)
    require_startup_memory()
    ready, count = capacity(helper)
    if not ready:
        raise RuntimeError('Capacity changed before archive; no mutation to partial directory')
    source.rename(ARCHIVE)
    if manifest(ARCHIVE) != before:
        raise RuntimeError('Archive manifest differs; no simulation dispatched')
    save(state, 'partial_archived', archive_manifest_sha256=digest(R/'archive_receipt_before.json'),
         archive=str(ARCHIVE), archived_file_count=len(before['files']))


def run():
    import fcntl
    helper = load_helper()
    if not (P/'.codex_project6_owned').exists():
        raise RuntimeError('Project ownership marker absent')
    R.mkdir(exist_ok=True)
    lock = (R/'runner.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (R/'status.json').exists() or (R/'events.jsonl').exists():
        raise RuntimeError('Existing one-shot state; refusing replay')
    queue_lock = (STUDY/'queue.lock').open('a')
    fcntl.flock(queue_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    own = next(r for r in process_rows() if r['pid'] == os.getpid())
    state = dict(status='running', pid=own['pid'], start=own['start'], boot_id=helper.boot_id(),
                 wrapper_sha256=digest(__file__), helper_sha256=HELPER_SHA, child=None,
                 scope='One unchanged noise retry after bounded read-in diagnostic; original environment, root cause unknown; completed noiseless reused, not an independent holdout',
                 complete_ADC_verified=False, automatic_retries=0)
    identity, child = None, None
    save(state, 'preflight')
    try:
        state['source_sha256'] = verify_sources(helper)
        state['guest_free_bytes'] = check_environment(helper)
        state['startup_MemAvailable_bytes'] = require_startup_memory()
        env = original_environment()
        state['diagnostic_gate'] = verify_diagnostic(env)
        verify_noiseless(helper)
        ledger = json.loads((P/'results/adc_backend_pam4_r5_holdout_usage.json').read_text())
        if not ledger or any(e.get('validation_data_seed') == 2026101302 and
                             e.get('choice_identity') != CHOICE_SHA for e in ledger):
            raise RuntimeError('Holdout ledger is absent or has incompatible reservation')
        if not any(e.get('validation_data_seed') == 2026101302 and e.get('choice_identity') == CHOICE_SHA for e in ledger):
            raise RuntimeError('Expected identical holdout reservation is missing')
        ready, count = capacity(helper)
        if not ready:
            raise RuntimeError('Global Spectre capacity unavailable; no dispatch')
        archive_partial(helper, state)
        verify_sources(helper)
        verify_noiseless(helper)
        check_environment(helper)
        ready, count = capacity(helper)
        if not ready or (STUDY/'validation_noise').exists():
            raise RuntimeError('Final dispatch capacity or destination changed')
        require_startup_memory()
        verify_diagnostic(env)
        command = ['python3', str(helper.VALIDATOR), 'validate', '--study', 'r5_late1',
                   '--variant', 'cml2_late1', '--validation-kind', 'noise', '--timeout', '7200', '--run']
        save(state, 'dispatching_noise', command=command, admitted_actual_spectres=count)
        with (R/'noise.log').open('xb') as log:
            child = subprocess.Popen(command, cwd=str(P/'scripts'), env=env, stdout=log,
                                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
            observed = next((r for r in process_rows() if r['pid'] == child.pid), None)
            if observed is None or observed['sid'] != child.pid or observed['pgid'] != child.pid:
                raise RuntimeError('Could not verify newly created child session; inspect before signaling')
            identity = dict(pid=child.pid, start=observed['start'], pgid=observed['pgid'],
                            sid=observed['sid'], boot_id=BOOT)
            save(state, 'running_noise', child=identity)
            started, last_save = time.monotonic(), 0
            summary = STUDY/'validation_noise/run_summary.json'
            checked = False
            while True:
                # p6_bench rewrites bench.scs after generated_only is saved. Its
                # console.log is opened only after that rewrite has completed.
                if not checked and summary.exists() and (STUDY/'validation_noise/console.log').exists():
                    check_generated(json.loads(summary.read_text()))
                    if digest(STUDY/'validation_noise/bench.scs') != DECK_SHA:
                        raise RuntimeError('Generated deck bytes differ from interrupted original')
                    checked = True
                if child.poll() is not None:
                    break
                elapsed = time.monotonic()-started
                if elapsed >= 7800:
                    raise RuntimeError('7800-second outer bound expired; no automatic retry')
                if elapsed-last_save >= 30:
                    free = check_environment(helper)
                    members = session_members(process_rows(), identity, helper.boot_id())
                    save(state, 'running_noise', elapsed_s=round(elapsed, 1), guest_free_bytes=free,
                         generated_identity_checked=checked, session_members=members)
                    last_save = elapsed
                time.sleep(1)
        rc = child.wait()
        survivors = session_members(process_rows(), identity, helper.boot_id())
        if survivors:
            state['survivors_after_child_exit'] = survivors
            raise RuntimeError('Validator exited with session survivors; cleanup required')
        verify_sources(helper)
        verify_noiseless(helper)
        check_environment(helper)
        record = json.loads(summary.read_text()) if summary.exists() else {}
        check_generated(record)
        if digest(STUDY/'validation_noise/bench.scs') != DECK_SHA:
            raise RuntimeError('Final deck bytes differ from interrupted original')
        if not checked or not helper.complete(record, 'noise', rc):
            raise RuntimeError('Noise validation failed or is incomplete; evidence preserved')
        save(state, 'noise_validation_complete', status='complete', child=None,
             exit_code=rc, noise_summary_sha256=digest(summary), noiseless_summary_sha256=NOISELESS_SHA,
             generated_identity_checked=True, remaining_session_members=[])
    except Exception as error:
        try:
            state['cleanup'] = cleanup_session(helper, identity)
            if child is not None and child.poll() is not None:
                state['child_exit_code'] = child.wait()
        except Exception as cleanup_error:
            state['cleanup_error'] = repr(cleanup_error)
        save(state, 'needs_attention', status='needs_attention', error=repr(error),
             automatic_retry_permitted=False)
        raise


def self_test():
    helper = load_helper()
    helper.self_test()
    identity = dict(pid=10, start='123', pgid=10, sid=10, boot_id=BOOT)
    good = dict(pid=11, start='124', pgid=10, sid=10, cwd=str(P/'runs'))
    assert session_members([good], identity, BOOT) == [good]
    assert session_members([], identity, BOOT) == []
    for row, boot in ((dict(good, cwd='/other'), BOOT), (dict(good, cwd=None), BOOT),
                      (dict(good, pgid=20), BOOT), (dict(good, sid=20), BOOT),
                      (dict(good, pid=10, start='999'), BOOT),
                      (dict(good, start='122'), BOOT), (good, 'different-boot')):
        try:
            session_members([row], identity, boot)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Unsafe session accepted')
    record = dict(deck_sha256=DECK_SHA, symbol_sequence_sha256=SYMBOL_SHA, symbol_count=3264, noise_seed=173)
    check_generated(record)
    for key in record:
        try:
            check_generated(dict(record, **{key: None}))
        except RuntimeError:
            pass
        else:
            raise AssertionError('Changed generated identity accepted')
    assert not owned_cwd(str(P)+'_other')
    assert not owned_cwd(None)
    def proc(pid, exe='/opt/spectre', args=None, cwd='/other'):
        return dict(pid=pid, exe=exe, args=[exe] if args is None else args, cwd=cwd)
    assert capacity_rows(helper, [], 1) == (True, 0)
    assert capacity_rows(helper, [proc(2, exe='/bin/ksh', args=['ksh', '/opt/spectre'])], 1) == (True, 0)
    assert capacity_rows(helper, [proc(2, args=['renamed_argv'])], 1) == (True, 1)
    assert capacity_rows(helper, [proc(2), proc(3)], 1) == (False, 2)
    for blocked in (proc(2, cwd=str(STUDY)), proc(2, exe=None, args=['/opt/spectre']),
                    proc(2, exe='/usr/bin/python3', args=['python3', str(P/'scripts/diagnose_readin_20261020.py')])):
        try:
            capacity_rows(helper, [blocked], 1)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Unsafe capacity accepted')
    env = {k: 'synthetic' for k in ENV_KEYS}
    case = dict(name='A_original', deck_sha256=DECK_SHA, removed_environment_keys=[],
                cleanup={'remaining': []}, cutoff_reached=True, exit_code=3, readin_progressed=True,
                phases=dict(spectre18=False, edb_visiting=True, circuit_inventory=True,
                            transient_started=True, error_codes=['SFE-1131']), env_allowlist=env)
    diag = dict(status='complete', stage='diagnostics_complete', boot_id=BOOT,
                wrapper_sha256=DIAG_SCRIPT_SHA, cases=[case])
    assert acceptable_diagnostic(diag, env)
    for altered in (dict(diag, status='running'), dict(diag, cases=[]),
                    dict(diag, boot_id='other'), dict(diag, cases=[dict(case, exit_code=-6)]),
                    dict(diag, cases=[dict(case, cleanup={'remaining': [123]})]),
                    dict(diag, cases=[dict(case, phases=dict(case['phases'], spectre18=True))])):
        assert not acceptable_diagnostic(altered, env)
    assert not acceptable_diagnostic(diag, dict(env, LD_LIBRARY_PATH='changed'))
    proof = dict(files=[dict(path=name, sha256=sha) for name, sha in FAILED_FILES.items()], directories=[])
    verify_failed_manifest(proof)
    for bad in (dict(proof, files=proof['files'][:-1]),
                dict(proof, files=proof['files']+[dict(path='extra', sha256='x')]),
                dict(proof, files=[dict(path=x['path'], sha256='wrong') for x in proof['files']])):
        try:
            verify_failed_manifest(bad)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Changed failure evidence accepted')
    print('PASS: immutable helper, actual-exe capacity, diagnostic/environment gate, exact five-file archive, session isolation, PID reuse, boot and generated identity; no signals or VM operations.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--run', action='store_true')
    modes.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    self_test() if args.self_test else run()
