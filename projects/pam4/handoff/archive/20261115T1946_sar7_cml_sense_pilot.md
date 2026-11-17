Stage: SAR7 原生 r5 CML 感測隔離單案（TT）
ZIP: ECEN721_PAM4_SAR7_CML_SENSE_20261115.zip（OneDrive ECEN 720/outputs）
SHA256: 8a8d5556b3dd6370889fdfb43152231bf527744fdea4eca58cc1e5daf5bb26cb
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_CML_SENSE_20261115/HANDOFF_zh_TW.md
Recommended: 只提交 sar7_06_tt_r5_cml_sense 一個短測，和 760091／760132 已保留原結果對照，完成後回報
Resources: 1 CPU／6 GiB／Slurm 30 min，solver 約 3–6 分鐘、raw 80–110 MB
Commit allowed: handoff + results
Needs user decision: no

## 依據與差異

直接負載的 Vref 修正已將總絕對碼差 30→8，輸出 12／12 可讀，但約 110 mV 共模下降仍在。隔離的理想臂約下降 4.3 mV。下一步驗證實體隔離，不再掃 Vref。此單案重用歷史 r5 B0 的 500 ohm CML、四個 CDF MOS 與既有偏壓。兩側反相輸出互換接到七個比較器，CDAC 不直接驅動七個 comparator gates。以 760132 的未 trim Vref 比較感測臂，勿把 760234 的 gain trim 套到本案。1,080 ps、60／60 ps、12 codes 和其他設定沿用，末端 scoring 採已驗證的 1030 ps。

與 760091 只增加八條實體支路／偏壓聲明，改七個比較器感測腳及一條 save；比較器 clock 和 CDAC 無變。先 verify 並跑兩項測試，確認完整原生 CDF，核對 root／manifest／單案 approval，再送出。回本機 outbox 報新 job、實體 sense gain／CM／誤符號、取樣點供應電流、CDAC 共模下移、碼差與 summary SHA。保留全部 raw，不重跑既有案。
