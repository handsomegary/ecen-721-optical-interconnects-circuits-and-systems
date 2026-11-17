#!/usr/bin/env python3
"""One-shot admission at the frozen r5 noiseless -> noise queue boundary.

Stops only the exact queue Python, never its validation worker or simulator.
The queue uses subprocess.call without a timeout. The first validation keeps
running while its parent is stopped. Admission cannot reserve capacity against
unrelated launchers. No frozen simulation or queue source is edited.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import time

P = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R = P/'runs/project6_admission_watch_20261013'
PIPELINE = P/'scripts/run_project6_resume_pipeline.py'
QUEUE = P/'scripts/run_r5_validation_queue.py'
VALIDATOR = P/'scripts/adc_backend_pam4_r5.py'
PIPELINE_PID, PIPELINE_START = 11646, '67680'
SOURCE_HASHES = {
    str(PIPELINE): '2fe6681d0fa104433758776f061a6a478489391cd965458a8daa92871c4e7468',
    str(QUEUE): 'af1f05981690fb565f11f0311527f95bea45b92a8fa1b68b62b6a267e6c0005a',
    str(VALIDATOR): '25f7168a47ea1a9b62b4548675534ac9c85c04d55d0a24414a9279f5c86e34f4',
}
QUEUE_STATE = P/'runs/adc_backend_pam4_r5_20261013/r5_late1/queue_status.json'
PIPELINE_STATE = P/'runs/project6_resume_pipeline_20261013/pipeline_status.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot():
    rows = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path/'stat').read_text()
            fields = raw[raw.rfind(')')+2:].split()
            args = [v.decode('utf8', 'replace') for v in (path/'cmdline').read_bytes().split(b'\0') if v]
            try:
                cwd = os.readlink(str(path/'cwd'))
            except PermissionError:
                cwd = None
            except FileNotFoundError:
                cwd = None
            rows[int(path.name)] = dict(pid=int(path.name), start=fields[19],
                                       state=fields[0], ppid=int(fields[1]), args=args, cwd=cwd)
        except (FileNotFoundError, ProcessLookupError):
            continue
        # Other read errors fail closed rather than undercounting simulators.
    return rows


def is_script(row, script):
    args = row.get('args', []) if row else []
    return (len(args) >= 2 and Path(args[0]).name.startswith('python') and
            args[1] == str(script) and row['state'] != 'Z')


def same(row, bound):
    return bool(row and row['pid'] == bound['pid'] and row['start'] == bound['start'] and
                row['ppid'] == bound['ppid'] and row['args'] == bound['args'])


def pipeline_live(rows):
    row = rows.get(PIPELINE_PID)
    return bool(is_script(row, PIPELINE) and row['start'] == PIPELINE_START)


def pipeline_active(rows):
    if not pipeline_live(rows):
        return False
    state = json.loads(PIPELINE_STATE.read_text())
    return (state.get('pid') == PIPELINE_PID and
            state.get('status') not in ('complete', 'complete_with_failures', 'stopped_with_error'))


def validation_kind(row):
    if not is_script(row, VALIDATOR):
        return None
    # Match this queue's complete invocation, not a substring or arbitrary arg.
    expected = ['validate', '--study', 'r5_late1', '--variant', 'cml2_late1',
                '--validation-kind', None, '--timeout', '7200', '--run']
    tail = row['args'][2:]
    if len(tail) != len(expected):
        return None
    if any(want is not None and got != want for got, want in zip(tail, expected)):
        return None
    return tail[6] if tail[6] in ('noiseless', 'noise') else None


def queue_and_first(rows):
    queues = [r for r in rows.values() if r['ppid'] == PIPELINE_PID and is_script(r, QUEUE)]
    if len(queues) > 1:
        raise RuntimeError('Multiple exact queue children; refusing to signal')
    if not queues:
        return None, None, False
    queue = queues[0]
    children = [r for r in rows.values() if r['ppid'] == queue['pid'] and r['state'] != 'Z']
    if any(validation_kind(r) == 'noise' for r in children):
        return queue, None, True
    first = [r for r in children if validation_kind(r) == 'noiseless']
    if len(first) > 1:
        raise RuntimeError('Multiple noiseless validation children; refusing to signal')
    return queue, first[0] if first else None, False


def spectres(rows):
    return [r for r in rows.values() if r['state'] != 'Z' and r['args'] and
            Path(r['args'][0]).name == 'spectre']


def child_finished(rows, child):
    row = rows.get(child['pid'])
    return row is None or row['start'] != child['start'] or row['state'] == 'Z'


def may_resume(rows, queue, child):
    jobs = spectres(rows)
    owned = [r for r in jobs if r.get('cwd') == str(P) or
             (r.get('cwd') or '').startswith(str(P)+'/')]
    return (same(rows.get(queue['pid']), queue) and rows[queue['pid']]['state'] in ('T', 't') and
            child_finished(rows, child) and len(jobs) < 2 and not owned)


def save(state, event, **details):
    state.update(updated_UTC=datetime.datetime.utcnow().isoformat()+'Z', event=event, **details)
    encoded = json.dumps(state, sort_keys=True, indent=2)+'\n'
    temporary = R/'status.tmp'
    with temporary.open('w') as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(R/'status.json')
    with (R/'events.jsonl').open('a') as handle:
        handle.write(json.dumps(state, sort_keys=True)+'\n')
        handle.flush()
        os.fsync(handle.fileno())
    descriptor = os.open(str(R), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def run():
    import fcntl
    if not (P/'.codex_project6_owned').exists():
        raise RuntimeError('Project ownership marker absent')
    R.mkdir(exist_ok=True)
    lock = (R/'watcher.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (R/'status.json').exists():
        raise RuntimeError('Prior watcher receipt exists; inspect it before any restart')
    for path, expected in SOURCE_HASHES.items():
        if sha(path) != expected:
            raise RuntimeError('Reviewed source changed: '+path)
    state = dict(status='running', watcher_pid=os.getpid(), watcher_sha256=sha(__file__),
                 source_sha256=SOURCE_HASHES, pipeline_pid=PIPELINE_PID,
                 pipeline_start=PIPELINE_START, paused_by_watcher=False,
                 limitation='Admission is checked before CONT; unrelated launchers do not share a reservation.')
    save(state, 'waiting_for_first_validation')
    deadline = time.monotonic()+21600
    queue = child = None
    try:
        while time.monotonic() < deadline:
            rows = snapshot()
            if not pipeline_active(rows):
                save(state, 'pipeline_ended', status='needs_attention' if state['paused_by_watcher'] else 'pipeline_ended',
                     note='No automatic CONT after the exact pipeline ends; preserve any pause receipt.')
                return
            if not state['paused_by_watcher']:
                queue, child, late = queue_and_first(rows)
                if queue and QUEUE_STATE.exists():
                    status = json.loads(QUEUE_STATE.read_text())
                    late = late or (status.get('pid') == queue['pid'] and
                                    status.get('stage') in ('validation_noise_running', 'paired_validation_complete'))
                if late:
                    save(state, 'noise_already_dispatched', status='too_late', queue=queue)
                    return
                if not child:
                    time.sleep(2)
                    continue
                if queue['state'] in ('T', 't'):
                    raise RuntimeError('Queue was already stopped by another actor; no ownership of pause')
                save(state, 'before_STOP', queue=queue, first_validation=child, intended_signal='SIGSTOP')
                latest = snapshot()
                if not pipeline_active(latest) or not same(latest.get(queue['pid']), queue):
                    raise RuntimeError('Pipeline or queue identity changed before STOP')
                if not same(latest.get(child['pid']), child) or latest[child['pid']]['state'] == 'Z':
                    save(state, 'first_child_ended_before_STOP', status='too_late', intended_signal=None)
                    return
                if latest[queue['pid']]['state'] in ('T', 't'):
                    raise RuntimeError('Queue became stopped before our signal; refusing to adopt pause')
                # Signal only this exact queue PID; never a process group or child.
                os.kill(queue['pid'], signal.SIGSTOP)
                state['paused_by_watcher'] = True
                save(state, 'after_STOP_sent', intended_signal=None)
                for unused in range(40):
                    latest = snapshot()
                    current = latest.get(queue['pid'])
                    if not same(current, queue):
                        raise RuntimeError('Queue identity changed after STOP')
                    if current['state'] in ('T', 't'):
                        break
                    time.sleep(.05)
                else:
                    raise RuntimeError('Queue did not enter stopped state')
                other_children = [r for r in latest.values() if r['ppid'] == queue['pid'] and
                                  r['state'] != 'Z' and not same(r, child)]
                if other_children:
                    raise RuntimeError('Child changed during STOP race; preserve stopped queue for inspection')
                save(state, 'queue_stopped_first_validation_continues', observed_queue_state=current['state'])
                continue
            current = rows.get(queue['pid'])
            if not same(current, queue):
                raise RuntimeError('Paused queue identity disappeared or changed; no CONT')
            if current['state'] not in ('T', 't'):
                raise RuntimeError('Another actor resumed the queue; watcher will not send more signals')
            if may_resume(rows, queue, child):
                save(state, 'before_CONT', intended_signal='SIGCONT', observed_actual_spectres=len(spectres(rows)))
                latest = snapshot()
                if not pipeline_active(latest):
                    raise RuntimeError('Exact pipeline ended before CONT; retain pause')
                if not may_resume(latest, queue, child):
                    save(state, 'CONT_deferred_after_recheck', intended_signal=None)
                    continue
                os.kill(queue['pid'], signal.SIGCONT)
                state['paused_by_watcher'] = False
                save(state, 'after_CONT_sent', intended_signal=None, status='admission_released',
                     observed_actual_spectres=len(spectres(latest)),
                     note='One-shot inter-pair gate released; this does not mark any simulation complete.')
                return
            time.sleep(2)
        save(state, 'six_hour_limit', status='needs_attention', note='Bound reached; no automatic CONT or new simulation.')
    except Exception as error:
        save(state, 'watcher_error', status='needs_attention', error=repr(error),
             note='No cleanup signal is sent; preserve receipt and any stopped queue for inspection.')
        raise


def self_test():
    # Pure synthetic snapshots only: no /proc reads, file writes, or signals.
    def row(pid, ppid, start, script, extra=None, state='S', cwd=None):
        return dict(pid=pid, ppid=ppid, start=start, state=state,
                    args=['python3', str(script)]+(extra or []), cwd=cwd)
    parent = row(PIPELINE_PID, 1, PIPELINE_START, PIPELINE)
    queue = row(44, PIPELINE_PID, '100', QUEUE)
    args = ['validate', '--study', 'r5_late1', '--variant', 'cml2_late1',
            '--validation-kind', 'noiseless', '--timeout', '7200', '--run']
    child = row(45, 44, '101', VALIDATOR, args)
    rows = {r['pid']: r for r in (parent, queue, child)}
    assert pipeline_live(rows)
    assert queue_and_first(rows) == (queue, child, False)
    wrong = dict(child, args=['python3', '/other/adc_backend_pam4_r5.py']+args)
    assert validation_kind(wrong) is None
    assert not pipeline_live({PIPELINE_PID: dict(parent, start='reused')})
    assert queue_and_first({44: dict(queue, ppid=999), 45: child}) == (None, None, False)
    noisy = dict(child, args=list(child['args']))
    noisy['args'][8] = 'noise'
    assert queue_and_first({44: queue, 45: noisy}) == (queue, None, True)
    stopped = dict(queue, state='T')
    assert not may_resume({44: stopped, 45: child}, queue, child)
    ended = {44: stopped, 45: dict(child, state='Z')}
    assert may_resume(ended, queue, child)
    spec = dict(pid=60, ppid=1, start='200', state='R', args=['/bin/spectre'], cwd='/other')
    wrapper = dict(spec, pid=70, args=['/bin/ksh', '/bin/spectre'])
    assert len(spectres({60: spec, 70: wrapper})) == 1
    assert may_resume({44: stopped, 60: spec}, queue, child)
    assert not may_resume({44: stopped, 60: spec, 61: dict(spec, pid=61)}, queue, child)
    assert not may_resume({44: stopped, 60: dict(spec, cwd=str(P)+'/runs/own')}, queue, child)
    assert not may_resume({44: dict(stopped, start='reused')}, queue, child)
    assert not may_resume({44: queue}, queue, child)
    print('PASS: synthetic identity, queue selection, late detection, child completion, and capacity checks; no signals sent.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--self-test', action='store_true')
    arguments = parser.parse_args()
    if arguments.self_test:
        self_test()
    else:
        run()
