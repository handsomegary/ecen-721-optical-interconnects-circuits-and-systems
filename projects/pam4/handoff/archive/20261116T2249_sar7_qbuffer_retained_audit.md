Stage: SAR7 761549／761524 保留波形因果稽核（零新solver）
ZIP: ECEN721_PAM4_SAR7_QBUFFER_AUDIT_20261116.zip（OneDrive ECEN 720/outputs）
SHA256: eb77a4017f375f6dce2fe4c5ab5d4fb95e5451e0166db494f53a8510df0833d4
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_QBUFFER_AUDIT_20261116/HANDOFF_zh_TW.md
Recommended: 只讀761549與761524既有PSF，各parse一次；核對前一bit接受reference至下一bit比較，不stage/run任何電路
Resources: 最多1個collector、1CPU／6GiB／Slurm10分鐘；0新Spectre／0新raw，保留所有原始資料；account總QOS6CPU
Commit allowed: handoff + results
Needs user decision: no

依既有SAR7背景委派接續已完成案的證據分析。**本包沒有新電路、沒有Spectre、沒有approval/stage/run路徑。** 只准既有raw的collector，不補跑761549／761524。collector提交仍須在2026-11-16 23:15 Chicago（2026-11-17 05:15 UTC）前；已提交job可完成收尾。這不是延長修補時窗。其後新solver持續暫停，下一步須先依稽核證據與授權判斷。

## 2237回報需更正的判讀

761549 registered565仍是12/12可讀、7錯、Σ10/max3；與761524逐碼相同。Raw q改善至82/84解析，但cmp只有10/12可讀，5錯、Σ5/max1只適用這10碼。缺失的conv7/conv8正好是85→88、42→44兩個多LSB錯碼，summary的comparator_registered_agreement=false。可讀10對相符不能當作原read的12對相符，也不能據此把所有錯碼歸因於比較器本體。

另以既有individual release（各read+2ps）作診斷時，84個raw q皆可分辨，重建12碼與reg565一致，包含88／44。這個「晚到後的最終q／register一致」成立，但不改原read未解析的gate，也不區分未建立sense、offset、先前bit回授或動態效應。

decode到rail的28/84是在**各bit自己的read**，不是全部552ps。conv0b6的compare/read是120/159ps，間隔39ps，不是61ps。現有collector時間欄位與非反相極性經獨立核對一致，問題在回報文字及因果延伸。Outbox稱截止已過亦不符本輪UTC時鐘；本案仍按05:15UTC實際截止，不因文字誤判延長或提前耗用權限。

conv7b3開比較前held/sense約+2.41/+3.11LSB，之後變負；conv8b2亦由+3.16/+1.79轉為後段接近零／異號。這支持檢查整段輸入軌跡，並不能由compare+30的負值直接判定intrinsic comparator offset或排除其他動態。Raw q在原read未達rail、release後才可分辨，應保留late-valid與原deadline未解析的區別。

## 本次可回答的因果問題

trial高時q_decode被遮蔽；trial解除後，前一bit的接受reference改由q_decode控制。現有JSON的q crossing止於next launch，reference gate crossing止於release，不能回答其後真正抵達底板及下一比較的時間。最重要的是conv7 b4→b3及conv8 b3→b2，並保留下一bit作上下文；另用conv0b6校正時間原點例子。

按照Guide的固定窗口，把前一bit解除前5ps到下一compare及再生／read的raw/mid/decode、trial/clock、實際四個reference gate、底板、held/sense、x/y與register對齊。回報gate crossing、相反reference命令的短暫proxy、held/sense符號、平台／建立與下一比較的相對時間。50% gate只是電壓proxy，不是實際導通或短路證明；稀疏/選定軌跡亦不能排除更快擾動。Dense選定樣點只留OneDrive/Olympus，repo只放compact去識別摘要，不存波形表。

若接受reference在下一比較前才晚到、或造成held/sense於再生期間換號，支持控制傳播與類比建立仍有貢獻；若控制／底板已穩定且sense輸入整段同號而內部決策不符，才較支持比較器／有效門檻的替代解釋。兩種機制可以共存，不先指定勝出原因。

## 文獻、來源與回報

[Ramkaj，JSSC DOI10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823) SectionIII-D以小comparator負載及隱藏logic延遲安排接受reference路徑；與我們增加兩INV的28nm固定時序實作不同。[Bheemisetti，JSSC DOI10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) 的3nm DTFB／bottom-plate-ready非同步時序，提醒必須量真正底板與sense建立，不能只看gate交越。[Um，A-SSCC DOI10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608) 的offset-first／隔離權重法仍是靜態替代診斷，動態軌跡未釐清前不再擬合CDAC。這次不提出新電路或sweep，也不把12碼短測當成論文DNL/INL或FFT驗證。

Manifest SHA `8931c3c771e45a7a2383b5ed107c9f25a141b90ef46c07b6defc14aaf4572fbf`。先驗ZIP/manifest/verify/unittest，再只送collector；sbatch前須以UTC秒數確認早於2026-11-17T05:15:00Z，若已過就不新提交並回報。程式綁定兩案summary、measurements、tran完整SHA，稽核前後來源不可變；一案至多parse一次，資料不符即回報而不改pin。761549原summary SHA為8ab3c03c13658704b2c4a20be6bd453e864f74c4e7e1a6169434a275bbe2eb93，本機checkout副本實測與其一致；761524如使用去識別repo副本，不能冒充原summary byte SHA，應直接在Olympus核對原檔。

請回本機outbox：collector jobID、來源SHA與前後不變證據、時間原點、關鍵轉換／位元的接受reference抵達與下一比較時間差、held/sense/內部節點判讀、compact和local-only evidence的SHA，以及仍無法區分的原因。不要新送Spectre或以收集失敗為由重跑；原raw全部保留。

C2陣列761525照已授權95案繼續，由2144原waiting_runs/jobs=['761525']監看，不重送或取消。此短collector用自己的task優先回報；不得與C2合併成需等53小時才回覆的等待集合。不改poll、transcript monitor、steering或其他專案。
