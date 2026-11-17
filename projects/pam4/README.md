# ECEN 721 Project #6：224 Gb/s ADC-Based Receiver Front-End with Differential PN Skew Compensation

## 最新交接

接手前先更新 `main`，打開 [PAM4 交接區](handoff/README.md)。Claude 查看 [待執行套件](handoff/to_claude/)，Codex 查看 [執行結果與問題](handoff/to_codex/)。各批已核對結果存放於對應的 `campaigns/` 目錄。

[7-bit SAR 單路原型與 Olympus 跑案說明](campaigns/sar7_slice_20261115/)

## 題目規格與目前狀態

課程題目要求：224 Gb/s PAM4 ADC-based receiver front-end，由 analog front-end 加 time-interleaved ADC 組成；AFE 在 56 GHz Nyquist 頻率最多提供 20 dB peaking；ADC 為 7 bit、112 GS/s；並需包含補償 ±0.5 UI 差動 PN skew 的技術（112 GBaud 下約 ±4.464 ps）。題目未規定功耗、雜訊、full-scale 或 BER 門檻。

| 規格 | 目前結果（原理圖層級，TT／25°C／0.9 V） | 狀態 |
| --- | --- | --- |
| 224 Gb/s PAM4 接收前端 | 112 GBaud；56 GHz 處 20 dB 的合成雙極點通道，0.4 Vppd 發送 | 前端可運作；只有標稱條件 |
| AFE 56 GHz 最多 20 dB peaking | 兩級 CTLE，56 GHz 相對低頻提升約 20–21.8 dB；響應峰值約 22 GHz；SS/85°C/0.81 V 為 16.6 dB | TT 達標；PVT 未完成 |
| 7b、112 GS/s TI-ADC | 8 路 × 14 GHz 實體 MOS TG 交錯取樣；量化與 FFE 目前為理想數值模型 | 實體 ADC 未完成 |
| ±0.5 UI 差動 PN skew 補償 | 只做過理想校正診斷 | 未完成，下一個工作項目 |

數值量化器、數值 FFE、理想時脈與 reset 比較器不構成完整實體 ADC 的證明；有限樣本的零錯誤也不是 BER 認證。

## 輸入案例

| 專案 | 輸入案例 | 訊號與分析 |
| --- | --- | --- |
| 224 Gb/s PAM4 接收前端 | `baseline`、`candidate`、`baseline_noise`、`candidate_noise` | 候選改次取樣支路為每側 25 fF／TG 2 µm。完整刺激 2,432 個 PAM4 符號，約 21.986 ns。Smoke 只跑 500 ps。 |

## 工程紀錄

[工程觀察與設計決策紀錄](ENGINEERING_JOURNAL.md)按日期保留假說、實際改動、成功與反例，以及下一次驗證的理由。2026-11-07 的三 seed 比較顯示 raw FFE 改善未穩健轉成7-bit ADC+FFE優勢；最後的新資料holdout為secondary raw220→205、7-bit ADC+FFE241→241平手，不能宣稱ADC勝出；分析/清理已完成並STOP。先建模、驗證，再核准少量 circuit 修改。

[Repository setup and scope](../../README.md) · [Case metadata](cases.json) · [Historical independent-validation summary](reference/independent_validation_summary.json)

本目錄既有案例與歷史結果維持原狀；journal 不會自行啟動舊排程或新設計掃描。
