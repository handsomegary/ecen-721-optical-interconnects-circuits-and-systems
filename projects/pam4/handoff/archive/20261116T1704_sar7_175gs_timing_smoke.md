Stage: Project #6 SAR7 單通道 1.75 GS/s TT 固定時序首案
ZIP: ECEN721_PAM4_SAR7_FAST_PILOT_20261116.zip（OneDrive ECEN 720/outputs）
SHA256: b01e56dbf8e9adbdf0f6779f60fc0ec3cc62beedac9b7ec98cbdf022422a2ecb
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_FAST_PILOT_20261116/HANDOFF_zh_TW.md
Recommended: 只送 sar7_12_tt_175gs_matched_q。先驗證 761279 同模型根目錄的 deck 差異。提交即回報 job ID，完成後回報量測；若收集出錯先 collect-only
Resources: 1 CPU、6 GiB、Slurm 12 分鐘、solver 540 秒；估 2–5 分鐘和 60–120 MB raw，一案
Commit allowed: handoff + results
Needs user decision: no

使用者在 Codex 主對話直接指示：「那你跟 Claude 繼續把 Project #6 做完，先驗證 SAR7 能不能到 1.75 GS/s，再往完整 112 GS/s ADC 整合。PAM4 deskew 先跑 C1，通過再跑 C2。性能跟 IEEE reference paper 差不多就好。」本批只做 SAR7 一個短案，與 C1 長案各自處理。沿用 761279 的 TT／25 °C／0.9 V、類比電路、100 mVppd／原共模與 12 個輸入碼。只替換 25 條時間相關卡片，週期 571.429 ps、試碼到比較 21 ps、比較到讀取 42 ps。manifest `e049fa8bda238eb15777db392ec377634807d7f630eae51caa7b062372bf98d0`，portable deck `903d79a53dcc36162f08c198f9337bbf8fcfe94308bc6fa2c4cb79ad2c785032`。

本案的問題是從 761279 量得最慢 45.5 ps，縮到 42 ps 後會不會掉 bit。請逐 bit 報剩餘讀取餘裕，並附比較前至讀取的 CDAC 差動變化、取樣誤差、共模與逐碼紀錄。這組配對可分辨 buffered rail 過慢、DAC 仍在移動，以及時序都正常但仍存在的靜態誤差。Bheemisetti 的 3 nm 原型在 1.75 GS/s 用來自 CDAC 的非同步 ready 和七級比較，接近 Nyquist 報 37/49 dB SNDR/SFDR；本案先測固定時序 28 nm 的轉換完整性，通過後才做動態／碼轉移驗證。[IEEE JSSC](https://doi.org/10.1109/JSSC.2024.3449115)

按 Guide 的 `screen_pass` 與 `logic_smoke_pass` 分開回報。首案篩選要求 84 個 bit 全解析、12 個 comparator 與 registered 碼都可讀且一致、末端共模變化絕對值不超過 10 mV、最大碼差 ≤1 LSB、錯碼不超過對照的 6／12。附 job 狀態、summary/measurements/tran SHA、solver 秒數及 raw bytes。本批先保留原始證據；結果回到本機 outbox，避免重複送件。
