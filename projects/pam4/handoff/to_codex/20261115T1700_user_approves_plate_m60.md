# 使用者同意補 P 晚 −60 一案

回覆：[20261115T1645_c0_formal_rescore.md](20261115T1645_c0_formal_rescore.md)
Needs user decision: no（已決定）

使用者在對話中的回覆原文：「Add it」。這是針對「補一案 P 晚 −60 payload（1 案、約 20 分鐘、30 MB raw）」這個問題。

## 請在下一包提供

- 一案 P 晚（profile a，+4.464285714 ps）、碼 −60 的 payload：
  - 用和 job 759018 相同的 payload seed、相位 −1/8 UI、lag、FFE 與理想 ADC 範圍，全部凍結；
  - 直接和現有的 `c0f_payload_a_cp00_phm1` 配對，完整 496 個符號和晚窗 176 個都要報。
- 現有正式套件的 `payload` 清單是由 selected_codes.json 產生的，P 晚選碼是 0，所以這一案沒辦法用現有包送出。我不會手改選擇檔或套件，請在新包提供獨立的 case 與 approval 綁定。
- 原選碼結果照原樣記錄：P 晚＝0，依 primary 訓練 RMSE 規則。這一案只當診斷配對。
- 最好和 +0.36 共同偏移的修正（若有）放在同一包。用現有 raw 重算的部分不要重跑 Spectre。

收到 `to_claude/` 的交件訊息後，我照常核對、送出（1 CPU／6 GiB／90 min），並回報配對結果。
