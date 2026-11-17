【ECEN 721 #6 P/N deskew GMDRIVE 首批（SS 短路徑 0–17）：只有 cs16 低於 2 dB，但 SS 功耗從 7.8 mW 升到 22.1 mW】

一、執行
- 套件（ZIP SHA 1ffa0ef8…）：SHA256SUMS 全部通過，`gm_drive.py --mode verify` 通過。這版沒有附單元測試，`unittest discover` 為 0 項。
- 審查 deck 索引 0、2、4、14、16：與 portable_review 的 000_bypass、002_ideal、004_cs12、014_cs12、016_ideal 相比，bench.scs 完全相同，la5_foundry_corners.scs 與 parent_diff.txt 只差模型根路徑，case.json 只多了 model_preflight 與 staged_source_sha256。
- 使用者批准 0–17（stage short）。job 752903 共 18 案 COMPLETED，drive_summary 沒有 invalid 案例。
- raw（79 個檔、190 MB）已用相同的量測核對條件退休，每案留有收據。
- 摘要：gmdrive_0_17_summary.json。

二、結果（SS/85 °C/0.81 V，短路徑，source R = 0）

| launch | 56 GHz Hdd | 相對 bypass | 相對同路徑理想 | 低於 2 dB | 功耗 | 增加功耗 | 56/7 GHz |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| bypass | −21.73 dB | 0 | +0.70 | – | 7.79 mW | 0 | +0.27 dB |
| ideal | −22.42 dB | −0.70 | 0 | – | 7.79 mW | 0 | −0.34 dB |
| cs12 | −25.13 dB | −3.40 | −2.71 | 否 | 18.94 mW | +11.15 | −3.48 dB |
| cs12lo | −25.83 dB | −4.11 | −3.41 | 否 | 16.21 mW | +8.42 | −3.30 dB |
| cs12r27 | −25.65 dB | −3.92 | −3.22 | 否 | 19.16 mW | +11.38 | −3.36 dB |
| cs16 | −23.34 dB | −1.61 | −0.92 | 是 | 22.11 mW | +14.32 | −3.77 dB |
| cs12l20 | −24.90 dB | −3.17 | −2.48 | 否 | 18.94 mW | +11.15 | −3.27 dB |

- 漏訊：cs12 的 dormant probe 為 −68.13 dB，相對 bypass −46.40 dB。ideal 的 dormant 沒有數值（null）。
- 最差導通裕度：原 r3 第二級尾管 XT2p0／XT2m0 為 +7 mV（region 2），與你的 OP 稽核一致，屬既有電路，不是新驅動造成的。
- 新增 CM→DM 都在 0.005–0.008。

三、判讀
1. 共源級把 follower 的損失（約 8–9 dB）降下來了：cs12 系列多損失 2.5–3.4 dB，cs16 為 0.92 dB。依預先寫定的 2 dB 判準，只有 cs16 通過。
2. 代價是功耗：cs16 讓 SS 下的總功耗從 7.79 增到 22.11 mW（+14.3 mW，約 2.8 倍）。cs12 系列也要 +8.4～+11.4 mW。依比例推估，TT 與 FF 的絕對增量可能更大。
3. 頻寬：CS 版的 56/7 GHz 比都約 −3.3～−3.8 dB，理想驅動為 −0.34 dB，所以不只是平坦損失，還有高頻滾降。這會改變 CTLE 的等化形狀，最後要在時域用 FFE 後的 SER 確認。串入 20 pH 電感（cs12l20）只改善約 0.2 dB。
4. 第一案的 raw 已用於核對 PSF 與 SS 的 OP，摘要的 OP 欄位齊全。

四、請你判斷（設計工作）
- 在功耗可接受的前提下，能否把增加的損失壓到 2 dB 以下。例如：
  - 只對延遲線那一側驅動，或兩組共用一個驅動；
  - 改善 CS 負載的頻寬（例如 shunt peaking 加大，或把延遲線輸入阻抗併入負載）；
  - 重新評估是否必須用實體驅動（例如讓延遲線直接由前級 CHB2 驅動）。
- 請把功耗預算明確化。題目沒有規定功耗，數值需要使用者批准。可用 AFE 原本約 10 mW（TT）作為參考。
- 若採用 cs16，請提出下一批案例（TT/FF、零 skew、端點、細調）的建議清單與預估，並說明功耗增量在三個角落的預期。
- 下一批需要使用者另外批准。這版沒有附離線測試，若方便請補上。
