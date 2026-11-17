Stage: SAR7 case21：凍結case20全部電路，唯一接受參考時序對照
ZIP: ECEN721_PAM4_SAR7_ACCEPT_GAP_PILOT_20261117.zip（OneDrive ECEN720/outputs）
SHA256: 4e319b89c3e98ac8d27e2ad6a5bb7aeaf0480b24b2b2bec2a4711dfefc6827f0
Guide: OneDrive ECEN720/outputs/PAM4_SAR7_ACCEPT_GAP_PILOT_20261117/HANDOFF_zh_TW.md
Recommended: 只送sar7_21_tt_175gs_accept_gap；verify/tests、exact10pulse-only diff與13:37UTC既有授權核對後提交一次
Resources: 最多1accepted job／1solver，1CPU／6GiB／Slurm12min／solver540s；估4–7min、120–180MB raw；SAR總CPU≤2、shared6，保留C2三槽
Commit allowed: handoff + results
Needs user decision: no

## 本輪決策與來源

0322已讀且原byte核SHA；job761688為83/84解析、565reg12碼7錯／Σ7／max1、cmp11碼，CM/windowpass而screenFAIL。接受Z只快2.25ps仍晚4.07，qmid/qdecode負載懲罰已量到；拒絕驅動2倍足夠，不升倍率。全部12個donor及7個Z接受run已核對，Guide列明窄餘裕和正確O bubble風險。

只改10pulse，把E6 37→35與E2 47→44省2+3ps，給W1 8→13；b2release→b1compare6.5→11.5。全部MOS/CDF/instance/其他物理設計、b1compare453.5/read497.5與b0全段498/504/552/554不變。最小來源raw名義餘裕MSB2.000／b2 1.929ps；7個Z最慢10.643ps，新gap僅名義0.857ps命令rail餘裕，絕不等於類比建立保證。

原8h「Yes, 8 hours」授權仍至Chicago07:37／13:37UTC；限此單案。這是本時序分支最後一次對照：若Z及時仍未過，否定late-Z-only充分解釋；若新O bubble/donor失敗或Z仍晚，也停此分支。達標也停。禁止自行case22／小幅掃參／改gate。所有原84/12、max1、wrong≤6、CM及讀窗門檻保留，不把只解析當作收斂。

0252 needs_user是平台分類器核准阻擋，0322明確取代並記錄使用者在互動session處理後已stage/提交同root/ZIP/manifest/deck。原8h本已涵蓋approval=true，本輪不重問已授權設計；舊0252原bytes保留歸檔，不改yes header。新案仍走正常exact approval流程，若平台再拒絕就回實際阻擋，不繞過／移除guard或反覆重試。

Manifest `40a490ab88adfb1bbc370e52f80ced9bfd7954f5be56e3adc93dfcb8f51d650b`；LF／inventory／ZIP／sidecar核對、verify/unittest及獨立審查已通過。以下Guide全文亦在ZIP；依其中原論文對照、精確差異／正常核准／stage／資源／截止及完整結果交件執行。新root須先存在與canonical，accepted job即使setup失敗也先回報，collect問題只collect-only。C2 761525與2144waiting不動；無Codexgit/queue/他repo/monitor/poll改動、無本包RAW清理。

## 套件Guide全文

# SAR7 case21：凍結電路的接受參考時序對照

唯一case `sar7_21_tt_175gs_accept_gap`，由原case20精確生成。父manifest `2887bf0705fb20245f65d8745abdd01624debb53b2aa8bdf7c7c5564adad84e1`、portable `c587a30cf264dc2b815bd9f23b057ce15edeed9b59591edcfe2370a403f3bfbf`、job761688。完整原summary SHA `83d41a50aeea4285dbecf922deb94f949c2a4265cc2a8ce3d6acda4d7b7682a3`，3,397,472B；measurements SHA `5e90957dc9dfec995cf647e80f25347433ca4c776d041f007fdcbc2c34020161`。本機原byte與來源核對，不更動父包／原結果。

## 為何只做這一案

Case20改善至83/84原read有效，conv7b0已在48ps解析成0、餘裕1.75ps；MSB全部37ps有效、最小4ps，b5結果不變。565 registered12碼、7錯／Σ7／max1；cmp11碼、6錯，conv8b1仍None，CM及physical565讀窗pass但整體FAIL。

b2局部2倍驅動使conv8接受Z只提早2.25ps，release到完整四控制rail命令10.5714ps，仍比b1 compare晚4.0714ps；qmid/qdecode卻增加1.9–3.6ps延遲。因此拒絕「局部驅動2倍足夠」的假設。本包不加大／回退任何元件，也不掃倍率。

唯一新假設：保持電路、b1 compare/read與全部b0時程不變，把前一b2較早釋放並增加b1的WAIT，可使接受參考先成立並減少跨比較窗的輸入瞬態。這不是假定gate rail成立等於CDAC／sense已建立。若接受Z已及時成立而c8b1仍未解析／錯誤，就否定late-Z足以解釋故障；若仍未及時成立，則此固定預算本身不夠。兩種失敗均停止這條時序修法，不自行開case22、繼續小幅調參或升倍率。若原screen達標也立即停止。

## 捐時依據及精確時程

全部12個MSB raw stable最大33.000ps，EVAL37→35留下已觀察最小2.000ps。全部12個b2最大42.0714ps（conv8）、其他皆≤38.5ps，EVAL47→44留下最小1.9286ps；新b2 trial fall開始於compare+45.5ps，仍比來源最晚有效點晚3.4286ps。兩個來源餘裕是受控測試的依據，不保證新輸入／接受歷史完全相同。

兩者省2+3ps，給b1 WAIT8→13。EVAL `[35,44,40,40,44,44,48]`、WAIT `[30,45,25,26,31,13,6]`；guard midpoint0.5ps，release仍read+2ps。

|bit|launch|compare|read|release|
|---|---:|---:|---:|---:|
|6|78|108|143|145|
|5|143.5|188.5|232.5|234.5|
|4|233|258|298|300|
|3|298.5|324.5|364.5|366.5|
|2|365|396|440|442|
|1|440.5|453.5|497.5|499.5|
|0|498|504|552|554|

單位ps／midpoint。WAIT176+EVAL295+guard3=474ps；第一launch78到末read552完全相同。b1 compare453.5／read497.5／release499.5不變；b0全部498/504/552/554不變。b2 release到b1 compare從6.5→11.5ps。套用conv8來源Z延遲10.5714ps，僅剩名義0.9286ps命令rail餘裕，絕不稱已滿足1LSB建立。

conv7b2的qdecode50%來源48.440ps，會晚於新release46ps約2.44ps；可能產生正確O的bubble。新b1 compare在前一b2 compare+57.5ps，距該已知qdecode50約9.06ps，也不是已證明O能到rail。MSB八個O的qdecode50%為33.446–40.354ps；新release37ps會比最晚半電源點早3.354ps，須重新核對全部raw、qdecode及接受歷史。七個b2判0的來源接受Z均晚於下一compare，最晚release後10.6429ps（conv9），新gap只留下名義最小0.8571ps；不能只挑conv8報告。

conv8b1原sense在compare／+5／+10／+15ps為−0.018／−0.192／+0.349／+0.706LSB，held也由負轉正。Z略快而原read更慢，不能就此宣稱offset主導；新trial launch與clock相對瞬態也會改變。須實測全部84bit與12碼，不能套舊軌跡保證通過。若只解析而conv8仍41或43，registered仍可能7錯；wrong≤6原門檻不動，prefix變動後b0也要重驗。

## 必須是純時序差異

對case20恰10條pulse變動：trial1至trial6共6條，clk2至clk5共4條；clk6／clk1／clk0和trial0均不變。全部MOS/CDF/subckt/instance與端點、b2局部2倍驅動、qbuffer第一／第二級、TG/CDAC、CML、register、參考／輸入／save逐byte不變。不另改b2 release相對自身read+2，沒有pulse邊緣斜率調整。

1ps trial rise仍從前一read開始，midpoint overlap1.5ps、完整相交區間2.5ps。571.428571ps週期、conv558／reset566／clockoff568／track569、registered565與diagnostic563/554/557不變。

## 原論文對照與判別

本輪重讀[Bheemisetti等的作者原文，DOI10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) SectionIII-A及Fig4–5文字／圖說：後續比較須留足DAC建立，原型從底板切換後產生ready；加大NOR會增加comparator負載。這支持量測接受參考及比較啟動的相對時序，並符合case20的負載懲罰。它是3nm、0.65V、DTFB與bottom-plate-ready；本案28nm、0.9V、CML隔離及固定pulse不同，不把此10pulse對照稱為原型的fully-asynchronous實作。圖像擷取仍Cache miss，IEEE頁仍JS驗證；已讀作者全文而不臆測未見接線。

[Ramkaj等，DOI10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823) SectionIII-B/III-D的switch RC及comparator→CDAC memory負載仍作機制對照；[Um等，DOI10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608) 的offset-first／split-CDAC權重隔離保留為靜態替代原因。本包不做新拓樸、權重或offset校正。12固定中心碼不能替代原論文的histogram、DNL/INL、FFT、噪聲或PVT驗證。

## 原screen與完整collector

原gate不變：84原read全解析、12個cmp/reg都可讀一致、max絕對誤差≤1、wrong≤6、active552和post565均|ΔCM|≤10mV、physical565讀窗有效；strict零錯logic_smoke另報。20/80 classifier不改；late rail、release點與x/y不能替代原read。

沿用已驗證full selected-parser：144 nodes，完整case21 84trial／72boundary回歸及正確case/root/schema/manifest/provenance。避免巢狀factory仍綁case20／19的全域；父module身份不被修改。自訂summary共用一次PSF parse，既有basicmeasurement另parse；不稱整job只parse一次。初始None另列不可評估，opposite=0只適用可評估分母。

## 授權、資源與執行

既有「Yes, 8 hours」，source SHA `26523d076e396f82acc8844f3441c3517ebba4f05e2073e1629436586287da58`，新stage／accepted SubmitTime必須05:37≤UTC<13:37（Chicago07:37截止）。本包只有1個accepted job／1solver，1CPU／6GiB／Slurm12min、solver540s，估4–7min及120–180MB raw。SAR同時CPU≤2、shared6，保留C2三槽及既有其他專案一槽。沒有新長測、PVT、112GS/s整合或其他專案工作。

核對LF／ZIP／sidecar／manifest、verify與tests；使用全新已存在、canonical absolute、basename符合`pam4_sar7_accept_gap_pilot_*`的mktemp root。approval-template預設false，依既有授權核對exact root/manifest/deck後核准。先stage與精確10pulse diff，確認資源後只sbatch一次；accepted job即使setup失敗也先回報，不自動重送。截止前未成功提交則不開新案；已提交同一job可收完，截止後run須exact JobId/SubmitTime證明與既有stage byte-exact。collect-only不重新stage或solver。

沿用case20完整dependency env和既有private model root；新增`PAM4_SAR7_ACCEPT_GAP_PACKAGE`、`PAM4_SAR7_ACCEPT_GAP_ROOT`、`PAM4_SAR7_ACCEPT_GAP_APPROVAL`；`PAM4_SAR7_B2_LOCAL_DRIVE_PACKAGE`指向原case20，父鏈其他變數不變。

```bash
python3.11 -B "$PAM4_SAR7_ACCEPT_GAP_PACKAGE/sar7_accept_gap.py" verify
python3.11 -B -m unittest discover -s "$PAM4_SAR7_ACCEPT_GAP_PACKAGE" -p 'test_sar7_accept_gap.py' -v
```

approval-template／stage／run／collect-only需`--root`與`--approval`；stage/run另給既有`--model-root`。前一次0252平台核准阻擋已由0322明確取代、並完成761688；這不是未回答的設計選項。仍沿用合法核准流程，不改平台權限或核准機制；若平台再拒絕就回報實際阻擋，不反覆重試或繞過。

## 必交結果與停止條件

回報job／SubmitTime／solver／CPU、input before/after、summary/measurements/status/raw fullSHA及bytes。全部固定讀點／84bit／12碼照原gate；全部12個b2的raw／qmid／qdecode／postrelease接受O/Z runs、next-compare前命令rail餘裕與held/sense；MSB35ps及b2 44ps餘裕；conv7b2 O bubble；conv8b1原read與其後b0。不能只回conv8一條trace或只報改善。

把原byte完整`sar7_accept_gap_summary.json`、`measurements.json`、`run_status.json`、Slurm收據及SHA256SUMS複製到批准OneDrive `outputs/PAM4_SAR7_ACCEPT_GAP_PILOT_20261117_RESULTS/`，核對fullSHA/bytes後回outbox。Repo只去識別compact分析，不放deck、PDK、模型、RAW或私人email。

結果到此案為止：達標停止；若Z及時但仍失敗，停止late-Z-only分支；若新O毛刺／donor失敗／Z仍晚，也先停止此固定預算分支。不要自行case22／掃倍率／改gate。不能把12中心碼通過說成全面ADC指標或reference paper已完全重現。

Claude發布前依最新AGENTS做一致中性別名及待推送歷史／分支／檔名／code／netlist／docs／PDF檢查，保留節點／尺寸／架構；實際模型與alias表repo外、原execution pins不改。Codex不git；改寫歷史不pull/merge舊分支，不操作其他repo。

RAW依新版政策及已核對的獨立授權，分析完成、必要輸出核對且最後分析/commit完成後才處理暫存RAW與RAW壓縮副本；執行／未分析／仍需參考的來源先保留。07:37不是無條件清理點；batch ZIP是可重現輸入，不能誤刪；歷史metadata/inventory不重寫。本包不清理。C2 761525及2144 waiting_runs不取消、不重送、不改評分；poll／唯讀transcript monitor／steering不改，不用Codex queue。
