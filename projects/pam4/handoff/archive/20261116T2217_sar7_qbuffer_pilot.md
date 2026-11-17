Stage: SAR7 1.75 GS/s：隔離 strong decoder 的 comparator q 負載
ZIP: ECEN721_PAM4_SAR7_QBUFFER_PILOT_20261116.zip（OneDrive ECEN 720/outputs）
SHA256: 51973c01c8c6943b9d8e6166dfd6efc1763737a79009ec8313031ab0fa417882
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_QBUFFER_PILOT_20261116/HANDOFF_zh_TW.md
Recommended: 只送sar7_16_tt_175gs_qbuffer；核對父761524後用原時序/原gate跑一案，完成即回Codex
Resources: 1CPU／6GiB／Slurm12分鐘／solver540秒，估4–7分鐘及100–180MB raw；加既有C2最多3路，account總QOS6CPU
Commit allowed: handoff + results
Needs user decision: no

使用者16:58要求繼續驗證實體SAR7 1.75 GS/s，18:43要求隔離案結果回來接著修。既有八小時短修正委派仍於 **2026-11-16 23:15 Chicago（2026-11-17 05:15 UTC）截止**；只在截止前提交這個有界單案，已提交job可完成。無新的C1/C2批次或其他範圍授權。

## 761524結果與本案假設

已核對2215結果及本機checkout的去識別summary。761524 registered在565ps為12/12可讀、7錯、Σ10、max3；comparator碼因26/84bit未到rail而全部缺失。缺失不是零錯，不能把其wrong=0當成功。Active552ps CM約−4mV，post565ps仍在±10mV，讀出窗有效。現有快照顯示內部x/y明顯分離，而q高端偏低；支持輸出負載有貢獻，尚不等同已逐bit證明全部錯碼原因。

新案保留strong decoder、reference TG、CDAC、原比較器與register，只在14個q正負路徑各加 **1x INV→2x INV的非反相局部buffer**，驅動strong decoder的q輸入。直接q仍接原register及原匹配負載。第一級使用原SAR_INV，第二級使用原decoder專用SAR_NDINV2；不改既有subckt定義。只重接28個XNDO/XNDZ的q輸入，新增28個buffer實例及mid/decode觀察點，正負兩側鏡像。

以N/P幾何加總作代理，strong decoder每路原輸入為3N+5P，buffer第一級為1N+1P，附加decoder輸入寬度代理約降4.35倍；連原NOR負載約降2.68倍。固定q電容、寄生/Miller和動態電流沒有因此消失，**這不是總電容比例或速度保證**。1→2 taper是固定的單一選擇，不掃倍率。

## 原時序、gate與可區分結果

週期571.428571ps，wait42/45/25/19/15/8/6、比較窗39/44/40/40/38/41/54ps、所有clock568ps下降；b0read552/release554，正式reg565、診斷563/554/557，conv558/reset566/track569，全部沿761524原樣。

trial為高時，trial路徑仍直接控制strong decoder；新buffer的延遲主要須在接受決策／trial解除附近被吸收。**原q恢復到rail還不算達標**：要同時量q_raw、q_mid、q_decode的極性、rail交越與傳播延遲，尤其compare+15/+30、read、release及下一launch附近；並列底板、gate、held、sense、x/y與原register。若rawq變快但q_decode在release後仍晚、held或錯碼未改善，則額外buffer的延遲是代價；若rawq本身仍慢，則負載解釋不足，先回報而不自行加強更多級。

正式screen保持84bit解析、12筆cmp/reg可讀且一致、max≤1LSB、wrong≤6/12、active552與post565的|ΔCM|均≤10mV、565讀出窗有效；strict logic_smoke零錯條件另外回報。不降低準位門檻、不改classifier、不事後挑讀點。通過就停止本輪修補；沒有通過也回Codex，不在執行端自行加第二案或改時序。

## 文獻對照與限制

[Ramkaj等，IEEE JSSC，DOI10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823) SectionIII-D的memory路徑刻意減少comparator負載，並把logic延遲藏在再生時間內。它採pass-device與INV/TG的短路徑、28nm／1V／1.25GS/s、triple-tail及USPC，並以晶片靜態／頻譜量測驗證。我們新增兩級INV的實作不同；這個原則支持隔離負載，同時要求實測額外延遲，不能直接套用其性能。

[Bheemisetti等，IEEE JSSC，DOI10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) 的3nm／0.65V core／320mVppd DTFB及bottom-plate-ready非同步架構與我們28nm／0.9V／100mVppd固定時槽StrongARM+CML不同；其DNL/INL與FFT量測也遠超12固定碼短測。[Um等，A-SSCC，DOI10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608) 的offset-first與split-CDAC孤立殘差法仍保留為替代診斷；本次動態q/內部節點差異支持先測負載，不再擬合bridge/LSB權重。

## 執行、證據與C2

Manifest SHA `928590bc897d6755e208f2729f8c0c9882e15a42262032edddf9b491fa0188ca`。先核對ZIP/sidecar/manifest、verify/unittest與stage對761524的精確差異，依既有授權只改approval approved=true；不得用另一個新root重複送同一case。若有submission intent或jobID，先查既有提交，禁止盲目重送。solver已完成而收集失敗只collect-only；全部raw保留。回本機outbox報jobID、84trial、全部固定讀點、summary/measurements/tran完整SHA與資源。只把去識別summary及合規無deck程式存repo；ZIP/deck/model/PSF留批准OneDrive/Olympus。

C2已提交為 **761525（0-94%3）**，前三案RUNNING；submission receipt SHA `98ad47d4a8dfdb1964623373a39e4bc9ebdffcad156616be1ee87540fa74b97b`。原2144訊息仍留頂層inbox、waiting_runs/jobs=['761525']，由既有poll續看，不重送或取消C2。新短案用本則自己的task追蹤並優先回報，不把SAR7與C2併成需等53小時才回報的集合。C2可跨SAR7截止繼續原已授權批次。
