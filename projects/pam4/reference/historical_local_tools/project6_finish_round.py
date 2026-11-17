import datetime
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
out = root / 'outputs'
handoff = root / 'work/project6_r5_handoff.json'
h = json.loads(handoff.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
summary = {
    'status': 'bounded_round_closed_noise_interrupted',
    'complete_ADC_verified': False,
    'PAM4_conditions': 'TT,25C,0.9V;112Gbaud PAM4;20dB channel at56GHz;0.4Vppd transmitter',
    'frozen_sha256': '4cda4c9ec967f2af4bf4f89eacdd1beae372668877c358cf6aa26092597482eb',
    'r5_noiseless_holdout': {
        'input_symbols': 2048, 'FFE_windows': 2032, 'data_seed': 2026101302,
        'fitting_performed': False, 'ideal7bit_FFE_errors_primary_secondary': [0, 2],
        'unquantized_FFE_errors_primary_secondary': [0, 0],
        'held_mVppd': [90.50758454, 50.63726773], 'quantizer_fullscale_mVpp': [100, 75],
        'clipped_counts': [0, 0], 'modeled_VDD_mW': 11.9683200676,
        'summary_sha256': 'ff8a466c80549cc476e8c768e56aea64cdab4ed4abb8a6b5d2709769519f716f',
    },
    'r5_noise': {
        'status': 'interrupted_by_VM_power_cycle', 'performance_result': None,
        'noise_seed': 173, 'last_partial_write_UTC': '2026-10-13T17:36:21.893045Z',
        'partial_files_preserved': 8,
        'partial_summary_sha256': 'ba3c4625a91c9483c1053d6877895f1cd2ed48920b4970fd51e29eaee8b4bbfa',
        'terminal_receipt_sha256': '67685952f7d820c2bea5fcda9fc0a3133261102daf503f92bf81dde5334d3719',
    },
    'r6_r6b_training': {
        'data_seed': 2026101303, 'noise_seed': 181, 'selection_windows': 224,
        'r6_new_candidates_passing_gain_gate': 0,
        'r6b_noiseless_secondary_errors': [0, 0, 0],
        'noise_secondary_errors_baseline_selected': [14, 23],
        'noise_VDD_mW_baseline_selected': [11.9668304, 15.715749863],
        'selected_adopted': False,
        'r6_summary_sha256': '28f8cb0daccfef041212ad0d6df1506cc6ca3f54269c70c35e626e96ec3bf20d',
        'r6b_summary_sha256': 'c86f65e98af878baba356315adf1457add7e5749e250c173265aae89e2980855',
    },
    'native_split_CDAC': {
        'acquisition_fixture': 'Noiseless;50ohm input surrogate;one native CDAC branch;other seven 10fF loads;comparators reset',
        'TG1_TG2_acquisition_RMS_mV': [0.779606, 0.404355],
        'TG1_TG2_acquisition_peak_mV': [1.60707, 0.829912],
        'TG1_TG2_hold_peak_drift_mV': [0.754216, 0.625832],
        'half_LSB_at_100mVpp_7bit_mV': 0.390625,
        'independent_step_top_settle_ps': 41.42,
        'acquisition_summary_sha256': '30a4c89deaef2292054d531e76cbb5ec16183ac0994b0a0d1f22ee0ef0082983',
        'step_summary_sha256': '946d203168196025531d8eafabaf98a20edd2a4fa9c6241ac0b681ba638ed5b0',
    },
    'limitations': 'Training is not holdout; unquantized FFE still uses equalization. Quantized/unquantized branches use different frozen FFEs. PAM4 uses numerical ADC with reset comparators; power excludes conversion and clock/bias/reference/control/DSP generators. CDAC steps are independent, not seven dependent SAR decisions. Interrupted noise is neither a performance pass nor fail.',
}
report = '''Project 6 — 28nm LVT：本輪結論與數值
2026-10-13；完整實體 ADC 尚未驗證。

結論
這組 MOS 值得用於前端、取樣器及 CDAC 分塊研究；目前這套電路不足以承諾完整 7 bit、112 GS/s 的 Project 6 達標。16.6 GHz 是特定負載电路的 −3 dB 頻寬，不是 MOS 本身的速度上限。這輪證明了部分電路可以工作，也找出取樣誤差、雜訊與連續判決的瓶頸，沒有證明整個製程不可行。

VM 與驗證狀態
已依 continue 恢復原本暫停的 VM；恢復前 D 槽可用空間約 62.47 GB。連線後確認為新的 guest boot，舊模擬程序均已不存在。r5 有雜訊驗證最後資料寫入於 10/13 12:36:21 CDT，沒有 Spectre 正常完成標記，摘要仍為 generated_only。8 個中斷檔案留在 VM 原位置，原流程與專案狀態已另存紀錄；未將中斷當作性能失敗或通過。
依本輪有界測試範圍，不再自動重跑或追加候選；Project 6 接續排程保持暫停。VM 本身已恢復運作。

1. 凍結 r5：新資料無雜訊驗證
條件：112 Gbaud PAM4、56 GHz 處 20 dB 損耗通道、發送端 0.4 Vppd、TT／25°C／0.9 V。2048 個新資料符號形成 2032 個完整 FFE 窗口；硬體、量化範圍與 FFE 均沿用凍結設定，未用 holdout 擬合。
理想 7 bit 量化加 17 tap FFE：主取樣端 0/2032、次取樣端 2/2032 符號錯誤（次級 SER 0.0984%）。兩級擺幅 90.51／50.64 mVppd，量化滿幅 100／75 mVpp，均未裁切；模型內 VDD 功耗 11.968 mW。
未量化的 FFE 分支兩級均為 0/2032，但兩分支 FFE 不同，不能把差異單獨歸因於量化。0/2032 也不代表零 BER。配對雜訊驗證未完成，因此目前沒有本版新資料的完整雜訊結論。

2. 固定 r6／r6b 比較
r6 三個新候選均未達預定緩衝增益門檻 0.8 V/V；最接近者為 0.7884 V/V。
r6b 三組無雜訊訓練的主、次取樣端均為 0/224。按預定評分選出的 input2_r400_bias060，在含雜訊訓練中次級為 23/224（10.27%），原版為 14/224（6.25%）；功耗 15.716 對 11.967 mW，增加約 31%。不支持採用這個 r6b 候選取代原版。
以上是 512 符號內的訓練篩選，各條件獨立選 FFE、延遲與範圍，不是獨立 holdout。相同種子不保證不同硬體有完全相同的類比雜訊實現；另外兩組 r6b 未做雜訊測試。

3. 真實 CDAC 與比較器
CML 驅動原生 split CDAC、主開關從 1 加大到 2 µm：追蹤落差 RMS 0.780→0.404 mV，最大 1.607→0.830 mV；保持期間最大漂移 0.754→0.626 mV。仍超過假設 CDAC 輸入滿幅 100 mVpp 時的半 LSB 預算 0.391 mV。此測試使用 50 Ω 輸入替代源、單一 CDAC 支路、reset 比較器且無雜訊；上游满幅需先換算路徑增益。
split 4+3 CDAC 的獨立位元步階推算 DNL／INL 約 0.0313／0.0289 LSB；經端點正規化的半 LSB 門檻下，最慢頂板建立約 41.42 ps。這不是完整逐碼線性度或七次相依 SAR 決策。
比較器較長窗口可判對 32/32，但短 reset 的連續判決尚未全過；較佳理想輸入固定測試在 48 ps 內為 28/32 正確、4 次未完成。

4. 56 GHz 與功耗的實際意義
固定取樣開關、64 個比較器 reset 的 AC 測試，較小 CML 介面造成的第一級 56 GHz 額外損失約 0.29–0.56 dB；總靜態功耗約 11.07–11.87 mW。這是負載影響，不等於整個接收器的絕對增益，也不是時鐘運作中完整 ADC 的頻寬。
本報告的 PAM4 量化器仍是數值模型。上述 12–16 mW 級功耗不含真實 ADC 轉換，以及時鐘、偏壓、參考、控制與 DSP 產生器，不能當作完整系統功耗。

下一步建議
若繼續投入，先取得凍結條件下不中斷的配對雜訊結果，再處理 CDAC 取樣誤差和比較器短 reset；接著做一個具真實 CDAC、參考、控制與七次相依判決的 ADC 通道，再驗證交錯取樣。改設計後使用新的 holdout 資料。最後仍須 PN skew、時鐘抖動、PVT／mismatch 與版圖寄生驗證。這些是後續範圍，這輪未新增執行。

資料與稽核
Project6_ADC_r5_block_summary.json：既有 62,049 bytes 分塊摘要，保持原檔不變。
Project6_ADC_round_terminal_summary.json：本輪訓練／holdout／CDAC 數值及原始結果 SHA256。
VM 中斷紀錄：notes/r5_noise_terminal_20261013/receipt.json；模型、元件卡、網表與波形均留在 VM。/path/to/local/cadence-home/pdk_probe 已依先前指示刪除。
'''
report = report.replace('电路', '電路').replace('满幅', '滿幅')
jpath = out/'Project6_ADC_round_terminal_summary.json'
tpath = out/'Project6_ADC_r5_進度與判讀.txt'
jbytes = (json.dumps(summary, ensure_ascii=False, separators=(',', ':'))+'\n').encode()
tbytes = report.encode()
existing = out/'Project6_ADC_r5_block_summary.json'
assert sha(existing) == '5832a5489e05ba0110c96ceaaed0b7b8f761b35db4553fd22a641180299312ff'
total = existing.stat().st_size + len(jbytes) + len(tbytes)
assert total <= 70000, total
jpath.write_bytes(jbytes)
tpath.write_bytes(tbytes)
now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
h['milestone'] = 'bounded_r5_r6_r6b_native_CDAC_round_closed_noise_interrupted'
h['session_status'] = 'VM_resumed_round_closed_no_active_simulation'
h['automatic_resume_authorized'] = False
h['automation_status'] = 'PAUSED'
h['complete_ADC_verified'] = False
h['last_heartbeat_update_UTC'] = now
h['current_progress_report'] = {'path': str(tpath.relative_to(root)), 'bytes': len(tbytes), 'sha256': sha(tpath), 'combined_summary_bytes': total}
h['terminal_summary'] = {'path': str(jpath.relative_to(root)), 'bytes': len(jbytes), 'sha256': sha(jpath), 'VM_receipt': 'notes/r5_noise_terminal_20261013/receipt.json', 'VM_receipt_sha256': summary['r5_noise']['terminal_receipt_sha256'], 'status': summary['status']}
h['active_work']['PAM4_training']['validation_noise_result'] = summary['r5_noise']
h['active_work']['PAM4_training']['next'] = 'Bounded round closed. No automatic retries. Full physical ADC remains unverified; any further experiments require a new explicit scope.'
h['active_work']['resume_pipeline'].update(stage='interrupted_by_VM_power_cycle', current_observation='New boot c0a881ae-b1e7-4b6a-9093-112dcebd35dc; no owned workers/simulators; stale running state snapshotted and marked terminal in VM.', active_pid=None)
h['pending_VM_sync'] = {'report': str(tpath.relative_to(root)), 'summary': str(jpath.relative_to(root))}
handoff.write_text(json.dumps(h, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'total_summary_bytes': total, 'report_bytes':len(tbytes), 'terminal_summary_bytes':len(jbytes), 'report_sha256':sha(tpath), 'terminal_summary_sha256':sha(jpath)}))
