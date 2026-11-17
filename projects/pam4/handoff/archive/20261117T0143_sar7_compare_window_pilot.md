Stage: SAR7 case19：固定週期內延長b2/b1比較窗，測late-valid與接受reference歷史
ZIP: ECEN721_PAM4_SAR7_COMPARE_WINDOW_PILOT_20261117.zip（OneDrive ECEN720/outputs）
SHA256: ff552f5285fa6930788d2036ddfa62c164d17570b60a85871fecdde77e067992
Guide: OneDrive ECEN720/outputs/PAM4_SAR7_COMPARE_WINDOW_PILOT_20261117/HANDOFF_zh_TW.md
Recommended: 唯一case sar7_19_tt_175gs_compare_window；精確case18電路只改12pulse，核對完整collector回歸及07:37授權後送單案
Resources: 1個新solver、1CPU／6GiB／Slurm12min／solver540s，估4–7min與120–180MB raw；SAR總CPU≤2、C2保留三槽、accountQOS6CPU
Commit allowed: handoff + results
Needs user decision: no

## 證據與授權

0126只是既有檔案回傳，無job/parse/solver；完整case18 summary與receipt原bytes已核對，分別為`121d50d9324627f4326149b17217f49dbbd9e4113076cced38919ac6127cca19`與`0ef32f07eb1c4c0d7c1b336605a8c204d977edefa06f151a3594caf9a7204f4f`。本包依原「Yes,8 hours」05:37–13:37UTC／Chicago07:37截止授權執行，不重問。原2337授權SHA26523d076e396f82acc8844f3441c3517ebba4f05e2073e1629436586287da58固定，新stage/SubmitTime proof仍用13:37，不用舊05:15。只有一個新case，達標停修，不推112GS/s/PVT或新增長測。

Case18在原read有4bit未解析：conv7b2/b1、conv8b2/b1。已知有效點分別為38.5、43、46.5、43ps；c8b2在+41仍無效，不能用已解析80bit的44.82ps最大值替缺失bit定上限。Reg12碼max1但7錯、cmp10/12，原screen仍FAIL。兩個prior-latch初始None邊界不能被opposite=0掩蓋；可判讀極性與不可判讀的分母要分開。

## 唯一時序預算變動

物理來源是精確case18（原manifestdf3b60ef048c03175e2e07a0d02f5f971bd0840708b9ea85ac2235fff1e0079d，portable63c73525a64b0136c66b2aa145da340386492ca5187082d295524213d2fe6aeb）。所有MOS/TG/CML/decoder/qbuffer/register/CDAC/參考/刺激PWL/save不變，只改12條pulse（b6到b1的trial+clock）；b0卡片完全相同。

MSB wait42→30回收12ps；b2 EVAL38→47用9ps，b1 EVAL41→44用3ps。其他wait/eval不動，guard midpoint0.5ps、release read+2、1ps上升沿從前一read開始均不變。這是一次固定比較窗/接受歷史的實驗，不掃倍率、不另外加b1 WAIT小調整。

| bit | launch midpoint | compare | read | release midpoint |
| --- | ---: | ---: | ---: | ---: |
|6|78|108|147|149|
|5|147.5|192.5|236.5|238.5|
|4|237|262|302|304|
|3|302.5|328.5|368.5|370.5|
|2|369|400|447|449|
|1|447.5|455.5|499.5|501.5|
|0|500|506|552|554|

WAIT=[30,45,25,26,31,8,6]，EVAL=[39,44,40,40,47,44,46]。最後b1 read499.5與全部b0/552/554/565、571.428571ps週期、conv558/reset566/clockoff568/track569皆不變。b0原最小1.18ps餘裕不再挪用。

MSB捐時間依據是receipt實測12碼在launch+30的sense皆與原MSB極性一致，最小|sense|約3.036LSB／2.37mV；不是假設22ps就安全。較早clock仍會改變後段軌跡，MSB39ps比較窗可能重新變薄，必須實測所有12個MSB。這是為覆蓋已知最晚46.5ps而選的12ps預算，不是保證新47ps一定夠。

延長b2 eval也延後trial release／下一trial，可能讓原本late qdecode在release前就緒並減少接受O的錯誤中間狀態；接受Z在release後的P路延遲仍須量測，不能推稱一定改善。conv7b1的原held/sense建立同時受前一b2接受reference影響，EVAL延長不保證修正7個錯碼，故仍不變更wrong≤6門檻。

## 文獻與正式判讀

[Ramkaj，IEEE JSSC DOI10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823) SectionII-B／III-D的semi-asynchronous比較／DAC時間共用與接受路徑說明這個預算交換機制；其28nm／1V triple-tail+USPC和實測1.25GS/s並非我們的固定時序StrongARM+CML。[Bheemisetti，IEEE JSSC DOI10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) 的3nm／0.65V／320mVppd、bottom-plate-ready與DTFB提醒readiness須看實際狀態，不能只看gate50%。[Um，A-SSCC DOI10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608) 的offset-first/權重隔離保留為靜態替代診斷，本包不擬合CDAC。

已優先查IEEE原始頁，Xplore目前JS驗證及部分PDF403限制已記錄；沿用已讀作者原文之章節／圖說，不臆測未見電路圖。兩文實際DNL/INL/FFT驗證也不由12固定碼替代。新案的鑑別是四個late bit是否在原新deadline到有效rail、下一trial前xy與q是否就緒、O/Z接受過渡是否離開下一compare；若MSB新增缺值或極性錯誤，表示捐時間不可用，不能只報中段改善。

原screen不變：84原read全解析、12cmp/reg可讀一致、max≤1、wrong≤6、active552與post565 |ΔCM|≤10mV及有效565讀窗；strict零錯logic_smoke另報。不降低20/80 classifier、不改case18原結果、不把late release值當原read通過。Gate/底板中點、初始None與決策起點的限制都保留。

## 交件與執行

Manifest `29234008ed5dcc04727ec9200c5a1e3b63c57fd8a589bec971b304eae319934d`。Linux payload已LF bytes後才計manifest；先驗ZIP/sidecar/manifest/verify/tests，stage對case18精確12pulse diff，再依現有授權只改template approved=true。提交前先檢查output/root已存在、canonical prefix與參數；已接受job即使setup失敗也回報，不自行連續重送。新root/approval綁CASE19/AUTH，截止前成功sbatch ID才算提交；期限內排隊的同一job可收完，收集失敗只collect-only。

新collector納入已驗證的full saved-signals union，完整selected-parser回歸必須跑到CASE19 84trial/72boundary。Extended summary各診斷共用一次PSF解析；既有基本measurements另有原先解析階段，不能宣稱整個物理job總共只parse一次。極性可評估與初始None不可評估邊界分開列數，不能把None當作無flip證明。

完成後請把**原byte完整summary與收據／parse診斷**一併複製到批准OneDrive `outputs/PAM4_SAR7_COMPARE_WINDOW_PILOT_20261117_RESULTS/`，核對bytes/fullSHA再回outbox，避免只留repo compact而缺少下一輪分析資料。回報全部84/12／全部固定讀點、MSB12碼、4原問題bit的xy/raw80%rail實際交越、b0餘裕、O/Z/reference_path、before/after hashes及資源。Dense或完整phase資料留OneDrive/Olympus；repo只compact去識別版本。

新版AGENTS生效：Claude遠端發布前，對待推送歷史/分支/檔名/程式/網表/文件/報告/PDF作一致中性別名檢查，保留節點、W/L、尺寸及架構；實際授權模型、專用名與別名表repo外，原執行包與pins不改。改寫過歷史的repo禁止pull/merge舊歷史，按新版fetch與reset/rebase-only-own-commits處理；Codex不git、不操作其他repo。本發布授權不追溯改寫前0126資料回傳的Commit allowed:no。

RAW依新版規則：可重現輸入與分析輸出/收據/校驗保留；本輪分析完成且必要輸出核對後，按實際授權處理暫存RAW及RAW壓縮副本。仍在執行／待收集／需作本輪參考的來源不能先清；07:37不是無條件刪除時點，還要完成最後分析/commit。Batch ZIP是輸入套件，不是待刪RAW壓縮備份，不能誤刪；metadata/historical raw_inventory不能重寫。

C2 761525／原95案/0-94%3與2144 waiting_runs不動，不取消或重送；本案1CPU且提交前核對shared6CPU、SAR≤2並保留C2三槽。此短task先回，不與C2合併53小時等待；不改poll/transcript monitor/steering。完成後回Codex，達標停止，不自行開case20或整合。
