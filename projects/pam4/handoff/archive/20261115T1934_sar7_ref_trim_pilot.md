Stage: SAR7 直接負載的 CDAC Vref 單案（TT）
ZIP: ECEN721_PAM4_SAR7_REF_TRIM_20261115.zip（OneDrive ECEN 720/outputs）
SHA256: c2268736c1b92a96ce6c9e68adfd06383c61cc54800959f6304483a7cb75e17f
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_REF_TRIM_20261115/HANDOFF_zh_TW.md
Recommended: 只送 sar7_05_tt_ref_trim 單案，和保留的 760091 做配對；完成後回報
Resources: 1 CPU／6 GiB／Slurm 30 min，solver 約 3–6 分鐘、raw 80–100 MB
Commit allowed: handoff + results
Needs user decision: no

## 調整依據與判讀

760174 對直接負載的 CDAC span 是 107.16 LSB（目標 127，leave-one-conversion-out 0.748 LSB）。本案基於實際權重乘上 127/107.16，Vref 共模 0.45 V 保持，網表只有 V_RHI、V_RLO 兩條 source 改變。保留 760091 的 12 個輸入、直接負載、1,080 ps 週期和 60／60 ps。B0 的 final read metadata 在每週期從 1027 延到 1030 ps（conv 開始下降前），逐 bit compare 時刻完全不改；原 760091 分數保持凍結。

報相對 760091 的實際比較器碼、總絕對碼誤差、max code error、未達 rail 的 final outputs、最大取樣誤差、滿刻度殘差、結果 SHA。區分 Vref 改善的比較器誤差和晚讀的輸出改善。這是相同 12 個碼的診斷，未達 1.75 GS/s 驗收；不加 sweep，不重跑舊案。先核對兩項離線測試，再依 Guide 送單案。保留新舊 raw。
