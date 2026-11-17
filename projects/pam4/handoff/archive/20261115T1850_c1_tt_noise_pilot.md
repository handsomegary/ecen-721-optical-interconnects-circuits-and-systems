Stage: 正式 C1 TT transient-noise smoke，seed 1001
ZIP: ECEN721_PAM4_C1_NOISE_SMOKE_20261115.zip（OneDrive ECEN 720/outputs）
SHA256: 3accf56c45b49bfd162a87dba4331295df2f157406a127ada06b27f0bec5c8f5
Guide: OneDrive ECEN 720/outputs/PAM4_C1_NOISE_SMOKE_20261115/HANDOFF_zh_TW.md（ZIP 內有同版）
Recommended: 先提交 index 0 零偏斜；核對完整首案量測後續送 indices 1–4，最多四案平行
Resources: 每案 1 CPU／6 GiB／Slurm 5 h（solver 4.5 h 上限）；歷史同長度 70.5–94.3 分鐘、約 133 MiB raw／案
Commit allowed: handoff + results
Needs user decision: no

## 授權與範圍

使用者在 Codex 主對話將 C1／C2 的判斷交給 Codex，並要求接下來三小時持續配合。此交件核准五個 C1 TT smoke 個案，先送 index 0。收到 Slurm ID 或遇到提交阻礙就從本機 outbox 回報，不必等整批。首案完整性通過後，直接依 Guide 送其餘四個含雜訊配對，這個已核准的分批不需要再等訊息。

五案共用相同包、C0 凍結相位 −1/8 UI、lag、極性、FFE、理想 ADC 範圍、歷史 r5 validation 刺激與 Spectre seed 1001；每面 2,032 符號。P 晚 −60 是固定碼診斷（正式 training 選碼仍是 0）。零偏斜首案門檻是有效、完整的波形和量測。報兩面錯誤數、clipping、RMSE、solver wall、MaxRSS、raw bytes 與正式 job IDs。任何新增模擬以此包列的五案為範圍，C2 再由 Codex 依 C1 實測決定。

## 運行

核對 ZIP／manifest、verify 和六項離線測試，綁定新的 run root、既有 C0 兩份選擇檔和五案 deck SHA。沿用原 Olympus Classic 設定和私有模型目錄。若 solver 完成而收集失敗，以保留 raw 用 collect-only。先保留 raw 供查核。ZIP、decks、PSF 和模型均留核准位置。
