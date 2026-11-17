Stage: SAR7 retained-raw CDAC 權重及 b0 readout 查核
ZIP: ECEN721_PAM4_SAR7_CDAC_AUDIT_20261115.zip（OneDrive ECEN 720/outputs）
SHA256: f41bba0b672f6b59fa5e99981927eabeeea2786d97f63cc1dd2726cdddc5a24f
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_CDAC_AUDIT_20261115/HANDOFF_zh_TW.md
Recommended: 只讀 job 760091、760132 已保留 PSF；在新 root 寫 compact audit。0 個新模擬。
Resources: 單一 Python 3.11 收集程序，估數分鐘；零 solver
Commit allowed: handoff + results
Needs user decision: no

## 判讀範圍

理想感測把末端 CM 下移約 110 mV 降到 4.3 mV，仍錯 10／12。用兩案原 PSF 審查 CDAC 權重、有效滿刻度與 held-input gain，報保留樣本數和留一轉換的預測 RMSE。若權重無法獨立辨識就按原樣回報。估計使用實際 bit 狀態和電位，預期碼不參與 fit，既有量測維持凍結。

b0 只在 valid conversion window 內查原 end_s 到 end_s＋3.5 ps，看 0 路徑是否已達 0.18／0.72 V。用原 PSF、同門檻，不改分數。依 Guide 核對 ZIP／manifest、verify、兩項測試再執行。回本機 outbox 報 audit SHA、權重、held-out 誤差及 b0 結果。兩來源 raw 與既有紀錄保留；本次只有讀取與新 compact 檔。
