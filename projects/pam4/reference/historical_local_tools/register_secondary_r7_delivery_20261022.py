"""Close the completed finite training screen after confirmed monitor deletion."""
import datetime
import hashlib
import json
import subprocess

import control_secondary_r7_20261022 as c

delivery_path = c.LOCAL / 'work/secondary_r7_delivery_20261022.json'
delivery_bytes = delivery_path.read_bytes()
delivery = json.loads(delivery_bytes)
assert delivery['status'] == 'verified_six_case_training_complete'
assert delivery['all_six_exit0'] and delivery['independent_metrics_recomputed']
assert not delivery['noise_fitting_performed'] and delivery['training_only']
assert len(delivery['case_hashes']) == 6
obs = json.loads((c.LOCAL / 'work/secondary_r7_observe_20261022.json').read_text(encoding='utf-8'))
assert obs['status']['status'] == 'complete'
assert obs['identity']['boot_matches'] and obs['identity']['script_matches']

comparison = []
for name in delivery['candidate_order']:
    n = delivery['comparisons']['noiseless_' + name]
    q = delivery['comparisons']['noise_' + name]
    config = delivery['candidate_configurations'][name]
    comparison.append(dict(
        candidate=name, secondary_cap_fF=config['secondary_cap_F'] * 1e15,
        TG_width_um=config['secondary_switch_width_m'] * 1e6,
        secondary_noiseless_errors=n['branches']['secondary']['ADC_FFE_errors'],
        secondary_noise_errors=q['branches']['secondary']['ADC_FFE_errors'],
        secondary_noise_SER=q['branches']['secondary']['ADC_FFE_SER'],
        secondary_noise_MSE=q['branches']['secondary']['ADC_FFE_MSE'],
        secondary_noise_held_mVpp=q['branches']['secondary']['held_Vpp'] * 1e3,
        primary_noise_errors=q['branches']['primary']['ADC_FFE_errors'],
        measured_VDD_mW=q['measured_VDD_W'] * 1e3,
        secondary_per_V_tap_L2=q['branches']['secondary']['equivalent_per_V_tap_L2'],
    ))

conclusion = dict(
    interpretation='Slight training-screen improvement; secondary path remains unqualified.',
    noisy_secondary_errors_per_224=[x['secondary_noise_errors'] for x in comparison],
    primary_noise_errors_per_224=[x['primary_noise_errors'] for x in comparison],
    preferred_for_possible_future_validation='secondary_c25_w2',
    preference_reason='Same26/224 errors as C25W1, but lowest ADC-FFE MSE. Not an adopted or validated hardware replacement.',
    independent_improvement_established=False,
    complete_ADC_verified=False,
    next='Stop this finite screen. If the user later requests further testing, freeze baseline and C25W2 and predeclare one fresh-data independent comparison; no automatic dispatch, refitting, new candidates or holdout.',
    limitations=[
        'One224-output training selection block and one noise seed; overlapping FFE windows are correlated. Five fewer errors does not establish robust gain or independent BER.',
        'Only compare to this round baseline, not older55/496 or other-data validation counts.',
        'Held swing decreases and equivalent per-V FFE gain increases with added capacitance.',
        'Measured approximately11.97mW VDD excludes clock/bias generation, CDAC/reference/control and digital FFE. Larger capacitance/TG is not demonstrated power-free.',
        'Paired noise-minus-noiseless differences include noise-induced dynamics and nonlinear changes; no pure device-noise decomposition.',
        'Acquisition and final8ps buffer diagnostics use saved banks0/7,60samples; closing-edge diagnostics use240samples.',
        'Ideal numeric7bit quantization, numerical FFE, reset comparators and ideal clocks do not verify a full physical7bit112GS/s ADC.',
    ],
)
stamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
entry = dict(json.loads((c.LOCAL / 'work/project6_r5_handoff.json').read_text(encoding='utf-8'))['active_work']['secondary_r7_20261022'])
entry.update(
    status='complete_verified_training_delivered', current_case=None,
    completed_cases=delivery['case_hashes'], completed_case_count=6,
    finished_utc=delivery['finished_utc'], last_observed_utc=obs['observed_utc'],
    identity=obs['identity'], diagnostic=obs['diagnostic'],
    delivery_receipt='notes/secondary_r7_delivery_20261022.json',
    local_delivery_receipt='work/secondary_r7_delivery_20261022.json',
    numerical_comparison=comparison, conclusion=conclusion, next=conclusion['next'],
    monitoring=dict(automation_id='project-6', status='DELETED', interval_minutes=30,
                    routine_notifications=False, closed_utc=stamp),
)

remote = c.PRELUDE + '\nentry=' + repr(entry) + '\nconclusion=' + repr(conclusion) + '\nexpected=' + repr(delivery) + r'''
assert sha(R/'status.json') == expected['status_sha256']
assert sha(R/'protocol.json') == expected['protocol_sha256']
assert sha(original.FROZEN_PATH) == expected['frozen_sha256']
state=json.loads((R/'status.json').read_text())
assert state['status']=='complete' and len(state['completed_cases'])==6 and state['current_case'] is None
launch=json.loads((R/'launch_receipt.json').read_text())
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==launch['boot_id']
assert not any((x.get('cwd') or '').startswith(str(P)+'/') for x in actual())
live=original.process_record(launch['runner']['pid'])
assert not (live and live['start_ticks']==launch['runner']['start_ticks']), 'Runner unexpectedly still active'
vm_delivery=P/'notes/secondary_r7_delivery_20261022.json'
assert json.loads(vm_delivery.read_text())==expected
for item in expected['case_hashes']:
 assert sha(R/item['name']/'summary.json')==item['summary_sha256']

report='Project 6 次取樣支路 r7：固定六案訓練篩選結果\n'
report+='六案全部退出碼0，原r5凍結版本不變，三組detector在有雜訊測試前固定；無新增holdout。\n'
report+='每組256個無雜訊輸入訓練17tap FFE，隔16符號後評分224個完整輸出；data2026102202/noise223。\n\n'
report+='次支路配置（每側） | 無雜訊錯誤/224 | 有雜訊錯誤/224 | SER | MSE | 有雜訊擺幅mVpp | 量測VDD mW\n'
for row in entry['numerical_comparison']:
 report+='{:.0f}fF/{:.0f}um | {} | {} | {:.2f}% | {:.3f} | {:.2f} | {:.5f}\n'.format(row['secondary_cap_fF'],row['TG_width_um'],row['secondary_noiseless_errors'],row['secondary_noise_errors'],row['secondary_noise_SER']*100,row['secondary_noise_MSE'],row['secondary_noise_held_mVpp'],row['measured_VDD_mW'])
report+='\n主支路在三組有雜訊測試都是0/224，所有無雜訊兩支路皆0/224，沒有clipping。\n'
report+='基準31次錯誤，兩個25fF候選都是26次。25fF/2um的MSE最低，但仍約11.6%符號錯誤，次支路尚未合格。\n'
report+='若未來繼續，最多值得先凍結基準與25fF/2um，預先規劃一次新資料獨立比較；本輪沒有自動加跑。\n\n'
report+='判讀限制：\n'
report+='這是單一種子的訓練篩選，FFE窗口相關，少5個錯誤不能證明穩定改善或BER達標。\n'
report+='增加電容同時讓擺幅變小、每V等效FFE增益提高，沒有單憑這輪證明純熱雜訊改善。\n'
report+='量測VDD約11.97mW排除時脈/偏壓產生、CDAC/參考/控制與數位FFE，不能說加大開關沒有功耗代價。\n'
report+='noise-noiseless差值包含雜訊引起的動態/非線性差異；banks0/7建立診斷只有60點。\n'
report+='理想數值量化器、數值FFE與reset比較器不是完整7bit112GS/s ADC；仍須真CDAC、參考、工作比較器、控制與七次相依判決。\n\n'
report+='下一課：在既有ViVA取樣相位掃描眼圖對照主/次支路群集與固定門檻，理解為何無雜訊可分、有雜訊卻重疊；本輪沒有重建或操作GUI。\n'
report+='所有原始波形、決策TSV、detector和既有相位眼圖資料留VM，未清除或匯出。本輪監看已停止並刪除。\n'
report_path=P/'notes/secondary_r7_result_and_learning_20261022.txt'
if report_path.exists():
 assert report_path.read_text(encoding='utf-8')==report
else:
 with report_path.open('x',encoding='utf-8') as f:f.write(report)
entry['VM_report']='notes/secondary_r7_result_and_learning_20261022.txt'
entry['VM_report_sha256']=sha(report_path)
original.atomic_json(P/'notes/secondary_r7_handoff_20261022.json',entry)
status_path=P/'project_status.json';status=json.loads(status_path.read_text())
status.update(updated_UTC=now(),status='secondary_r7_training_delivered',automation_status='DELETED',
 automatic_resume_authorized=False,complete_ADC_verified=False,latest_secondary_training=entry,
 latest_secondary_delivery='notes/secondary_r7_delivery_20261022.json',next_action=conclusion['next'])
original.atomic_json(status_path,status)
closure=dict(utc=now(),automation_id='project-6',automation_status='DELETED',
 reason='Fixed6case training screen complete, every exit0/hash/recomputed metrics verified. No further authorized dispatch.',
 delivery_sha256=sha(vm_delivery),report_sha256=sha(report_path),
 frozen_sha256=sha(original.FROZEN_PATH),boot_id=launch['boot_id'],own_actual_simulators=0,
 original_runner_still_active=False,numerical_comparison=entry['numerical_comparison'],conclusion=conclusion)
original.atomic_json(P/'notes/secondary_r7_monitor_closed_20261022.json',closure)
print(json.dumps(dict(entry=entry,closure=closure)))
'''
cmd = ['C:/Windows/System32/OpenSSH/ssh.exe', '-i', str(c.LOCAL / 'work/ssh/vm_pdk_access_ed25519'),
       '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=8',
       '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=192.0.2.1',
       'user@192.0.2.1', 'python3 -']
result = subprocess.run(cmd, input=remote, text=True, encoding='utf-8', capture_output=True, timeout=35)
if result.returncode:
    raise RuntimeError(result.stderr or result.stdout)
receipt = json.loads(result.stdout)
entry = receipt['entry']
hpath = c.LOCAL / 'work/project6_r5_handoff.json'
h = json.loads(hpath.read_text(encoding='utf-8'))
h.update(session_status='secondary_r7_training_delivered',
         milestone='fixed_six_case_secondary_training_verified', updated_date='2026-10-22',
         updated_utc=receipt['closure']['utc'], automation_status='DELETED',
         automatic_resume_authorized=False, complete_ADC_verified=False,
         automation_stop='Completed fixed6case training study; project-6 deleted. No automatic new candidates or holdout.',
         VM='user@192.0.2.1')
if 'HostKeyAlias=192.0.2.1' not in h['SSH_options']:
    h['SSH_options'].append('HostKeyAlias=192.0.2.1')
h['active_work']['secondary_r7_20261022'] = entry
h['monitoring_secondary_r7_20261022'] = entry['monitoring']
h['secondary_r7_final_delivery_20261022'] = dict(
    status=delivery['status'], local_receipt='work/secondary_r7_delivery_20261022.json',
    local_receipt_sha256=hashlib.sha256(delivery_bytes).hexdigest(),
    VM_receipt='notes/secondary_r7_delivery_20261022.json',
    VM_receipt_sha256=receipt['closure']['delivery_sha256'],
    numerical_comparison=comparison, conclusion=conclusion,
)
temp = hpath.with_suffix('.r7_delivery.tmp')
temp.write_text(json.dumps(h, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
temp.replace(hpath)
(c.LOCAL / 'work/secondary_r7_monitor_closed_20261022.json').write_text(
    json.dumps(receipt['closure'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('VM and local final handoffs saved; monitor DELETED; six completed cases retained.')
print(json.dumps(dict(status=h['session_status'], cases=6, noisy_secondary_errors=[x['secondary_noise_errors'] for x in comparison],
                     report_sha256=entry['VM_report_sha256'], automation_status='DELETED')))
