#!/usr/bin/env python3
"""Resume the already authorized, predeclared r5 paired PAM4 validation."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time

P=Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R=P/'runs/adc_backend_pam4_r5_20261013/r5_late1'
STATE=R/'queue_status.json'

def status(stage,**kw):
    value=dict(stage=stage,pid=os.getpid(),updated_unix=time.time(),**kw)
    tmp=STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,indent=2)+'\n')
    tmp.replace(STATE)

def main():
    assert (P/'.codex_project6_owned').exists()
    assert (R/'protocol.json').exists()
    lock=(R/'queue.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    status('waiting_for_training')
    deadline=time.time()+2400
    while time.time()<deadline:
        record=json.loads((R/'training/run_summary.json').read_text())
        if record['status']=='training_complete_frozen' and (R/'frozen.json').exists():
            break
        if record['status']=='simulation_failed':
            raise RuntimeError('Training failed; retain evidence and do not validate')
        time.sleep(20)
    else:
        raise RuntimeError('Training did not reach frozen completion before queue timeout')
    env=os.environ.copy()
    env['CDS_LIC_FILE']='<LICENSE_FILE>'
    env['LM_LICENSE_FILE']='<LICENSE_FILE>'
    for kind in ('noiseless','noise'):
        directory=R/('validation_'+kind)
        if directory.exists():
            record=json.loads((directory/'run_summary.json').read_text())
            if record['status']=='validation_complete':continue
            raise RuntimeError('Preexisting incomplete validation; refuse duplicate/overwrite')
        status('validation_'+kind+'_running')
        with (R/('queue_'+kind+'.log')).open('w') as log:
            rc=subprocess.call(['python3',str(P/'scripts/adc_backend_pam4_r5.py'),
                'validate','--study','r5_late1','--variant','cml2_late1',
                '--validation-kind',kind,'--timeout','7200','--run'],
                cwd=str(P/'scripts'),env=env,stdout=log,stderr=subprocess.STDOUT)
        record=json.loads((directory/'run_summary.json').read_text())
        if rc or record['status']!='validation_complete':
            raise RuntimeError('Validation '+kind+' failed or incomplete; inspect retained VM log')
    status('paired_validation_complete',complete_ADC_verified=False)

if __name__=='__main__':
    try:main()
    except Exception as error:
        status('failed',error=str(error))
        raise
