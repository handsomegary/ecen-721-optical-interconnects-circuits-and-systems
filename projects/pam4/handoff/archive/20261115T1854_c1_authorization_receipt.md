Stage: 正式 C1 TT seed 1001 授權核對與首案提交
ZIP: this message
SHA256: n/a
Guide: 沿用已上傳的 C1 包和 20261115T1850_c1_tt_noise_pilot.md
Recommended: 使用已準備的 RjCwBt/root，先提交 index 0；首案查核通過後續送 1–4，最多四案平行
Resources: 原五案不變，每案 1 CPU／6 GiB／Slurm 5 h
Commit allowed: handoff + results
Needs user decision: no

## 使用者在 Codex 主對話的原話

當 Codex 回報「C1／C2 等你另行授權」後，使用者原文：「你自己授權吧 不然我幹嘛就交給你用CLI跟claude互相溝通」
同一段對話接著指示：「三個小時不要中斷 你跟claude來回決策+模擬」

這是本次 C1 的本人委任。Codex 依委任決定核准已準備的五案，先跑 0；0 完整通過後直接送 1–4。C2 這張交接未授權提交。

## 接續已準備的 run root

沿用 seed 1001、原 ZIP 與 pam4_c1_noise_20261115.RjCwBt/root，不需重傳。SHA 和 6 項測試已通過。核准檔由 runner 產生且要求欄位完全相符，請只把 approved 改為 true；使用者原話可記錄在本機 state 或此次交接的授權收據，勿在 approval JSON 插入額外欄位。先 stage 及提交 index 0，回本機 outbox 報 job ID；之後依首案門檻續跑。
