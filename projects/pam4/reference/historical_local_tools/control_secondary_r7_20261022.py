"""One-shot transport for the user-authorized fresh-training secondary-cap screen."""
import argparse,base64,hashlib,json,subprocess
from pathlib import Path
import control_ffe_phase_resume2_20261022 as prior
LOCAL=prior.LOCAL
NAME='secondary_cap_training_r7_20261022'
PRELUDE=prior.PRELUDE.replace("R=P/'runs/ffe_phase_resume2_20261022'","R=P/'runs/secondary_cap_training_r7_20261022'")
PREPARE=r'''
assert not R.exists(),'Study root exists; no duplicate preparation'
script=P/'scripts/secondary_cap_training_r7_20261022.py'
subprocess.check_call(['python3',str(script),'--self-test'])
subprocess.check_call(['python3',str(script),'--prepare'],cwd=str(P/'scripts'))
state=json.loads((R/'status.json').read_text())
print(json.dumps(dict(state=state,script_sha256=sha(script))))
'''
LAUNCH=r'''
import fcntl
with (P/'runs/.secondary_r7_dispatch_20261022.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert not (R/'launch_receipt.json').exists(),'Already dispatched; do not launch twice'
 state=json.loads((R/'status.json').read_text());assert state['status']=='prepared'
 assert not any(original.owned_process(x) for x in actual()),'Project already simulating'
 script=P/'scripts/secondary_cap_training_r7_20261022.py'
 env=os.environ.copy();env['CDS_LIC_FILE']='<LICENSE_FILE>';env['LM_LICENSE_FILE']=env['CDS_LIC_FILE']
 with (R/'worker.log').open('xb') as log:
  child=subprocess.Popen(['python3',str(script),'--run'],cwd=str(P/'scripts'),env=env,
   stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 time.sleep(.3)
 receipt=dict(started_utc=now(),runner=original.process_record(child.pid),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
  script_sha256=sha(script),protocol_sha256=sha(R/'protocol.json'),automatic_retry=False,
  scope='User explicitly requested background improvement: new training only; fixed3secondarycap/TG configurations x noiseless/noise, maximum6simulations; no holdout access/refit.')
 original.atomic_json(R/'launch_receipt.json',receipt)
 print(json.dumps(dict(launch=receipt)),flush=True);time.sleep(3)
 print(json.dumps(dict(state=json.loads((R/'status.json').read_text()),exit_code=child.poll())),flush=True)
'''
OBSERVE=r'''
state=json.loads((R/'status.json').read_text());launch=json.loads((R/'launch_receipt.json').read_text())
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();ref=launch['runner'];live=original.process_record(ref['pid']) if ref else None
identity=dict(live=live,boot_matches=boot==launch['boot_id'],start_matches=bool(live and live['start_ticks']==ref['start_ticks']),script_matches=sha(P/'scripts/secondary_cap_training_r7_20261022.py')==launch['script_sha256'])
if live:identity['command_matches']=str(P/'scripts/secondary_cap_training_r7_20261022.py').encode() in (Path('/proc')/str(live['pid'])/'cmdline').read_bytes().split(b'\0')
diagnostic={};case=state.get('current_case')
if case:
 assert Path(case).name==case
 logpath=R/case/'spectre.log';log=logpath.read_text(errors='replace') if logpath.exists() else ''
 diagnostic=dict(transient_started="Transient Analysis `tranResponse'" in log,spectre18_seen='SPECTRE-18' in log,log_bytes=logpath.stat().st_size if logpath.exists() else 0,completion_lines=re.findall(r'spectre completes with[^\r\n]*',log)[-1:])
print(json.dumps(dict(observed_utc=now(),status=state,launch=launch,identity=identity,diagnostic=diagnostic,
 actual_simulators=actual(),frozen_sha256=sha(original.FROZEN_PATH))))
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=('prepare','launch','observe'));a=p.parse_args();code=PRELUDE
 if a.action=='prepare':
  data=(LOCAL/'work/project6_start'/('secondary_cap_training_r7_20261022.py')).read_bytes();digest=hashlib.sha256(data).hexdigest()
  code+='\nimport base64\ndata=base64.b64decode('+repr(base64.b64encode(data).decode())+')\nassert hashlib.sha256(data).hexdigest()=='+repr(digest)+'\n'
  code+="target=P/'scripts/secondary_cap_training_r7_20261022.py'\nif target.exists():assert target.read_bytes()==data\nelse:\n with target.open('xb') as f:f.write(data)\n"
  code+=PREPARE
 else:code+=LAUNCH if a.action=='launch' else OBSERVE
 cmd=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(LOCAL/'work/ssh/vm_pdk_access_ed25519'),'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','HostKeyAlias=192.0.2.1','user@192.0.2.1','python3 -u -']
 r=subprocess.run(cmd,input=code,text=True,encoding='utf-8',capture_output=True,timeout=55)
 if r.returncode:raise RuntimeError(r.stderr or r.stdout)
 rows=[json.loads(x) for x in r.stdout.splitlines() if x.strip().startswith('{')]
 (LOCAL/('work/secondary_r7_'+a.action+'_20261022.json')).write_text(json.dumps(rows if a.action!='observe' else rows[-1],indent=2)+'\n',encoding='utf-8')
 for v in rows:
  if isinstance(v.get('state'),dict):v['state'].pop('prepared_sha256',None)
 print(json.dumps(rows))
if __name__=='__main__':main()
