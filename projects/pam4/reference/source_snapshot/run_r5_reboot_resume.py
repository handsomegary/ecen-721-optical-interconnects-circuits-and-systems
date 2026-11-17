#!/usr/bin/env python3
"""Resume only the immutable r5 validation pair after the recorded VM reboot.

No archive, deletion, process signal, retraining, or new candidate is performed.
Each validation gets a separate admission check; unrelated launchers cannot be
reserved against. Existing run directories and wrapper receipts are refused.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

P = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R = P/'runs/project6_reboot_resume_20261013'
STUDY = P/'runs/adc_backend_pam4_r5_20261013/r5_late1'
FROZEN_SHA = '4cda4c9ec967f2af4bf4f89eacdd1beae372668877c358cf6aa26092597482eb'
VALIDATOR = P/'scripts/adc_backend_pam4_r5.py'
EXPECTED = {
    VALIDATOR: '25f7168a47ea1a9b62b4548675534ac9c85c04d55d0a24414a9279f5c86e34f4',
    P/'scripts/p6_bench.py': 'bd0ddf7376b8c3273a0f51a9c60fdcc3dbc207e0f5e3849f0599fd83ac7b43b7',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def uptime():
    return float(Path('/proc/uptime').read_text().split()[0])


def require_stable_boot(expected):
    if boot_id() != expected or uptime() < 600:
        raise RuntimeError('Boot changed or has not reached ten minutes; no dispatch')


def snapshot():
    rows = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            stat = (path/'stat').read_text()
            fields = stat[stat.rfind(')')+2:].split()
            if fields[0] == 'Z':
                continue
            args = [s.decode('utf8', 'replace') for s in (path/'cmdline').read_bytes().split(b'\0') if s]
            try:
                cwd = os.readlink(str(path/'cwd'))
            except (PermissionError, FileNotFoundError):
                cwd = None
            rows.append(dict(pid=int(path.name), start=fields[19], ppid=int(fields[1]), args=args, cwd=cwd))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return rows


def script_path(row):
    args = row['args']
    if not args or not Path(args[0]).name.startswith('python'):
        return None
    index = 1
    while index < len(args) and args[index].startswith('-'):
        option = args[index]
        if option in ('-', '-c', '-m') or option.startswith(('-c', '-m')):
            return None
        index += 2 if option in ('-W', '-X') else 1
    if index >= len(args):
        return None
    path = Path(args[index])
    if not path.is_absolute():
        if row.get('cwd') is None:
            raise RuntimeError('Cannot classify a relative Python script without its cwd')
        path = Path(row['cwd'])/path
    return str(path.resolve())


def capacity(rows, self_pid):
    scripts = (P/'scripts').resolve()
    own_workers = [r for r in rows if r['pid'] != self_pid and script_path(r) is not None
                   and scripts in Path(script_path(r)).parents]
    jobs = [r for r in rows if r['args'] and Path(r['args'][0]).name == 'spectre']
    project = P.resolve()
    own_jobs = [r for r in jobs if r.get('cwd') and
                (Path(r['cwd']).resolve() == project or project in Path(r['cwd']).resolve().parents)]
    if own_workers or own_jobs:
        raise RuntimeError('Owned worker or simulator already exists; refusing overlapping dispatch')
    return len(jobs) < 2, len(jobs)


def verify_sources():
    if digest(STUDY/'frozen.json') != FROZEN_SHA:
        raise RuntimeError('Frozen r5 bytes changed')
    frozen = json.loads((STUDY/'frozen.json').read_text())
    expected = dict(EXPECTED)
    for name, sha in frozen['identity']['scripts'].items():
        if Path(name).name != name:
            raise RuntimeError('Unexpected frozen script path')
        path = P/'scripts'/name
        if path in expected and expected[path] != sha:
            raise RuntimeError('Frozen script identity conflicts with reviewed source')
        expected[path] = sha
    for path, sha in expected.items():
        if digest(path) != sha:
            raise RuntimeError('Reviewed source changed: '+str(path))
    if digest(P/'configs/native_geometry_cards_r5.json') != frozen['identity']['native_geometry_metadata']['native_cards_sha256']:
        raise RuntimeError('Native geometry identity changed')
    if json.loads((P/'configs/ctle_selected_r3.json').read_text()) != frozen['identity']['frontend']:
        raise RuntimeError('Frozen frontend configuration changed')
    return {str(path.relative_to(P)): sha for path, sha in expected.items()}


def complete(record, kind, rc):
    return (rc == 0 and record.get('status') == 'validation_complete' and
            record.get('run_status', {}).get('exit_code') == 0 and
            record.get('frozen_file_sha256_before_run') == FROZEN_SHA and
            record.get('frozen_file_unchanged') is True and
            record.get('validation_fitting_performed') is False and
            record.get('fresh_holdout_seed') == 2026101302 and
            record.get('validation_input_symbols') == 2048 and
            record.get('FFE_complete_windows') == 2032 and
            record.get('noise_seed') == (None if kind == 'noiseless' else 173) and
            record.get('complete_ADC_verified') is False)


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


def run():
    import fcntl
    if not (P/'.codex_project6_owned').exists():
        raise RuntimeError('Project ownership marker absent')
    R.mkdir(exist_ok=True)
    lock = (R/'runner.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (R/'status.json').exists():
        raise RuntimeError('Existing recovery receipt; refusing replay')
    queue_lock = (STUDY/'queue.lock').open('a')
    fcntl.flock(queue_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    myself = next(r for r in snapshot() if r['pid'] == os.getpid())
    state = dict(status='running', pid=os.getpid(), start=myself['start'], boot_id=boot_id(),
                 wrapper_sha256=digest(__file__), frozen_sha256=FROZEN_SHA,
                 results=[], child=None, complete_ADC_verified=False,
                 scope='Retry the same frozen holdout protocol after interruption; no new data or fitting.',
                 admission_limit='One owned simulation; check total actual Spectre count <2 before every dispatch. No reservation against unrelated launchers.')
    save(state, 'starting')
    try:
        state['source_sha256'] = verify_sources()
        save(state, 'waiting_for_stable_boot')
        while uptime() < 600:
            if boot_id() != state['boot_id']:
                raise RuntimeError('Boot identity changed during initial stability wait')
            time.sleep(min(30, max(.1, 600-uptime())))
        require_stable_boot(state['boot_id'])
        for kind in ('noiseless', 'noise'):
            directory = STUDY/('validation_'+kind)
            if directory.exists():
                raise RuntimeError('Existing validation directory must be inspected and preserved before recovery: '+kind)
            save(state, 'waiting_for_capacity_'+kind)
            deadline = time.monotonic()+21600
            while True:
                ready, count = capacity(snapshot(), os.getpid())
                if ready:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Six-hour admission wait expired; no simulation dispatched: '+kind)
                time.sleep(30)
            verify_sources()
            require_stable_boot(state['boot_id'])
            if directory.exists():
                raise RuntimeError('Boot identity or destination changed before dispatch')
            ready, count = capacity(snapshot(), os.getpid())
            if not ready:
                raise RuntimeError('Capacity changed at final dispatch check; no simulation dispatched')
            env = os.environ.copy()
            env['CDS_LIC_FILE'] = '<LICENSE_FILE>'
            env['LM_LICENSE_FILE'] = env['CDS_LIC_FILE']
            command = ['python3', str(VALIDATOR), 'validate', '--study', 'r5_late1',
                       '--variant', 'cml2_late1', '--validation-kind', kind, '--timeout', '7200', '--run']
            save(state, 'dispatching_'+kind, admitted_actual_spectres=count, command=command)
            with (R/(kind+'.log')).open('xb') as log:
                child = subprocess.Popen(command, cwd=str(P/'scripts'), env=env,
                                         stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
                observed = next((r for r in snapshot() if r['pid'] == child.pid), None)
                save(state, 'running_'+kind, child=dict(pid=child.pid,
                     start=observed['start'] if observed else None, boot_id=state['boot_id']))
                rc = child.wait()
            verify_sources()
            if boot_id() != state['boot_id']:
                raise RuntimeError('Boot identity changed during validation')
            path = directory/'run_summary.json'
            record = json.loads(path.read_text()) if path.exists() else {}
            passed = complete(record, kind, rc)
            state['results'].append(dict(kind=kind, exit_code=rc, completed=passed,
                                         summary_sha256=digest(path) if path.exists() else None))
            save(state, 'finished_'+kind, child=None)
            if not passed:
                raise RuntimeError('Validation failed or incomplete; preserved output requires inspection: '+kind)
        save(state, 'paired_validation_complete', status='complete', child=None)
    except Exception as error:
        save(state, 'needs_attention', status='needs_attention', error=repr(error))
        raise


def self_test():
    def row(pid, args, cwd=str(P/'scripts')):
        return dict(pid=pid, args=args, cwd=cwd)
    mine = row(1, ['python3', str(P/'scripts/run_r5_reboot_resume.py')])
    assert capacity([mine], 1) == (True, 0)
    external = row(2, ['/opt/spectre'], '/other')
    assert capacity([mine, external], 1) == (True, 1)
    assert capacity([external, dict(external, pid=3)], 1) == (False, 2)
    assert capacity([row(3, ['/bin/ksh', '/opt/spectre'], '/other')], 1) == (True, 0)
    assert script_path(row(2, ['python3', '-c', 'print(1)', str(VALIDATOR)])) is None
    assert script_path(row(2, ['python3', '-u', 'adc_backend_pam4_r5.py'])) == str(VALIDATOR.resolve())
    for blocked in (row(3, ['python3', 'run_r5_validation_queue.py']),
                    row(3, ['/opt/spectre'], str(STUDY)),
                    row(3, ['python3', str(P/'scripts/run_r5_reboot_resume.py')])):
        try:
            capacity([mine, blocked], 1)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Owned overlap was not refused')
    record = dict(status='validation_complete', run_status={'exit_code': 0},
                  frozen_file_sha256_before_run=FROZEN_SHA, frozen_file_unchanged=True,
                  validation_fitting_performed=False, fresh_holdout_seed=2026101302,
                  validation_input_symbols=2048, FFE_complete_windows=2032,
                  noise_seed=None, complete_ADC_verified=False)
    assert complete(record, 'noiseless', 0)
    assert not complete(record, 'noise', 0)
    assert not complete(record, 'noiseless', 1)
    assert not complete(dict(record, validation_fitting_performed=True), 'noiseless', 0)
    assert not complete(dict(record, validation_input_symbols=1024), 'noiseless', 0)
    assert not complete(dict(record, frozen_file_sha256_before_run='changed'), 'noiseless', 0)
    print('PASS: synthetic admission, script-path classification, overlap, and completion checks; no VM access or simulations.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    self_test() if args.self_test else run()
