# case18 collector-only修正：原資料不動、零新solver

原job761649 Spectre已正常完成；原case18摘要在新增prior-latch診斷讀 `trial6` 時失敗。精確原因是父qbuffer選取式parser沒有載入trial0–6；clk0–6原本已載入。trial訊號已經在原save卡與既有PSF，不需新deck、save、stage或Spectre。

本包只有 `verify` 與 `collect-only`，不提供run／stage／approval-template，不呼叫base.collect，不新增或改寫原package、manifest、AUTH、approval、case、execution intent/status、measurements或raw。原case18包仍保持發布時SHA；不在原run根目錄補寫summary，而是在獨立collector根目錄輸出。此包也沒有raw退休／刪除功能，不更動既有另行授權policy。

## 不變的來源

- 原package `PAM4_SAR7_READ_OVERLAP_PILOT_20261117`，manifest `df3b60ef048c03175e2e07a0d02f5f971bd0840708b9ea85ac2235fff1e0079d`。
- 原case `sar7_18_tt_175gs_read_overlap`，job761649，root basename `pam4_sar7_read_overlap_pilot_20261117.3abvDG`。
- Portable `63c73525a64b0136c66b2aa145da340386492ca5187082d295524213d2fe6aeb`；staged deck `cff34259f212d8c76ea342d06e7fef0ab7ae285cba5170b066eaf23462e7a3e4`。
- 原AUTH `ec86523474c7fb6a20bb5e2d806f31b12bed6d177060672e67ff0b08371a9fd8`。
- Measurements `1729b55e4f7ecbe8941bbde5826b9d22fe9125b413ff60728c55021ca64aad37`。
- Tran `a380f63b5e42532c98cfbf24f8352117c9c9a9e4080e314b4fc0abbfe2c6f69d`。
- Spectre log `9a58539f46fe86b9b25a915fefc0882975f9232d6f07146bf266d89b36682211`。

讀取前後使用原case18 build/evidence驗證既有stage、model substitution、execution intent、status、jobID、bench/log/hash與raw inventory；核對原exact approval，並記錄各檔bytes與SHA。來源不符就拒絕，不找替代raw或重新量測。原共享base的render/evidence binding只在try/finally內指向原case18並復原；所有原parent module globals不變。

## 修正與驗證範圍

以獨立FunctionType globals複製父qbuffer.summarize，只把EXTRA_SAVES擴成原集合∪全部原wave.saved_signals∪time/trial/clk；case18原summarize使用只帶這個clone的隔離parent proxy。原parser、helper、scorer、threshold、clock／readout／physical-window及CM gates不變。用read-only base/review proxy計數真正parser呼叫，限制**同一既有PSF只parse一次**；不對原module做monkeypatch。

整合regression透過選取式parser只回傳實際requested nodes：原完整case18 summary路徑必須重現KeyError trial6，修正後同一完整summary路徑必須跑完84trial及72段prior_latch aggregate；不以直接helper/full mock資料規避缺訊號。另驗證來源SHA／路徑隔離／失敗時binding復原、只有verify/collect-only CLI、全部新payload與manifest沒有CR。**本包全部Linux腳本已在manifest／ZIP前正規化成LF**，不需產生去CR wrapper，也不要改動原case18 package。

原measurement僅能說12個registered code可讀、max1，另有兩個comparator code不可讀；不能把「兩個code」直接當成「只有兩個bit」未解析。完整原gate與逐bit數量必須等此summary成功後判斷，不能先宣布pass。原screen仍包含84bit原read全解析、12cmp/reg可讀且一致、max≤1、wrong≤6、active552與post565 CM均≤10mV、565physical window有效；72段prior-latch／accepted O/Z及b0實測margin仍由原case18函式計算。沒有放寬gate或換scorer。

同一parse另在receipt的supplemental_diagnostics記錄全部12次b6於launch+30/+35/+38/+41ps的held/sense、x/y、rawq、clock/trial與相對compare時間。這48點僅供日後判讀，沒有更動原summary contract、gate或提出／執行新物理計畫。

## 執行與輸出

這是新八小時授權內的既有資料收集：1個collector job、1CPU、6GiB、10min、0 Spectre、0新raw。SAR7整體CPU≤2，C2不碰；不開新的physical case。沿用原完整dependency chain，指向**未修改的原case18包**及完成根目錄。

```bash
export PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_PACKAGE=/approved/PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_20261117
export PAM4_SAR7_READ_OVERLAP_PACKAGE=/approved/PAM4_SAR7_READ_OVERLAP_PILOT_20261117
export PAM4_SAR7_READ_OVERLAP_SOURCE_ROOT=/approved/pam4_sar7_read_overlap_pilot_20261117.3abvDG
export PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_ROOT=/approved/pam4_sar7_read_overlap_collect_fix_20261117.NEW
python3.11 -B "$PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_PACKAGE/sar7_read_overlap_collect_fix.py" verify
python3.11 -B -m unittest discover -s "$PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_PACKAGE" -p 'test_sar7_read_overlap_collect_fix.py' -v
sbatch "$PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_PACKAGE/sar7_read_overlap_collect_fix.sbatch"
```

每步須exit0；只提交這一個collector並記錄jobID。直接執行用 `collect-only --source-root ... --output-root ...`。不需要新approval，不呼叫原run／stage／collect-only，也不重寫measurements。

獨立新根目錄會產生 `sar7_read_overlap_summary.json`（原case18 schema／provenance／評分）與 `sar7_read_overlap_collect_fix_receipt.json`（fix manifest、實際selected required、parsecount=1、前後source bytes/inventory、0solver/0newraw/0sourcewrites與48點supplemental）。兩檔已有且相同可驗證；不同就拒絕覆寫。回報兩個輸出SHA、collector job/耗時、原來源不變證明、正式565／552CM與72段診斷、b0餘裕。沒有下一個physical case或自動調時序；private deck/model/raw仍留核准位置。
