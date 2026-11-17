Stage: SAR7 比較器輸入隔離單案＋既有輸出位元查核
ZIP: ECEN721_PAM4_SAR7_SENSE_ISOLATION_20261115.zip（OneDrive ECEN 720/outputs）
SHA256: 43ecd1547d01571f844c2ed925cb686d7f705d1e5de959a0ae51d698df8d0393
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_SENSE_ISOLATION_20261115/HANDOFF_zh_TW.md
Recommended: 讀現有 760091 暫存輸出；只新增 sar7_04_tt_ideal_sense_isolation 一個短測，完成後回報
Resources: 1 CPU／6 GiB／Slurm 30 min，預估 solver 3–6 分鐘、raw 80–100 MB
Commit allowed: handoff + results
Needs user decision: no

## 下一個可區分問題的對照

依 760091 的 60 ps＋60 ps 結果，停止掃時序。先用 baseline-audit 讀保留波形，比較每顆比較器在 read 與 end_s 的電位，以及 end_s 的輸出 bit pair，定位六筆無法判出的來源。

新案保留 760091 全部時序及電路條件，只加 EISO_P／EISO_N 兩個理想 unity VCVS 並改七條 XCMP 的輸入接點。這對照移除比較器輸入的總負載，包含靜態寄生和動態回灌；不可由此單獨宣稱是哪一項。若 CDAC 共模、滿刻度或誤碼改善，後續才評估實體隔離；若仍差，轉向 CDAC 轉移與權重。這是診斷而非 1.75 GS/s 規格通過。

依 Guide 核對 ZIP、manifest、verify、兩項離線測試、scope 與 deck 差異，再提交一案。若 solver 完整，必要時 collect-only。回本機 outbox 報新 job ID、兩側 rail 查核、共模和錯碼、摘要 SHA。保留一切現有及新 raw，勿重跑原本三案、增加 sweep 或搬出 PDK。
