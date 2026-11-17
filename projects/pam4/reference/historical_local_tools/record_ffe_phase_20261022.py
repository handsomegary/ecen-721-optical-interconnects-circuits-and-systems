"""Record verified launch metadata only; preserves prior numeric deliverables."""
import json
import subprocess
from pathlib import Path

LOCAL=Path(__file__).resolve().parents[1]
record=json.loads((LOCAL/'work/ffe_phase_last_observation_20261022.json').read_text(encoding='utf-8'))
state=record['status']
entry=dict(root='runs/ffe_phase_sweep_20261022',state='runs/ffe_phase_sweep_20261022/status.json',
 runner='scripts/ffe_phase_sweep_20261022.py',runner_sha256=record['launch']['script_sha256'],
 protocol_sha256=record['launch']['protocol_sha256'],launch=record['launch'],
 verified_runner=state['runner'],last_observed_utc=record['observed_utc'],status=state['status'],
 current_case=state['current_case'],completed_cases=state['completed_cases'],
 frozen_sha256=record['frozen_sha256'],phase_offsets_UI=[-.5,-.375,-.25,-.125,0,.125,.25,.375,.5],
 total_cases=18,data_seed=2026102201,noise_seed=197,warmup=256,score_inputs=512,FFE_windows=496,guard=128,
 observation_command='python work/control_ffe_phase_20261022.py observe',
 viewer_script='scripts/ffe_phase_viva_20261022.py',viewer_build_requires='all 18 cases complete with verified hashes',
 viewer_sha256='23e310f6740b5e5a45542ea2a78e15b2490f1a28d01a2a45cb460b380626dd09',
 native_API_check='notes/ffe_viva_api_check_20261022/receipt.json',native_API_check_passed=True,
 native_API_check_scope='Synthetic parser/family/helper load only; no GUI opened; actual data check still required after completion.',
 learning_guide_local='outputs/Project6_FFE相位眼圖_實戰第一課.txt',
 viewer_directory='runs/ffe_phase_sweep_20261022/viva_sampled_eye',
 authorization='User chose real sampling-clock phase sweep with fixed FFE on 2026-10-22 for practical learning.',
 limits='One owned Spectre at a time, global actual simulators <2 before launch, 3600s/case, 10h dispatch bound, no automatic retry.',
 scope='Native AFE and both sampler stages, ideal numerical 7-bit quantizer plus frozen FFE. Sampled phase eye, not physical continuous FFE or full ADC.',
 next='Observe only existing runner; on complete build native ViVA views, verify in OCEAN without GUI, explain how user can open them. On failure report promptly, preserve evidence, pause. No retry/new candidates.')

remote=r'''
import json
from pathlib import Path
P=Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R=P/'runs/ffe_phase_sweep_20261022'
assert (P/'.codex_project6_owned').is_file()
entry=ENTRY
path=P/'project_status.json'
backup=R/'project_status_before_phase_sweep.json'
if not backup.exists():
 with backup.open('x') as f:f.write(path.read_text())
status=json.loads(path.read_text())
status.update(updated_UTC=entry['last_observed_utc'],status='ffe_phase_sweep_'+entry['status'],
 complete_ADC_verified=False,automation_status='ACTIVE',automatic_resume_authorized=False,
 latest_phase_sweep=entry,next_action=entry['next'])
tmp=path.with_name('project_status.phase_sweep.tmp')
tmp.write_text(json.dumps(status,indent=2)+'\n')
tmp.replace(path)
note=P/'notes/ffe_phase_sweep_handoff_20261022.json'
note.write_text(json.dumps(entry,indent=2)+'\n')
print('VM phase sweep handoff recorded; old results unchanged')
'''.replace('ENTRY',repr(entry))
cmd=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(LOCAL/'work/ssh/vm_pdk_access_ed25519'),
 '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes',
 'user@192.0.2.1','python3 -']
result=subprocess.run(cmd,input=remote,encoding='utf-8',capture_output=True,timeout=25)
print(result.stdout)
if result.returncode:raise RuntimeError(result.stderr)
path=LOCAL/'work/project6_r5_handoff.json'
h=json.loads(path.read_text(encoding='utf-8'))
h.update(updated_date='2026-10-22',local_root=str(LOCAL).replace('\\','/'),
 milestone='authorized_real_clock_FFE_phase_sweep_running',session_status='phase_sweep_running',
 automation_status='ACTIVE',automatic_resume_authorized=False,
 automation_stop='Monitor only the bounded new 18-case phase sweep; pause after terminal failure or after verified native ViVA delivery. Never restart old queues.',
 current_experiment='active_work.ffe_phase_sweep_20261022')
h['active_work']['ffe_phase_sweep_20261022']=entry
h['workspace_migration_20261021']={'old_root':'C:/Users/User/Documents/Codex/2026-10-10/high-speed-mos',
 'new_root':str(LOCAL).replace('\\','/'),'note':'Historical absolute paths retained as evidence; resolve current local files against new_root.'}
h['monitoring_phase_sweep_20261022']=dict(automation_id='project-6',interval_minutes=5,
 normal_progress_notifications=False,automatic_retries=False,status='ACTIVE')
temp=path.with_name(path.name+'.phase.tmp')
temp.write_text(json.dumps(h,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
temp.replace(path)
print('Local handoff updated at '+str(path))
