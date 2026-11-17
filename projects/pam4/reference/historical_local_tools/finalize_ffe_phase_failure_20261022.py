"""Preserve and record the terminal phase-sweep failure; never retry or signal."""
import json
import subprocess
from pathlib import Path

LOCAL=Path(__file__).resolve().parents[1]
REMOTE=r'''
import datetime,hashlib,json,os,sys
from pathlib import Path
P=Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R=P/'runs/ffe_phase_sweep_20261022'
assert (P/'.codex_project6_owned').is_file()
sys.dont_write_bytecode=True
sys.path.insert(0,str(P/'scripts'))
import ffe_phase_sweep_20261022 as runner
def sha(p):return runner.digest(p)
state=json.loads((R/'status.json').read_text())
launch=json.loads((R/'launch_receipt.json').read_text())
protocol=json.loads((R/'protocol.json').read_text())
assert state['status']=='failed_terminal' and state['current_case']=='noiseless_phase_02'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==launch['boot_id']
runner.assert_unchanged(protocol)
assert sha(R/'protocol.json')==launch['protocol_sha256']
assert runner.process_record(launch['runner']['pid']) is None,'Runner identity must be rechecked'
assert not any(runner.owned_process(x) for x in runner.spectre_inventory()),'Owned Spectre still exists'
D=R/state['current_case']
run_status=json.loads((D/'run_status.json').read_text())
assert run_status['exit_code']==-6 and 'SPECTRE-18' in run_status['issue_codes']
log=(D/'spectre.log').read_text(errors='replace')
assert "Transient Analysis `tranResponse'" not in log
completed=[]
for item in state['completed_cases']:
 path=R/item['name']/'summary.json'
 assert sha(path)==item['summary_sha256']
 summary=json.loads(path.read_text())
 assert summary['run_status']['exit_code']==0 and summary['frozen_unchanged'] is True
 assert summary['validation_fitting_performed'] is False
 assert all(summary['branches'][point]['FFE_output_count']==496 for point in ('primary','secondary'))
 completed.append(dict(name=item['name'],summary_sha256=sha(path),exit_code=0,FFE_windows_per_branch=496))
assert len(completed)==2
manifest={name:dict(bytes=(D/name).stat().st_size,sha256=sha(D/name))
 for name in ('bench.scs','prepared.json','run_status.json','spectre.log','console.log') if (D/name).exists()}
receipt=dict(recorded_utc=datetime.datetime.utcnow().isoformat()+'Z',
 failure_utc=state['updated_utc'],status='failed_terminal',case=state['current_case'],
 run_status=run_status,transient_started=False,completed_cases=completed,total_cases=18,
 unstarted_cases=15,complete_phase_eye_available=False,all_noise_cases_unstarted=True,
 boot_id=launch['boot_id'],frozen_sha256=sha(runner.FROZEN_PATH),
 runner_sha256=sha(P/'scripts/ffe_phase_sweep_20261022.py'),protocol_sha256=sha(R/'protocol.json'),
 failure_manifest=manifest,automatic_retry=False,owned_running_simulators=0,
 automation_id='project-6',automation_status='DELETED',
 interpretation='Third noiseless case failed before transient with SPECTRE-18 and exit -6. Two earlier cases completed. Root cause undetermined; this does not establish a transient-noise-only fault or memory exhaustion.',
 next_action='Keep all files in place. No restart, retries or additional simulation. User may later authorize a bounded simulator-startup diagnosis; no complete phase-eye claim.')
note=P/'notes/ffe_phase_sweep_terminal_20261022.json'
with note.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
status_path=P/'project_status.json'
old=json.loads(status_path.read_text())
old.update(updated_UTC=receipt['recorded_utc'],status='ffe_phase_sweep_failed_terminal',
 automation_status='DELETED',automatic_resume_authorized=False,complete_ADC_verified=False,
 latest_phase_sweep_terminal=receipt,next_action=receipt['next_action'])
if 'latest_phase_sweep' in old:
 old['latest_phase_sweep'].update(status='failed_terminal',current_case=receipt['case'],
  completed_cases=completed,last_observed_utc=receipt['recorded_utc'],next=receipt['next_action'])
tmp=status_path.with_name('project_status.phase_terminal.tmp')
tmp.write_text(json.dumps(old,indent=2)+'\n');tmp.replace(status_path)
receipt['VM_receipt']=str(note.relative_to(P))
receipt['VM_receipt_sha256']=sha(note)
print(json.dumps(receipt))
'''
args=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(LOCAL/'work/ssh/vm_pdk_access_ed25519'),
 '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes',
 'user@192.0.2.1','python3 -']
result=subprocess.run(args,input=REMOTE,encoding='utf-8',capture_output=True,timeout=35)
if result.returncode:raise RuntimeError(result.stderr or result.stdout)
receipt=json.loads(result.stdout)
(LOCAL/'work/ffe_phase_terminal_20261022.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
path=LOCAL/'work/project6_r5_handoff.json'
h=json.loads(path.read_text(encoding='utf-8'))
h.update(updated_date='2026-10-22',milestone='phase_sweep_terminated_incomplete',
 session_status='phase_sweep_failed_terminal',automation_status='DELETED',automatic_resume_authorized=False,
 automation_stop='Phase sweep failed in third noiseless case. Heartbeat deleted after recording failure. No restart or automatic retry.')
entry=h['active_work']['ffe_phase_sweep_20261022']
entry.update(status='failed_terminal',current_case=receipt['case'],completed_cases=receipt['completed_cases'],
 last_observed_utc=receipt['recorded_utc'],terminal_receipt=receipt,next=receipt['next_action'])
h['monitoring_phase_sweep_20261022'].update(status='DELETED',reason='Terminal simulator failure; no further automatic work.')
tmp=path.with_name(path.name+'.terminal.tmp')
tmp.write_text(json.dumps(h,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(path)
print(json.dumps(dict(status=receipt['status'],completed_cases=2,total_cases=18,
 failure_utc=receipt['failure_utc'],case=receipt['case'],automation_status='DELETED',
 receipt_sha256=receipt['VM_receipt_sha256'],owned_running_simulators=0)))
