# SAR7 有效判決門檻：互補負載短案（2026-11-16）

- 套件：ECEN721_PAM4_SAR7_OFFSET_PILOT_20261116（ZIP SHA-256 e766d044…10f0，manifest f04d9107…0e90）。`package/` 為 Codex 原始碼，無 deck／ZIP；含逐 trial 電位的 `evidence/source_features.json` 依 Guide 留在 OneDrive／Olympus。
- 授權：使用者「八小時授權任何修正」（2026-11-16 15:15–23:15 Chicago）；approval 只改 approved=true。
- 結果：index0 `sar7_10_tt_matched_q_load`（job 761279，在 760874 上補 7 個互補 dummy SAR_NOR）gate **STOP_TARGET**：wrong 6/12、Σ6、max 1 LSB（760874：6/12、Σ7、max2）；84/84 bit 解析、registered 一致、CDAC CM −4.0 mV。共同 sense 門檻區間由約 (−0.673, −0.554] 移到 (−0.220, +0.078] LSB。#6 新錯 −1，#7 修正。index1 未執行。
- `results/sar7_offset_pilot_index0_aggregate.json`：gate＋去除 84 筆 sense.points 的聚合摘要（完整 summary SHA 84b051d7…1a0a）。
- `prompts/`：Claude 回覆。
