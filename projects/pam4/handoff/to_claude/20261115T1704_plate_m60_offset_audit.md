Stage: 正式 C0 payload · P 晚 −60 單案與共同偏移查核
ZIP: ECEN721_PAM4_P_LATE_M60_20261115.zip（OneDrive ECEN 720/outputs）
SHA256: 851f26dfceadc6e4b33c9cb9d9119088ed68a3c504f7922eaf2e554bc156a107
Guide: OneDrive ECEN 720/outputs/PAM4_P_LATE_M60_20261115/HANDOFF_zh_TW.md（ZIP 內也有）
Recommended: 只提交 c0f_payload_a_cm60_phm1 一案，並用既有兩案 raw 做 offset-audit
Resources: 並行最多 1 案，1 CPU／6 GiB／Slurm 90 min，solver 約 20 min，raw 約 30 MB
Commit allowed: handoff + results
Needs user decision: no

## 一案正式配對

使用者授權見 [P 晚 −60 確認](../to_codex/20261115T1700_user_approves_plate_m60.md)。核對 SHA、verify、六項離線測試、approval 和 run root 綁定。維持同 payload seed、−1/8 UI、lag、FFE、ADC 範圍，和 job 759018 的 P 晚碼 0 逐窗配對。網表 diff 限於 32 條控制電壓。回報 primary／secondary 的完整 496 和晚窗 176 的錯誤數、RMSE、帶符號殘差。正式訓練選碼仍為 P 晚 0、N 晚 +60。

## 共同偏移

用同一包的 offset-audit 比較 phase −1 零偏斜 training VERIFY 和零偏斜 payload 原始 PSF。等權四階後晚窗仍有約 +0.337／+0.338 符號單位，標籤比例只另增加約 +0.029／+0.033。可用既有 raw 對照 PNC 輸入、AFE 輸出、held/ADC、17-tap 加權均值。LP14 名義 AC 耦合為 10 pF × 10 kΩ，約 100 ns；兩個種子起始差動位準約 +66.7／−200 mV，耦合初態是待查假說。原 raw 沒存 post-cap gate 或 Vb1。沿用凍結的正式分數，完成查核前保留相關原始 PSF。

此交接只含指引。ZIP、網表、模型與 raw 留 OneDrive／Olympus，GitHub 僅回傳交接與可分享的摘要。
