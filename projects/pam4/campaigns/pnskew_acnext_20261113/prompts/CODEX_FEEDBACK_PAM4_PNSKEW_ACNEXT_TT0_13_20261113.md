【ECEN 721 #6 P/N deskew ACNEXT：TT 0–13 的 Olympus 結果。原生 TG 選擇器損失過大，先停在這裡回報】

一、執行
- 套件 ACNEXT（ZIP SHA 9a676e50…）：SHA256SUMS 全部通過，`ac_next.py --mode verify` 通過，4 項離線測試通過。
- 審查 deck 索引 0、2、8、22、36、46：bench、corner、parent_diff 只差模型根路徑。case.json 只多了 model_preflight 與 staged_source_sha256，沒有其他欄位不同。
- 使用者批准全部 94 案，並依你的順序執行。實際只跑了 0–3（job 752358）、8–13（752364）、4–7（752370），共 14 案全部 COMPLETED，summarize_acnext 沒有 invalid 案例。
- 每案 Spectre 約 1.5–2.4 秒，RSS 約 230 MB，raw 0.8–8 MB。
- 依使用者事先約定（TT 0–13 若顯示 TG 版範圍或損失明顯不行，就停下回報），其餘 80 案（14–93）沒有送出。
- 14 案的 raw（63 個檔、74 MB）已用相同的量測核對條件退休，每案留有收據。
- 摘要：acnext_tt0_13_summary.json。

二、結果（TT/25 °C/0.9 V，Rs=25 Ω、Rt=25 Ω，r3 負載；7–56 GHz 加權有效延遲）

| 變體 | P/N 碼 | τ_eff | 加權 phase RMS | 最差 phase 誤差 | 56 GHz Hdd 相對 bypass（輸入無 skew） | 新增 CM→DM |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| bypass | 00/00 | 0 | 0 | 0 | 0 dB | 0 |
| ttd_selected（理想選路） | 06/06 | 0 | 0 | 0 | −0.33 dB | 0 |
| ttd_selected | 06/16 | −5.245 ps | 0.012 ps | 0.019 ps | −4.90 dB（施加 5.2 ps skew 的結果） | 1.484 |
| ttd_selected | 16/06 | +5.245 ps | 0.012 ps | 0.019 ps | −4.90 dB | 1.484 |
| ttd_switch（原生 TG） | 06/06 | 0 | 0 | 0 | −30.11 dB | 0 |
| ttd_switch | 06/16 | −3.356 ps | 1.534 ps | 7.665 ps | −27.10 dB | 0.071 |
| ttd_switch | 16/06 | +3.356 ps | 1.534 ps | 7.665 ps | −27.10 dB | 0.071 |

- P/N 互換的對稱誤差：理想版 7e-16，TG 版 1.4e-13，兩者都對稱。
- 輸入雜訊（X_ip−X_im，1 MHz–56 GHz）：bypass 0.151、理想選路 0.153、原生 TG 0.198 mVrms。
- 已知輸入 skew 為 −4.464 ps 時，TG 版在 trim 點的 Hdd 為 −32.9 dB（相對 bypass），AFE 出口約 −33 dB。

三、判讀
1. 理想的 6/16 節等阻抗固定長短路徑完全符合你的解析模型：±5.245 ps（需求 ±4.464 ps）、頻帶內幾乎沒有 dispersion，等長時只有 −0.33 dB。路徑本身成立。
2. 加入原生 TG 選擇器後無法使用：
   - 等長 06/06 就有 −30 dB 的 56 GHz 損失。等長時兩腿理應等效，所以這是選擇器本身的損失，不是延遲差造成的。
   - 06/16 的有效延遲只剩 ±3.36 ps，未達 ±4.464 ps。頻帶內加權 RMS 1.53 ps、最差 7.7 ps，dispersion 又回來了。
   - 推測 W=1 µm、L=30 nm TG 的 Ron 與 Coff 在 56 GHz 形成很大的串聯損失與分流。請用 Ron/Coff 掃描或解析模型確認主因：是導通路徑的 Ron，還是未選路徑的 off 電容。
3. 碼表診斷（42–77）、端接敏感度（78–89）、SS/FF（14–41）與相鄰碼（90–93）都還沒跑。它們已在使用者批准範圍內，但在選擇器確定之前跑，意義有限。下一版選擇器確定後，舊 LC 碼表的診斷是否還需要，請一併判斷。

四、請你判斷並給下一版（設計工作）
- 選擇器：在 56 GHz 下要能做到接近 −0.33 dB 的等長損失。可考慮更寬的 TG（同時權衡 Coff）、分佈式或 series-shunt 開關、在選擇器前後加端接匹配，或改成不在訊號路徑上切換的結構（例如兩條路徑永遠接通，只切換 buffer 或 combiner）。請說明 Ron、Coff 與節數的取捨，以及 SS/FF 下的範圍。
- 若換結構，請保留目前 ttd_selected 的理想對照，並重新給 TT 稀疏案例：bypass、等長、正負兩端，以及至少一個中間碼。延續相同格式與 approval 機制。
- 使用者已核准的 94 案 approval 綁定的是目前的 plan SHA；新套件需要新的批准。
