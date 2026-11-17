Stage: SAR7 case20：b2局部平衡驅動，MSB比較窗捐2ps給尾端b0
ZIP: ECEN721_PAM4_SAR7_B2_LOCAL_DRIVE_PILOT_20261117.zip（OneDrive ECEN720/outputs）
SHA256: 9165595b88b36065ad35937a92802fca8aff1ecfd5ee39e2da0959cb2253cc01
Guide: OneDrive ECEN720/outputs/PAM4_SAR7_B2_LOCAL_DRIVE_PILOT_20261117/HANDOFF_zh_TW.md
Recommended: 唯一sar7_20_tt_175gs_b2_local_drive；依Guide核對exact case19 physical diff、verify/tests與原07:37授權後提交1案
Resources: 最多1個accepted job／1 solver，1CPU／6GiB／Slurm12min／solver540s；估4–7min、120–180MB raw；SAR總CPU≤2，shared6CPU，保留C2三槽
Commit allowed: handoff + results
Needs user decision: no

## 已處理0200與本輪設計決策

job761674完成，source summary、measurements與status完整原bytes/fullSHA已本機重核。565結果仍FAIL：82/84、cmp10碼，reg12碼7錯／Σ7／max1；CM與physical565window pass。缺值conv8b1仍在，conv7b0新增；不能把已解析b0最小3.57ps當全部12個都改善。72邊界只有71可判讀、1初始None，不以opposite0掩蓋。保留原結果與raw作參考。

下一步是有限單案，不開新長測、不調classifier：b2 real+dummy的OAI/NOR/互補INV整體2倍及兩路qbuffer第二級INV2→4；14路第一INV1、TG/CDAC/其他bit cell完全不動。只換b2局部10個instance cell並新增3個專用cell。這是隔離接受Z驅動的介入，不重跑先前全bit/TG refpath2倍率。

conv8b2原read已解析0，接受Z卻晚於下一compare約6.32ps。簡化RC理想代理約省5.2ps，尚未含intrinsic C及qmid可能多4ps負載懲罰，故沒有預測會過。必須同報conv8Z的控制rail／底板／held/sense與conv7正確O的qmid/qdecode／bubble；若只快Z但O或其他gate壞掉仍FAIL。不自行升4倍、不另掃。

原12個MSB raw在33ps內有效，EVAL39→37捐2ps給b0 EVAL46→48，MSBcompare108不變、最後read552/release554/registered565不變。MSB較早release可能在qdecode50%39.764ps前造成O毛刺，來源accepted-reference到b5compare最小30.679ps提供有限headroom；須重驗12個MSB與b5，不將raw餘裕當無條件安全證明。新時程完整表在Guide；相對case19恰13pulse變動，b2release→b1compare仍6.5ps，無額外WAIT掩蓋驅動效果。

## 文獻、原門檻與授權

Guide已對照Ramkaj原文SectionIII-B/III-D（DOI10.1109/JSSC.2018.2822823）的RC與comparator→CDAC memory負載，及Bheemisetti（DOI10.1109/JSSC.2024.3449115）的ready/CDAC/DTFB機制、電壓/製程/拓樸及驗證差異。IEEE原始頁本輪仍JS驗證、另一DOI工具開啟失敗，沿用已讀primary文字／圖說，不聲稱看過未取得電路圖。12中心碼不替代DNL/INL/FFT；Um split-CDAC offset-first論文DOI10.1109/ASSCC.2011.6123608作靜態替代原因，本案不校正擬合。

原screen不變：84原read有效、12cmp/reg可讀一致、max≤1、wrong≤6、active552及post565 |ΔCM|≤10mV、有效565讀窗；strict零錯logic_smoke另報。既有晚到值與x/y不替代原read。

原使用者「Yes, 8 hours」source SHA26523d076e396f82acc8844f3441c3517ebba4f05e2073e1629436586287da58仍有效至13:37UTC／Chicago07:37，新stage和accepted SubmitTime用05:37–13:37時窗。限這一案，達標停；未達也先回Codex，不自行開case21。截止後queued同一job可完成且須exactSlurm SubmitTime證明，未提交不得開新案。既有C2 761525/三槽及2144waiting_runs不動，不取消、不重送、不改評分。

## 執行與完整交件

manifest `2887bf0705fb20245f65d8745abdd01624debb53b2aa8bdf7c7c5564adad84e1`，ZIP/sidecar/manifest全部核對，Linux payload已LF才計SHA。沿用原case19dependency chain/private root，環境變數與命令在Guide。root要先建立、存在、canonical且basename符合pam4_sar7_b2_local_drive_pilot_*；approval-template只改approved=true、stage成功後diff核對，再sbatch一次。accepted job即使setup失敗也先回報，不自動重送。收集失敗只collect-only，不重跑solver。

自訂summary沿用完整selected-parser並重綁case20巢狀helper，完整回歸須144nodes/84trial/72boundary及正確case20root/provenance；原basicmeasurement另parse，不稱整job只有一次。請直接複製原byte完整summary、measurements.json、run_status.json、Slurm收據與SHA256SUMS到OneDrive outputs/PAM4_SAR7_B2_LOCAL_DRIVE_PILOT_20261117_RESULTS/，核對bytes/fullSHA再回outbox；不要只回compact。

遠端發布及RAW遵循最新AGENTS：一致中性別名檢查待推送歷史/分支/檔名/code/deck/docs/PDF，保留節點/尺寸/架構，模型專用名/檔/alias表repo外；原private pins不改。Codex不git，不碰其他repo，改寫歷史不pull/merge舊分支。RAW只在分析完成、必要輸出核對且最後分析/commit完成後按既有獨立授權處理；活動中、未分析或仍需參考的來源保留，07:37不是自動刪除點。Batch ZIP是輸入不屬RAW壓縮備份，不能誤刪；歷史metadata不改。本包不清理、不改poll/唯讀transcript monitor/steering、不用Codex queue。
