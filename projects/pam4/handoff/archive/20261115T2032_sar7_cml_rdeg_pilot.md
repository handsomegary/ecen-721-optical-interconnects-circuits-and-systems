Stage: SAR7 補齊原生 r5 CML source 差動路徑單案（TT）
ZIP: ECEN721_PAM4_SAR7_CML_RDEG_20261115.zip（OneDrive ECEN 720/outputs）
SHA256: 938e179f33863ddec49894ba0a44f27b5249cf4efad3dfbfe4ac1bd9248e43dc
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_CML_RDEG_20261115/HANDOFF_zh_TW.md
Recommended: 核對 ZIP、五項 manifest、verify、三項 unittest、單案 approval 與 staged 差異後，只提交 sar7_07_tt_r5_cml_rdeg；結果回本機 outbox，不自動續案
Resources: 最多並行一案；1 CPU／6 GiB／Slurm 30 min，solver 約 3–6 分鐘、raw 80–110 MB；Chicago 2026-11-15 21:45:37 後不送新 job
Commit allowed: handoff + results
Needs user decision: no

## 對 1953 結果的決定

已讀 20261115T1953_sar7_cml_sense_result.md，標記不需使用者決定。760254 的共模隔離有效，但增益 0.0335、Σ|Δcode| 197，不應拿來當可用 SAR。核對歷史原包與本機活動紀錄後，確認 1946 包遺漏原 r5 兩腿 source 間的 250 Ω 電阻。這次是恢復既定實體感測拓樸的單項修正，沿用使用者已授權的 SAR7 短診斷範圍；不更動既有結果、不重跑舊案。

## 唯一改動與驗證

新包從 SHA 綁定的歷史 r5 來源提取該電阻；對 760254 portable bench 只增加這一項。四顆 MOS、兩個 500 Ω 負載、供應／tail bias、sense 極性、七個 comparator、CDAC、未 trim Vref、12 碼、1,080 ps／60–60 ps 和 1030 ps final read 全保留。這仍是約 0.926 GS/s 診斷，不能宣稱 1.75 GS/s。

本機 verify 通過，portable SHA256 為 362dc80f1ca8444f59c1f620d2fb5fdae2d8c8948ef2bb7aa3155b2533cbf006；三項測試全部通過，其中一項核對移除新增電阻後，完整 bench 及 wave metadata 和 760254 一致。ZIP／sidecar／五項 manifest 已另行核對，未帶入模型或 raw。

繼承 760254 已驗證的 SAR7／relaxed 與既有模型環境，另外設定新包的 PAM4_SAR7_CML_RDEG_PACKAGE／ROOT／APPROVAL。unittest 明確需要舊 PAM4_SAR7_CML_PACKAGE 指向原 CML 包；不得指向新包。新 root 前綴 pam4_sar7_cml_rdeg_。approval-template 只能把 approved 改成 true，勿加欄位。stage 後和 760254 bench 差異必須恰好一條 source 間電阻，核對通過再 sbatch。

## 結果與收斂

回報新 job ID、summary SHA256、84 點 sense gain／符號一致／CM／取樣點供應電流、未解析 bit、逐碼 comparator／registered、Σ|Δcode|／max、CDAC 共模下降及末端殘差。只用 760254／760132／760234 已有結果比較，不送那些舊案。新舊 raw 全部保留。

若增益恢復、CDAC 隔離維持，即便剩下約 1–2 LSB 差異，也先回報總結，符合「reference paper 差不多就好，不為小差異反覆修」。若仍有主要失敗，回報保留 raw 的證據，不自行換 tail、改 bias、掃 Vref 或送下一案。C1／C2 仍未授權，不碰其他專案。逾越範圍須 Needs user decision: yes 並停下。截止後不新送 job；不因截止刪除或中斷既有資料。

溝通維持本機 inbox／outbox，不啟用 archived steering command，不使用 codex queue；本機 transcript monitor 僅唯讀。repo 僅由 Claude 存不含 deck 的程式、去識別結果及 handoff，ZIP／deck／私有模型／raw 留核准 OneDrive 或 Olympus。
