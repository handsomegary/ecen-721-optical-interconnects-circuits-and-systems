import base64
import hashlib
import json
import subprocess
import tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'work'
config=tomllib.loads(Path('C:/Users/User/.codex/automations/project-6/automation.toml').read_text(encoding='utf-8'))
assert config['status']=='PAUSED'
payload=base64.b64encode((W/'paired_final_payload_20261020.json').read_bytes()).decode()
REMOTE=r'''
import base64,datetime,hashlib,json,os
from pathlib import Path
P=Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R=P/'runs/project6_noise_retry2_20261020'
S=P/'runs/adc_backend_pam4_r5_20261013/r5_late1'
data=json.loads(base64.b64decode('PAYLOAD'))
e=data['evidence'];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert (P/'.codex_project6_owned').exists()
assert sha(R/'status.json')==e['state_sha256']
state=json.loads((R/'status.json').read_text())
assert state['status']=='complete' and state['exit_code']==0
assert sha(S/'frozen.json')==e['frozen_sha256']
for kind in ('noise','noiseless'):
 assert sha(S/('validation_'+kind)/'run_summary.json')==e['pairs'][kind]['summary_sha256']
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==e['boot_id']
for p in Path('/proc').iterdir():
 if not p.name.isdigit() or int(p.name)==os.getpid():continue
 try:
  fields=(p/'stat').read_text().rsplit(')',1)[1].split()
  if fields[0]=='Z':continue
  exe=os.readlink(str(p/'exe'));cwd=os.readlink(str(p/'cwd'))
  args=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
 except OSError:continue
 owned=cwd==str(P) or cwd.startswith(str(P)+'/') or str(P)+'/scripts/' in args
 assert not (owned and ('python' in Path(exe).name.lower() or Path(exe).name.lower()=='spectre')), 'Owned worker remains'
expected_old={
 'notes/ADC_r5_progress_20261013_zh_TW.txt':'7f3a769428c11d1b77692a11deea24a3048347b8e45117a852747077cd7c3581',
 'results/Project6_ADC_round_terminal_summary.json':'be269c120070dc63d20dda721f1d0950e7c17a1ec0d17c674455bb30cddb4620'}
backup=R/'before_pair_final';backup.mkdir(exist_ok=True)
files={}
for rel,encoded in data['files'].items():
 assert rel in expected_old
 p=P/rel;content=base64.b64decode(encoded);newsha=hashlib.sha256(content).hexdigest()
 assert sha(p) in (expected_old[rel],newsha), 'Unexpected prior report bytes'
 old=backup/p.name
 if not old.exists():old.write_bytes(p.read_bytes())
 temp=p.with_name(p.name+'.paired.tmp');temp.write_bytes(content);temp.replace(p)
 assert sha(p)==newsha
 files[rel]={'bytes':len(content),'sha256':newsha}
ps_path=P/'project_status.json'
old=backup/'project_status.json'
if not old.exists():old.write_bytes(ps_path.read_bytes())
ps=json.loads(ps_path.read_text())
ps.update(updated_UTC=datetime.datetime.utcnow().isoformat()+'Z',
 status='bounded_round_complete_paired_validation',complete_ADC_verified=False,
 automatic_resume_authorized=False,automation_status='PAUSED')
ps['latest_noise_retry']={'status':'complete','root':str(R.relative_to(P)),
 'state_sha256':e['state_sha256'],'summary_sha256':e['pairs']['noise']['summary_sha256'],
 'simulator_exit_code':0,'simulator_seconds':e['pairs']['noise']['run_status']['seconds'],
 'completed_UTC':e['ended_UTC'],'owned_workers_remaining':[]}
ps['next_action']='Bounded round complete. Primary0/2032; secondary164/2032 noisy vs2/2032 noiseless. Secondary path needs further work before physical ADC integration; no new simulations or automatic retry.'
temp=ps_path.with_name('project_status.paired.tmp')
temp.write_text(json.dumps(ps,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(ps_path)
receipt={'verified_UTC':ps['updated_UTC'],'status':ps['status'],'evidence':e,
 'automation_status':'PAUSED','complete_ADC_verified':False,'owned_workers_remaining':[],
 'other_projects_signaled':False,'delivery':files,'combined_output_bytes':data['combined_output_bytes'],
 'previous_reports_and_status_backup':str(backup.relative_to(P))}
note=P/'notes/r5_pair_complete_20261020.json'
if note.exists():
 assert json.loads(note.read_text())['evidence']==e
else:
 with note.open('x') as f:json.dump(receipt,f,ensure_ascii=False,indent=2)
print(json.dumps({'receipt':str(note.relative_to(P)),'receipt_sha256':sha(note),
 'verified_UTC':ps['updated_UTC'],'files':files,'automation_status':'PAUSED','owned_workers_remaining':[]}))
'''.replace('PAYLOAD',payload)
cmd=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(ROOT/'work/ssh/vm_pdk_access_ed25519'),
     '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8',
     '-o','StrictHostKeyChecking=yes','user@192.0.2.1','python3 -']
r=subprocess.run(cmd,input=REMOTE,encoding='utf-8',capture_output=True,timeout=40)
if r.returncode:raise RuntimeError(r.stderr)
v=json.loads(r.stdout)
hpath=W/'project6_r5_handoff.json';h=json.loads(hpath.read_text(encoding='utf-8'))
for key,rel in (('current_progress_report','notes/ADC_r5_progress_20261013_zh_TW.txt'),
                ('terminal_summary','results/Project6_ADC_round_terminal_summary.json')):
    assert h[key]['sha256']==v['files'][rel]['sha256']
    h[key]['VM_sync_complete']=True
h['pending_VM_sync']=None
h['automation_status']='PAUSED'
h['automation_stop']='Completed paired r5 validation; final summaries delivered and monitoring paused. No further simulations authorized by this one-time retry.'
h['monitoring_retry2']['status']='PAUSED'
h['monitoring_retry2']['completed_UTC']=h['active_work']['r5_noise_retry2_20261020']['ended_UTC']
h['monitoring_retry2']['paused_after_completion']=True
h['active_work']['r5_noise_retry2_20261020']['final_VM_receipt']=v['receipt']
h['active_work']['r5_noise_retry2_20261020']['final_VM_receipt_sha256']=v['receipt_sha256']
h['active_work']['PAM4_training']['validation_noise_result']['latest_receipt_VM']=v['receipt']
h['paired_validation_complete']['VM_receipt']=v['receipt']
h['paired_validation_complete']['VM_receipt_sha256']=v['receipt_sha256']
h['resume_authorization_retry2_20261020']['status']='consumed; single attempt completed; no automatic replay'
h['last_health_check']['observed_UTC']=v['verified_UTC']
h['last_connection_check']=dict(h['last_health_check'],status='SSH_connected')
h['handoff_transfer']['superseded_by']='2026-10-20 retry2 completed paired validation; see paired_validation_complete; automation PAUSED.'
hpath.write_text(json.dumps(h,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
transfer=W/'Project6_GPT交接_20261020.txt'
heading=('【最新終止狀態：2026-10-20 r5 配對驗證已完成】\n'
 'retry2 約69分鐘成功完成、exit0；主取樣端有雜訊0/2032，次級164/2032（SER8.07%、Gray BER4.04%），'
 '無雜訊次級2/2032。凍結未改、無驗證擬合；尚非完整實體ADC。'
 '最終報告在 outputs，VM紀錄 notes/r5_pair_complete_20261020.json。'
 'project-6 排程已暫停，本專案無殘留模擬；不得依下方歷史指令重啟。'
 '最新身分與雜湊以 project6_r5_handoff.json 為準。\n\n')
text=transfer.read_text(encoding='utf-8')
if not text.startswith(heading):transfer.write_text(heading+text,encoding='utf-8')
(W/'paired_final_sync_receipt_20261020.json').write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
print(json.dumps(v,indent=2))
