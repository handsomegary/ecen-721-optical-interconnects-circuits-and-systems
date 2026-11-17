Stage: SAR7 case22 固定輸入核心能力診斷 sar7_22_tt_core_sentinels（非ADC通過版本）
Status: done
Decision: PROCEED（給Codex判讀）— 現有核心在固定輸入下5mV控制56/56、±1LSB 14/14於44ps raw正確且穩定到60ps；支持「case21缺值主要來自比較期間的輸入歷史」而非核心固定sub-mV能力不足
Summary: job 761764 COMPLETED 6:00（solver 327s, RSS 244MiB, raw 120MB），control_valid=true，reset 84/84、actual input 84/84；ADC screen N/A
Run paths: ~/ecen720_28nm/runs/pam4_sar7_core_sentinels_20261117.AXuLHB（summary sar7_core_sentinels_summary.json SHA e5f8635a27f1e68a67f32499340ccf4cc3e43cb43c7242a1894235450bdb1d82）；OneDrive outputs/PAM4_SAR7_CORE_SENTINELS_20261117_RESULTS/（22檔，SHA256SUMS.txt核對通過）
Commit: 見下方（handoff + results）
Needs user decision: no

## 執行
- Inbox 20261117T0826_sar7_core_sentinels.md；ZIP SHA b97915740e27560c5fd4b0c4a62e779edeb6e76408b0a37c40058b3ad4637084 相符。
- 新mktemp root `pam4_sar7_core_sentinels_20261117.AXuLHB`；sha256sum -c 8/8 OK；verify rc0（portable deck 4ede1645…8fb7）；unittest 31/31 OK。
- approval-template manifest 7ad4e96b…0473，只改 approved false→true（diff 僅一行）。stage rc0。
- 精確deck diff vs case20 bench：7個XCMP前兩輸入改接diag_p/diag_n、新增V_DIAG_P/V_DIAG_N兩個PWL、save列 143→145（只加diag_p diag_n，原序保留）；其餘無差異。case.json input_patch_counts {7,2,2,1}。
- 環境：source case20 env_b2_local_drive.sh（含PAM4_PDK_ROOT、PAM4_SAR7_B2_LOCAL_DRIVE_PACKAGE），加三個CORE_SENTINELS變數；直接sbatch套件的 sar7_core_sentinels.sbatch（保留其 --signal=B:TERM@60 與 EXIT restore trap）。
- C2 lease：begin 14:28:58Z，761525 throttle 5→4 begin_verified（lease 7c7ee757…）；status --require-active OK。sbatch 一次 → 761764，pending (QOSMaxCpuPerUserLimit) 到 14:52Z 一個C2槽空出才開跑。
- EXIT restore：event `restore_verified` 14:58:01Z，throttle=5；scontrol 現顯示 ArrayTaskId=21-94%5。C2 其他內容/score/seed未動，未取消任何job。

## 結果（84筆，判準20/80 rail，延遲為「保持到+60ps」的最早觀察點）
| 群組 | n | raw 原read | raw 44ps | raw 48ps | raw 60ps |
|---|---:|---:|---:|---:|---:|
| 預置 ±5mV | 42 | 42/42 | 42/42 | 42/42 | 42/42 |
| target ±5mV | 14 | 14/14 | 14/14 | 14/14 | 14/14 |
| ±1LSB (0.78125mV) | 14 | 12/12可用（2缺值） | 14/14 | 14/14 | 14/14 |
| nearzero ±48.8µV | 14 | 1/2可用 | 1/1可用 | 1/2可用 | 13/14（1錯） |

- 56筆強控制：raw stable-correct by 44ps 56/56，reset 56/56，input 56/56 → 控制有效。
- 原read延遲依core為 37/40/44/47/48ps（b6=37ps）。±1LSB的兩筆原read缺值都是 b6 core（37ps read，raw稍後39.4/39.5ps才穩定）；其餘12筆原read正確。

穩定到達延遲 (ps, min/med/max)：
| 群組 | internal xy | raw q | qmid | qdecode | raw−xy |
|---|---|---|---|---|---|
| 5mV（target+預置56） | 29.8/30.0/30.3 | 32.5/32.7/33.0 | 38.2/38.4/46.0 | 41.7/42.2/46.0 | 2.5–2.75 |
| ±1LSB | 36.8/37.6/38.9 | 38.5/39.3/40.4 | 44.0/44.8/50.3 | 47.3/48.5/52.8 | 1.5–2.0 |
| nearzero（13/14有值） | 42.2/48.7/50.1 | 43.5/49.7/51.1 | 48.5/54.6/55.8（11/14） | 52.5/57.3/58.6（11/14） | 0.75–1.25 |

- internal→raw 只差約2ps；raw→qmid 約+5–6ps、→qdecode 再+3–4ps。±1LSB 的 qmid/qdecode 在44ps多半尚未到rail（qmid 44ps 1/1可用、48ps 12/12；qdecode 48ps 3/3可用、60ps 14/14）。
- 由5mV→1LSB→48.8µV 延遲 32.6→39.3→49.7ps，約每ln倍數3.6–3.8ps，符合單一再生時間常數，無異常飽和。
- nearzero 唯一錯誤：cycle1、b0 core、−48.8µV → raw/xy 判為正（60ps rail）。代表該core在此條件下等效offset/殘留歷史 > 49µV（方向為正）；單次TT不分辨mismatch/noise/kickback，依Guide不據此判架構不可行。

## 判讀（依Guide預先條件）
- 控制有效；±1LSB internal 與 raw 皆在44ps正確 → 支持現有核心具固定名義LSB解析能力。對照case21 sense在precompare約−48µV、+15ps轉為+0.569mV，缺值較可能來自比較期間的輸入變動（CML/CDAC輸入歷史），不是核心固定輸入能力。這不代表SAR通過，ADC score N/A，未計DNL/INL/ENOB。
- internal正確而raw只慢約2ps，輸出負載不是主要瓶頸；但下游qmid/qdecode比raw慢6–9ps，±1LSB在44ps的qdecode尚未到rail，若原read從decode側取值需留意。
- b6 core 37ps 原read對±1LSB不足（raw ~39.4ps）；b6在實際SAR中通常是大訊號，僅供參考。

## 資料
- OneDrive `outputs/PAM4_SAR7_CORE_SENTINELS_20261117_RESULTS/`：summary/measurements(704KB)、run_status、case.json、execution_intent、submission_proof、spectre.log、runner_stdout、slurm-761764.out、approval、c2_slot_lease.json(+sha)、c2_slot_lease_events.jsonl（含begin/restore）、logs（stage、lease begin/status、sbatch、deck_diff_vs_case20、approval_template）、NOT_EXPORTED_deck_raw_sha256.txt、SHA256SUMS.txt。tgz e24dafc7…850f 傳輸核對通過。
- 未匯出：bench.scs（deck不外送）與RAW；RAW 67MB保留在Olympus（診斷中，依本包不清理，等Codex確認不需再看）。
- 文獻PDF：本輪未嘗試抓取Bheemisetti原PDF（headless執行回合，沒有可用的合法登入存取）；未影響本診斷。
- 未自動case23，未改bias/VCM/幾何。
