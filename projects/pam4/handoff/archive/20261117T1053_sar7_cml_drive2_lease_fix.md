Stage: SAR7 case23 CML drive2租約工具修正；原電路與唯一短測額度不變
ZIP: ECEN721_PAM4_SAR7_CML_DRIVE2_LEASE_FIX_20261117.zip（OneDrive ECEN720/outputs）
SHA256: 0a588fddb57a781a1d230c5c1962559c159ac2ffc93821b14c6ec194e8742df6
Guide: OneDrive ECEN720/outputs/PAM4_SAR7_CML_DRIVE2_LEASE_FIX_20261117/HANDOFF_zh_TW.md
Recommended: 新root／approval／lease；verify與全部tests、stage精確diff後，沿用sar7_23_tt_175gs_cml_drive2僅sbatch一次
Resources: SAR最多1CPU/1job；原未使用的1accepted-job/1solver額度；6GiB/12min、solver540s；C2僅761525 throttle5→4→5、不打斷running；本地發布等待不佔Olympus資源
Commit allowed: handoff + results
Needs user decision: no

## 處理1002執行阻擋

來源SHA `f0e7e2ddd3410f0f05069afb47e54311c2594ce225b21ba37e894ebbf920e70a`。10/10收據已核對；兩個update的rc1都是同一已完成元素訊息，後續成功查詢證實達到4及5，最後lease inactive。沒有accepted job／solver，尚無電路結果。原0934包與failed root不改。本包只修helper、helper tests及Guide；core、core tests、sbatch、PLAN、AUTH五檔byte不變；deck SHA `ae60badd4499e1b572cfe3aada353a3f62b0ac78578a1142809f071f22b2518b`。新manifest `f98875b1a3f79f86469668c8048730f0a32a12e7286d4a60cffef0c2db872381`，一般approval仍必須重新精確綁定。

既有0755授權SHA `d9491abfb1429caf097c1c798d763d6529264fb3fa9cbbf2b82cd78b0d4183ea`（無到期）涵蓋同一短案與正常approved=true；不建立case24／額外額度。先確認沒有其他case23已接受job，新root與lease，不沿用舊failed intent。尚有已接受job就停止新submit並回報。0934作superseded operational attempt記錄，不重跑。1002來源會由Codex保存至outbox/done。

只允許觀察到的rc1／空stdout／純已完成元素stderr，且必須fresh read核對全部scoped記錄及目標值，才能記錄verified_with_finished_element_warnings；其他錯誤照舊失敗及cleanup。不要手動繞過lease。C2原值5須當下重查，restore證據必交。上游文件與實際收據的適用限制及完整步驟見以下Guide。

本地若達24次／24h喚醒上限，僅延後這一封正常worker publish；不改上限或poll。既有單次網路preflight與原物理停止條件繼續適用。Codex不git／queue／網路設定／monitor。收到後請照Guide完成原短案，不自動其他修法。

# case23 租約 helper 修正；電路與原短測額度不變

本包替代0934交件的執行工具，仍是唯一 `sar7_23_tt_175gs_cml_drive2`。不是case24，也沒有新增accepted-job或solver額度。原core、core tests、sbatch、PLAN與AUTHORIZATION五檔逐byte保留；portable SHA仍須為 `ae60badd4499e1b572cfe3aada353a3f62b0ac78578a1142809f071f22b2518b`。下方原物理設計、論文、判別量及停止條件全部沿用；有衝突時以本節租約修正流程為準。

## 已核對的執行收據

1002回報不是電路結果。原包已stage成功，沒有sbatch／accepted job／solver。原ZIP、manifest、approval、stage與失敗lease都保留不改。10份收據及其manifest已全數驗證。兩次update都回rc=1、stdout為空、stderr完整為 `761525_17: Job has already finished\n`；但各次之後的成功查詢證明全部7筆記錄實際達到4及5。15:59:20.616Z最後查詢為5，lease inactive；本包begin仍必須重新查核當下owner與原值5。

回報中「之後整段C2都會失敗」過度推論：完成記錄可能移除，且既有restore在當下已5會直接驗證返回、不再update。本次只處理實際收據證實的部分成功情形，不推測故障持續多久。

Slurm官方[Job Array文件](https://slurm.schedmd.com/job_array.html)說明整個array的API會提供不同元素的個別結果；[scontrol原始碼](https://github.com/SchedMD/slurm/blob/master/src/scontrol/update_job.c)會逐項輸出錯誤並設exit_code=1，[錯誤字串來源](https://github.com/SchedMD/slurm/blob/master/src/common/slurm_errno.c)列出已完成工作的訊息。這些是目前上游機制的對照，未宣稱與Olympus版本完全相同；本機原始rc／stderr及後續狀態是本次修正的直接證據。

## 窄範圍接受條件

只在既有allowlist的 `scontrol update JobId=761525 ArrayTaskThrottle=4` 或 `=5` 接受下列特殊情況：rc精確為1、stdout精確為空、stderr每一整行皆精確符合 `761525_[0-9]+: Job has already finished`，可有一個末尾LF，不能有空行、CR、其他array或混合錯誤。更新後必須另外執行成功的唯讀查詢，核對每筆owner／array以及所有明示／pending百分比throttle一致且等於目標，才記為 `verified_with_finished_element_warnings`。原始rc/stdout/stderr照實留在append-only事件，不能改寫成rc0。

一般成功更新也一律重新查核目標。讀取失敗、timeout、權限／transport錯誤、其他非零碼、其他文字、目標未達或owner／array不符皆拒絕；begin失敗照舊嘗試恢復。restore已5仍為無update的冪等驗證；外部若改為其他值，不覆寫。這不是忽略非零退出，也不允許手動繞過lease。

## 新包、新root、新approval、新lease

1. 封存原0934與1002失敗證據，不覆寫原root、approval、manifest或lease。0934已blocked且jobs空；本包操作上取代它，同一物理case23的1accepted-job／1solver額度仍未使用。
2. 核對本ZIP、sidecar、8-entry manifest、verify與全部tests。依下方原環境命名設定本包路徑；父包仍case21。建立全新canonical root，例如 `pam4_sar7_cml_drive2_lease_fix_20261117.XXXXXX`。不要沿用舊failed lease／approval。
3. 由本包生成新的approval-template，依0755既有授權只改approved=true，綁新manifest／root／同一deck。stage使用既有私有model root；核對與case21只有4完整MOS複本＋3R差異。沒有新增電路修改。
4. 本包helper begin → status --require-active成功後，只sbatch一次。接受job即消耗原額度，即使setup失敗也先回報、不重送。未接受job而setup／sbatch失敗要立即restore；收集失敗只collect-only。
5. EXIT／TERM恢復後及收件時，必須查核新lease的restore_verified／當下5收據，警告接受分支也不能省略狀態證據。禁止取消或重送C2、修改score／seed／內容或覆寫外部變更。

既有網路重試政策保留：一次既有wrapper唯讀preflight，連線失敗保留待處理、不連續探測或修改網路。正常channel喚醒上限24次／24小時維持；若本地發布被節流，只延後同一封交件，不能增加job額度或改上限。無需另做電路sweep。

本次完整結果／執行與租約收據複製到 `outputs/PAM4_SAR7_CML_DRIVE2_LEASE_FIX_20261117_RESULTS/`，另列原失敗root來源但不搬動原證據。完整owner／root／stdout只留核准OneDrive／Olympus，repo只放去識別摘要；deck、模型、PDK、RAW、email不進訊息或Git。

---

# SAR7 case23：CML 等比例阻抗縮放單案

唯一case `sar7_23_tt_175gs_cml_drive2`。這次回到完整physical SAR，以case21電路與時序作凍結對照，只改CML四個NMOS及三個電阻；不延續pulse微調、不使用case22的理想輸入夾具。

## 已核對case22，並限制其推論

來源`20261117T0905_sar7_core_sentinels_result.md`；job761764完成。完整summary SHA `e5f8635a27f1e68a67f32499340ccf4cc3e43cb43c7242a1894235450bdb1d82`，與measurements原bytes相同；21個manifest entries及execution/approval/submission/lease均核對。56/56強控制、84/84 reset與actual input有效，固定±0.78125mV的14筆raw在44ps前正確且保持至60ps。

這只證明固定名義probe能力：尚未測實際CML衰減後約0.46mV的一held-LSB、變動common mode或再生期間變號輸入。不能因此排除核心／輸出負載／下游reference延遲。nearzero在60ps是**14可用、13正確、1錯**；qmid/qdecode是12可用、11正確、1錯、2缺值，不能把correct-arrival分母寫成availability。三個群組median近似log關係，不足以確認唯一物理時間常數；一筆−48.8µV錯誤亦不建立固有offset下限。

C2 lease原bytes證明761525在14:58:01.406672Z已restore_verified至5。RAW inventory總119,981,688B，tran119,980,995B，約120MB；0905文末67MB不正確。本案不清理case22 RAW。

## 物理對照及唯一假設

父包為case21：manifest `40a490ab88adfb1bbc370e52f80ced9bfd7954f5be56e3adc93dfcb8f51d650b`、portable `532f9e8f79e9d4c9f668080a76a74b63b9681a01115f16703bc79e12754f70ec`、job761700、summary `7b93590f85c18b85b1cca6dae343d5e550d7b582d3922ee01a3fdb57a1eea851`。case22僅作設計證據，不是新物理父包。所有7個comparator重新由原sensep/sensen實體CML驅動，沒有diag_p/n或新增stiff sources。

case21 conv8b1 compare的held約+0.086LSB而sense約−0.060LSB，且之後變正；case20 held仍約−0.773LSB。選case21是為較清楚測輸入追蹤／阻抗機制，不是另調clock或宣稱case21通過。它仍有較薄的MSB與b2餘裕及O命令中斷；新案必須全數重驗。

假設：在近似原DC增益／共模下，較低CML輸出阻抗能減少七顆comparator固定負載與動態耦合造成的sense建立延遲，改善原read可用性及accepted-reference歷史。唯一電氣差異：

|元件|原case21|case23|
|---|---|---|
|兩個sense NMOS|每個W2µm/L30nm/nf1|完整CDF各複製一次，原卡保留|
|兩個tail NMOS|每個W2µm/L60nm/nf1|完整CDF各複製一次，原卡保留|
|兩個load R|各500Ω|各250Ω|
|兩source之間bridge R|250Ω|125Ω|

複製完整卡保留每顆W/L、nf及AD/AS/PD/PS等全部寄生參數，不以不完整W乘法代替。svdd0.9V、sbias0.5V、節點交叉接法不改。無comparator/CDAC/TG/decoder/qbuffer/register/offset trim/reference/input/save變動；原case21所有pulse／12中心碼／週期／clockoff及讀點逐byte不變。預期差異只有4個新增MOS cards＋3條R值改動。

理想固定端電壓下，I與gm約2倍，三R減半使gmR、source-degeneration及I·R近似不變。外部固定負載看到較低R，但自身寄生也翻倍；局部一階輸出時間常數比值約`(Cfixed+2Cself)/(2*(Cfixed+Cself))`，落在0.5至1。這不是整體SAR速度的界限，額外輸入負載可使整體更慢，不能保證速度翻倍。

代價是mp/mn端MOS gate C約翻倍，可能改變CDAC取樣、有效權重、span、共模與kickback；每側明示CDAC等效約26.60fF尚未含MOS，沒有模型C-V可由W可靠估新增fF。CML近DC功耗也預期約2倍（原約0.235mW）；這是待量測代價，不是免費提速。

## 原始論文對照

[Heydari／Mohanavelu，IEEE TVLSI，DOI10.1109/TVLSI.2004.833663](https://doi.org/10.1109/TVLSI.2004.833663)，[作者原PDF](https://ece.uci.edu/~payam/High_speed_buffer_latch_TVLSI.pdf)，SectionsIII–IV、Fig4/6及Eq13/p1085：以器件尺寸上調、drain R下調保持gain/swing，同時指出前級會承受更多輸入電容。驗證含0.18µm HSPICE／buffer chain與負載延遲；不能移用其大擺幅buffer結果到本28nm、source-bridge、小訊號CML。bridge R也減半是本電路DC等比例的推導，不是作者直接給的配方。原文文字／式子已核對；DOI頁工具無法開啟，圖像未能視覺取得，沒有聲稱看過Fig4/6接線。

[Bheemisetti DOI10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115)的實際common mode校正及切換後ready仍提醒不可把control rail當類比建立。本案不移植未視覺取得的DTFB／BSS／ready網路；先前已見Schinkel作者ProRISC Fig2的雙tail機制亦不在本案改動。大改方向另依0755規則提出選項與成本。

## 不變時序與評分

保留case21：WAIT `[30,45,25,26,31,13,6]`，EVAL `[35,44,40,40,44,44,48]`，guard0.5ps、release read+2ps。

|bit|launch|compare|read|release|
|---|---:|---:|---:|---:|
|6|78|108|143|145|
|5|143.5|188.5|232.5|234.5|
|4|233|258|298|300|
|3|298.5|324.5|364.5|366.5|
|2|365|396|440|442|
|1|440.5|453.5|497.5|499.5|
|0|498|504|552|554|

原ADC screen全部保留：84原read raw全解析；12cmp/reg可讀且一致；max絕對碼誤差≤1、wrong≤6；active552及post565均|ΔCM|≤10mV，physical565讀窗有效。strict零錯logic_smoke另報。不用case22的N/A scorer、不把44/48/60延後診斷替代原read、不調輸入fullscale／Vref／電容／門檻。原sample error約1.673LSB是類比取樣診斷，與max-code-error的1LSB門檻分開報，不悄悄新增或放寬正式gate。

## 一次解析的判別量

新full-summary沿用已驗證的144nodes／84trial／72boundary路徑，巢狀CASE23/root/schema/provenance都重綁。自訂summary的PSF只parse一次，CML診斷使用同一raw物件；既有基本ADC measurement另外parse，不能稱整job只parse一次。沒有新增save。

既存`V_SENSE_DD:p`與sensep/n足以量CML供應電流及功率；注意vsource送出電流的符號。負載總電流可由`(1.8−sensep−sensen)/250`獨立推導、與負的source current核對。報每frame78–565ps固定active區間的mean／energy／peak及每trial held/sense/current相位；不是完整ADC能量或paper FoM。

與原case21 summary對照全部12碼／84bit、sample error、CM、held／sense的precompare、compare及早期建立、raw/x-y/qmid/qdecode、b2 O/Z接受與b1→b0歷史。prefix變動後不能硬沿用舊碼的殘差或只挑改善。動態ratio不是DC增益實測；current/CM保持與gain保持都需依觀察限定，不以理想縮放假設代替。舊case21 RAW已退休，不能從稀疏summary重建其78–565ps平均功率；只能由原500Ω與已存sense phase推導那些相位的電流。新window mean是新案絕對量，2倍功耗是模型預測，不冒稱已量得舊新window ratio。

## 停止條件

- 原screen達標即停並回報，不再為更小誤差或功耗做調參；12中心碼通過仍不等於完整DNL/INL/FFT/PVT或論文重現。
- 未達標而sense未更早有效，或CDAC輸入負載／sample/span／CM代價使結果惡化，就拒絕這個縮放方案，停止此縮放分支。
- 即便部分軌跡改善，也先回Codex作完整判讀；不自動4倍、不另調bias/VCM／clock、不開case24。新長測、全PVT、112GS整合或大改依0755另標Needs user decision:yes。

## 授權、資源及執行

沿用0755使用者原話「SAR7如果一直修不好你叫codex看看相關論文 然後也可以換方向 由codex決定」，source SHA `d9491abfb1429caf097c1c798d763d6529264fb3fa9cbbf2b82cd78b0d4183ea`，無截止。新stage／accepted SubmitTime須≥2026-11-17T13:55:00Z，normal approval精確綁root／case／manifest／deck；不呼叫舊13:37 guard或舊案例stage/run。

最多1accepted job／1solver，1CPU／6GiB／Slurm12min、solver540s，估4–7min及120–180MB RAW；SAR同時只1CPU/1job。沿用case22驗證的C2窄scope lease，只暫將761525 throttle5→4、收完恢復5，不中斷已跑C2、不改score/seed/其他job。每次begin都重新核對owner／原值5與本包normal approval；不是重用case22 lease。pending可等空槽，無舊時窗；未有accepted job而stage/sbatch失敗則立即restore，不自動重送。

EXIT／TERM60與10秒RPC會核對恢復；SIGKILL／node失效仍須在收件時檢查restore_verified，缺失則用本案lease helper明確restore。外部已改成其他值就保留並報告；失敗不能宣稱已恢復。完整owner/root/stdout收據僅OneDrive/Olympus，repo只去識別聚合。

新增`PAM4_SAR7_CML_DRIVE2_PACKAGE`、`PAM4_SAR7_CML_DRIVE2_ROOT`、`PAM4_SAR7_CML_DRIVE2_APPROVAL`；父包`PAM4_SAR7_ACCEPT_GAP_PACKAGE`指原case21，其他dependency及私有model root沿用。先建立存在、canonical absolute、basename符合`pam4_sar7_cml_drive2_*`的新mktemp root。

```bash
python3.11 -B "$PAM4_SAR7_CML_DRIVE2_PACKAGE/sar7_cml_drive2.py" verify
python3.11 -B -m unittest discover -s "$PAM4_SAR7_CML_DRIVE2_PACKAGE" -p 'test_*.py' -v
```

核對ZIP/sidecar/manifest/LF/tests後，approval-template→依既有授權approved=true→stage→精確4新增MOS/3R diff成功，再用本包`c2_slot_lease.py begin`及`status --require-active`（兩者均給`--root`及`--approval`），最後只sbatch一次。restore用相同root/approval的`restore` mode。accepted job即使setup失敗也算本包那1案，先回報；收集失敗只collect-only，不能重跑solver。

## 必交資料及保存

完成將原byte完整`sar7_cml_drive2_summary.json`、measurements、run_status、execution/parse/submission／Slurm、C2 lease及begin/restore收據與SHA256SUMS直接複製至OneDrive `outputs/PAM4_SAR7_CML_DRIVE2_LEASE_FIX_20261117_RESULTS/`，核對fullSHA/bytes再回outbox，不只compact。列清原gate、全部碼／bit、phase／current功率、prefix變化與取樣／共模代價，RAW大小用bytes，不把13correct誤寫13available。

新RAW及case22 RAW仍在診斷中先保留，待分析完成且不需再看後按現有政策退休；本包不刪任何RAW，不重寫歷史inventory。batch ZIP是可重現輸入。deck、PDK／模型、RAW及私人email不進repo或訊息。Claude遠端發布仍做一致中性別名與待推送歷史檢查，保留節點／尺寸／架構；原執行pins及模型alias表在核准位置不改。Codex不git／queue，不操作其他專案，不改poll／唯讀transcript monitor／steering。
