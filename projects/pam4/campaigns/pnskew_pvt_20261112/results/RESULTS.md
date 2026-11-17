# 結果：PN skew 影響與 r3 AFE PVT（Olympus，2026-11-12～13）

全部 106 案完成：77 個 skew 案、27 個 PVT AC 案、2 個 PVT transient 案。`summarize_skew.py` 回報 `COMPLETE_DEVELOPMENT_CHARACTERIZATION`，無無效或缺漏案例；`summarize_pvt.py` 回報 `PVT_CHARACTERIZATION_COMPLETE`。這些都是有限樣本的開發量測。題目沒有定義合格門檻，所以 `course_pass` 維持 null，不宣稱任何規格通過。

## 1. PN skew：無雜訊 9 點掃描

條件：理想 7-bit 量化加凍結的 17-tap FFE，每點 2,032 個 symbol。δ = τP − τN，P/N 各移 ±δ/2，平均延遲與取樣時脈固定。

| δ (UI) | δ (ps) | primary 錯誤 | primary FFE MSE | secondary 錯誤 | secondary FFE MSE | 明顯劣化 |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| −0.500 | −4.464 | 5 | 0.143 | 126 | 0.292 | secondary |
| −0.375 | −3.348 | 0 | 0.066 | 26 | 0.195 | secondary |
| −0.250 | −2.232 | 0 | 0.030 | 5 | 0.135 | 否 |
| −0.125 | −1.116 | 0 | 0.015 | 4 | 0.112 | 否 |
| 0 | 0 | 0 | 0.012 | 2 | 0.102 | 參考點 |
| +0.125 | +1.116 | 0 | 0.016 | 4 | 0.112 | 否 |
| +0.250 | +2.232 | 0 | 0.029 | 4 | 0.135 | 否 |
| +0.375 | +3.348 | 0 | 0.066 | 25 | 0.197 | secondary |
| +0.500 | +4.464 | 6 | 0.144 | 126 | 0.289 | secondary |

判讀規則是預先寫定的：SER 增加至少 1 個百分點，或零 skew 最小 held 間距縮小至少 10%，就標為明顯劣化。

- 兩個方向對稱。最後一個連續未觸發的點是 ±0.25 UI（±2.23 ps），第一個觸發點是 ±0.375 UI（±3.35 ps）。觸發都來自 secondary。
- 劣化的實際起點落在 2.23–3.35 ps 之間。格點間距 1.116 ps，格點之間不做內插保證。
- 零 skew 時 held sample 的相鄰電平 p05−p95 間距已經是負值（約 −51 mV primary、−24 mV secondary），代表 FFE 前眼圖沒有張開，所以「間距縮小 %」這項無法評估，判定只用 SER。

## 2. PN skew：20 組配對雜訊種子（seed 1001–1020，只測 δ = 0、±0.5 UI）

| δ | 取樣點 | 錯誤數範圍（/2032） | 配對平均 ΔSER | 標為劣化的 seed 數 |
| --- | --- | --- | ---: | ---: |
| 0 | primary | 0–0 | 參考 | – |
| 0 | secondary | 161–236 | 參考 | – |
| ±0.5 UI | primary | 21–46 | +1.66 / +1.63 pp | 20/20 |
| ±0.5 UI | secondary | 326–419 | +8.46 / +8.45 pp | 20/20 |

零 skew 時 secondary 在加雜訊後就有 161–236 個錯誤。這是先前就知道的次取樣端雜訊問題，與 skew 無關。

## 3. 56 GHz 模態傳遞（tone 診斷）

- **DM→DM（Hdd）**：±0.5 UI 時相對零 skew 下降 3.006 dB，匹配延遲模型為 cos(πfδ) → −3.010 dB。
- **CM→DM 新增轉換**：等於 1.391 × |Hdd(0)|，模型為 1.414。
- **線性度**：DM 的半振幅對照誤差在 5% 內。AFE 輸出 CM 的半振幅對照差 17%，超過 5% 診斷門檻。原量測照樣保留；這一點只影響 CM 輸出相位的解讀，不影響 DM 結論。

## 4. 補償電路的需求（交給設計階段用）

- **範圍**：差動 ±4.464 ps。若兩腿互補調整，每腿 ±2.232 ps。
- **未補償容忍度**：無雜訊時 ±2.23 ps 內沒有觸發判準，±3.35 ps 已觸發。有雜訊的資料只有 0 與 ±0.5 UI 兩組，中間點沒有測。
- **殘餘 skew**：草案目標 0.25 ps；若 CM→DM 預算取 10%，模型給出 0.284 ps。理想均勻碼的量化 LSB ≤ 0.5 ps 只是必要條件，偏差、非線性與 PVT 的裕度要另外留。目前 1.116 ps 的格點量不出 0.25 ps 等級的容差；若需要，只在 ±0.25 與 ±0.375 UI 之間加局部掃描。
- **理想補償上限**：理想反向延遲在代數上等同零 skew 結果。無雜訊時 primary 0、secondary 2 個錯誤；有雜訊時回到同 seed 的零 skew 結果。實際延遲電路可能引入共同延遲，需要和取樣相位另外驗證。

## 5. r3 AFE PVT：27 個 AC corner

製程 TT/SS/FF × 溫度 −40/25/85 °C × VDD 0.81/0.90/0.99 V，完整表格見 [pvt_table.txt](pvt_table.txt)。

| 量 | 範圍 | TT/25 °C/0.9 V |
| --- | --- | --- |
| 56 GHz 相對 1 kHz | 2.46 dB（FF/85/0.81）～ 8.15 dB（TT/−40/0.99） | 6.48 dB |
| 響應峰值頻率 | 22.9–25.1 GHz | 24.0 GHz |
| 峰值相對 1 kHz | 8.6–14.0 dB | 12.3 dB |
| 1 kHz 增益 | −17.6 ～ −21.1 dB | −19.8 dB |
| AFE 靜態功耗 | 5.85–15.35 mW | 10.08 mW |
| 最小 rail 餘裕 | 90 mV（SS/−40）～ 188 mV | 137 mV |
| track 雜訊（1 MHz–56 GHz） | 0.60–0.76 mVrms | 0.69 mVrms |

- 題目要求「56 GHz 最多 20 dB peaking」，27 個 corner 全部在上限內。
- 但 r3 在 56 GHz 只提供 2.5–8.2 dB 的提升，遠不足以單獨補償 20 dB 的通道損耗，其餘要靠 FFE。
- 歷史 r2 的 21.83、16.64、24.78 dB 是不同版本、不同分析格點的量測。summary 註明兩者不能直接相減比較。
- 峰值在 22–25 GHz，不在 56 GHz。

## 6. PVT transient（凍結 TT 訓練的 FFE，不重新適應）

| corner | primary 錯誤 | primary FFE MSE | secondary 錯誤 | secondary FFE MSE |
| --- | ---: | ---: | ---: | ---: |
| TT/25 °C/0.90 V（quiet_z000） | 0 | 0.012 | 2 | 0.102 |
| SS/85 °C/0.81 V | 227（SER 11.2%） | 0.402 | 635 | 0.848 |
| FF/−40 °C/0.99 V | 7 | 0.378 | 191 | 0.790 |

FFE 權重是 TT 訓練後凍結的。換到 corner 時沒有重新適應，SS 高溫低壓劣化最嚴重。這組結果只說明需要 per-corner 適應或校正，不代表適應後的表現。本輪沒有做 PVT 加 transient noise。

## 執行紀錄

- 摘要工具的 `--run-root` 必須給絕對路徑。給相對路徑時，`native/readback_guard.owned_file()` 會把絕對路徑和相對的 case root 比較，一路走到 `/`，結果 69 案全被判為 "Keeper escaped case root"。改用絕對路徑重跑後全部有效。PVT 摘要用相對或絕對路徑，輸出逐位元相同。建議下一版修正。
- r1 有 5 個 PVT AC 案因 PermissionError 沒刪 raw。已用相同的量測核對條件手動刪除，共 31.5 MB，每案留有 `raw_retirement_manual_20261113.json`。Olympus 上 raw 已全部清除，剩餘 356 MB 是輸入 deck 和 compact 量測。
- 每案的 compact 證據（measurements、held samples CSV、run status、退休收據與 logs，共 1,801 檔、14.7 MB）保留在本機，不進 Git。SHA-256：`a858bebf67f1dc90e97e71efa460e7e9e514d1322e574e51bf0054eeb4b0a01d`。
