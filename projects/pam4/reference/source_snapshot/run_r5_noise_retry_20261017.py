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
R = P/'runs/project6_noise_retry_20261017'
STUDY = P/'runs/adc_backend_pam4_r5_20261013/r5_late1'
BOOT = '3490e49c-4bfb-400c-a537-9a5d936e2e6d'
HELPER_SHA = '0c02120d0a049f22b52f5fa08392cb1498f13718c6a6a410f35c263416b25b16'
NOISELESS_SHA = 'ff8a466c80549cc476e8c768e56aea64cdab4ed4abb8a6b5d2709769519f716f'
PARTIAL_SHA = 'ba3c4625a91c9483c1053d6877895f1cd2ed48920b4970fd51e29eaee8b4bbfa'
DECK_SHA = '3109f222211963fe5fcadbbb96b6605f8c4c7a8d32aa35bae178678f1d927fa2'
SYMBOL_SHA = '67fa287fe82d08414b207177bf915c50e4b61692cc1fde0d4b9dbf4774f54633'
CHOICE_SHA = '7fb7dbcbe76fa94857d80fea75b9b47db81761b69ac2a4efd5698332a1daff4e'
ARCHIVE = STUDY/'validation_noise_interrupted_powercycle_20261013_archived_20261017'
MIN_FREE = 8*1024**3


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
            rows.append(dict(pid=int(path.name), ppid=int(fields[1]), pgid=int(fields[2]),
                             sid=int(fields[3]), start=fields[19], cwd=cwd))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return rows


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
    for signum, grace in ((signal.SIGTERM, 8), (signal.SIGKILL, 3)):
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
    if len(before['files']) != 8:
        raise RuntimeError('Interrupted directory no longer has the eight preflight files')
    prior_state = P/'runs/project6_reboot_resume_20261013/status.json'
    snapshot = dict(source=str(source), archive=str(ARCHIVE), manifest=before,
                    partial_summary_sha256=PARTIAL_SHA, observed_boot_id=BOOT,
                    prior_runner_status=json.loads(prior_state.read_text()),
                    prior_runner_status_sha256=digest(prior_state),
                    reason='User continue on 2026-10-17 authorizes one unchanged noise-only retry after power-cycle interruption')
    write_new(R/'archive_receipt_before.json', snapshot)
    check_environment(helper)
    ready, count = helper.capacity(helper.snapshot(), os.getpid())
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
                 scope='One unchanged noise retry; completed noiseless reused; not independent holdout',
                 complete_ADC_verified=False, automatic_retries=0)
    identity, child = None, None
    save(state, 'preflight')
    try:
        state['source_sha256'] = helper.verify_sources()
        state['guest_free_bytes'] = check_environment(helper)
        verify_noiseless(helper)
        ledger = json.loads((P/'results/adc_backend_pam4_r5_holdout_usage.json').read_text())
        if not ledger or any(e.get('validation_data_seed') == 2026101302 and
                             e.get('choice_identity') != CHOICE_SHA for e in ledger):
            raise RuntimeError('Holdout ledger is absent or has incompatible reservation')
        if not any(e.get('validation_data_seed') == 2026101302 and e.get('choice_identity') == CHOICE_SHA for e in ledger):
            raise RuntimeError('Expected identical holdout reservation is missing')
        ready, count = helper.capacity(helper.snapshot(), os.getpid())
        if not ready:
            raise RuntimeError('Global Spectre capacity unavailable; no dispatch')
        archive_partial(helper, state)
        helper.verify_sources()
        verify_noiseless(helper)
        check_environment(helper)
        ready, count = helper.capacity(helper.snapshot(), os.getpid())
        if not ready or (STUDY/'validation_noise').exists():
            raise RuntimeError('Final dispatch capacity or destination changed')
        env = os.environ.copy()
        env['CDS_LIC_FILE'] = '<LICENSE_FILE>'
        env['LM_LICENSE_FILE'] = env['CDS_LIC_FILE']
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
        helper.verify_sources()
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
    print('PASS: immutable helper, capacity/completion, session isolation, PID reuse, boot, and generated identity; no signals or VM operations.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--run', action='store_true')
    modes.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    self_test() if args.self_test else run()
