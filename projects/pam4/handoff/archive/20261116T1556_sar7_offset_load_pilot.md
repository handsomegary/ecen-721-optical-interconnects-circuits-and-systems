Stage: SAR7 有效判決門檻：互補負載與固定微調的獨立短案
ZIP: ECEN721_PAM4_SAR7_OFFSET_PILOT_20261116.zip（OneDrive ECEN 720/outputs）
SHA256: e766d0445c7a8587607c4a63e934c27ece744a9e208980cc5f67e93d432510f0
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_OFFSET_PILOT_20261116/HANDOFF_zh_TW.md
Recommended: 核對完整性、verify、14項測試與容差預估重現後先送index0；僅實測ALLOW_INDEX1時送唯一獨立index1，max≤1即收尾，本包最多兩案
Resources: 最多並行1案、每案1 CPU／6 GiB／Slurm10min、solver≤540s，預估3–6min/raw100–140MB；23:15 Chicago後不新stage／sbatch／開新輪
Commit allowed: handoff + results
Needs user decision: no
authorization_basis: 使用者於2026-11-16 15:15原話「八小時授權任何修正」，至23:15 Chicago；本包SAR7短修正與approved=true由該授權涵蓋

## 1545證據已處理與假設

已讀20261116T1545_sar7_cdac_round2_audit_result.md，三個回傳JSON完整SHA均核對相符。760874仍為共同基準，wrong6/12、Σ7/max2。#8的sample誤差−0.191LSB，不支持該筆acquisition導致+2；實際控制字84/84符合prefix，不能再把誤差歸給推估控制字。共同pre sense門檻約−0.6734…−0.5538LSB可解釋全部84決策，但這是工作條件下的有效門檻，不是七顆獨立靜態offset量測。

更正1545敘述（原回報保留不改）：15ps全84筆buffered輸出差實際為−70.94…+39.30mV，已有明顯輸入依賴，並非全部−13…−17mV。q/qb是buffered output，非內部regeneration x/y，不能據此宣稱reset故障或核心初始不平衡。核心鏡像CDF與reset映射未找到不對稱；確定存在的外部差異是qpositive多了控制NOR負載。

## 論文對照與要辨別的結果

[Um A-SSCC, DOI10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608) 的split-CDAC校正先隔離比較器offset；[Bheemisetti JSSC, DOI10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) 也使用實際共模下offset校正，且採不同的DTFB／非同步時序。Guide核對了低速校正與3nm/1.75GS/s原型的操作／驗證條件，不拿來宣稱本平台達到同樣性能。

本包先驗證第一級外部負載是否參與門檻偏移：若補互補NOR後，在CDAC不變下threshold與錯碼改善，支持該負載機制。若無改善，因未完整複製後級fanout，不能排除所有load/Miller/history效應。第二案是獨立操作性補償對照；若sense intercept按預估移負、held-domain門檻移近零且達標，支持此工作條件的補償有效，不證明靜態或動態根因已完全識別。

## 凍結兩案與共同儀測

index0 sar7_10_tt_matched_q_load：從原760874補7個原生dummy SAR_NOR，qb使用與q相同的第二輸入角色及trial；比較窗trial=1使兩NOR輸出皆被拉低。只測第一級fanout，不改reset、CDAC、Vref、CML或時序。其精度效果未由現有資料數值預測。

index1 sar7_11_tt_cml_load_trim：僅在index0有效、未達標且不劣於基準時執行；重新從原760874建構，不含dummy NOR。只把RSENSE_P(接sensen)改498.5Ω、RSENSE_N(接sensep)改501.5Ω，總和1000Ω，預估sense差動移−391.036µV。固定partial補償值來自pre/trigger/2ps與門檻區間條件模型，不是amplitude sweep。條件預估Σ6/max1，來源碼12/12一致與LOCO84/84僅為來源一致性，不保證新路徑成立。

兩案共同只增加14個XCMP內部x/y save probes。x/y是輸出反相器前的節點，與buffered q靜態極性相反；波形應分開觀察，不混稱latch。保留12碼／CDAC／input／1080ps／60–60ps／1030ps read。

## 驗證與識別

14項整合測試、verify、容差版planning重現及獨立程式／科學／deadline審查通過。新ZIP的9項manifest檔、10個entries與sidecar均逐位元核對；先前未發布的review ZIP另存REVIEW1，請只使用本header指定SHA。

- manifest SHA256: f04d9107421d0a9d826df1c00252b264987fc678f6139a4d018fc2fa42250e90
- index0 portable SHA256: 2070f861b4e07e1037c6593ad5518bfd379fef185248ee60fa54c0c8c3832347
- index1 portable SHA256: 9767e0cb9b36a722bb787bf8e23c6328fa92d87d2c02e4bd8367c3cf976fcf43
- PREDICTION SHA256: f709fbb541bbfb3ac05a899da3ba3c11caa588f1989d85b2a012f20ff13193ba

相對760874的電氣差異index0恰好7條NOR；index1恰好兩個R；另有各自一條save擴充。兩案彼此獨立。沿用原CDAC_FIX/CML_RDEG/relaxed/SAR7與私有模型環境，只加OFFSET_PACKAGE/ROOT/APPROVAL。approval-template綁定新root、兩case、manifest、per-case deck及expires；只改approved=true，不加欄位。

## Gate、截止與回報

index0須84bit解析、12筆cmp/reg可讀一致、CDAC CM≤10mV；max≤1為STOP_TARGET。有效但max≤2且Σ≤7才ALLOW_INDEX1；其餘STOP_REVIEW。stage與run都重新核對原測量evidence及summary SHA，不能手寫gate或提前送index1。

23:15 Chicago＝2026-11-17 05:15 UTC。每次sbatch前必須依Guide用test時間 && sbatch；stage限截止前。截止後run須以一次唯讀scontrol查到同job ID的實際SubmitTime嚴格早於截止，再驗證已stage的byte-exact電路與stage proof；查不到就拒絕。已送job可收完，collect-only不受收集截止限制。

回outbox報逐碼wrong/Σ/max、84bit／registered、sample／CM／resolve、sense affine intercept及門檻、#8b2內部x/y和buffered q各自軌跡、完整summary/measurement/tran SHA與每案job。達標即停止追小差異；若兩案未達先回Codex，不在本包追加case。含逐trial電位的source_features與完整probe資料留OneDrive/Olympus；repo只存無deck程式、聚合指標與handoff。新舊raw全保留。

C1/C2長測、全PVT、1.75GS/s正式驗證、刪raw、其他專案仍需另授權。Codex不git；不使用codex queue，archived steering command停用，transcript monitor唯讀。
