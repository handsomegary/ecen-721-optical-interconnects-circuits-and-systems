Stage: 修復case18摘要collector；只重讀761649既有波形，零新solver
ZIP: ECEN721_PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_20261117.zip（OneDrive ECEN720/outputs）
SHA256: 72ce4fe5e1ebb00b34b94eab26c5611a606f6aa10ee1d3f0ff870e910d6568fb
Guide: OneDrive ECEN720/outputs/PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_20261117/HANDOFF_zh_TW.md
Recommended: verify/tests後只執行collect-only，來源761649原root及原measurement/raw不變；新獨立輸出root，不重跑Spectre或原base.collect
Resources: 最多1個collector、1CPU／6GiB／Slurm10min；0新Spectre、0新raw；C2原三路及account總6CPU上限不變
Commit allowed: handoff + results
Needs user decision: no

## 本包只修摘要，不是新物理case

761649 Spectre已完成，原measurement已寫出。本包補回case18 summary需要但parent selected parser沒有載入的trial*；clk*原本已載入，不籠統宣稱所有clock缺失。這是前包collector/測試覆蓋問題，沒有任何理由重跑317.8秒solver。此次只能用原raw重收；不得stage/run/approval-template、改原package/manifest/approval、sourcecase/status、measurement或gate。

原root為 `~/ecen720_28nm/runs/pam4_sar7_read_overlap_pilot_20261117.3abvDG`，case `sar7_18_tt_175gs_read_overlap`，job761649。原manifest `df3b60ef048c03175e2e07a0d02f5f971bd0840708b9ea85ac2235fff1e0079d`、portable `63c73525a64b0136c66b2aa145da340386492ca5187082d295524213d2fe6aeb`、AUTH `ec86523474c7fb6a20bb5e2d806f31b12bed6d177060672e67ff0b08371a9fd8`皆保持不變。

固定來源bytes：measurement `1729b55e4f7ecbe8941bbde5826b9d22fe9125b413ff60728c55021ca64aad37`；tran `a380f63b5e42532c98cfbf24f8352117c9c9a9e4080e314b4fc0abbfe2c6f69d`；spectre.log `9a58539f46fe86b9b25a915fefc0882975f9232d6f07146bf266d89b36682211`。先核對原evidence/approval綁定，再只讀既有report與PSF；來源hash/inventory前後均不可變，至多parse一次。不呼叫原base.collect或覆寫量測，不以新manifest替代原manifest。

修正方法是隔離的函式／globals副本，把原wave.saved_signals與需要節點聯集傳入相同parser，原scorer、原CASE18與所有門檻不變。回歸測試走完整selected parser→summary→72邊界aggregate，先重現未修版KeyError trial6，再驗證修正版完整走完，不能只用含全部節點的helper mock。

## 正式結論仍等完整summary

父層measurement顯示registered12碼都可讀、7錯、Σ7/max1；cmp10碼可讀、5錯/max1，conv7/8缺失。兩個缺碼不直接等於僅兩個bit未解析，也不算12對一致。Register max1是改善，尚不能改寫原84bit解析、12cmp/reg一致、wrong≤6、552/565 CM與physical565 window的完整screen。不得為了收尾把7錯門檻放寬或改classifier。

請完整回收72段prior_latch_during_overlap、原四讀點、O/Z reference、b0最小餘裕、全部未解析bit及其x/y/q、active552和post565 CM。max observed44.82ps應列出位元／轉換及實際比較窗，不能先假設屬b0。先把collector修好、核對新summary，再由Codex依資料設計；本包沒有下一個物理案。

## 執行及回報

Manifest `cafe5b467a7063e31e1ec32f73e7b44602721ffc5417c364ad449ea4053abb60`。新包所有text/sbatch已轉LF bytes後才計manifest；先驗ZIP/manifest/verify/unittest。保留原CRLF包不改，原761649只有一次有效sbatch；先前DOS-linebreak拒收未產生job，不能算第二次solver。新collector若送Slurm，也使用此新LF腳本，不覆寫父包。

依既有「Yes,8 hours」時窗05:37–13:37UTC／Chicago07:37截止，最多送一個短collector；若截止後既有job仍需收尾可以完成，但不得因此新開Spectre。使用Guide的新輸出root，只寫修正summary與collector receipt，receipt分開標原物理manifest和本次fix manifest／選取集合／parse次數／來源不變證據。

回本機outbox報collectorID、原report/PSF的hash前後不變、summary與receipt完整SHA、正式screen各條件與72邊界診斷。原raw因collector尚需使用而保留，之後另按已授權retirement時窗及分析/commit條件處理；本包不執行刪除。Repo只收compact去識別摘要，dense/PSF/deck/private model留批准位置。

## 新版遠端repo發布規則

使用者剛更新AGENTS.md：每次遠端發布前，Claude須將製程供應商／相關系列與授權PDK、專用模型代號改為一致中性別名，並檢查即將推送的Git歷史、分支名稱、檔名、程式、網表、文件、報告與PDF。保留製程節點、W/L、版圖與其他尺寸數值、電路架構及設計內容。實際授權模型檔、專用名稱及別名對照留repo外，已發布檔案之間的引用／別名須一致。

`Commit allowed: handoff + results`以完成上述檢查為前提；Git仍只由Claude操作，Codex沒有git操作。若發布副本需要中性化，原OneDrive/Olympus執行包、approval、來源與measurement/raw之byte pins仍保留，不能改寫原證據或把發布副本冒稱原執行檔。Batch ZIP、deck、私有模型與dense raw繼續留批准位置。

C2 761525仍依2144 waiting_runs繼續，已完成3/95、另外3路running是進度資料，不是重新提交理由。不修改／取消／重送C2，不改poll/transcript monitor/steering或其他專案。本collector使用自己的短task先回報，不與C2合併等待。
