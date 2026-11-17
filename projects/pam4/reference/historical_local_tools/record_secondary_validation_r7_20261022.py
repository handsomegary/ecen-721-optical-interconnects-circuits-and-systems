"""Record the already-started independent R7 validation; never dispatch work."""
import argparse
import json
import subprocess

import control_secondary_validation_r7_20261022 as c

parser = argparse.ArgumentParser()
parser.add_argument('--automation-id', default='project-6')
parser.add_argument('--monitor-status', choices=('ACTIVE', 'DELETED', 'PENDING'), default='ACTIVE')
args = parser.parse_args()
obs = json.loads((c.LOCAL / 'work/secondary_validation_r7_observe_20261022.json').read_text(encoding='utf-8'))
s = obs['status']
assert s['status'] in ('simulating', 'waiting_capacity', 'launching', 'analyzing', 'case_complete')
assert obs['identity']['boot_matches'] and obs['identity']['script_matches']
assert obs['identity']['start_matches'] and obs['identity'].get('command_matches')
preflight = json.loads((c.LOCAL / 'work/secondary_validation_r7_preflight_20261022.json').read_text(encoding='utf-8'))
entry = dict(
    root='runs/' + c.NAME, state='runs/' + c.NAME + '/status.json',
    script='scripts/' + c.NAME + '.py', script_sha256=obs['launch']['script_sha256'],
    protocol_sha256=obs['launch']['protocol_sha256'], frozen_sha256=obs['frozen_sha256'],
    launch=obs['launch'], identity=obs['identity'], diagnostic=obs['diagnostic'],
    status=s['status'], current_case=s.get('current_case'), completed_cases=s['completed_cases'],
    completed_case_count=len(s['completed_cases']), last_observed_utc=obs['observed_utc'],
    candidates=['baseline_r5', 'secondary_c25_w2'], maximum_simulations=4,
    order='Two noiseless then two noise cases; no retries.', data_seed=2026102301, noise_seed=251,
    generated_symbols=2432, warmup_symbols=256, score_input_symbols=2048, end_guard_symbols=128,
    complete_FFE_outputs_per_branch=2032, fixed_lags=dict(primary=1, secondary=3),
    fixed_quantizer_fullscale_Vpp=dict(primary=.100, secondary=.075),
    source_training_root='runs/secondary_cap_training_r7_20261022',
    source_training_protocol_sha256=preflight['training_protocol_sha256'],
    frozen_candidate_detector_sha256=preflight['detector_sha256'],
    fitting_performed=False, independent_fresh_data=True, automatic_retry=False,
    complete_ADC_verified=False,
    monitor=dict(automation_id=args.automation_id, status=args.monitor_status,
                 interval_minutes=30, routine_notifications=False),
    observer='python work/control_secondary_validation_r7_20261022.py observe',
    limits=dict(case_s=7200, capacity_wait_s=1800, batch_s=43200, minimum_free_bytes=8*1024**3),
    next='Observe only the already-started four cases. Any failure terminal; report and preserve evidence without retry. After four complete verify every exit0, frozen and detector hashes, seeds, 2048inputs/2032outputs, no fitting. Compare only this independent same-round baseline/candidate. Then deliver and delete monitor; no extra candidates or automatic new holdout.',
)
remote = c.PRELUDE + '\nentry=' + repr(entry) + r'''
assert sha(R/'protocol.json')==entry['protocol_sha256']
assert sha(P/entry['script'])==entry['script_sha256']
assert sha(original.FROZEN_PATH)==entry['frozen_sha256']
assert json.loads((R/'status.json').read_text())['status'] not in ('failed_terminal','complete'), 'New terminal state: observe again and record terminal truth'
original.atomic_json(P/'notes/secondary_validation_r7_handoff_20261022.json',entry)
path=P/'project_status.json';v=json.loads(path.read_text())
v.update(updated_UTC=entry['last_observed_utc'],status='secondary_r7_independent_validation_'+entry['status'],
 automation_status=entry['monitor']['status'],automatic_resume_authorized=False,
 complete_ADC_verified=False,latest_secondary_validation=entry,next_action=entry['next'])
original.atomic_json(path,v)
print('VM independent validation handoff saved.')
'''
command = ['C:/Windows/System32/OpenSSH/ssh.exe', '-i', str(c.LOCAL / 'work/ssh/vm_pdk_access_ed25519'),
           '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=8',
           '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=192.0.2.1',
           'user@192.0.2.1', 'python3 -']
result = subprocess.run(command, input=remote, text=True, encoding='utf-8', capture_output=True, timeout=30)
if result.returncode:
    raise RuntimeError(result.stderr or result.stdout)
path = c.LOCAL / 'work/project6_r5_handoff.json'
h = json.loads(path.read_text(encoding='utf-8'))
h.update(session_status='secondary_r7_independent_validation_running',
         milestone='user_authorized_one_fresh_baseline_vs_c25w2_comparison',
         current_experiment='active_work.secondary_validation_r7_20261022',
         updated_utc=obs['observed_utc'], updated_date='2026-10-22',
         automation_id=args.automation_id, automation_status=args.monitor_status,
         automatic_resume_authorized=False,
         automation_stop='Four fixed independent validation cases only, no fitting/retries/extra candidates. Stop and delete monitor after verified delivery or terminal failure.')
h['active_work']['secondary_validation_r7_20261022'] = entry
h['monitoring_secondary_validation_r7_20261022'] = entry['monitor']
h['secondary_validation_r7_authorization'] = '2026-10-22 user: 用25fF/2um跟原版做一次新資料獨立比較，繼續背景跑，半小時檢查一次，崩潰就回報不要自動重跑.'
temp = path.with_suffix('.r7_validation.tmp')
temp.write_text(json.dumps(h, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
temp.replace(path)
print(result.stdout.strip())
print(json.dumps(dict(status=h['session_status'], completed_cases=entry['completed_case_count'],
                     current_case=entry['current_case'], monitor=entry['monitor'])))
