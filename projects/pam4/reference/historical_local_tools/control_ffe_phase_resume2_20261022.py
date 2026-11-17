"""Transport for one user-authorized continuation after verified VM reboot."""
import argparse,base64,hashlib,json,subprocess
from pathlib import Path
import control_ffe_phase_resume1_20261022 as previous
LOCAL=previous.LOCAL
PRELUDE=previous.PRELUDE.replace("R=P/'runs/ffe_phase_resume1_20261022'","R=P/'runs/ffe_phase_resume2_20261022'")
PREPARE=r'''
assert not R.exists(),'New continuation already prepared; do not replay'
script=P/'scripts/ffe_phase_resume2_20261022.py'
subprocess.check_call(['python3',str(script),'--self-test'])
subprocess.check_call(['python3',str(script),'--prepare'],cwd=str(P/'scripts'))
print(json.dumps(dict(state=json.loads((R/'status.json').read_text()),script_sha256=sha(script))))
'''
LAUNCH=r'''
import fcntl
with (P/'runs/.ffe_phase_resume2_dispatch_20261022.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert not (R/'launch_receipt.json').exists(),'Already dispatched; no duplicate'
 state=json.loads((R/'status.json').read_text());assert state['status']=='prepared'
 inventory=actual()
 assert not any(original.owned_process(x) for x in inventory),'Owned simulator already active'
 assert os.statvfs(str(P)).f_bavail*os.statvfs(str(P)).f_frsize>=8*1024**3
 original.assert_unchanged(json.loads((R/'protocol.json').read_text()))
 script=P/'scripts/ffe_phase_resume2_20261022.py'
 env=os.environ.copy();env['CDS_LIC_FILE']='<LICENSE_FILE>';env['LM_LICENSE_FILE']=env['CDS_LIC_FILE']
 with (R/'worker.log').open('xb') as log:
  child=subprocess.Popen(['python3',str(script),'--run'],cwd=str(P/'scripts'),env=env,
   stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 time.sleep(.3)
 receipt=dict(started_utc=now(),runner=original.process_record(child.pid),
  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),script_sha256=sha(script),
  protocol_sha256=sha(R/'protocol.json'),automatic_retry=False,
  scope='User continue after travel and verified VM reboot: reuse eight complete cases, one retry of case08 lacking recorded exit status, and nine untouched noise cases once.')
 original.atomic_json(R/'launch_receipt.json',receipt)
 print(json.dumps(dict(launch=receipt)),flush=True)
 time.sleep(3)
 result=json.loads((R/'status.json').read_text());result.pop('prepared_sha256',None)
 print(json.dumps(dict(state=result,exit_code=child.poll())),flush=True)
'''
OBSERVE=previous.OBSERVE.replace('scripts/ffe_phase_resume1_20261022.py','scripts/ffe_phase_resume2_20261022.py')
BUILD_VIEWER=previous.BUILD_VIEWER
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=('prepare','launch','observe','build-viewer'));a=p.parse_args()
 code=PRELUDE
 if a.action=='prepare':
  data=(LOCAL/'work/project6_start/ffe_phase_resume2_20261022.py').read_bytes()
  digest=hashlib.sha256(data).hexdigest();payload=base64.b64encode(data).decode()
  code+='\nimport base64\ndata=base64.b64decode('+repr(payload)+')\nassert hashlib.sha256(data).hexdigest()=='+repr(digest)+'\n'
  code+="target=P/'scripts/ffe_phase_resume2_20261022.py'\nif target.exists():\n if target.read_bytes()!=data:\n  assert not R.exists() and sha(target)=='cba4fb5f198d24cea9b22609f152f3136fe6eefa0989a42f6e79063154e428a1'\n  original.atomic_json(P/'notes/resume2_preparation_capacity_guard_revision_20261022.json',dict(utc=now(),old_sha256=sha(target),new_sha256=hashlib.sha256(data).hexdigest(),reason='Preparation does not launch a simulator; allow known external jobs, but keep per-case simulation capacity gate unchanged. No run root created or simulation launched before revision.'))\n  target.write_bytes(data)\nelse:\n with target.open('xb') as f:f.write(data)\n"
  code+=PREPARE
 else:code+={'launch':LAUNCH,'observe':OBSERVE,'build-viewer':BUILD_VIEWER}[a.action]
 cmd=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(LOCAL/'work/ssh/vm_pdk_access_ed25519'),'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','HostKeyAlias=192.0.2.1','user@192.0.2.1','python3 -u -']
 r=subprocess.run(cmd,input=code,text=True,encoding='utf-8',capture_output=True,timeout=55)
 if r.returncode:raise RuntimeError(r.stderr or r.stdout)
 if a.action=='observe':
  v=json.loads(r.stdout)
  (LOCAL/'work/ffe_phase_resume2_last_observation_20261022.json').write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
  v['status'].pop('prepared_sha256',None);print(json.dumps(v))
 else:
  # Suppress large prepared source maps from the transcript; preserve only metadata locally.
  rows=[json.loads(x) for x in r.stdout.splitlines() if x.strip().startswith('{')]
  (LOCAL/('work/ffe_phase_resume2_'+a.action+'_20261022.json')).write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
  for v in rows:
   if isinstance(v.get('state'),dict):v['state'].pop('prepared_sha256',None)
  print(json.dumps(rows))
if __name__=='__main__':main()
