Stage: SAR7 1.75GS/s：回到761549電路，測read後trial重疊與固定週期借時
ZIP: ECEN721_PAM4_SAR7_READ_OVERLAP_PILOT_20261117.zip（OneDrive ECEN720/outputs）
SHA256: 2fe8ade1e7f6f09f122ede34fe87ac68ab0d2aa6f4aea3ef5dd09f723218aee9
Guide: OneDrive ECEN720/outputs/PAM4_SAR7_READ_OVERLAP_PILOT_20261117/HANDOFF_zh_TW.md
Recommended: 唯一case sar7_18_tt_175gs_read_overlap；MOS/電路完全回到761549，只改12條trial/clock脈波，先驗SHA/tests/精確diff再跑一案
Resources: 最多1個新solver，1CPU／6GiB／Slurm12min／solver540s，估4–7min及120–180MB raw；SAR7總並行CPU≤2且保留C2三槽，accountQOS6CPU
Commit allowed: handoff + results
Needs user decision: no

## 授權與本次唯一案

依使用者「Yes, 8 hours」新委派（來源2337 SHA26523d076e396f82acc8844f3441c3517ebba4f05e2073e1629436586287da58），時窗為2026-11-17 05:37–13:37UTC＝Chicago 11/16 23:37–11/17 07:37。不重問已授權的短案；stage、sbatch與queued-run proof都使用新13:37期限，不得落回舊05:15函式。每包case/gate/SHA仍獨立綁定，本包只一個solver。達84原read全解析、12碼cmp/reg可讀一致、max≤1即停修；wrong≤6、active552/post565 CM±10mV及有效565讀窗仍保留。112GS/s整合、PVT與新增長測另候授權，C2不改動。

## 為何不繼續放大

761632 refpath2失敗：registered12/12可讀但8錯、Σ58/max32；cmp只有5/12可讀，7bit未解析，不能把可讀子集max1當完整性能。不能沿用這個較差電路。

但0012回報的因果須精確化：相同phase下，2×案的底板移動確實更快，gate時間幾乎相同；held/sense與MSB初始overdrive也變了。因此失敗沒有推翻已量到的類比建立問題，峰值電流2.1×亦不能單獨證明feedthrough/kickback增加。Raw stable median比較的是76 vs82個有限值；同conv/bit的75對中位差為0ps。Decode的18個配對中位差約+4ps；+6.6ps是18 vs28不同母群中位數差，不能當純延遲增量。39個accepted-margin None不能視為全部安全。

## 回到原電路，只改時間分配

物理來源是精確qbuffer761549（manifest928590bc897d6755e208f2729f8c0c9882e15a42262032edddf9b491fa0188ca，portable509bbedfdc2be956eafade7021b968eeb60d29f0fcb654d2c0037a22b5da813a），不是refpath2。所有MOS、TG、decoder、qbuffer、CML、register、CDAC、reference、取樣、輸入PWL、save完全相同；預期只12條pulse卡改變。沒有新CDF倍率或權重修正。

原761549的84個內部x/y在各自原read均達20/80 rail，最小|x−y|約0.590V；但compare+30並非全部到rail。因此本案只把下一trial上升沿的**起點放在前一read**，不提前到再生早期。native pulse為1ps rise，故next launch midpoint=prev read+0.5ps；previous release midpoint仍read+2ps。兩trial midpoint overlap為1.5ps，整段邊緣交疊至read+2.5ps，不能簡寫成全部事件同時或保證無干擾。

原六段guard3→0.5ps回收15ps，b0比較窗54→46再回收8ps，合計23ps分給b3 wait+7及b2 wait+16。b0舊有限raw rail最大43.18ps，46ps僅保留約2.82ps舊樣本餘裕；新決策歷史可能改變它，必須重新實測。這是已觀察到的兩處settling及read-validity預算測試，不是按碼擬合權重，也不保證過關。

| bit | launch midpoint | compare | read | release midpoint |
| --- | ---: | ---: | ---: | ---: |
| 6 |78|120|159|161|
| 5 |159.5|204.5|248.5|250.5|
| 4 |249|274|314|316|
| 3 |314.5|340.5|380.5|382.5|
| 2 |381|412|450|452|
| 1 |450.5|458.5|499.5|501.5|
| 0 |500|506|552|554|

單位ps。WAIT=[42,45,25,26,31,8,6]；EVAL=[39,44,40,40,38,41,46]。總期571.428571ps；formal565、diagnostic563/554/557、conv558/reset566/clockoff568/track569全部不變。比較器本身仍用原raw q準位計分，不用內部xy或late release的有效值取代原read gate。

## 文獻與判別

[Ramkaj，JSSC DOI10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823) 的semi-asynchronous／parallel logic把critical-loop延遲重疊；其28nm 1V triple-tail+USPC實測1.25GS/s，與我們固定時序及StrongARM+CML不同。[Bheemisetti，JSSC DOI10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) 的3nm DTFB與bottom-plate-ready控制同樣提醒比較必須等實際類比狀態，其0.65V／320mVppd及實測DNL/INL/FFT不等於本次12碼TT。這次只試從已量測read開始重疊的局部控制，不宣稱複製非同步prototype。Um的split-CDAC offset-first/isolated-weight方法仍是替代靜態診斷，本包不調CDAC：[DOI10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608)。

判別是：新trial上升沿開始前／開始時，前一內部xy及原q是否已穩；重疊後read→release是否翻判；接受O/Z與當前底板／held／sense是否在新compare前改善。若前一決策受擾或接受reference晚到，就否定這個重疊安排；若兩問題位元輸入建立改善且84/12完整通過，支持控制路徑重疊可用。保留input在再生中變號、offset及kickback可能共存的限制，不能只看某一50%交越。

## 執行、資料與回報

Manifest SHA `df3b60ef048c03175e2e07a0d02f5f971bd0840708b9ea85ac2235fff1e0079d`。先驗ZIP/sidecar/manifest/verify/unittest、stage對761549精確diff，再依本次既有授權只改template approved=true提交單案。新root/approval綁新schema/AUTH；若已有jobID或intent先查，不換root盲目重送。截止前成功取得sbatch接受ID才算提交；截止後只收既有提交與collect-only，不開新case。

回報jobID/SubmitTime、全部84trial及12碼/讀點/gates、每個read附近的前一xy/q/next-trial edge、release後接受O/Z與下一compare、held/sense/x-y/q/mid/decode、b0解析餘裕、CM/取樣/reference電流、summary/measurements/tran完整SHA和CPU/walltime。首次不通過就回Codex，不自行縮guard、加overlap或減b0窗。

本包沒有刪除操作。另有使用者後續「delete sorry」對已列raw的退休授權，由Claude依既有延至07:37且最後結果分析/commit後的條件處理；目前需要的SAR7來源先保留，不能把本包當額外刪除批准。C0/C1 raw退休不改原measurements、status/historical inventory、case/bench/intent/log/.study_owned、selection、approval與summary的byte pins，C2依賴這些歷史證據；不要為退休重寫metadata。Dense樣點只留批准位置，repo只compact去識別summary與合規無deck程式。

C2 761525／0-94%3照原批次與2144waiting_runs繼續，不修改／取消／重送；本案1CPU且提交前檢查account總6CPU上限、SAR≤2並保留C2三槽。使用自己的短task先回報，不與C2合併等待。不得修改poll、transcript monitor、steering或其他專案。
