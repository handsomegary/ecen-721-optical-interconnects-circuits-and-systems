# SAR7 read-aligned overlap：exact qbuffer 的12條pulse改動

本包只有 `sar7_18_tt_175gs_read_overlap` 一案，直接從已量測job761549 qbuffer生成，**不是refpath2**。parent manifest `928590bc897d6755e208f2729f8c0c9882e15a42262032edddf9b491fa0188ca`、portable `509bbedfdc2be956eafade7021b968eeb60d29f0fcb654d2c0037a22b5da813a`、summary `8ab3c03c13658704b2c4a20be6bd453e864f74c4e7e1a6169434a275bbe2eb93`。唯一deck差異是b5到b0的6條trial與6條clock pulse；b6 pulse相同。全部MOS/CDF、subckt、instance、TG、qbuffer、register、matchedNOR、CML/CDAC、reference/input與save卡不變。

## 精確時程與根因假設

單位ps、均為每次conversion起點後的midpoint：

| bit | trial launch | compare | read | trial release |
|---|---:|---:|---:|---:|
|6|78|120|159|161|
|5|159.5|204.5|248.5|250.5|
|4|249|274|314|316|
|3|314.5|340.5|380.5|382.5|
|2|381|412|450|452|
|1|450.5|458.5|499.5|501.5|
|0|500|506|552|554|

WAITS `[42,45,25,26,31,8,6]`、EVAL `[39,44,40,40,38,41,46]`；下一trial rising midpoint＝前一read+0.5ps。edge是1ps，因此**rise開始恰好在前一read**，不是提早0.5ps。前一trial fall midpoint仍是read+2，fall結束read+2.5；midpoint overlap為1.5ps、從新rise開始到舊fall結束是2.5ps，不能統稱2ps midpoint overlap。新rise結束read+1、舊fall開始read+1.5，因此兩trial同在full-high的區間約0.5ps。

舊budget wait160+eval296+guard18＝474ps；新wait183+eval288+guard3＝474ps。guard從3變0.5回收15ps，b0 eval54→46回收8ps，供b3 wait19→26（+7）及b2 wait15→31（+16）。1.75GS/s／571.428571ps、b0read552/release554、clockoff568、conv558/reset566/track569、正式registered read565與diagnostic563/554/557都不變。b0原量測最大raw解析約43.18ps，46ps只剩約2.82ps名義餘裕，不能當作保證。

retained audit顯示兩個問題bit在compare時sense仍正、稍後才過零；refpath2雖讓bottom移動變快，卻改變MSB初始overdrive並增加qmid延遲，沒有達標。因此回到exact qbuffer，改由時槽重疊增加b3/b2建立時間，不繼續strength sweep。

原qbuffer全部84個內部x/y在原read已滿足20/80% rail且與可讀rawq一致；+30ps仍有54/84不滿足，因此不假設+30ps已commit。read時最小|x−y|約0.590V，但最緊rail邊界僅約8mV，下一CDAC步階仍可能造成擾動。先前trial high會強制register/decoder為1/O；release後register跟rawq、decoder跟較晚的qdecode。接受0/Z路徑可能晚到，所以不能只驗證接受1/O。

Bheemisetti等prototype的非同步ready/completion與CDAC控制提醒digital ready和類比建立的差別，其製程／comparator與我們不同：[10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115)。Ramkaj等SectionIII-D討論縮短comparator→CDAC memory path、減少comparator負載；本案沒有抄用其拓撲，而是量測固定時程重疊的影響：[10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823)。鑑別結果是：較早trial是否讓sense在compare前有正確符號，同時前一latch與accepted reference仍穩；不是宣稱內部rail已證明可任意提早。

## 新八小時授權與deadline

`AUTHORIZATION.json`固定來源 `20261116T2337_user_delegates_8h_sar7_175gs.md` SHA `26523d076e396f82acc8844f3441c3517ebba4f05e2073e1629436586287da58`，原話「Yes, 8 hours」，2026-11-17T05:37:00Z≤新stage/submit<13:37:00Z（Chicago 11/16 23:37至11/17 07:37）。此包最多一個solver case/job；1CPU、6GiB、Slurm12min、solver540s。grant整體SAR7同時最多2CPU；不碰C2、不作PVT／長測／112GS/s整合或其他專案。達標或沒有合理方向就停。

approval-template輸出false，依此既有授權核對exact root／manifest／deck後可改true，不需重問使用者。新runner自行處理13:37截止；舊parent只提供rendering／evidence／既有底層執行能力，**不呼叫舊05:15 guard**。截止後只容許原本已提交的queued job：一次只讀scontrol查出匹配JobId及decimal SubmitTime，證明是在新授權時窗提交且不晚於現在，並驗證既有stage逐位元相同。查詢使用epoch UTC格式；缺失／模糊／失敗即拒絕，不重試或自動submit。collect-only可收已完成資料，不開solver。

此runner沒有raw刪除功能。另行確認的raw退休policy須等07:37與最後result commit後由既有worker處理；本包不修改該policy、不刪raw。

## 執行

沿用完整已核對qbuffer dependency chain與既有private model root，不重新打包父包。設定現有父包變數，另設：

```bash
export PAM4_SAR7_READ_OVERLAP_PACKAGE=/approved/PAM4_SAR7_READ_OVERLAP_PILOT_20261117
export PAM4_SAR7_QBUFFER_PACKAGE=/approved/PAM4_SAR7_QBUFFER_PILOT_20261116
export PAM4_SAR7_READ_OVERLAP_ROOT=/approved/pam4_sar7_read_overlap_pilot_20261117.NEW
export PAM4_SAR7_READ_OVERLAP_APPROVAL="$PAM4_SAR7_READ_OVERLAP_ROOT/approval.json"
python3.11 -B "$PAM4_SAR7_READ_OVERLAP_PACKAGE/sar7_read_overlap.py" verify
python3.11 -B -m unittest discover -s "$PAM4_SAR7_READ_OVERLAP_PACKAGE" -p 'test_sar7_read_overlap.py' -v
python3.11 -B "$PAM4_SAR7_READ_OVERLAP_PACKAGE/sar7_read_overlap.py" approval-template --root "$PAM4_SAR7_READ_OVERLAP_ROOT" --approval "$PAM4_SAR7_READ_OVERLAP_APPROVAL"
```

核對approval，只改approved=true，然後stage。各步必須exit0；整體SAR7≤2CPU且C2不受影響才提交這一個job。

```bash
python3.11 -B "$PAM4_SAR7_READ_OVERLAP_PACKAGE/sar7_read_overlap.py" stage --root "$PAM4_SAR7_READ_OVERLAP_ROOT" --approval "$PAM4_SAR7_READ_OVERLAP_APPROVAL" --model-root "$PAM4_PDK_ROOT"
test "$(date -u +%s)" -lt "$(date -u -d '2026-11-17 13:37:00 UTC' +%s)" && sbatch "$PAM4_SAR7_READ_OVERLAP_PACKAGE/sar7_read_overlap.sbatch"
```

以sbatch實際回覆jobID認定已提交；截止前未成功提交就不開新案。重收用 `collect-only --root ... --approval ...`，不要重新stage/run。deck／private model／raw留核准OneDrive/Olympus位置，不進repo／訊息。

## Summary與不變gate

`sar7_read_overlap_summary.json`保留84bit原read解析、12碼comparator/registered誤差與一致性、565physical window、active552與postconv565兩個CM gate。screen仍要求84bit原read全解析、12cmp/reg可讀且一致、max|Δcode|≤1、wrong≤6、兩個CM均|ΔCM|≤10mV及physical window有效。digital logic_smoke定義不變；不把晚到的raw／decode或內部x/y拿來替換原read評分。

同一次PSF parse保留原qbuffer的held/sense/bottom/gates/x-y/raw/mid/decode資料；`timing[].q_buffer.reference_path`延伸crossings／accepted O/Z command runs到下一compare/read，含下一compare+5/10/15/20/30ps固定點。穩定margin只算下一compare前的連續command；左側已穩是截尾證據，不保證更早無擾動。看已知conv8b4→b3接受Z、兩個舊問題碼及所有其他碼，不能只報改善。

新增 `prior_latch_during_overlap` 為12次conversion×6個邊界＝72段（第一bit為null，沒有跨conversion假觀察）。在前一read、新trial edge開始／midpoint、前一release、新compare/read及compare後固定點，記錄前一x/y、raw/mid/decode、register/trial/clock、reference O/Z、bottom、held/sense與新trial。內部class使用(y,x)才與rawq極性相同；統計到新read前的內部未解析／反向rail樣點與最小|x−y|，summary頂層 `overlap_diagnostic`聚合72段。這些都是診斷，不新增／放寬gate。

回報jobID、summary/measurements/tran SHA、所有原gate、b3/b2 sense是否提前、72邊界的前一latch／O/Z擾動，以及b0較短eval的實測餘裕；失敗照實保留。沒有自動下一案、retime、strength sweep或PVT。
