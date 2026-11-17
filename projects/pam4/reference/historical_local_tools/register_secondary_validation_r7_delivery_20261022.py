"""Record verified completion after the app confirmed deletion of project-6."""
import datetime
import hashlib
import json
import subprocess

import control_secondary_validation_r7_20261022 as c

delivery_path = c.LOCAL / 'work/secondary_validation_r7_delivery_20261022.json'
delivery_bytes = delivery_path.read_bytes()
d = json.loads(delivery_bytes)
assert d['status'] == 'verified_four_case_independent_validation_complete'
assert d['all_four_exit0'] and d['independent_metrics_recomputed']
assert d['independent_fresh_data'] and not d['validation_fitting_performed']
assert len(d['case_hashes']) == 4 and d['FFE_outputs_per_branch'] == 2032
obs = json.loads((c.LOCAL / 'work/secondary_validation_r7_observe_20261022.json').read_text(encoding='utf-8'))
assert obs['status']['status'] == 'complete'
assert obs['identity']['boot_matches'] and obs['identity']['script_matches']
base = d['results']['noise_baseline_r5']['branches']['secondary']
cand = d['results']['noise_secondary_c25_w2']['branches']['secondary']
comparison = d['same_round_comparison']['noise']['secondary']['ADC_FFE']
conclusion = dict(
    interpretation='Modest observed improvement on this fresh-data independent comparison; secondary path still has substantial symbol errors.',
    baseline_errors=base['ADC_FFE']['errors'], candidate_errors=cand['ADC_FFE']['errors'], symbols=2032,
    baseline_SER=base['ADC_FFE']['SER'], candidate_SER=cand['ADC_FFE']['SER'],
    fewer_errors=comparison['error_reduction_count'],
    relative_error_reduction=comparison['relative_error_reduction'],
    absolute_SER_reduction_percentage_points=-100 * comparison['absolute_SER_change'],
    baseline_MSE=base['ADC_FFE']['MSE_target_units_squared'],
    candidate_MSE=cand['ADC_FFE']['MSE_target_units_squared'],
    relative_MSE_reduction=1-cand['ADC_FFE']['MSE_target_units_squared']/base['ADC_FFE']['MSE_target_units_squared'],
    baseline_raw_FFE_errors=base['raw_FFE']['errors'], candidate_raw_FFE_errors=cand['raw_FFE']['errors'],
    baseline_held_mVpp=base['held_Vpp']*1000, candidate_held_mVpp=cand['held_Vpp']*1000,
    noiseless_secondary_baseline_MSE=d['results']['noiseless_baseline_r5']['branches']['secondary']['ADC_FFE']['MSE_target_units_squared'],
    noiseless_secondary_candidate_MSE=d['results']['noiseless_secondary_c25_w2']['branches']['secondary']['ADC_FFE']['MSE_target_units_squared'],
    all_primary_errors_zero=True, all_noiseless_errors_zero=True, all_clipping_zero=True,
    robust_improvement_or_BER_certified=False, complete_ADC_verified=False,
    limitations=d['limitations'],
    next='Stop after delivering this fixed comparison. No new simulations, candidates, fitting, retries or holdout automatically. Preserve all evidence; further design work requires a new user instruction.',
)
assert all(v['branches']['primary'][mode]['errors'] == 0 for v in d['results'].values() for mode in ('raw_FFE', 'ADC_FFE'))
assert all(v['branches'][point]['clipped_inputs'] == 0 for v in d['results'].values() for point in ('primary', 'secondary'))
assert all(d['results'][name]['branches'][point][mode]['errors'] == 0 for name in ('noiseless_baseline_r5', 'noiseless_secondary_c25_w2') for point in ('primary', 'secondary') for mode in ('raw_FFE', 'ADC_FFE'))

report = 'Project 6：25 fF／2 um 對原版的新資料獨立比較\n\n'
report += '結論：本次新資料顯示小幅改善，但次取樣支路仍有明顯符號錯誤，未達完整 ADC 驗證。\n'
report += '四案正常完成、退出碼均為0；原凍結版本及兩份訓練 detector bytes 不變，沒有重新訓練或重跑。\n'
report += 'data2026102301 / noise251；每案2432輸入符號，2048評分輸入，每支路2032完整17tap FFE輸出。\n'
report += '每組沿用自己在既有訓練資料得到的固定 detector；比較的是完整候選支路與其固定 FFE。\n\n'
report += '配置／條件／支路 | raw FFE 錯誤/2032, SER, MSE | 理想7bit量化+FFE 錯誤/2032, SER, MSE | clipping/2048 | 取樣擺幅mVpp\n'
for name, value in d['results'].items():
    for point, v in value['branches'].items():
        r, a = v['raw_FFE'], v['ADC_FFE']
        report += '{} / {} | {}, {:.4f}%, {:.6f} | {}, {:.4f}%, {:.6f} | {} | {:.4f}\n'.format(name, point, r['errors'], 100*r['SER'], r['MSE_target_units_squared'], a['errors'], 100*a['SER'], a['MSE_target_units_squared'], v['clipped_inputs'], 1000*v['held_Vpp'])
    report += '  本案量測 VDD 功耗：{:.6f} mW\n'.format(value['measured_VDD_mW'])
report += '\n主要比較：有雜訊次支路，理想7bit量化+FFE錯誤235→210/2032，SER 11.56%→10.33%，少25個錯誤，下降1.23百分點，相對少10.64%。\n'
report += '同一指標MSE僅0.470982→0.467304，下降約0.78%；未量化的raw FFE錯誤218→190。\n'
report += '代價：次支路有雜訊擺幅49.47→39.79mVpp；無雜訊MSE 0.020402→0.055235，雖仍為零錯誤，失真增加。每V等效FFE tap L2 649.74→850.12。\n'
report += '主支路在四案均零錯誤，兩組無雜訊次支路也均零錯誤，所有案均無clipping。零觀察錯誤不代表真實錯誤率為零。\n'
report += '本次只能說此批新資料上觀察到改善；只有單一資料序列與單一雜訊seed，重疊FFE窗口相關，不能宣稱穩定改善、顯著性或獨立iid BER達標。\n'
report += '跨硬體使用相同seed不保證同一雜訊實現，也不能當成多份獨立雜訊重複。差值含雜訊引起的動態／非線性變化，不是純元件雜訊分離。\n'
report += '量測VDD約11.968mW不含時脈／偏壓產生、CDAC／參考／控制與DSP，不能說大電容及大TG沒有額外功耗。\n'
report += '理想數值7bit量化器、數值FFE、reset比較器及理想時脈，不代表完整7bit112GS/s ADC；仍需真CDAC、參考、工作比較器、控制與七次相依判決。\n\n'
report += '資料核對：四份原始波形在VM內解析；用固定predict_window重算，另以固定門檻獨立核對錯誤與MSE，與已保存摘要一致。\n'
report += '所有波形、網表、detector、TSV和ViVA資料留VM，既有交付與歷史證據保留。監看排程已停止並刪除；不自動啟動下一輪。\n'
report += '下一步可先學習取樣擺幅、無雜訊失真與FFE雜訊放大之間的取捨；任何新設計或驗證另由使用者決定。\n'

stamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
hpath = c.LOCAL / 'work/project6_r5_handoff.json'
entry = dict(json.loads(hpath.read_text(encoding='utf-8'))['active_work']['secondary_validation_r7_20261022'])
entry.update(status='complete_verified_independent_validation_delivered', current_case=None,
             completed_cases=d['case_hashes'], completed_case_count=4, finished_utc=d['finished_utc'],
             last_observed_utc=obs['observed_utc'], identity=obs['identity'], diagnostic=obs['diagnostic'],
             delivery_receipt='notes/secondary_validation_r7_delivery_20261022.json',
             local_delivery_receipt='work/secondary_validation_r7_delivery_20261022.json',
             conclusion=conclusion, next=conclusion['next'],
             monitor=dict(automation_id='project-6', status='DELETED', interval_minutes=30,
                          routine_notifications=False, closed_utc=stamp))

remote = c.PRELUDE + '\nentry=' + repr(entry) + '\nexpected=' + repr(d) + '\nreport=' + repr(report) + r'''
assert sha(R/'status.json')==expected['status_sha256']
assert sha(R/'protocol.json')==expected['protocol_sha256']
assert sha(P/entry['script'])==expected['script_sha256']
assert sha(original.FROZEN_PATH)==expected['frozen_sha256']
state=json.loads((R/'status.json').read_text())
assert state['status']=='complete' and len(state['completed_cases'])==4 and state['current_case'] is None
launch=json.loads((P/'runs/secondary_cap_validation_r7_20261022_dispatch/launch_receipt.json').read_text())
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==launch['boot_id']
assert not any((x.get('cwd') or '').startswith(str(P)+'/') for x in actual())
live=original.process_record(launch['runner']['pid'])
assert not (live and live['start_ticks']==launch['runner']['start_ticks'])
vm_delivery=P/'notes/secondary_validation_r7_delivery_20261022.json'
assert json.loads(vm_delivery.read_text())==expected
for item in expected['case_hashes']:
 assert sha(R/item['name']/'summary.json')==item['summary_sha256']
for candidate,digest in expected['detector_sha256'].items():
 assert sha(R/(candidate+'_detectors.json'))==digest
report_path=P/'notes/secondary_validation_r7_result_20261022.txt'
if report_path.exists():
 assert report_path.read_text(encoding='utf-8')==report
else:
 with report_path.open('x',encoding='utf-8') as f:f.write(report)
entry['VM_report']='notes/secondary_validation_r7_result_20261022.txt'
entry['VM_report_sha256']=sha(report_path)
original.atomic_json(P/'notes/secondary_validation_r7_handoff_20261022.json',entry)
path=P/'project_status.json';project_status=json.loads(path.read_text())
project_status.update(updated_UTC=now(),status='secondary_r7_independent_validation_delivered',
 automation_status='DELETED',automatic_resume_authorized=False,complete_ADC_verified=False,
 latest_secondary_validation=entry,latest_secondary_validation_delivery='notes/secondary_validation_r7_delivery_20261022.json',
 next_action=entry['next'])
original.atomic_json(path,project_status)
closure=dict(utc=now(),automation_id='project-6',automation_status='DELETED',
 reason='Four fixed independent validation cases passed exit0, hashes, fixed detector bytes and independent rescore; app confirmed monitor deletion.',
 delivery_sha256=sha(vm_delivery),report_sha256=sha(report_path),
 frozen_sha256=expected['frozen_sha256'],protocol_sha256=expected['protocol_sha256'],
 boot_id=launch['boot_id'],own_actual_simulators=0,original_runner_still_active=False,
 conclusion=entry['conclusion'])
original.atomic_json(P/'notes/secondary_validation_r7_monitor_closed_20261022.json',closure)
print(json.dumps(dict(entry=entry,closure=closure)))
'''
command = ['C:/Windows/System32/OpenSSH/ssh.exe', '-i', str(c.LOCAL / 'work/ssh/vm_pdk_access_ed25519'),
           '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=8',
           '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=192.0.2.1',
           'user@192.0.2.1', 'python3 -']
r = subprocess.run(command, input=remote, text=True, encoding='utf-8', capture_output=True, timeout=35)
if r.returncode:
    raise RuntimeError(r.stderr or r.stdout)
receipt = json.loads(r.stdout)
h = json.loads(hpath.read_text(encoding='utf-8'))
h.update(session_status='secondary_r7_independent_validation_delivered',
         milestone='fixed_four_case_independent_validation_verified', updated_date='2026-10-23',
         updated_utc=receipt['closure']['utc'], automation_status='DELETED',
         automatic_resume_authorized=False, complete_ADC_verified=False,
         automation_stop='Four-case independent comparison completed and delivered; project-6 deleted. No automatic further work.')
h['active_work']['secondary_validation_r7_20261022'] = receipt['entry']
h['monitoring_secondary_validation_r7_20261022'] = receipt['entry']['monitor']
h['secondary_validation_r7_final_delivery_20261022'] = dict(
    status=d['status'], local_receipt='work/secondary_validation_r7_delivery_20261022.json',
    local_receipt_sha256=hashlib.sha256(delivery_bytes).hexdigest(),
    VM_receipt='notes/secondary_validation_r7_delivery_20261022.json',
    VM_receipt_sha256=receipt['closure']['delivery_sha256'], conclusion=conclusion)
temp = hpath.with_suffix('.validation_delivery.tmp')
temp.write_text(json.dumps(h, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
temp.replace(hpath)
(c.LOCAL / 'work/secondary_validation_r7_monitor_closed_20261022.json').write_text(
    json.dumps(receipt['closure'], ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(status=h['session_status'], cases=4, automation_status='DELETED',
                     report_sha256=receipt['entry']['VM_report_sha256'], conclusion=conclusion), ensure_ascii=False))
