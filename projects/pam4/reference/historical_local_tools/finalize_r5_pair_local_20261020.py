import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'work';O=ROOT/'outputs'
e=json.loads((W/'paired_r5_evidence_20261020.json').read_text())
sha=lambda b:hashlib.sha256(b).hexdigest()
report_path=O/'Project6_ADC_r5_進度與判讀.txt'
terminal_path=O/'Project6_ADC_round_terminal_summary.json'
hpath=W/'project6_r5_handoff.json'
old=json.loads(terminal_path.read_text())
def compact_pair(pair):
    b=[pair['branches'][p] for p in ('primary','secondary')]
    return dict(
        status=pair['status'],input_symbols=2048,FFE_windows=2032,
        data_seed=pair['fresh_holdout_seed'],noise_seed=pair['noise_seed'],
        fitting_performed=False,frozen_unchanged=True,
        ideal7bit_FFE_errors_primary_secondary=[x['ideal7bit_ADC_then_FFE']['symbol_errors'] for x in b],
        ideal7bit_FFE_SER=[x['ideal7bit_ADC_then_FFE']['SER'] for x in b],
        gray_bit_errors=[x['ideal7bit_ADC_then_FFE']['gray_bit_errors'] for x in b],
        scored_bits=4064,
        gray_BER=[x['ideal7bit_ADC_then_FFE']['gray_BER'] for x in b],
        unquantized_FFE_errors_primary_secondary=[x['raw_held_FFE_before_ADC']['symbol_errors'] for x in b],
        held_mVppd=[x['held_Vppd']*1000 for x in b],
        quantizer_fullscale_mVpp=[x['fullscale_Vpp']*1000 for x in b],
        clipped_counts=[x['clipped_input_count'] for x in b],
        modeled_VDD_mW=pair['modeled_VDD_mW'],
        noise_conditions=pair['noise_conditions'],
        simulator_exit_code=pair['run_status']['exit_code'],
        simulator_seconds=pair['run_status']['seconds'],
        summary_sha256=pair['summary_sha256'],
        raw_transient_sha256=pair['raw_transient_sha256'])
terminal={k:old[k] for k in ('complete_ADC_verified','PAM4_conditions',
                            'frozen_sha256','r6_r6b_training','native_split_CDAC')}
terminal.update(status='bounded_round_complete_paired_noise_validation',
                r5_noiseless_holdout=compact_pair(e['pairs']['noiseless']),
                r5_noise=compact_pair(e['pairs']['noise']),
                completed_UTC=e['ended_UTC'],
                retry2_state_sha256=e['state_sha256'],
                retry2_wrapper_sha256=e['wrapper_sha256'],
                noise_spectre_log_sha256=e['noise_spectre_log_sha256'],
                noise_deck_sha256=e['pairs']['noise']['deck_sha256'],
                execution_history='10/13 VM interruption;10/17 and first10/20 read-in SPECTRE-18;10/20 retry2 completed. Same frozen design/data/noise seed, not additional independent holdouts. Prior failure root cause remains unknown.',
                limitations='One noise seed,TT25C0.9V,schematic. No holdout fitting. Numerical7bit ADC and reset comparators,not a complete physical converter. Quantized/unquantized paths use different frozen FFEs. Held swing is not RMS noise. VDD excludes conversion and clock/bias/reference/control/DSP generators. CDAC steps are independent,not seven dependent SAR decisions.')
report='''Project 6 — 28nm LVT：配對驗證完成與可行性判斷
2026-10-20 更新；完整實體 ADC 尚未驗證。

結論
這組 MOS 值得用於高速前端與取樣電路研究，但目前這版整體接收鏈不適合直接投入完整 Project 6 ADC。新資料測試的主取樣端可工作，次取樣端加入雜訊後錯誤大增；先解決次級鏈路的建立誤差與雜訊敏感度，再整合實體 ADC。這沒有證明 28nm 製程本身做不到 56 GHz。

1. 凍結 r5 配對新資料驗證
條件：TT／25°C／0.9 V、112 Gbaud PAM4、56 GHz 處 20 dB 損耗通道、發送端 0.4 Vppd。硬體、量化範圍及 17 tap FFE 均凍結，未用驗證資料擬合。資料種子 2026101302；每支路 2048 輸入，2032 完整 FFE 窗口。

                        無雜訊          有雜訊
主取樣端符號錯誤        0/2032          0/2032
次取樣端符號錯誤        2/2032          164/2032
次取樣端 SER            0.0984%         8.0709%
次取樣端 Gray 位元錯誤  2/4064          164/4064
次取樣端 Gray BER       0.0492%         4.0354%
主／次擺幅 mVppd        90.51／50.64     90.61／52.38
模型內 VDD 功耗 mW      11.9683         11.9684

以上錯誤率使用理想 7 bit 量化器加凍結 FFE。滿幅 100／75 mVpp，兩條件均無輸入裁切。雜訊種子 173，noisefmin=500 MHz、noisefmax=150 GHz；只有這一個雜訊實現，0/2032 不代表零 BER 或長期達標。
未量化但有 FFE 的分支：主端兩條件皆 0/2032；次端無雜訊 0/2032、有雜訊 156/2032。量化與未量化分支使用各自凍結的 FFE，不能將 164 與 156 的差異單獨歸因於量化。擺幅是觀測極值，不是輸入等效 RMS 雜訊。

2. 本次執行與記憶體
retry2 於美國中部時間 10/20 10:59 啟動、12:08 完成；Spectre 4139.794 秒（約 69 分鐘），exit 0、0 errors、3 warnings，峰值約 128 MB。本專案已無模擬工作。先前兩次讀入崩潰與中斷紀錄完整保留；本次成功不等於已定位或修復先前根因。這是相同凍結設定、資料及種子的重試，不是額外獨立 holdout。

3. 已完成的 r6／r6b 與實體 CDAC
r6 三個新候選均未達緩衝增益 0.8 V/V 門檻，最高 0.7884。r6b 選定候選的含雜訊次級訓練錯誤 23/224，原版 14/224；功耗 15.716 對 11.967 mW，增加約 31%，不採用。這是訓練篩選，不是新資料驗證。
CML 驅動原生 split CDAC、主開關 1→2 µm：取樣落差 RMS 0.780→0.404 mV，最大 1.607→0.830 mV；保持漂移最大 0.754→0.626 mV。仍超過 100 mVpp、7 bit 的半 LSB 0.391 mV。條件是 50 Ω 替代輸入、單一實體 CDAC 支路、其餘七支路 10 fF、reset 比較器且無雜訊。
split 4+3 CDAC 獨立步階推算 DNL／INL 約 0.0313／0.0289 LSB，端點正規化半 LSB 建立最慢 41.42 ps；不是七次相依 SAR 決策。較佳理想輸入比較器短 reset 測試在 48 ps 內 28/32 正確、4 次未完成。

4. 下一步與限制
目前不建議把「完整 7 bit、112 GS/s ADC 已可達成」當作專題前提。若繼續，先針對次級取樣／緩衝鏈做有限範圍的建立時間、雜訊與增益配置診斷；改設計後另用新資料驗證，再做真實 CDAC、參考、控制及七次相依判決的單通道，最後交錯整合。
此輪只有標稱條件與原理圖模型，尚缺 PVT／mismatch、抖動、PN skew、版圖寄生與完整時鐘。約 12 mW 不含 ADC 轉換及時鐘、偏壓、參考、控制與 DSP 產生器。reset 比較器與理想量化器不能證明完整 ADC 達標。本輪已結束，不追加候選或重試。

資料
Project6_ADC_round_terminal_summary.json 保存配對結果、訓練／CDAC 摘要與雜湊；62,049 bytes 的既有 block summary 保持不變。VM 最新紀錄 notes/r5_pair_complete_20261020.json。模型、元件卡、網表與原始波形留在 VM。
'''
rb=report.encode('utf-8')
tb=(json.dumps(terminal,ensure_ascii=False,separators=(',',':'))+'\n').encode()
block=O/'Project6_ADC_r5_block_summary.json'
assert sha(block.read_bytes())=='5832a5489e05ba0110c96ceaaed0b7b8f761b35db4553fd22a641180299312ff'
total=block.stat().st_size+len(rb)+len(tb)
assert total<=70000, (total,len(rb),len(tb))
backup=W/'paired_finalization_20261020';backup.mkdir(exist_ok=True)
for path in (report_path,terminal_path,hpath):
    dest=backup/(path.name+'.before')
    if not dest.exists():dest.write_bytes(path.read_bytes())
report_path.write_bytes(rb);terminal_path.write_bytes(tb)
h=json.loads(hpath.read_text(encoding='utf-8'))
now=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
retry=h['active_work']['r5_noise_retry2_20261020']
retry.update(status='complete',stage='noise_validation_complete',ended_UTC=e['ended_UTC'],
             state_sha256=e['state_sha256'],exit_code=0,child=None,owned_workers_remaining=[],
             summary_sha256=e['pairs']['noise']['summary_sha256'],
             log_sha256=e['noise_spectre_log_sha256'],
             simulator_seconds=4139.794,performance_result=terminal['r5_noise'],
             next='Bounded round complete; no further automatic simulations. Secondary path remains unsuitable for complete receiver claim.')
h['active_work']['PAM4_training']['validation_noise_result']=terminal['r5_noise']
h['active_work']['PAM4_training']['next']=retry['next']
h.update(updated_date='2026-10-20',session_status='bounded_round_complete_paired_validation',
         milestone='bounded_round_complete_paired_validation',automatic_resume_authorized=False)
h['monitoring_retry2']['last_observation']=json.loads((W/'retry2_observation_20261020.json').read_text())
h['paired_validation_complete']=dict(evidence_local='work/paired_r5_evidence_20261020.json',
    evidence_sha256=sha((W/'paired_r5_evidence_20261020.json').read_bytes()),
    no_holdout_fitting=True,complete_ADC_verified=False,observed_UTC=e['observed_UTC'],
    report_local=str(report_path),terminal_summary_local=str(terminal_path))
h['current_progress_report'].update(bytes=len(rb),sha256=sha(rb),combined_summary_bytes=total,VM_sync_complete=False)
h['terminal_summary'].update(bytes=len(tb),sha256=sha(tb),latest_VM_receipt='notes/r5_pair_complete_20261020.json')
h['pending_VM_sync']='Final paired validation note and numerical report; then pause monitoring.'
h['last_health_check']=dict(observed_UTC=e['observed_UTC'],boot_id=e['boot_id'],
    stage='paired_validation_complete',owned_simulations=0,owned_workers=[],
    action='Completed with exit0; original frozen design verified; no new jobs.')
hpath.write_text(json.dumps(h,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
payload=dict(updated_UTC=now,evidence=e,combined_output_bytes=total,
    files={'notes/ADC_r5_progress_20261013_zh_TW.txt':base64.b64encode(rb).decode(),
           'results/Project6_ADC_round_terminal_summary.json':base64.b64encode(tb).decode()})
(W/'paired_final_payload_20261020.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(combined_bytes=total,report_bytes=len(rb),terminal_bytes=len(tb),
                     report_sha256=sha(rb),terminal_sha256=sha(tb))))
