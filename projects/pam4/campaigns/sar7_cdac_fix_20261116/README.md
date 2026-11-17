# SAR7 CDAC span／比例修正 pilot（2026-11-16）

- 套件：ECEN721_PAM4_SAR7_CDAC_FIX_20261116（ZIP SHA-256 8e290b0e…a9e7，manifest bb97b973…5153）。`package/` 為 Codex 原始碼與去識別證據，無 deck／ZIP。
- 第一次停下：planner 預估在 Olympus python3.11 重現時 8 個浮點值最後一位不同（`results/prediction_check_olympus_py311.json`）；使用者選「A: run as is」後照原包執行。
- 結果：**STOP**。index 0（job 760873，共同 Vref ×1.1148）gate ALLOW_INDEX1：9／12 錯、Σ12、max2。index 1（job 760874，主陣列比例＋bridge）：6／12 錯、Σ7、max2（明顯收斂條件達成，目標 max≤1 未達）。基準 760348：10／12、Σ23、max5。兩案 84/84 bit 解析、registered 一致、CDAC 共模 −4 mV。
- `results/sar7_cdac_fix_round_summary.json`：兩案去識別摘要（SHA 56a3ad6a…526e）。
- `prompts/`：Claude 回覆。
