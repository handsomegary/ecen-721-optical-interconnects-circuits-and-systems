# SAR7 reference path ×2：單一 TT physical pilot

本包只有 `sar7_17_tt_175gs_refpath2` 一案，從已量測的 job761549 qbuffer 原 bench 獨立生成；parent manifest `928590bc897d6755e208f2729f8c0c9882e15a42262032edddf9b491fa0188ca`、portable `509bbedfdc2be956eafade7021b968eeb60d29f0fcb654d2c0037a22b5da813a`、summary `8ab3c03c13658704b2c4a20be6bd453e864f74c4e7e1a6169434a275bbe2eb93`。所有既有父包只作 rendering/evidence dependency，絕不使用父包的舊05:15UTC截止函式。

## 授權與資源

新的 `AUTHORIZATION.json` 固定來源 `20261116T2337_user_delegates_8h_sar7_175gs.md` SHA `26523d076e396f82acc8844f3441c3517ebba4f05e2073e1629436586287da58`，使用者原話「Yes, 8 hours」，授權2026-11-17T05:37:00Z到13:37:00Z（Chicago 11/16 23:37到11/17 07:37）。此包最多一個新 solver job；1CPU、6GiB、Slurm12min、solver540s。整個 SAR7 grant 同時最多2CPU，C2完全不碰；不含PVT、長測、112GS/s整合、其他專案或刪raw。達標或沒有合理方向就停止。

approval-template 固定輸出 `approved:false`。本次既有授權容許將這個 exact root／manifest／deck 對應的 approval 改成true，不需要重新詢問使用者；不可套到其他案。authorization 本文與JSON／PLAN／manifest／case metadata互相固定。

新 stage 必須在05:37≤UTC<13:37。實際 `sbatch` 也必須在截止前成功回覆jobID；沒有自動submit。截止後的 queued job 可以完成，但 run 必須同時通過：本案既有stage逐位元相同，以及一次只讀 `scontrol --oneliner show job` 證明匹配的 `SLURM_JOB_ID` SubmitTime落在新授權時窗且不晚於現在。使用 `SLURM_TIME_FORMAT=%s,TZ=UTC,LC_ALL=C`，錯誤／缺值／重複值／RPC失敗直接拒絕，不重試。collect-only沒有截止限制，保留已提交工作的raw。

## 單一物理假設

retained audit761591顯示，兩筆錯位的前一bit接受reference在compare前約16–20ps已穩，當前trial→最後control半VDD約14ps，bottom到名義reference中點另約8–12ps，held→sense再落後約5–6ps。支持當前trial類比建立不足有貢獻，不能證明只由單一延遲／offset／kickback造成。過零與gate crossing是proxy，不能當LSB settling或直接導通證據。原read兩筆rawq仍未達20/80%；release後才有效是診斷，不能改寫fail gate。

一個耦合物理尺度×2：只在28個functional XRef與28個matched XNDLOAD使用完整CDF雙份 `SAR_REFTG2`；OAI/NOR原strong所有device replicas各×2（OAI每N4、seriesP4、single-enP2；NOR每N2、每P6）；28個decoder complementary INV換成4，14個qbuffer第二級也換成4，第一級14個SAR_INV保持1。共126個既有instance換cell，加入四個局部cell，所有原cell定義保留相同；real/dummy與兩邊鏡像。

這樣保持兩種極性launch／acceptance的近似drive/load比例，避免只加TG及outputINV卻讓前級P path負載變成兩倍。已知正確conv8b4→b3接受Z僅提前7.43ps，這個margin尤其需要看。first qbuffer由1→2變成1→4，會增加mid延遲；TG的diffusion與feedthrough也變大，因此不保證2倍速度或直接達標。

全域SAR_TG/SAR_INV、register、matchedNOR、CML、CDAC、reference電壓、輸入、rawq第一級fanout、clocks、waits、readouts完全相同。1.75GS/s／571.428571ps；b0read552/release554；registered正式read565、diagnostic563/554/557；conv558、reset566、clockoff568、track569。565接近reset開始，仍須通過原physical-window檢查。

Bheemisetti等prototype的非同步ready/completion和CDAC控制提醒digital ready與類比settling的差別，其拓撲／製程與我們不同，不能直接套delay：[10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115)。Ramkaj等SectionIII-D說明縮短comparator→CDAC memory path、降低comparator loading的機制；我們的兩級qbuffer不是照抄拓撲，負載隔離與延遲要一起看：[10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823)。本案鑑別是保持時序下 gate／bottom／held／sense是否提前，以及accepted O/Z是否仍在下一compare前穩定；不是參數掃描。

## 執行順序

沿用已核對的完整parent dependency chain與既有private model root；不要重新打包父包、不要把deck／PDK／模型放repo或訊息。設定父包既有環境變數，再設定：

```bash
export PAM4_SAR7_REFPATH2_PACKAGE=/approved/PAM4_SAR7_REFPATH2_PILOT_20261116
export PAM4_SAR7_QBUFFER_PACKAGE=/approved/PAM4_SAR7_QBUFFER_PILOT_20261116
export PAM4_SAR7_REFPATH2_ROOT=/approved/pam4_sar7_refpath2_pilot_20261116.NEW
export PAM4_SAR7_REFPATH2_APPROVAL="$PAM4_SAR7_REFPATH2_ROOT/approval.json"
python3.11 -B "$PAM4_SAR7_REFPATH2_PACKAGE/sar7_refpath2.py" verify
python3.11 -B -m unittest discover -s "$PAM4_SAR7_REFPATH2_PACKAGE" -p 'test_sar7_refpath2.py' -v
python3.11 -B "$PAM4_SAR7_REFPATH2_PACKAGE/sar7_refpath2.py" approval-template --root "$PAM4_SAR7_REFPATH2_ROOT" --approval "$PAM4_SAR7_REFPATH2_APPROVAL"
```

核對exact approval，依本次「Yes, 8 hours」改true，再執行stage。命令須exit0；不要看到輸出就忽略失敗。

```bash
python3.11 -B "$PAM4_SAR7_REFPATH2_PACKAGE/sar7_refpath2.py" stage --root "$PAM4_SAR7_REFPATH2_ROOT" --approval "$PAM4_SAR7_REFPATH2_APPROVAL" --model-root "$PAM4_PDK_ROOT"
test "$(date -u +%s)" -lt "$(date -u -d '2026-11-17 13:37:00 UTC' +%s)" && sbatch "$PAM4_SAR7_REFPATH2_PACKAGE/sar7_refpath2.sbatch"
```

先確認SAR7並行CPU≤2與C2不受影響；此包只提交一次sbatch並記錄實際jobID。若截止前未成功提交，不開新案；已提交的queued/running可收完。重收使用 `collect-only --root ... --approval ...`，不會重新stage或開solver。

## 判讀與回報

`sar7_refpath2_summary.json`保留原全部12碼／84bit、comparator與registered誤差、原read解析、565physical window、active552與postconv565兩個CM gate，並保留各trial held/sense/x-y/bottom/gates/q-mid-decode。嚴格screen：84bit原read全解析、12cmp/reg都可讀且一致、max|Δcode|≤1、wrong≤6、552與565的|ΔCM|≤10mV及physical window有效；不改digital `logic_smoke_pass`定義。

新增 `timing[].q_buffer.reference_path` 由同一次PSF parse取值，從trial到下一compare/read延伸：目前trial與release、compare+0/5/10/15/20/30ps、下一launch/compare/read以及下一compare+5/10/15/20/30ps、gate/raw/mid/decode半VDD crossing、bottom/held/sense/x-y，並列release後一直到extended window尾的accepted O/Z command runs、565register對應command、下一compare前連續穩定margin。穩定起點若在視窗起點已成立，只代表左側截尾；不是更早無毛刺的保證。q_buffer舊欄位保留原較短視窗，新判讀使用reference_path extended欄位。

重點比較：trial→gate時間、gate→bottom中點／held／sense、conv8b4→b3 accepted Z margin、兩個問題bit與所有其他bit的qmid/decode延遲，以及reference源peak電流與CM。sample／crossing不是直接settling精度或開關電流；保留所有fail與raw，不只報改善。沒有pass就回報量到的機制，不自動retime或啟動第二個case。只把一般summary送repo；private deck/model/raw仍留核准位置。
