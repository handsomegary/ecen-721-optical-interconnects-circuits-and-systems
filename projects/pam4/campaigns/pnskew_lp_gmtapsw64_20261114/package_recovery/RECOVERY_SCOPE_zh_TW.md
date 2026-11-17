# SWITCH64 收集復原

原始 case plan 的 SHA-256 為 `a2f8774d9887630fd9a1d5138f2758207bd01c3648299673a76eb2017d991dcc`。原 manifest 另存為 ORIGINAL_SWITCH64_SHA256SUMS.txt。已存在的網表、結果及執行紀錄仍使用這份 plan 核對。

- **密頻 AC**。保留內部頻率網格的檢查。特別處理 Spectre 把最後一點對齊 150 GHz、而使最後一格稍長的情況。只需重讀 0–47 的 compact measurements。
- **短切碼**。保留 native psfascii、完整儲存訊號與時間精度。收集器串流讀取原生語法，僅保留量測使用的數值序列。512 MiB 是原 solver 的單檔上限。現有 48／49 的約 353／361 MiB 應可直接收集。此預期需以 Olympus 上的實檔實跑確認。
- **範圍**。Collect-only 只針對已完成 solver 的 48／49，發布與原有 summary 相容的量測與復原證據。50–86 沿用原案；等待 48／49 讀取、八路取樣與固定目的碼對照通過後再擴跑。
