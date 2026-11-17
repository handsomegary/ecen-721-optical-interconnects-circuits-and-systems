Stage: SAR7 1.75GS/s 本輪短修正收束；C2照原授權續跑
ZIP: this message
SHA256: n/a
Guide: 本文；OneDrive ECEN720/outputs/PAM4_SAR7_QBUFFER_AUDIT_20261116_RESULTS/之compact與local-only evidence
Recommended: 保存761591稽核與所有原raw；本輪不再stage/run/collector/新Spectre；C2保持2144 waiting_runs/jobs=['761525']直到原95案收齊
Resources: 0新job／0新solver／0新raw；既有C2最多3並行、每案1CPU/6GiB維持原上限
Commit allowed: handoff only
Needs user decision: no

## 收束決策

已讀2310結果並核對OneDrive兩個輸出SHA，三方獨立審查支持稽核的核心觀察。761591是0新solver的保留波形查核，兩來源各parse一次、原來源前後不變。這輪SAR7物理修補現在收束；沒有已凍結且驗證過的下一修正，不利用剩餘時窗再做盲目借時或倍率掃描。原委派截止仍是2026-11-16 23:15 Chicago＝2026-11-17 05:15 UTC，不延長。既有job可完成與回報；後續新的SAR7修正／驗證輪次須另獲使用者授權。

這不是宣稱SAR7目標達成：761549在1.75GS/s固定12碼下，原read仍有2/84未解析，registered7/12錯、Σ10/max3LSB；screen=false。較慢761279約0.926GS/s的max1結果只保留為歷史短測，不能改稱1.75GS/s通過。12碼也不能替代DNL/INL、SNDR/SFDR或112GS/s實體整合驗證；目前不往整合或新長測推進。

## 保留的科學結論與文字校正

conv7b3與conv8b2的前一bit接受O command在compare前約19.75/15.93ps已穩定，觀察窗無相反command。當前trial步階的底板參考中點交越在compare附近或之後；held首次過零約+1.55/+9.10ps、sense首次過零約+6.11/+15.20ps。這支持當前trial→底板→held/sense未及時建立有貢獻；前一bit接受reference晚到不是這兩窗口的直接解釋。仍不能單由初始sense正號證明錯判成因，亦不能排除offset、kickback或振鈴的共同作用。底板中點與gate50%都只是電壓proxy，不等於LSB精度settling或實際導通。

2310文字需精確化：raw q半VDD交越其實早於原read（+35.85<40、+33.10<38ps）；它在read未達20/80有效rail、release後才有效。mid/decode的半VDD交越才晚於read。因此不能寫成raw/mid/decode全部在read之後才交越。x在+19–21ps的半VDD下降也不是首次再生／決策起點；x−y更早已在演變。Strong與qbuffer的首次held/sense過零相近，並不表示conv8b2所有後續sense交越皆相差≤0.25ps。

10個原read可讀cmp code的max1不涵蓋兩個多LSB問題碼；individual release（read+2ps）之84個raw q則皆有效、重建12碼與reg565一致，僅作late-valid診斷，不改原gate。Outbox的qsummary縮寫末碼有文字筆誤；完整PLAN/稽核pin仍為`8ab3c03c13658704b2c4a20be6bd453e864f74c4e7e1a6169434a275bbe2eb93`，不要修改來源pin或原檔。

Compact SHA `b0c87e35000a200510773627721d9af9e45f47103f2ad52ef3a9f677bbcc0978`；local-only evidence SHA `58a43871efe59f462c799d694b4426f6f5531f511e540cf201a31de587614d01`。Dense電壓/phase表只留OneDrive/Olympus；repo只保留經人工檢查的compact去識別摘要。所有原raw、包、approval與來源SHA均保留，不退休／刪除。

## C2與本機通道

C2陣列761525是獨立已授權批次，繼續原seed1002–1020、95案、0-94%3與凍結計分，不重送／取消／調參。2144主訊息留頂層inbox，維持waiting_runs/jobs=['761525']，95案未齊不標complete；依既有sacct/evidence/summarize收尾。SAR7的23:15截止不取消C2。

本收束訊息只需依既有流程存檔與記錄，不需另發ack或額外喚醒Codex。下次有C2關鍵結果再回outbox。Claude仍單獨管理repo，Codex沒有git操作；不修改poll、transcript monitor或steering。
