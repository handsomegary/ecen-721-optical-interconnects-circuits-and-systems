Stage: SAR7 760348 保留資料最後收尾查核（零新模擬）
ZIP: ECEN721_PAM4_SAR7_CML_RDEG_AUDIT_20261115.zip（OneDrive ECEN 720/outputs）
SHA256: 83bf3ae00747c95cbe9badabff9282e300a1f378afc23b802c844f7abe217039
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_CML_RDEG_AUDIT_20261115/HANDOFF_zh_TW.md
Recommended: 核對 ZIP／manifest、verify、三項 unittest 後，只對已完成的 job 760348 執行 audit；輸出新 JSON，回本機 outbox 後停止，不送任何 Spectre 案
Resources: 最多一個 Python collector；1 CPU／6 GiB／10 分鐘；零 solver、零新增 raw；Chicago 2026-11-15 21:45:37 後不新啟動 collector
Commit allowed: handoff + results
Needs user decision: no

## 2042 結果的決定

已讀 20261115T2042_sar7_cml_rdeg_result.md。760348 增益恢復至約 0.588，共模下降約 4 mV，未解析 bit 為零，證明實體隔離和差動路徑的診斷目的已達成。仍錯碼 10／12、Σ|Δcode| 23、max 5 LSB，只是約 0.926 GS/s 慢速診斷；不可宣稱 SAR smoke 通過或達到參考論文。

停止調參與新模擬。不將直接負載 760234 的 127/107.16 修正直接套到隔離電路；不同電路條件的最佳數字不能合併宣稱。利用現有 raw 回答最後一個問題：隔離後的有效 CDAC span／sample gain 與感測級 affine 關係究竟如何。這是既有授權下的單次唯讀收尾查核，不是新的電路方案或長測。

## 套件與限制

新包綁定原 CML_RDEG manifest、原 CDAC_AUDIT 分析 manifest、唯一 source root／case／job 760348，以及已回報 summary 的完整 SHA。只有 verify／audit，沒有 stage、run、approval 或 solver 入口。沿用原 SAR7／relaxed／CML_RDEG 環境；PAM4_SAR7_AUDIT_PACKAGE 指向舊 CDAC_AUDIT 包，PAM4_SAR7_CML_RDEG_PACKAGE 指向原 760348 包，不可指向 audit 新包。

同一原生 PSF 只 parse 一次；先後核對執行證據、inventory 與已存在的 summary／measurements。輸出新的 sar7_cml_rdeg_final_audit.json，放在分離的 pam4_sar7_cml_rdeg_audit_ 新 root；不修改既有文件或計分。若需要 Slurm，只能啟動這一個 Python collector。不得重跑 solver、改波形／網表／偏壓／時序，或因無法辨識而新增樣本。

本機 verify 與三項測試通過；獨立程式審查與 ZIP／sidecar／三項 manifest 檔核對通過。包內含 guide、collector、tests、manifest，沒有模型、deck 或 raw。

## 收尾輸出

回報 CDAC 七權重、sample gain、span、offset、逐轉換留一 RMSE／點數；無法辨識就如實標記。感測級報 slope／intercept／輸出端 affine RMSE、大小訊號符號一致數；零交越明確標成感測級零交越，不等同 comparator offset。不做 trim 值或新電路的碼預測。

2042 訊息的兩處 SHA 縮寫尾碼與原本完整雜湊不一致。本機核對的原 ZIP 完整 SHA 是 938e179f33863ddec49894ba0a44f27b5249cf4efad3dfbfe4ac1bd9248e43dc；原 portable 完整 SHA 是 362dc80f1ca8444f59c1f620d2fb5fdae2d8c8948ef2bb7aa3155b2533cbf006。請從既有檔案回覆原 summary／measurements／tran／staged bench／portable／manifest 的完整 SHA，另報新 audit JSON SHA。若原 ZIP 尚在，可用 --source-zip 核對完整 receipt；若不在就標 unavailable，不以 expected SHA 充當實測。原回報保留不改，於新結果更正縮寫即可；若實際完整性核對失敗，依原規則停下並標 Needs user decision: yes。

本輪查核後停止調參，不自行追加新模擬；保留所有 raw 與結果。C1／C2 維持未授權，不碰其他專案。不啟用 archived steering command，不使用 codex queue，transcript monitor 僅唯讀。repo 僅由 Claude 存無 deck 程式、去識別指標及 handoff；不放私有路徑／模型／deck／raw。
