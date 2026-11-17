Stage: SAR7／相關 PAM4 八小時委派：時窗與執行邊界更新
ZIP: this message
SHA256: n/a
Guide: this message；現行查核 Guide 為 OneDrive ECEN 720/outputs/PAM4_SAR7_CDAC_ROUND2_AUDIT_20261116/HANDOFF_zh_TW.md
Recommended: 記錄此授權時窗，沿用已交接的1525保留波形查核與既有campaign；不要重複啟動collector。下一個設計／pilot仍等Codex依證據凍結交件
Resources: 本則無新job；現行collector最多1個、1 CPU／6 GiB／10 min；後續各包依Resources與共用QOS≤6CPU，不占滿、不碰其他專案job
Commit allowed: handoff only
Needs user decision: no
authorization_basis: 使用者原話「八小時授權任何修正」，2026-11-16 15:15 Chicago 起8小時，SAR7／相關PAM4達標修正與短pilot的approved=true由該授權涵蓋

## 已讀與有效時窗

已讀20261116T1515_user_delegates_8h_sar7_fixes.md。其yes明載使用者已授權，依目前使用者規則接續，不再詢問。時窗為2026-11-16 15:15:00–23:15:00 America/Chicago（UTC-06:00），截止對應2026-11-17 05:15:00 UTC。

此新授權取代1514那則「總共最多兩solver／兩案後不再開第三輪」的總限制。時窗內可依結果安排連續、有明確假設的SAR7／相關PAM4設計／參數修正與短pilot，直到max|Δcode|≤1 LSB或Codex判斷已無合理方向。個別已凍結套件的case清單、gate、SHA及Resources仍照原包執行；後續由Codex另發新固定包，不在執行端臨時放寬。

23:15後不新開修正輪次。已送出的job照常收完與回報，保留全部資料。不為小差異無止境調整；每輪需說明證據、機制及可區分替代原因的結果。

## 本刻的具體下一步

1525交接的760874保留PSF查核仍是現行任務：讀真正sample、實際pre_s控制rails及#8 b2周圍hold／sense，判別42→44來自sample、LSB-bank／bridge或有效offset／動態。此查核不消耗新solver；若同一campaign或collector已存在，接續收集，不能因本授權訊息再啟動一份。

兩篇IEEE主文對照已完成並記於research_round2及1525 Guide：Um [10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608)、Bheemisetti [10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115)。後續每輪新設計仍要把所量測失敗與適用的機制、操作條件及驗證方法對照；不能直接延用上一輪偏樂觀planner。數值重現用具名容差，來源完整SHA與核准deck仍精確核對。

## 仍需另外授權

此時窗不涵蓋刪任何raw、C1／C2長測、全PVT或1.75 GS/s正式驗證、其他專案。Codex不做任何git操作；repo仍只由Claude依Commit allowed處理。所有新舊raw保留，ZIP／deck／PDK／模型留核准OneDrive／Olympus。

保持本機worker／inbox／outbox，archived steering command停用，不使用codex queue，transcript monitor僅唯讀。這是一則授權範圍更新，不是新的電路／simulation任務；無需為此產生往返ack，合併於現行查核結果回報即可。
