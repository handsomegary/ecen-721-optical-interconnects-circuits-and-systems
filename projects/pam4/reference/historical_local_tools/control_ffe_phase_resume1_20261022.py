"""Transport for one user-authorized resume; all simulation data stays on VM."""
import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path

LOCAL=Path(__file__).resolve().parents[1]
PRELUDE=r'''
import datetime,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
P=Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R=P/'runs/ffe_phase_resume1_20261022'
OLD=P/'runs/ffe_phase_sweep_20261022'
assert (P/'.codex_project6_owned').is_file()
sys.dont_write_bytecode=True;sys.path.insert(0,str(P/'scripts'))
import ffe_phase_sweep_20261022 as original
def now():return datetime.datetime.utcnow().isoformat()+'Z'
def sha(path):return original.digest(path)
def actual():return [x for x in original.spectre_inventory() if x.get('executable') and Path(x['executable']).name=='spectre']
'''
PREPARE=r'''
assert not R.exists(),'Resume root already exists; no duplicate prepare'
script=P/'scripts/ffe_phase_resume1_20261022.py'
subprocess.check_call(['python3',str(script),'--self-test'])
subprocess.check_call(['python3',str(script),'--prepare'],cwd=str(P/'scripts'))
print(json.dumps(dict(state=json.loads((R/'status.json').read_text()),script_sha256=sha(script))))
'''
LAUNCH=r'''
import fcntl
with (P/'runs/.ffe_phase_resume1_dispatch_20261022.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert not (R/'launch_receipt.json').exists(),'Already dispatched; no replay'
 state=json.loads((R/'status.json').read_text())
 assert state['status']=='prepared'
 assert json.loads((OLD/'status.json').read_text())['status']=='failed_terminal'
 original.assert_unchanged(json.loads((R/'protocol.json').read_text()))
 inventory=actual()
 assert len(inventory)<2 and not any(original.owned_process(x) for x in inventory),'Wait for capacity'
 assert os.statvfs(str(P)).f_bavail*os.statvfs(str(P)).f_frsize>=8*1024**3
 env=os.environ.copy();env['CDS_LIC_FILE']='<LICENSE_FILE>';env['LM_LICENSE_FILE']=env['CDS_LIC_FILE']
 script=P/'scripts/ffe_phase_resume1_20261022.py'
 with (R/'worker.log').open('xb') as log:
  child=subprocess.Popen(['python3',str(script),'--run'],cwd=str(P/'scripts'),env=env,
   stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 time.sleep(.3)
 receipt=dict(started_utc=now(),runner=original.process_record(child.pid),
  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
  script_sha256=sha(script),protocol_sha256=sha(R/'protocol.json'),automatic_retry=False,
  scope='User continue: reuse first two completed cases, attempt failed third case once, then remaining cases once. Stop on failure.')
 original.atomic_json(R/'launch_receipt.json',receipt)
 print(json.dumps(dict(launch=receipt)),flush=True)
 time.sleep(3)
 print(json.dumps(dict(state=json.loads((R/'status.json').read_text()),exit_code=child.poll())),flush=True)
'''
OBSERVE=r'''
state=json.loads((R/'status.json').read_text())
launch=json.loads((R/'launch_receipt.json').read_text()) if (R/'launch_receipt.json').exists() else None
identity={}
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
if launch:
 reference=launch['runner'];live=original.process_record(reference['pid']) if reference else None
 identity=dict(live=live,boot_matches=boot==launch['boot_id'],
  start_matches=bool(live and live['start_ticks']==reference['start_ticks']),
  script_matches=sha(P/'scripts/ffe_phase_resume1_20261022.py')==launch['script_sha256'])
 if live:
  args=(Path('/proc')/str(live['pid'])/'cmdline').read_bytes().split(b'\0')
  identity['command_matches']=str(P/'scripts/ffe_phase_resume1_20261022.py').encode() in args
diagnostic={};case=state.get('current_case')
if case:
 assert Path(case).name==case
 directory=R/case;logpath=directory/'spectre.log'
 log=logpath.read_text(errors='replace') if logpath.exists() else ''
 diagnostic=dict(transient_started="Transient Analysis `tranResponse'" in log,spectre18_seen='SPECTRE-18' in log,
  completion_lines=re.findall(r'spectre completes with[^\r\n]*',log)[-1:],
  memory_lines=re.findall(r'Peak (?:resident )?memory used[^\r\n]*',log)[-1:],
  log_bytes=logpath.stat().st_size if logpath.exists() else 0)
 if (directory/'run_status.json').exists():diagnostic['run_status']=json.loads((directory/'run_status.json').read_text())
print(json.dumps(dict(observed_utc=now(),status=state,launch=launch,identity=identity,diagnostic=diagnostic,
 actual_simulators=actual(),frozen_sha256=sha(original.FROZEN_PATH),
 original_terminal_status=json.loads((OLD/'status.json').read_text())['status'])))
'''
BUILD_VIEWER=r'''
viewer_path=P/'scripts/ffe_phase_viva_20261022.py'
assert sha(viewer_path)=='23e310f6740b5e5a45542ea2a78e15b2490f1a28d01a2a45cb460b380626dd09'
import ffe_phase_viva_20261022 as viewer
viewer.ROOT=R;viewer.OUTPUT=R/'viva_sampled_eye'
viewer.build()
env=os.environ.copy();env['CDS_LIC_FILE']='<LICENSE_FILE>';env['LM_LICENSE_FILE']=env['CDS_LIC_FILE'];env.pop('DISPLAY',None)
with (viewer.OUTPUT/'native_check.log').open('x') as log:
 result=subprocess.run(['/opt/eda/cadence/IC618/tools/dfII/bin/ocean','-nograph','-restore',str(viewer.OUTPUT/'check_native_data.ocn')],
  cwd=str(viewer.OUTPUT),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=40)
content=(viewer.OUTPUT/'native_check.log').read_text(errors='replace')
passed=result.returncode==0 and 'P6_NATIVE_DATA_CHECK_OK 17856' in content and '*Error*' not in content
receipt=dict(passed=passed,exit_code=result.returncode,points=17856,GUI_opened=False,
 log_sha256=sha(viewer.OUTPUT/'native_check.log'),viewer_sha256=sha(viewer_path),
 provenance_sha256=sha(viewer.OUTPUT/'provenance.json'),summary_sha256=sha(viewer.OUTPUT/'sampled_eye_summary.json'))
original.atomic_json(viewer.OUTPUT/'native_check_receipt.json',receipt)
print(json.dumps(receipt))
assert passed,'Native data check failed; preserve outputs and inspect'
'''

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('prepare','launch','observe','build-viewer'))
    args=parser.parse_args();code=PRELUDE
    if args.action=='prepare':
        data=(LOCAL/'work/project6_start/ffe_phase_resume1_20261022.py').read_bytes()
        payload=base64.b64encode(data).decode();digest=hashlib.sha256(data).hexdigest()
        code+='\nimport base64\ndata=base64.b64decode('+repr(payload)+')\n'
        code+='assert hashlib.sha256(data).hexdigest()=='+repr(digest)+'\n'
        code+="target=P/'scripts/ffe_phase_resume1_20261022.py'\nif target.exists():assert target.read_bytes()==data\nelse:\n with target.open('xb') as f:f.write(data)\n"
        code+=PREPARE
    elif args.action=='launch':code+=LAUNCH
    elif args.action=='observe':code+=OBSERVE
    else:code+=BUILD_VIEWER
    command=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(LOCAL/'work/ssh/vm_pdk_access_ed25519'),
     '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes',
     'user@192.0.2.1','python3 -u -']
    result=subprocess.run(command,input=code,encoding='utf-8',capture_output=True,timeout=55)
    if args.action=='observe' and result.returncode==0:
        record=json.loads(result.stdout)
        (LOCAL/'work/ffe_phase_resume1_last_observation_20261022.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
        record['status'].pop('prepared_sha256',None)
        print(json.dumps(record))
    else:print(result.stdout)
    if result.stderr:print(result.stderr)
    raise SystemExit(result.returncode)

if __name__=='__main__':main()
