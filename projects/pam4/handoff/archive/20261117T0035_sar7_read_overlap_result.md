Stage: SAR7 1.75GS/s read-overlap 單案 sar7_18_tt_175gs_read_overlap（回到761549電路，只改12條trial/clock pulse）
Status: blocked
Decision: INCONCLUSIVE — Spectre 正常完成（0 errors），但 package 的 overlap 診斷在 summarize 時 KeyError 'trial6' 中斷，沒有 sar7_read_overlap_summary.json；正式 gate 無法判定。父層基本計分顯示 registered 12/12 可讀、7 錯但全部 |Δ|≤1（Σ7, max1），兩個舊問題碼 85→86、42→43；comparator 10/12 可讀
Summary:
- 處理 inbox 20261117T0024_sar7_read_overlap_pilot.md；ZIP SHA 2fe8ade1e7f6f09f122ede34fe87ac68ab0d2aa6f4aea3ef5dd09f723218aee9 相符；SHA256SUMS（df3b60ef…079d，與 header manifest 相同）6/6 OK（CRLF，以去 CR 串流核對，未改檔）；verify rc0（portable deck 63c73525a64b0136c66b2aa145da340386492ca5187082d295524213d2fe6aeb）；unittest 11/11 OK；approval-template 只改 approved=true（template 存 logs/approval_template.json）；stage 06:27:56Z rc0，staged deck cff34259f212d8c76ea342d06e7fef0ab7ae285cba5170b066eaf23462e7a3e4。
- 對 761549 deck diff：恰好 12 行改變，V_trial0–5 與 V_clk0–5；b6 相同，與宣告一致（例：trial5 delay 161.5→159.0 ps，即 midpoint 159.5；clk5 delay 206.5→204.0 ps，width 360→362.5 ps）。
- 提交：package sbatch 為 CRLF，sbatch 拒收（"DOS line breaks"，未產生 job）。改用去 CR 的逐位元相同副本 wrappers/sar7_read_overlap_lf.sbatch（diff 對去 CR 原檔完全相同）提交，未修改 package。Job 761649 SubmitTime 2026-11-17T06:28:19Z（新授權窗 05:37–13:37Z 內），Start 06:28:20Z，End 06:34:20Z，Slurm elapsed 6:00（上限 12 min）。提交前 account 執行中 4 CPU（C2 三路 + 他人 cdr4 1），提交後 5 ≤ 6；SAR7 只用 1 CPU，C2 761525 未動（_3/_4/_5 RUNNING，6–94 PENDING）。
- Solver：exit 0，spectre_wall 317.8 s（上限 540 s），CPU 316 s，peak 237 MB，「0 errors, 3 warnings」；deck SHA 前後相同；raw tranResponse 118,288,756 B（a380f63b5e42532c98cfbf24f8352117c9c9a9e4080e314b4fc0abbfe2c6f69d），case dir 67 MB。
- 失敗點（唯讀診斷，未改 Codex 程式）：sar7_read_overlap.py:186 prior_observe 中 `at(f'trial{pb}',instant)`（以及同行 new_trial、prior_clock 等）讀 `values['trial6']` → KeyError。trial6 已在 bench.scs 的 save 列中，raw PSF 也有 trial6 資料；是父層 qbuffer summarize 傳入的 `values` 沒有載入 trial*/clk* 這類節點（parser 只取父層所需子集）。因此 collect-only 會在同一處失敗，需 Codex 修正 collector（例如把 trial/clk 加入載入集合），再以 collect-only 重收，不需新 solver。
- 父層基本計分（measurements.json，status=measured，於中斷前寫出；尚未經新 summary 的 565 正式窗/CM gate）：
  - 逐碼（expected | cmp / reg）：64|64/64；0|0/0；127|127/127；31|31/31；96|95/95；63|64/64；65|64/64；85|—/86；42|—/43；1|0/0；126|127/127；64|64/64。
  - registered：12/12 可讀，7 錯，Σ7，max 1 LSB（761549：7 錯 Σ10 max3；refpath2 761632：8 錯 Σ58 max32）。comparator：10/12 可讀（conv7、conv8 未解析），可讀者 5 錯 max1。
  - unresolved_conversions 2、wrong_conversions 7、logic_smoke_pass False；max sample error 1.673 LSB（761549 1.677）；max observed resolve delay 44.82 ps（761549 43.18 ps）——若此最大值落在 b0，代表 46 ps 窗只剩約 1.2 ps，需新 summary 確認是哪個 bit。
  - final DAC CM change（非正式 CM gate）：範圍 −9.15 ~ +5.39 mV。
- 初步判讀：較長的 b3/b2 建立時間讓兩個問題碼從 +3/+2 改為 +1/+1，registered 全部 ±1 以內，方向上支持「建立時間不足」。但 comparator 在原讀點仍有 2 碼未解析，wrong 7 > 6，依既定 screen（84 bit 全解析、wrong≤6）預期仍不通過；正式結論等修正後的 summary（含 72 段 prior_latch_during_overlap、O/Z、b0 餘裕、CM gate）。
- 依指示不自行縮 guard、加 overlap 或減 b0 窗，未開下一案。
- SHA：measurements 1729b55e4f7ecbe8941bbde5826b9d22fe9125b413ff60728c55021ca64aad37；tranResponse.tran.tran a380f63b5e42532c98cfbf24f8352117c9c9a9e4080e314b4fc0abbfe2c6f69d；spectre.log 9a58539f46fe86b9b25a915fefc0882975f9232d6f07146bf266d89b36682211；authorization ec86523474c7fb6a20bb5e2d806f31b12bed6d177060672e67ff0b08371a9fd8；summary 無（未產生）。
- Raw 全部保留（collector 未完成、需 collect-only 重收；也在 07:37 窗內）。
- C2 761525：仍在跑，3/95 完成、3 RUNNING，照 2144 waiting_runs 繼續，未修改。
Run paths: ~/ecen720_28nm/runs/pam4_sar7_read_overlap_pilot_20261117.3abvDG/（case sar7_18_tt_175gs_read_overlap/、slurm-761649.out、logs/sbatch_receipt.txt、wrappers/env_read_overlap.sh）；repo projects/pam4/campaigns/sar7_read_overlap_pilot_20261117/
Commit: 見本機 state（handoff + results；無 summary JSON，只封存 package/README/reply）
Needs user decision: no（需 Codex 修正 collector 後發 collect-only 包）
