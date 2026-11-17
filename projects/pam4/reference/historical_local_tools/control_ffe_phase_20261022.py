"""Restricted transport for the newly authorized sweep; never transfers VM waves."""
import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path

LOCAL = Path(__file__).resolve().parents[1]
PRELUDE = r'''
import datetime,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
P=Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R=P/'runs/ffe_phase_sweep_20261022'
assert (P/'.codex_project6_owned').is_file()
sys.dont_write_bytecode=True
sys.path.insert(0,str(P/'scripts'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now():return datetime.datetime.utcnow().isoformat()+'Z'
'''

def upload_code(names):
    files = {}
    for name in names:
        data=(LOCAL/'work/project6_start'/name).read_bytes()
        files[name] = {'data':base64.b64encode(data).decode(), 'sha256':hashlib.sha256(data).hexdigest()}
    return 'payload='+repr(files)+r'''
import base64
for name,entry in payload.items():
 assert Path(name).name==name
 data=base64.b64decode(entry['data'])
 assert hashlib.sha256(data).hexdigest()==entry['sha256']
 target=P/'scripts'/name
 if target.exists():assert target.read_bytes()==data,'Existing script differs: '+name
 else:
  with target.open('xb') as f:f.write(data)
 print(json.dumps(dict(upload=name,sha256=entry['sha256'])))
'''

PREPARE=r'''
import ffe_phase_sweep_20261022 as s
assert not s.ROOT.exists(),'Study already exists; inspect rather than overwrite'
subprocess.check_call(['python3',str(P/'scripts/ffe_phase_sweep_20261022.py'),'--self-test'])
subprocess.check_call(['python3',str(P/'scripts/ffe_phase_sweep_20261022.py'),'--prepare'],cwd=str(P/'scripts'))
protocol=json.loads((R/'protocol.json').read_text())
print(json.dumps(dict(prepared=True,protocol_sha256=sha(R/'protocol.json'),
 frozen_sha256=protocol['frozen_sha256'],cases=len(protocol['cases']),
 symbols=protocol['generated_symbols'],data_seed=protocol['data_seed'],noise_seed=protocol['noise_seed'],
 deltas=protocol['delta_phase_UI'],scope=protocol['scope'])))
'''

LAUNCH=r'''
import fcntl
import ffe_phase_sweep_20261022 as s
with (P/'runs/.ffe_phase_dispatch_20261022.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 state=json.loads((R/'status.json').read_text())
 assert state['status']=='prepared' and not state['completed_cases']
 assert not (R/'launch_receipt.json').exists(),'Already dispatched; no replay'
 protocol=json.loads((R/'protocol.json').read_text())
 s.assert_unchanged(protocol)
 actual=s.spectre_inventory()
 assert len(actual)<2 and not any(s.owned_process(x) for x in actual) and all(x['cwd'] for x in actual)
 assert os.statvfs(str(P)).f_bavail*os.statvfs(str(P)).f_frsize>=8*1024**3
 env=os.environ.copy()
 env['CDS_LIC_FILE']='<LICENSE_FILE>'
 env['LM_LICENSE_FILE']=env['CDS_LIC_FILE']
 with (R/'worker.log').open('xb') as log:
  child=subprocess.Popen(['python3',str(P/'scripts/ffe_phase_sweep_20261022.py'),'--run'],
    cwd=str(P/'scripts'),env=env,stdin=subprocess.DEVNULL,stdout=log,
    stderr=subprocess.STDOUT,start_new_session=True)
 receipt=dict(started_utc=now(),runner=s.process_record(child.pid),
   boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
   script_sha256=sha(P/'scripts/ffe_phase_sweep_20261022.py'),
   protocol_sha256=sha(R/'protocol.json'),automatic_retry=False,
   scope='One bounded 18-case phase sweep, no old queue restart or parameter fitting')
 s.atomic_json(R/'launch_receipt.json',receipt)
 s.atomic_json(P/'notes/ffe_phase_sweep_started_20261022.json',receipt)
 print(json.dumps(dict(launch=receipt)),flush=True)
 time.sleep(3)
 print(json.dumps(dict(state=json.loads((R/'status.json').read_text()),launcher_child_exit=child.poll())),flush=True)
'''

OBSERVE=r'''
import ffe_phase_sweep_20261022 as s
state=json.loads((R/'status.json').read_text())
launch=json.loads((R/'launch_receipt.json').read_text()) if (R/'launch_receipt.json').exists() else None
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
identity=None
if launch:
 live=s.process_record(launch['runner']['pid'])
 identity=dict(live=live,boot_matches=boot==launch['boot_id'],
  start_matches=bool(live and live['start_ticks']==launch['runner']['start_ticks']),
  script_matches=sha(P/'scripts/ffe_phase_sweep_20261022.py')==launch['script_sha256'])
 if live:
  args=(Path('/proc')/str(live['pid'])/'cmdline').read_bytes().split(b'\0')
  identity['command_matches']=str(P/'scripts/ffe_phase_sweep_20261022.py').encode() in args
case=state.get('current_case')
diagnostic={}
if case:
 assert Path(case).name==case
 logpath=R/case/'spectre.log'
 log=logpath.read_text(errors='replace') if logpath.exists() else ''
 diagnostic=dict(transient_started="Transient Analysis `tranResponse'" in log,
  spectre18_seen='SPECTRE-18' in log,
  completion_lines=re.findall(r'spectre completes with[^\r\n]*',log)[-1:],
  memory_lines=re.findall(r'Peak (?:resident )?memory used[^\r\n]*',log)[-1:],
  log_bytes=logpath.stat().st_size if logpath.exists() else 0)
 if (R/case/'run_status.json').exists():diagnostic['run_status']=json.loads((R/case/'run_status.json').read_text())
print(json.dumps(dict(observed_utc=now(),boot_id=boot,status=state,launch=launch,
 identity=identity,actual_spectre=s.spectre_inventory(),diagnostic=diagnostic,
 frozen_sha256=s.digest(s.FROZEN_PATH))))
'''

NATIVE_CHECK=r'''
import ffe_phase_viva_20261022 as viewer
D=P/'notes/ffe_viva_api_check_20261022'
assert not D.exists(),'Native API check evidence already exists'
D.mkdir()
(D/'view_sampled_eye.il').write_text(viewer.viewer_source(viewer.OUTPUT))
(D/'synthetic_api_only.xy').write_text('-0.5 -3\n-0.375 -3\n-0.25 -3\n-0.125 -3\n0 -3\n0.125 -3\n0.25 -3\n0.375 -3\n0.5 -3\n')
source='load("'+str(D/'view_sampled_eye.il')+'")\n'
source+='p6TestWave=getAsciiWave("'+str(D/'synthetic_api_only.xy')+'" 1 2 ?formatFloat t ?xName "phase" ?xUnits "UI" ?yName "target" ?yUnits "")\n'
source+='unless(drVectorLength(drGetWaveformXVec(p6TestWave)) == 9 error("API point count mismatch"))\n'
source+='unless(drGetElem(drGetWaveformYVec(p6TestWave) 0) == -3.0 error("API value mismatch"))\n'
source+='p6TestFam=famCreateFamily("target_symbol_index" \'double)\nfamAddValue(p6TestFam 264 p6TestWave)\n'
source+='unless(getd(\'awvPlotWaveform) && getd(\'awvSetPlotStyle) error("Native plot API absent"))\n'
source+='printf("P6_NATIVE_API_CHECK_OK no windows opened; synthetic parser check only\\n")\nexit()\n'
(D/'check.ocn').write_text(source)
env=os.environ.copy()
env['CDS_LIC_FILE']='<LICENSE_FILE>'
env['LM_LICENSE_FILE']=env['CDS_LIC_FILE']
env.pop('DISPLAY',None)
with (D/'ocean.log').open('w') as log:
 outcome=subprocess.run(['/opt/eda/cadence/IC618/tools/dfII/bin/ocean','-nograph','-restore',str(D/'check.ocn')],
   cwd=str(D),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=40)
text=(D/'ocean.log').read_text(errors='replace')
passed=outcome.returncode==0 and 'P6_NATIVE_API_CHECK_OK no windows opened;' in text and '*Error*' not in text
receipt=dict(passed=passed,exit_code=outcome.returncode,GUI_opened=False,simulations_started=0,
 viewer_sha256=sha(P/'scripts/ffe_phase_viva_20261022.py'),source_sha256=sha(D/'view_sampled_eye.il'),
 log_sha256=sha(D/'ocean.log'),scope='Synthetic getAsciiWave/family parse and helper load only; no actual data or graphical render checked')
(D/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
if not passed:
 print('\n'.join(line for line in text.splitlines() if '*Error*' in line or '*WARNING*' in line))
 raise RuntimeError('Native viewer API check failed; evidence retained')
'''

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('prepare','launch','observe','upload-viewer','native-check'))
    args=parser.parse_args()
    code=PRELUDE
    if args.action=='prepare':code+=upload_code(['ffe_phase_sweep_20261022.py'])+PREPARE
    elif args.action=='upload-viewer':code+=upload_code(['ffe_phase_viva_20261022.py'])
    elif args.action=='launch':code+=LAUNCH
    elif args.action=='native-check':code+=NATIVE_CHECK
    else:code+=OBSERVE
    command=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(LOCAL/'work/ssh/vm_pdk_access_ed25519'),
      '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8',
      '-o','StrictHostKeyChecking=yes','user@192.0.2.1','python3 -u -']
    result=subprocess.run(command,input=code,encoding='utf-8',capture_output=True,timeout=55)
    print(result.stdout)
    if result.stderr:print(result.stderr)
    if args.action=='observe' and result.returncode==0:
        record=json.loads(result.stdout)
        (LOCAL/'work/ffe_phase_last_observation_20261022.json').write_text(
          json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(result.returncode)

if __name__=='__main__':main()
