# SAR7 case19 compare-window：單一12ps重分配案

本包只有 `sar7_19_tt_175gs_compare_window` 一個physical TT case，從immutable **case18**原包生成，不回退成qbuffer舊時程，也不沿用refpath2。Parent manifest `df3b60ef048c03175e2e07a0d02f5f971bd0840708b9ea85ac2235fff1e0079d`、portable `63c73525a64b0136c66b2aa145da340386492ca5187082d295524213d2fe6aeb`、parent job761649。設計依據是已核對的完整summary `121d50d9324627f4326149b17217f49dbbd9e4113076cced38919ac6127cca19` 與receipt `0ef32f07eb1c4c0d7c1b336605a8c204d977edefa06f151a3594caf9a7204f4f`；build/verify不需要舊raw或這兩個分析JSON，原包與其rendering dependencies已足夠。

## 可否定的單一假設

case18有四個bit在原read未達rail：conv7/8的b2、b1。既有樣點已觀察到conv7b2在38.5ps有效，兩個b1在43ps有效；conv8b2在41ps仍無效、46.5ps有效。這些是**已觀察的有效上界，並非精確最早80%crossing**。b0最小餘裕僅1.18ps，不能再捐時間。

同一來源的12次b6在launch+30ps，sense符號全與既有MSB決策一致，最小|sense|約3.036LSB（約2.37mV）；35ps最小約6.056LSB。選30ps會降低已觀察sign margin，而且改變clock後的再生／kickback未知。因此一次只測這個12ps重分配：b6 wait42→30省12；b2 EVAL38→47用9，覆蓋既有46.5ps有效點；b1 EVAL41→44用3，覆蓋既有43ps有效點。沒有掃描、沒有額外b1 WAIT微調。

這也測試較晚b2 release能否減少accepted-reference bubble：conv7b2實際判1/O，但原release後qdecode較晚而出現不互補command；conv8b2實際判0/Z則有release後P path延遲。兩者不能當成同一機制。conv7b1自身WAIT8仍讓最後control半VDD交越在compare後約6ps，80%rail與類比建立更晚；EVAL延長未必修好其錯判，更不保證wrong7變≤6。所有結果依原gate判定。

## 精確時程與唯一deck差異

WAITS `[30,45,25,26,31,8,6]`、EVAL `[39,44,40,40,47,44,46]`；下一trial midpoint仍是前一read+0.5ps，previous release仍read+2。

| bit | trial launch | compare | read | trial release |
|---|---:|---:|---:|---:|
|6|78|108|147|149|
|5|147.5|192.5|236.5|238.5|
|4|237|262|302|304|
|3|302.5|328.5|368.5|370.5|
|2|369|400|447|449|
|1|447.5|455.5|499.5|501.5|
|0|500|506|552|554|

單位ps、時間為每conversion起點後的midpoint。1ps rise從previous read才開始；midpoint overlap1.5ps、從新rise開始至舊fall結束是2.5ps。新budget wait171+eval300+guard3＝474ps，第一launch78到最後read552完全相同。

對exact case18 deck僅改12條pulse：**b1到b6**的trial與clk各6條；b0兩條pulse與全部metadata時程不變。沒有任何MOS/CDF/subckt/instance/save、reference電壓、input、CDAC、CML、register、qbuffer改動。b1 read499.5/release501.5與b0整段保持case18原值；1.75GS/s／571.428571ps、conv558/reset566/clockoff568/track569、正式registered read565與diagnostic563/554/557均保留。沒有新增或放寬classifier／threshold。

Bheemisetti等原型的非同步ready/completion與CDAC控制，說明固定clock需要分開驗證類比建立和比較完成；其製程、comparator與此7個unfolded comparator不同，不能把本案當作複製原型：[10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115)（Figures3–5的ready/CDAC時序、Figures6–7的DTFB comparator，依已讀primary文字與圖說；沒有把未取得的圖像當成已檢查的transistor接線）。Ramkaj等SectionIII-D討論comparator→CDAC memory path負載與延遲：[10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823)。本案不加新buffer／強度，保持同電路來區分「晚到rail與accepted-history」和「仍然不足的b1建立／offset」；MSB clock改早後也必須重新證明39ps內解析。

## 完整signal admission與不變評分

直接納入已驗證的collector修正：在隔離FunctionType globals中，qbuffer summarize的required集合加入全部既有wave.saved_signals∪time及trial/clk。沒有新增save或對原module globals做monkeypatch。case18原summary/helper以case19的CASE_ID/schema/manifest/provenance執行；完整selected-parser regression先在**case19**重現舊required的trial6 KeyError，再以144個實際requested nodes跑完84trial與72boundary，避免直接helper/full-data測試漏掉parser路徑。

`selected_parser.summary_psf_parse_count=1`只指**自訂完整summary**的一次PSF parse，原底層基本measurement另有自己的parse；沒有宣稱整個physical job只parse一次，也沒有cache或execution-layer重構。72段原prior-latch、accepted O/Z、x/y/raw/mid/decode/held/sense/control及b0 margin診斷都保留。新增polarity_assessed/unassessable counts；initial_internal_class=None的邊界不能以opposite=0宣稱穩定。既有欄位／gate不改。

正式screen仍要求84bit原read全解析、12cmp/reg可讀且一致、max|Δcode|≤1、wrong≤6、active552與post565 CM均|ΔCM|≤10mV及565physical window有效；digital logic_smoke定義不變。晚到raw、內部x/y或改讀點不能代替原read評分。

## 授權、資源、只提交一次

AUTHORIZATION.json固定原話「Yes, 8 hours」、來源note SHA `26523d076e396f82acc8844f3441c3517ebba4f05e2073e1629436586287da58`；新stage與實際submit必須2026-11-17T05:37:00Z≤UTC<13:37:00Z（Chicago至07:37）。本包最多**1個新solver／1個已接受Slurm jobID**，1CPU／6GiB／12min，solver timeout540s；整個SAR7 grant同時CPU≤2，C2不變。不含PVT／長測／112GS/s整合或其他專案。

approval-template預設false；依既有授權核對exact root/manifest/deck後可改true。新runner使用自己的13:37 guard，不呼叫舊05:15 helper。截止後queued job可完成，但run須一次只讀scontrol SubmitTime證明JobId匹配、submit在新時窗且不晚於現在，以及既有stage byte-exact；缺失或查詢失敗即拒絕。collect-only可收既有工作，不開新solver。本包不刪raw、不修改既有另行核對的退休policy。

## 執行與提交前檢查

沿用原完整case18 dependency chain與既有private model root；所有新payload與sbatch都已在manifest／ZIP前正規化LF。不要改父包或自己補parser；不要把private deck/model/raw放repo或訊息。遠端發布另依最新AGENTS做一致中性別名與待推送歷史檢查，原private package/pin chain留核准位置不改。

```bash
export PAM4_SAR7_COMPARE_WINDOW_PACKAGE=/approved/PAM4_SAR7_COMPARE_WINDOW_PILOT_20261117
export PAM4_SAR7_READ_OVERLAP_PACKAGE=/approved/PAM4_SAR7_READ_OVERLAP_PILOT_20261117
export PAM4_SAR7_COMPARE_WINDOW_ROOT=/approved/pam4_sar7_compare_window_pilot_20261117.NEW
export PAM4_SAR7_COMPARE_WINDOW_APPROVAL="$PAM4_SAR7_COMPARE_WINDOW_ROOT/approval.json"
python3.11 -B "$PAM4_SAR7_COMPARE_WINDOW_PACKAGE/sar7_compare_window.py" verify
python3.11 -B -m unittest discover -s "$PAM4_SAR7_COMPARE_WINDOW_PACKAGE" -p 'test_sar7_compare_window.py' -v
```

先建立真正的新mktemp root，確認它存在、canonical absolute path、basename符合prefix（不能用未建立的子目錄或out這種basename）。再做approval-template、核對並改true、stage，每步須exit0：

```bash
set -euo pipefail
test -d "$PAM4_SAR7_COMPARE_WINDOW_ROOT"
test "$(readlink -f "$PAM4_SAR7_COMPARE_WINDOW_ROOT")" = "$PAM4_SAR7_COMPARE_WINDOW_ROOT"
case "$(basename "$PAM4_SAR7_COMPARE_WINDOW_ROOT")" in pam4_sar7_compare_window_pilot_*) ;; *) exit 1 ;; esac
python3.11 -B "$PAM4_SAR7_COMPARE_WINDOW_PACKAGE/sar7_compare_window.py" approval-template --root "$PAM4_SAR7_COMPARE_WINDOW_ROOT" --approval "$PAM4_SAR7_COMPARE_WINDOW_APPROVAL"
# 核對exact approval後，依既有授權只改approved=true
python3.11 -B "$PAM4_SAR7_COMPARE_WINDOW_PACKAGE/sar7_compare_window.py" stage --root "$PAM4_SAR7_COMPARE_WINDOW_ROOT" --approval "$PAM4_SAR7_COMPARE_WINDOW_APPROVAL" --model-root "$PAM4_PDK_ROOT"
test "$(date -u +%s)" -lt "$(date -u -d '2026-11-17 13:37:00 UTC' +%s)" && sbatch "$PAM4_SAR7_COMPARE_WINDOW_PACKAGE/sar7_compare_window.sbatch"
```

提交前再確認SAR7 CPU≤2、C2未動與LF；以sbatch實際accepted jobID記錄。已接受job即使setup失敗也算本包那1個job，先回報，不自行再送。截止前未成功提交則不開新案；既有submitted的收完。重收用collect-only，不重新stage/run。

輸出 `sar7_compare_window_summary.json`，回報job／耗時、summary/measurements/tran SHA、全部原gate、12個MSB是否原39ps內解析、b2/b1 availability及accepted O/Z bubble、72個boundary可評估／不可評估極性、b0原時程下的新餘裕與CM。失敗照實保留，不能只報改善；達標或沒有合理方向就停止，沒有自動第二案或時序微調。
