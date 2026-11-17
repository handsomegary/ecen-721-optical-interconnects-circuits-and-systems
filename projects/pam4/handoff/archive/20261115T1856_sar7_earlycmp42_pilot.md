Stage: SAR7 單案比較器時序 pilot（TT、42 ps）
ZIP: ECEN721_PAM4_SAR7_TIMING_PILOT_20261115.zip（OneDrive ECEN 720/outputs）
SHA256: 8d4c53e7c176369ebec1041b5d205db5e1d47206793e62284f850b037defdea3
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_TIMING_PILOT_20261115/HANDOFF_zh_TW.md
Recommended: 只送 sar7_02_tt_earlycmp42 一個短測；不送案 1 和其他 timing sweep，完成後回報
Resources: 每案 1 CPU／6 GiB／Slurm 30 min；原案 113.6 秒、43.8 MB
Commit allowed: handoff + results
Needs user decision: no

## 本案判讀

使用者在 Codex 主對話已約定 SAR7 時序修正走這個本機通道，並要求「三個小時不要中斷 你跟claude來回決策+模擬」。這個短測是獨立的 SAR7 案；C1 長測維持原授權狀態。

原 job 759069 在 25 ps 比較窗有 73／84 個未解析 bit、12／12 筆轉換含未解析、5 筆可觀察碼錯；最大取樣誤差 1.375 LSB。此案固定電路、12 個刺激、1.75 GS/s，只讓七個比較器時脈提早 17 ps，得到 42 ps 決策窗；DAC 試碼後的等待由 38 降到 21 ps。

依 Guide 核對 ZIP／manifest、verify、三項離線測試與網表最小差異，再提交單案。回本機 outbox 報 job ID、逐 bit 解析時間與結果、錯碼、CDAC 共模、殘差和資料大小。未解析數下降時也核對錯碼，因為 DAC 可能在比較前尚未穩定。保留新舊 raw，無需重跑原案。若 solver 完成但收集未完成，沿用執行證據 collect-only。
