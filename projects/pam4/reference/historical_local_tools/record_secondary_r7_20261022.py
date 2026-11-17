"""Persist a routine r7 observation; never touches completed eye-study artifacts."""
import json,subprocess
import control_secondary_r7_20261022 as c
obs=json.loads((c.LOCAL/'work/secondary_r7_observe_20261022.json').read_text(encoding='utf-8'))
s=obs['status'];assert s['status'] in ('simulating','waiting_capacity','launching','analyzing','case_complete')
entry=dict(root='runs/secondary_cap_training_r7_20261022',state='runs/secondary_cap_training_r7_20261022/status.json',
 script='scripts/secondary_cap_training_r7_20261022.py',script_sha256=obs['launch']['script_sha256'],
 launch=obs['launch'],status=s['status'],current_case=s.get('current_case'),completed_cases=s['completed_cases'],
 protocol_sha256=s['protocol_sha256'],frozen_sha256=obs['frozen_sha256'],
 last_observed_utc=obs['observed_utc'],identity=obs['identity'],diagnostic=obs['diagnostic'],
 candidates=[dict(name='baseline_r5',secondary_cap_F=10e-15,TG_width_m=1e-6),dict(name='secondary_c25_w1',secondary_cap_F=25e-15,TG_width_m=1e-6),dict(name='secondary_c25_w2',secondary_cap_F=25e-15,TG_width_m=2e-6)],
 data_seed=2026102202,noise_seed=223,generated_symbols=896,warmup_symbols=256,training_inputs=512,
 fit_inputs=256,fit_FFE_windows=240,internal_guard=16,score_inputs=240,score_FFE_windows=224,
 fit_policy='Candidate-specific noiseless first256 fit only, all3detectors frozen before noise; no phase/lag/range/noise refit.',
 training_only=True,holdout_accessed=False,full_ADC_verified=False,automatic_retry=False,
 observer='python work/control_secondary_r7_20261022.py observe',
 monitoring=dict(automation_id='project-6',status='ACTIVE',interval_minutes=30,routine_notifications=False),
 next='Observe only six fixed cases. Any new failure terminal; preserve evidence and report, no retry. After6 complete verify hashes/exit0/noisefitfalse/224points, compare secondary SER/MSE/clipping/swing/power and FFE L2; report finite training result without fullADC or BER claim; delete heartbeat. No automatic new holdout/candidates.')
remote=c.PRELUDE+'\nentry='+repr(entry)+r'''
original.atomic_json(P/'notes/secondary_r7_handoff_20261022.json',entry)
p=P/'project_status.json';v=json.loads(p.read_text())
v.update(updated_UTC=entry['last_observed_utc'],status='secondary_r7_'+entry['status'],automation_status='ACTIVE',
 automatic_resume_authorized=False,latest_secondary_training=entry,next_action=entry['next'],complete_ADC_verified=False)
original.atomic_json(p,v)
print('VM r7 handoff saved; completed eye roots unchanged.')
'''
cmd=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(c.LOCAL/'work/ssh/vm_pdk_access_ed25519'),'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','HostKeyAlias=192.0.2.1','user@192.0.2.1','python3 -']
r=subprocess.run(cmd,input=remote,text=True,encoding='utf-8',capture_output=True,timeout=30)
if r.returncode:raise RuntimeError(r.stderr or r.stdout)
p=c.LOCAL/'work/project6_r5_handoff.json';h=json.loads(p.read_text(encoding='utf-8'))
h.update(session_status='secondary_r7_training_running',milestone='user_authorized_secondary_noise_cap_comparison',automation_status='ACTIVE',automatic_resume_authorized=False,current_experiment='active_work.secondary_r7_20261022',automation_stop='Observe r7sixcases only; no retries or extra candidates. Delete heartbeat after terminal failure or verified training result delivery.')
h['active_work']['secondary_r7_20261022']=entry
h['monitoring_secondary_r7_20261022']=entry['monitoring']
h['secondary_r7_authorization']='2026-10-22 user answered 繼續背景改善次取樣支路; finite3configx2noise-condition fresh-training study authorized.'
tmp=p.with_suffix('.r7.tmp');tmp.write_text(json.dumps(h,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(p)
print(r.stdout.strip());print('Local r7 handoff saved.')
