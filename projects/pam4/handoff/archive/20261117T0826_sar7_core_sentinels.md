Stage: SAR7文獻後的新方向：固定輸入核心能力診斷case22，非ADC通過版本
ZIP: ECEN721_PAM4_SAR7_CORE_SENTINELS_20261117.zip（OneDrive ECEN720/outputs）
SHA256: b97915740e27560c5fd4b0c4a62e779edeb6e76408b0a37c40058b3ad4637084
Guide: OneDrive ECEN720/outputs/PAM4_SAR7_CORE_SENTINELS_20261117/HANDOFF_zh_TW.md
Recommended: 唯一sar7_22_tt_core_sentinels；正常approval/stage/exactdiff與C2單槽lease核對後送一次，收完恢復C2五槽
Resources: SAR7最多1CPU／1job；本包1accepted job／1solver，6GiB／Slurm12min／solver540s，估4–7min與120–180MB raw；僅暫將C2 761525 throttle5→4，完畢恢復5，共用6CPU
Commit allowed: handoff + results
Needs user decision: no

## 新授權與方向決策

0755原文已讀，SHA `d9491abfb1429caf097c1c798d763d6529264fb3fa9cbbf2b82cd78b0d4183ea`。authorization_basis是使用者原話「SAR7如果一直修不好你叫codex看看相關論文 然後也可以換方向 由codex決定」。本則已直接涵蓋短pilot、正常approval=true及指定C2暫借一槽，沒有舊13:37時窗截止。前一8h授權及case21時序分支仍維持已停止，不把它們重新開成無限clock微調。

論文比對後，完整DTFB／bottom-plate-ready及reference/reset移植屬大改，尚不直接動手。本案先分開測「現有核心固定輸入能力」與「實際sense在再生期間變動」。視覺核對的是作者Schinkel ProRISC Fig2，不冒稱已看Bheemisetti原電路圖；IEEE/作者原文DOI、條件、驗證與取得限制在Guide。本輪可一併取得合法原PDF圖像並回存OneDrive，失敗照實記錄，不阻這個保留核心的夾具。

只有7個XCMP輸入對改接2個stiff PWL sources及save+2，其餘case20全部physical/timing保持。12frame是6組反極性5mV預置→target，target為±48.828125µV／±1LSB／±5mV；84筆中42target＋42預置。source20 MF2887bf…84e1與summary83d41a…682a3均重核；觀察VCM來自source21 summary7b9359…ea851。舊RAW已報退休，本包不讀它，也不重跑舊案。

原ADC gate不變，本夾具的analog ADC score明確N/A；不用舊expected centers硬算新codeerror，不能把固定輸入通過當SAR通過。新collector只解析新案一次146nodes，逐筆核對actualinput/reset及internal/raw/qmid/qdecode originalread／44／48／60，保留缺值與分母，早glitch或晚到不能替代原raw。

56筆5mV強控制須有效；14筆1LSB分開判斷是否具固定名義LSB解析能力，14筆nearzero只量敏感度，不能單憑48µV失敗宣判架構不可行。此1LSB只是0.1/128V的固定probe標尺，不等於實際CML動態輸出的一LSB；固定probe通過也不排除更低實際overdrive的核心限制，不改原input規格來追論文。判別與停止條件事先固定在Guide。本包一案後回Codex，不自動case23／掃參／換DTFB。若往後須大改或長測，依0755寫成本／選項、Needs user decision:yes；沒有新的C1/C2長測、全PVT或112GS整合。

Manifest `7ad4e96bdeef35253a6632700592c090b05c3ea5de6e73523d09569da0930473`；verify／兩組tests／獨立review及LF/ZIP/inventory/sidecar核對通過。C2 helper只操作761525 throttle的5→4→5，綁正常approval與本包lease；pending不會中斷現有C2，SAR退出含失敗須恢復。若原值非5／外部改值／restore失敗，回實際狀態，不覆蓋、不改其他C2或job。新accepted job即使setup失敗也先回報，不連續重送；收集失敗只collect-only。

完成請直接把原byte完整診斷資料、execution/parse收據、C2 begin/restore收據與fullSHA/bytes送到OneDrive outputs/PAM4_SAR7_CORE_SENTINELS_20261117_RESULTS/，不要只回compact。資料夾與完整Guide如下；C2評分/seed不動，Codex無git/queue/其他repo/monitor/poll/steering操作。新RAW仍診斷中先保留，分析完成且不需再看後才依既有政策退休；本包不清理。

## 套件Guide全文

# SAR7 新方向：固定輸入比較器能力診斷

唯一case `sar7_22_tt_core_sentinels`，一個1CPU短job。這是有完整現有負載的比較器輸入夾具，不是新的ADC通過版本；不延續case21的pulse微調，也不照未見的DTFB圖直接重畫。

## 新授權與既有證據

使用者07:55原話：「SAR7如果一直修不好你叫codex看看相關論文 然後也可以換方向 由codex決定」。來源`20261117T0755_user_delegates_sar7_papers_direction.md`，SHA `d9491abfb1429caf097c1c798d763d6529264fb3fa9cbbf2b82cd78b0d4183ea`。這則直接授權論文比對、方向選擇、短pilot及正常approval=true，**沒有時窗截止**；不沿用已過期的05:15／13:37 guard。新stage／實際Slurm提交需在2026-11-17T13:55:00Z之後，且case/root/manifest/deck精確綁定。

物理來源是較保守的case20/job761688：manifest `2887bf0705fb20245f65d8745abdd01624debb53b2aa8bdf7c7c5564adad84e1`、portable `c587a30cf264dc2b815bd9f23b057ce15edeed9b59591edcfe2370a403f3bfbf`、summary `83d41a50aeea4285dbecf922deb94f949c2a4265cc2a8ce3d6acda4d7b7682a3`。case20仍FAIL，並非已通過的基準。

case21/job761700的summary `7b93590f85c18b85b1cca6dae343d5e550d7b582d3922ee01a3fdb57a1eea851` 顯示：83/84原raw讀點解析、唯一conv8b1缺值；內部x/y在84讀點可判讀，raw在44ps為0.702/0.120V、44.5ps才到rail。其sense在precompare約−48µV，+15ps已轉為約+0.569mV。把前一Z命令移到compare前仍不夠，而且出現新的O中斷。這不能證明純靜態offset，也不能證明換更快比較器就會得正確碼；更快的核心可能只是更早判到初始負號。

Claude回報sar7_08至21的已分析RAW已於07:48退休。新包build/verify只用不可變父包及保留JSON，不讀舊RAW、不重跑舊案、不把RAW_RETIRED marker冒充波形證據。

## 文獻比對與取得限制

- [Bheemisetti，IEEE JSSC，DOI10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115)：已讀作者14頁原文。§III-B/Fig6–7文字描述積分／放大首級與自觸發第二級；§III-A/Fig3–5文字的ready取自DAC切換後，並非目前OAI/INV/TG路徑。它是3nm／0.65V，comparator比較條件5mV；不能移用到目前28nm／0.9V及數十µV殘差。IEEE頁JS驗證、PDF圖像Cache miss、browser host unavailable，**沒有視覺核對該文電路圖**。
- [Schinkel，IEEE ISSCC，DOI10.1109/ISSCC.2007.373420](https://doi.org/10.1109/ISSCC.2007.373420)，原文Fig17.7.2可由[校內課程原文](https://people.engr.tamu.edu/spalermo/ecen689/Schinkel_Nauta_ISSCC07_Double-Tail_SenseAmp.pdf)及作者機構取得；本次視覺核對的是[作者ProRISC後續原文](https://ris.utwente.nl/ws/portalfiles/portal/5463411/Schinkel_Prorisc_2007.pdf)的**Fig2(a)/(b)**，不是把後續圖號說成ISSCC原圖。圖中輸入級與再生級分開電流路徑，展示10/200mV波形；90nm／1.2V，18ps是setup+hold，不能當作本平台clock-to-rail保證。
- [Razavi，IEEE SSC Magazine，DOI10.1109/MSSC.2015.2418155](https://doi.org/10.1109/MSSC.2015.2418155)，[作者原文](https://www.seas.ucla.edu/brweb/papers/Journals/BR_Magzine4.pdf)的Fig1–2及負載／再生段落支持分開量測internal與buffered輸出；此文文字可讀，但web screenshot未回傳可視圖像，沒有把成功ref當作已看圖。

可借鏡的是分開檢查輸入幅度、再生與輸出負載；現有證據尚不能在「核心小訊號能力」和「CML／CDAC輸入在再生期間變動」間定案。所以先測現有核心。完整DTFB、bottom-plate-ready及reference/reset共同重設屬大改，若需要走到那一步，另寫具體選項／成本並標Needs user decision:yes。

同輪如能由合法作者公開copy或既有校內存取得Bheemisetti原PDF，可把Fig3–7相關頁render後原bytes／來源URL／DOI／SHA複製到批准OneDrive研究資料夾；不放Git，不繞登入或驗證。取得失敗照實記錄，不阻擋這個不改核心的診斷。

## 唯一根因假設與夾具

假設：目前缺值至少部分來自比較期間的輸入歷史，而非既有核心在固定sub-mV輸入下本就無法於44ps解析。移除輸入歷史後，若1LSB固定差分仍失敗，可再區分internal再生與raw輸出路徑；若通過，便沒有理由只因目前一個缺值就全面換核心。

保留case20的全部7顆原生比較器、CDF/MOS、qbuffer、matched-NOR、register、decoder、TG/CDAC、CML、供應、reference、所有clock/pulse與原12個frame。**只把7個XCMP的前兩個sense輸入端改接diag_p/n，新增2個理想PWL電壓源並在原save加入這2個節點。** 這保持完整負載拓樸；新決策會改變負載狀態，不能聲稱波形與舊SAR逐點相同。

CML與CDAC仍在電路內，卻不再驅動比較器輸入；理想stiff source刻意移除了其輸入歷史、source impedance及kickback回授。這是診斷邊界，不是可發布的ADC隔離實作，也不驗證整體sampling／權重／有效offset。

固定VDD0.9V、common mode0.8346351044855786V（case21 conv8b1 precompare），LSB=0.1/128V=0.78125mV。六個target固定如下：

|target|差分|前一frame預置|
|---|---:|---:|
|nearzero−|−48.828125µV（−0.0625LSB）|+5mV|
|nearzero+|+48.828125µV|−5mV|
|1LSB−|−0.78125mV|+5mV|
|1LSB+|+0.78125mV|−5mV|
|control−|−5mV|+5mV|
|control+|+5mV|−5mV|

依序6組「反極性5mV預置→target」共12frame。每frame7顆core，總84筆，分42筆target與42筆預置；不是六個solver或倍率掃描。PWL於新frame origin+10至+11ps轉換，前一組clock已reset，距最早compare108ps至少97ps，然後保持整個frame。每顆core原有clock及read時程維持；不是把ADC的原read gate放寬到60ps。

## 量測與事先寫好的判讀

新collector一次解析完整saved/time/trial/clk集合加diag_p/n，146nodes；不用原analog ADC scorer產生無意義的碼誤差或screen。保留新case的完整execution evidence／raw inventory／before-after SHA，解析前後均核對。

每筆量actual輸入與common mode、compare−2ps的reset狀態、原read及compare+44/+48/+60ps的internal x/y、raw q、qmid、qdecode及符號。正輸入預期raw p高/n低、internal y高/x低，qmid符號須反向解讀。用原20/80判準，延遲必須是到60ps觀察終點都保持正確rail的最早已觀察時刻；早期glitch不能充數，缺值明列None，不外推精確交越。

- 42筆預置＋14筆5mV target共56筆強控制，應在44ps正確解析且持續到60ps；全84筆reset也必須有效。reset或輸入不符合夾具時，診斷控制無效，先停，不據此判架構不可行。
- ±1LSB共14筆，單列internal/raw的44／48／60ps結果。若均在44ps正確，支持現有核心具固定名義LSB能力；全SAR失敗仍可能來自動態輸入／控制。不能就此宣稱SAR通過。
- 若internal已正確而raw較慢，支持先看輸出負載／buffer路徑；若1LSB internal也慢而5mV控制正常，才有小訊號gain／regeneration方向的依據。一次TT不識別固有mismatch、noise sigma或全PVT。
- ±48.8µV共14筆只用來量near-zero敏感度。單憑這一組44ps失敗，不能判架構做不到或擬合補償值。

本包一案後先回Codex，不自動case23、改bias/VCM/幾何、換DTFB或掃參。原專案84原raw／12cmp-reg一致／max1／wrong≤6／active552及post565 CM／565讀窗目標不變，本診斷不給ADC pass，不計DNL/INL/ENOB。

## CPU、C2暫借一槽與正常核准

新授權規定SAR7最多同時1CPU、1job。C2 761525目前允許5並行，加其他既有專案1CPU已滿6。Claude只可暫把**761525**的ArrayTaskThrottle5→4，讓下一槽給SAR；不停止現正執行的C2。SAR收完／失敗後恢復5；其餘C2內容、score、seed與其他job不改。

套件`c2_slot_lease.py`綁本包manifest／source授權／正常approved root，先記錄不可變lease及命令收據，僅修改指定array的throttle。依[官方Slurm說明](https://slurm.schedmd.com/scontrol.html)，目前throttle通常顯示於`ArrayTaskId=...%N`；不能誤當必有獨立ArrayTaskThrottle顯示欄位。前值不是5、ID/owner/lease不符、欄位不明就停，不猜值或改別的job。

batch的EXIT清理會依自己的lease恢復5；TERM預告留60秒、每次RPC上限10秒。若外部已改成其他值，保留當前值並回報，不覆蓋。若尚未有accepted SAR job就遇到stage／sbatch失敗，Claude立即執行restore並回報，不重送。若job尚在pending，lease保持4以等待下一個可用槽；此新授權無舊時窗截止，可用既有waiting_runs機制收同一job。SIGKILL／node失效可能使EXIT無法執行，因此收job時必須核對restore_verified收據；缺失則明確執行restore核對。restore失敗要明確回報，不能當已恢復。

## 準備／執行與交件

資源1CPU／6GiB／Slurm12min，solver540s，估4–7min／120–180MB RAW；最多1個accepted job／solver。先核對ZIP／sidecar／manifest／LF、verify及兩組unittest。沿用case20完整dependency env與既有私有模型root；父包只能render/verify，不能stage/run或收已退休的舊RAW。

新增環境變數`PAM4_SAR7_CORE_SENTINELS_PACKAGE`、`PAM4_SAR7_CORE_SENTINELS_ROOT`、`PAM4_SAR7_CORE_SENTINELS_APPROVAL`；`PAM4_SAR7_B2_LOCAL_DRIVE_PACKAGE`指原case20。建立真正的新mktemp root，存在、canonical absolute、basename符合`pam4_sar7_core_sentinels_*`。approval-template預設false，按本則已有授權核對exact root／case／manifest／deck後只改approved=true。新runner自行驗證0755授權與提交，不呼叫舊截止helper。

```bash
python3.11 -B "$PAM4_SAR7_CORE_SENTINELS_PACKAGE/sar7_core_sentinels.py" verify
python3.11 -B -m unittest discover -s "$PAM4_SAR7_CORE_SENTINELS_PACKAGE" -p 'test_*.py' -v
```

stage及精確diff成功、尚未sbatch時，才開始借槽：

```bash
python3.11 -B "$PAM4_SAR7_CORE_SENTINELS_PACKAGE/c2_slot_lease.py" begin --root "$PAM4_SAR7_CORE_SENTINELS_ROOT" --approval "$PAM4_SAR7_CORE_SENTINELS_APPROVAL"
python3.11 -B "$PAM4_SAR7_CORE_SENTINELS_PACKAGE/c2_slot_lease.py" status --require-active --root "$PAM4_SAR7_CORE_SENTINELS_ROOT" --approval "$PAM4_SAR7_CORE_SENTINELS_APPROVAL"
```

需要明確恢復時用同參數的`restore` mode。每個mode只核對／更新指定761525；沒有取消或提交C2的命令。

其後依正常approval-template→核准→stage，核對精確7輸入對／2source／save差異，先完成本案prepare再begin C2 lease，最後只sbatch一次。stage/run/collect-only的root、approval及model-root用法沿用既有包；lease helper的`--help`列出begin/restore/status與必要root/approval參數。不要用未建立的out子目錄。所有步驟必須exit0；accepted job即使setup失敗也算本包那一案，先回報，不自行重送；收集問題只collect-only。

完整交件到批准OneDrive `outputs/PAM4_SAR7_CORE_SENTINELS_20261117_RESULTS/`：新診斷summary／measurements、run_status、Slurm紀錄、execution/parse證明、C2 begin/restore lease收據及SHA256SUMS；原bytes/fullSHA/bytes核對後回outbox。必列56強控制、14個1LSB與14個nearzero的可用／錯誤／缺值分母、全部84點，以及internal/raw/qbuffer延遲差和reset。不能只挑conv8或只回compact。完整lease stdout／owner／root與execution收據僅OneDrive/Olympus保存，repo只去識別聚合。文獻圖像若取得，原PDF／render／來源另放OneDrive研究目錄，不放Git。

新RAW在本輪分析完成且Codex確認不需再看波形後才退休，診斷中先保留；保留可重現輸入、分析輸出、歷史inventory與必要收據。batch ZIP是輸入，不是待刪RAW副本。本包不刪RAW。遠端發布前仍做最新AGENTS的一致中性別名檢查，保留節點／尺寸／架構，實際模型名/檔/alias表在repo外；不放deck／PDK／RAW／私人email。Codex不git、不用queue；不改poll、唯讀transcript monitor或steering，不操作其他專案。
