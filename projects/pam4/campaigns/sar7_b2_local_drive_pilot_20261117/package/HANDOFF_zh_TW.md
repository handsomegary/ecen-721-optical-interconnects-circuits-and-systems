# SAR7 case20：b2 局部接受參考驅動與尾端比較預算

只有一個 physical TT case `sar7_20_tt_175gs_b2_local_drive`，由 immutable case19 生成。父包 manifest `29234008ed5dcc04727ec9200c5a1e3b63c57fd8a589bec971b304eae319934d`、portable deck `13cb54f364340ce86656e3f1b7280f53fa69f11d996ae55ac65b5ee2b63f8d73`、來源 job761674；完整 summary `bb7c5418c967d1b7e76d31e93e6dea64115e7888660b521cca797292c35e1594`。執行包和原始 pins 保留在批准 OneDrive/Olympus；不修改父包。

## 已量到的瓶頸與可否定假設

Case19 在565ps有12個 registered code 可讀、7錯／總誤差7／max1；comparator只有10碼、82/84原read有效。未解析的是 conv8b1，以及新增的 conv7b0。CM和physical565讀窗通過，整體screen仍 FAIL，不能把逐碼max1當作已達標。

conv8b2已在EVAL47ps內解析成0，卻在release後經O→transition→Z，Z四個控制端20/80命令直到下一b1 compare之後約6.32ps才成立。這是實際命令rail觀察，不是以50%gate或底板中點代替類比建立。其qdecodep保持低，但Z的三串P及互補INV仍有延遲；qdecoden較晚不能被當成Z唯一原因。conv7b2判1時，qdecodep在read47ps約0.697V、release49ps約0.813V；提前release會使正確O產生毛刺，因此本包不採只憑raw已解析就提前release的修法。

只在b2的real及dummy局部控制cell，把整個OAI／NOR及其互補INV驅動加倍，qbuffer第二級INV2→INV4（p/n兩路）。TG開關與CDAC尺寸不動；14路raw q直接看到的第一級INV1不動；其他bit控制cell不動。這使負載較大的參考控制端驅動更強，同時承認第二級buffer加大會增加第一級輸出負載，可能讓qdecode更晚並重現O毛刺。它不是把先前全bit refpath2／TG倍率掃描重跑。

簡化外部RC代理估計只有約5.2ps加速，還忽略intrinsic C與qmid可能約4ps額外延遲；不能宣稱必定抹去6.32ps遲到，也不能當成預測會過。此單案的判別量是：conv8b2→b1接受Z是否提早、底板／held／sense是否跟上；conv7b2的qmid、qdecode、接受O是否因新增負載變晚／出現bubble。若前者沒有改善，或後者惡化，拒絕「局部驅動足夠」假設，不自行升成4倍或繼續掃倍率。

## 固定預算：MSB捐2ps給b0

Case19全部12次MSB原始q都在33ps內到rail，原EVAL39的最小餘裕6ps。MSB EVAL39→37捐2ps，保留launch78與compare108，不以更早MSB clock改變初始輸入；b0 EVAL46→48，覆蓋來源conv7b0在46ps無效、48ps已有效的已知界限。這不是聲稱精確交越點在46.25或47ps，也不保證新軌跡仍相同。

MSB提早release2ps可能在qdecode尚未rail時產生O短暫毛刺：來源最晚qdecode50%為39.764ps，會晚於新release39ps。來源MSB接受命令距b5compare的最小餘裕30.679ps，且b5 WAIT45ps，這讓本次有限預算交換有依據；仍須重新檢查全部12個MSB、b5類比建立及逐碼結果，不能用raw餘裕直接證明CDAC狀態安全。

WAITS `[30,45,25,26,31,8,6]`；EVALS `[37,44,40,40,47,44,48]`；guard midpoint0.5ps，release read+2ps。

|bit|trial launch|compare|read|release|
|---|---:|---:|---:|---:|
|6|78|108|145|147|
|5|145.5|190.5|234.5|236.5|
|4|235|260|300|302|
|3|300.5|326.5|366.5|368.5|
|2|367|398|445|447|
|1|445.5|453.5|497.5|499.5|
|0|498|504|552|554|

單位ps，皆為midpoint。1ps trial rise仍從前一read開始，midpoint overlap1.5ps，完整邊緣相交區間2.5ps。b2 release到b1 compare仍6.5ps，沒有額外WAIT補貼掩蓋驅動效果。最後read552／release554、registered565、571.428571ps週期、conv558／reset566／clockoff568／track569、輸入與save均維持。Budget為wait171+eval300+guard3=474ps。

## 文獻對照與適用限制

[Ramkaj等，IEEE JSSC，10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823) Section III-B/III-D討論switch RON與寄生RC建立、comparator到CDAC memory路徑負載及延遲。本包針對量到的接受參考路徑，不把gate50%當成建立完成。該原型為28nm／1V／triple-tail／USPC，1.25GS/s及800mVppd；其機制可借鏡，電路、速度與條件不能直接照搬。

[Bheemisetti等，IEEE JSSC，10.1109/JSSC.2024.3449115](https://ieeexplore.ieee.org/document/10723273) 的3nm／0.65V／320mVppd、bottom-plate-ready與DTFB提示應分開量測比較完成和CDAC狀態。沿用已讀primary文字／圖說的ready、CDAC及comparator章節；本輪重開IEEE原始頁仍遇JavaScript驗證，Ramkaj DOI頁工具亦未成功開啟。沒有把未取得的圖像當作已視覺核對的電晶體接線。兩文的DNL/INL及FFT驗證不能由12個固定中心碼替代。

[Um等，A-SSCC，10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608) 的offset-first與split-CDAC權重隔離仍是靜態替代原因的基準；本包不擬合權重、不重跑校正。先前電流峰值與單一初始符號都未排除offset或kickback。

## 原gate、collector與授權

正式screen不變：84原read全解析；12個cmp/reg都可讀且一致；max絕對誤差≤1、wrong≤6；active552與post565均|ΔCM|≤10mV；physical565讀窗有效。strict零錯logic_smoke另報。原20/80 classifier不改；晚到rail、release點或內部x/y不替代原read。

沿用case19已驗證的完整selected-parser，required涵蓋144 saved/time/trial/clk nodes，自訂summary共用一次PSF解析，既有基本measurement另有原解析。回歸必須走完整case20 84trial／72boundary，不只直接helper；initial None邊界另列不可判讀，不能用opposite=0宣稱全部穩定。新summary須用case20 case/schema/manifest/root與正確physical provenance，不改父module全域。

原使用者「Yes, 8 hours」來源SHA `26523d076e396f82acc8844f3441c3517ebba4f05e2073e1629436586287da58`。新stage及accepted sbatch須05:37≤UTC<13:37（Chicago07:37截止）；queued同一job可收完，截止後run須讀scontrol證明exact JobId／期限前SubmitTime及既有stage byte-exact。不得沿用舊05:15 helper。最多1個accepted job／1 solver，1CPU／6GiB／12min，solver540s；SAR總CPU≤2、shared6，保留C2三槽及既有其他專案一槽。不新增長測、PVT、112GS/s整合或其他專案工作。

## 執行及交件

沿用case19完整dependency chain及現有private model root。新payload全部LF後才計manifest、ZIP與sidecar；先verify／unittest／sha256sum。建立真正新mktemp root，必須存在、canonical absolute且basename為`pam4_sar7_b2_local_drive_pilot_*`。approval-template預設false，依既有授權核對exact root/manifest/deck後只改approved=true；stage成功、精確deck diff及資源核對後才提交一次。accepted job即使setup失敗也先回報，不自行重送。

環境變數使用`PAM4_SAR7_B2_LOCAL_DRIVE_PACKAGE`、`PAM4_SAR7_B2_LOCAL_DRIVE_ROOT`、`PAM4_SAR7_B2_LOCAL_DRIVE_APPROVAL`，父包`PAM4_SAR7_COMPARE_WINDOW_PACKAGE`仍指原case19，其他rendering dependencies不變。先用下列命令，stage/run/collect-only另提供`--root`、`--approval`，stage另給既有`--model-root`：

```bash
python3.11 -B "$PAM4_SAR7_B2_LOCAL_DRIVE_PACKAGE/sar7_b2_local_drive.py" verify
python3.11 -B -m unittest discover -s "$PAM4_SAR7_B2_LOCAL_DRIVE_PACKAGE" -p 'test_sar7_b2_local_drive.py' -v
```

回報solver狀態、job／SubmitTime／耗時／CPU、input before/after與summary/measurement/raw hashes，完整84/12及所有固定讀點。重點逐項報conv8b2→b1的raw/mid/decode、四控制rail、Z接受時間與held/sense；conv7b2的O毛刺／qdecode；conv7b0新的48ps讀取；全部MSB37ps可用與b5建立。不能只報改善，達標就停，不自行開case21。

把原byte完整`sar7_b2_local_drive_summary.json`、`measurements.json`、`run_status.json`、Slurm收據及SHA256SUMS一併複製到批准OneDrive `outputs/PAM4_SAR7_B2_LOCAL_DRIVE_PILOT_20261117_RESULTS/`，核對fullSHA/bytes再回outbox，避免compact資料不夠再次分析。Repo只去識別compact分析，不放deck、PDK、模型、RAW、私人email。

Claude遠端發布前依最新AGENTS作一致中性別名及待推送歷史／分支／檔名／程式／網表／文件／PDF檢查，保留節點、尺寸與架構；實際專用模型與別名表在repo外，原execution pins不改。Codex不git。改寫過歷史的repo不pull/merge舊歷史；不操作其他repo。

RAW依新版規則與已核對的後續獨立授權：分析完成、必要輸出核對且完成最後分析/commit後才處理本輪暫存RAW／RAW壓縮副本；執行中、未分析或仍作參考的來源先保留。07:37不是無條件刪除點。Batch ZIP屬可重現輸入，不能誤當RAW壓縮副本；歷史metadata/inventory不重寫。本包不執行清理。C2 761525及2144 waiting_runs原任務不取消、不重送、不改評分；不更改poll、唯讀transcript monitor或steering。
