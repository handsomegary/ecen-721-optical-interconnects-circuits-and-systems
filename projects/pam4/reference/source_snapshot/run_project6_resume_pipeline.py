#!/usr/bin/env python3
"""One owned simulation at a time: resumed r6, bounded r6b, frozen r5 validation."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

P = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R = P/'runs/project6_resume_pipeline_20261013'
R6 = P/'runs/adc_backend_r6_screen_20261013'
R6B = P/'runs/adc_backend_r6b_screen_20261013'
R5 = P/'runs/adc_backend_pam4_r5_20261013/r5_late1'
EXPECTED = {
    'adc_backend_screen_r6.py': 'f14fb804fafa9f6b4f59b793ba0ddb232ed3eeb25ed380bf922b064a13c74b2b',
    'adc_backend_screen_r6b.py': '9edd0dc301205d0626944f7d7723ed24787fdd3f520da2c4642d55279e948553',
    'adc_backend_pam4_r5.py': '25f7168a47ea1a9b62b4548675534ac9c85c04d55d0a24414a9279f5c86e34f4',
    'run_r5_validation_queue.py': 'af1f05981690fb565f11f0311527f95bea45b92a8fa1b68b62b6a267e6c0005a',
}
FROZEN_HASH = '4cda4c9ec967f2af4bf4f89eacdd1beae372668877c358cf6aa26092597482eb'
R6_RESUMED_PID, R6_RESUMED_START = 6039, '21352'
claimed = False
state = dict(status='running', stage='starting', pid=os.getpid(), results=[],
             complete_ADC_verified=False, holdout_used_for_redesign=False,
             own_simulations_at_once=1, user_resume_date='2026-10-13')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(stage, **values):
    state.update(stage=stage, updated_UTC=datetime.datetime.utcnow().isoformat()+'Z', **values)
    tmp=R/'pipeline_status.tmp'
    tmp.write_text(json.dumps(state, indent=2)+'\n')
    tmp.replace(R/'pipeline_status.json')
    print(json.dumps(dict(stage=stage, status=state['status'], child_pid=state.get('child_pid'))), flush=True)


def processes():
    rows=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw=(path/'stat').read_text()
            fields=raw[raw.rfind(')')+2:].split()
            if fields[0]=='Z':
                continue
            args=(path/'cmdline').read_bytes().split(b'\0')
            args=[v.decode('utf8', 'replace') for v in args if v]
            rows.append(dict(pid=int(path.name), start=fields[19], args=args, cwd=str((path/'cwd').resolve())))
        except (OSError, ValueError):
            continue
    return rows


def owned_workers(rows):
    names=('adc_backend_screen_r6.py', 'adc_backend_screen_r6b.py',
           'adc_backend_pam4_r5.py', 'run_r5_validation_queue.py')
    expected={str(P/'scripts'/name) for name in names}
    result=[]
    for row in rows:
        args=row['args']
        if len(args)<2 or not Path(args[0]).name.startswith('python') or args[1].startswith('-'):
            continue
        script=Path(args[1])
        if not script.is_absolute():
            script=Path(row['cwd'])/script
        if str(script.resolve()) in expected:
            result.append(row)
    return result


def verify_sources():
    for name, expected in EXPECTED.items():
        if digest(P/'scripts'/name)!=expected:
            raise RuntimeError('Reviewed script identity changed: '+name)
    if digest(R5/'frozen.json')!=FROZEN_HASH:
        raise RuntimeError('r5 frozen design changed')


def wait_r6():
    save('waiting_for_resumed_r6')
    deadline=time.time()+21600
    while time.time()<deadline:
        d=json.loads((R6/'summary.json').read_text())
        rows=processes()
        same_pid=[x for x in rows if x['pid']==R6_RESUMED_PID]
        if same_pid and same_pid[0]['start']!=R6_RESUMED_START:
            raise RuntimeError('Predecessor PID has been reused; inspect before continuing')
        alive=[x for x in owned_workers(rows) if Path(x['args'][1]).name=='adc_backend_screen_r6.py']
        if any(x['pid']!=R6_RESUMED_PID or x['start']!=R6_RESUMED_START for x in alive):
            raise RuntimeError('Unexpected predecessor worker identity; no duplicate dispatched')
        if not alive:
            if d.get('stage')=='complete' and d.get('status') in ('complete', 'complete_with_failures') and not (R6/'runner.lock').exists():
                state['r6_completion_summary_sha256']=digest(R6/'summary.json')
                return True
            state['results'].append(dict(job='resumed_r6', status='predecessor_incomplete', observed_status=d.get('status')))
            return False
        time.sleep(30)
    raise RuntimeError('Resumed r6 exceeded six-hour wait; no duplicate launched')


def wait_capacity(job):
    save('waiting_for_capacity_'+job, child_pid=None)
    deadline=time.time()+21600
    while time.time()<deadline:
        rows=processes()
        if owned_workers(rows):
            raise RuntimeError('Another owned worker exists; refusing overlapping dispatch')
        # Count actual simulator executables, not the ksh wrapper with the same comm name.
        jobs=[x for x in rows if x['args'] and Path(x['args'][0]).name=='spectre']
        if any(x['cwd']==str(P) or x['cwd'].startswith(str(P)+'/') for x in jobs):
            raise RuntimeError('Owned simulator remains after its worker ended; inspect preserved process before dispatch')
        if len(jobs)<2:
            return
        time.sleep(30)
    raise RuntimeError('Other simulations occupy both slots; no external process was changed')


def run(job, args, result_file, success):
    wait_capacity(job)
    verify_sources()
    env=os.environ.copy()
    env['CDS_LIC_FILE']='<LICENSE_FILE>'
    env['LM_LICENSE_FILE']=env['CDS_LIC_FILE']
    with (R/(job+'.log')).open('xb') as log:
        child=subprocess.Popen(args, cwd=str(P/'scripts'), env=env,
                               stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        save('running_'+job, child_pid=child.pid)
        rc=child.wait()
    result=json.loads(result_file.read_text()) if result_file.exists() else {}
    passed=rc==0 and success(result)
    state['results'].append(dict(job=job, exit_code=rc, completed=passed,
                                 summary_sha256=digest(result_file) if result_file.exists() else None))
    save('finished_'+job, child_pid=None)
    return passed


def main():
    global claimed
    assert (P/'.codex_project6_owned').exists()
    R.mkdir(exist_ok=True)
    lock=(R/'pipeline.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (R/'pipeline_status.json').exists():
        raise RuntimeError('Existing pipeline state must be inspected; refusing duplicate replay')
    claimed = True
    verify_sources()
    if wait_r6():
        run('r6b', ['python3', str(P/'scripts/adc_backend_screen_r6b.py'),
                    '--run', '--noise-check', '--timeout', '7200'], R6B/'summary.json',
            lambda d: d.get('stage')=='complete' and d.get('status') in ('complete', 'complete_with_failures'))
    else:
        save('r6b_skipped_due_to_incomplete_baseline')
    if digest(R5/'frozen.json')!=FROZEN_HASH:
        raise RuntimeError('Frozen design changed before validation dispatch')
    run('r5_paired_validation', ['python3', str(P/'scripts/run_r5_validation_queue.py')],
        R5/'queue_status.json', lambda d: d.get('stage')=='paired_validation_complete')
    failed=any(not row.get('completed', False) for row in state['results'])
    save('complete', status='complete_with_failures' if failed else 'complete', child_pid=None)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        if claimed:
            save('error', status='stopped_with_error', error=str(error))
        raise
