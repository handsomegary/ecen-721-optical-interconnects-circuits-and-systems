【ECEN 721 #6 C0 五案（TT、固定碼）完成，status＝fixed_endpoint_diagnostic。零偏斜兩端都是 0／240。±4.464 ps 偏斜下，固定端點碼補償讓 primary 錯誤從 11 降到 1（P 晚）、2（N 晚），secondary 從 9 降到 4、25 降到 5。paired_delta_SER 四項都是負的（改善）。注意：solver 每案 53 分鐘，已接近 3300 s timeout】

一、執行
- 修正包 3b60a876…：SHA256SUMS、`c0_rescore.py --mode verify`、5 項測試都通過。
- 第 0 案用現有 PSF 做 collect-only 重算（srun 1 CPU／4 GB），沒有重跑 Spectre。
- 第 1–4 案：job 758820（--array=1-4%4，1 CPU／6 GiB／60 min），四案 COMPLETED，每案 53:15–54:14。
- summary：c0_aligned_summary.json，completed_cases 5，calibration SHA 507009fa…。

二、校準（只用第 0 案 TX [128,1088)，payload 之前）

| 平面 | 歷史 lag | 新 lag | Pearson | 預期極性 | 最後訓練讀取 |
| --- | ---: | ---: | ---: | ---: | ---: |
| primary | 1 | 3 | +0.749 | +1 | 9.935 ns |
| secondary | 3 | 3 | −0.730 | −1 | 9.967 ns |

- payload 起點 10.486 ns，guard 64 個符號，兩端的極性都和電路一致。

三、計分（TX [1152,1408)，每端 256 個 ADC 輸入、240 個 FFE 符號；同一份校準套用到五案）

| 案 | 偏斜 | 碼 | primary 錯誤（SER） | primary RMSE | secondary 錯誤（SER） | secondary RMSE |
| --- | ---: | ---: | --- | ---: | --- | ---: |
| 00 | 0 | 0 | 0（0） | 0.276 | 0（0） | 0.312 |
| 01 | P 晚 +4.464 ps | 0 | 11（4.58%） | 0.481 | 9（3.75%） | 0.515 |
| 02 | P 晚 +4.464 ps | −60 | **1（0.42%）** | 0.463 | **4（1.67%）** | 0.496 |
| 03 | N 晚 −4.464 ps | 0 | 11（4.58%） | 0.527 | 25（10.42%） | 0.626 |
| 04 | N 晚 −4.464 ps | +60 | **2（0.83%）** | 0.458 | **5（2.08%）** | 0.504 |

- 表中是 ideal 7-bit ADC＋FFE 的結果。gray bit errors 和 symbol errors 相同，都是相鄰階的錯誤。
- paired_delta_SER（補償減未補償）：
  - P 晚：primary −0.0417、secondary −0.0208；
  - N 晚：primary −0.0375、secondary −0.0833。
- ADC clipping 都是 0；validation_fitting_performed＝false。

四、判讀
1. 零偏斜下，資料路徑和新對齊都正確。±4.464 ps 偏斜在兩個方向都會造成錯誤（primary 4.6%）。用固定端點碼補償後，錯誤明顯減少，兩個方向都成立。所以補償電路在時域有效。
2. 補償後 RMSE 0.46–0.50，未補償 0.48–0.63，零偏斜 0.28–0.31。RMSE 只改善一點，但 SER 改善很多，代表補償後的眼主要是被殘餘誤差壓縮，而不是錯位。可能原因：
   - 校準只用零偏斜訓練，FFE 沒有隨偏斜重新訓練；
   - ±60 是預設碼，不是訓練得出的最佳碼；
   - 共同相位用的是歷史值。
   這些都在你研究文件列出的「正式 C0 待辦」裡。照使用者的原則，不為這點另開補驗；正式 C0 的獨立選碼與相位訓練會回答。
3. 樣本只有 240 個，1–5 個錯誤的差異不具統計意義。這只是固定碼診斷，不推論 BER。
4. 資源：solver wall 2373 s（第 0 案）與 3161–3221 s（第 1–4 案），峰值 RSS 277–283 MB，raw 每案 69.4 MB。第 1–4 案比第 0 案慢約 35%，可能是四案並行在同一節點上。最慢的一案 3221 s，只比 runner 的 3300 s timeout 少 79 s。之後若加長時間窗（C1／C2），請把 solver timeout 和 walltime 提高，或分段跑。

五、請你處理
- 照研究文件的順序提下一步。使用者的原則：做到 reference paper 差不多就好，不要為小差異一直修。
- 如果下一步是正式 C0（獨立訓練選碼加共同相位），請把訓練案和 payload 案放在同一包，並附 timeout 調整與每案資源估計。
- C1／C2 仍要使用者同意才送。

六、空間
- summary commit 後，依規則退役五案 raw（約 347 MB），量測、校準與收據保留。
