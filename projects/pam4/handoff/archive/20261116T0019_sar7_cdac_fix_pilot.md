Stage: SAR7 CDAC span／比例修正：新授權的一輪小型 pilot（TT）
ZIP: ECEN721_PAM4_SAR7_CDAC_FIX_20261116.zip（OneDrive ECEN 720/outputs）
SHA256: 8e290b0e44137488c27a3631e1246453f654ef345bb0fed3c090618cc922a9e7
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_CDAC_FIX_20261116/HANDOFF_zh_TW.md
Recommended: 完整性核對後先送 index 0；只在實測 gate 為 ALLOW_INDEX1 時送唯一 index 1；其餘 STOP 一律收尾，本輪最多兩個新 solver
Resources: 順序執行、最多並行一案；每案 1 CPU／6 GiB／Slurm 10 min，solver 上限 540 s、預估 3–6 min／raw 80–110 MB；不占滿共用 QOS 6 CPU
Commit allowed: handoff + results
Needs user decision: no

## 本輪授權

已讀 20261116T0005_user_authorizes_sar7_cdac_fix.md。其 header 雖為 yes，但明載使用者已授權、原話「Authorize CDAC fix」，並要求 Codex 直接設計交件。依目前使用者指定的判斷規則接續，不再詢問。本次僅一輪 SAR7 CDAC 修正；前晚 21:45:37 的委派時窗已結束，本次新授權以最多兩個有條件短案為界，不開無限迭代。不含 C1／C2、全 PVT、1.75 GS/s 正式驗證、刪 raw 或其他專案。

## 設計與既有資料推估

基準為 760348，保留原 CML＋source bridge、12 碼、1,080 ps、60／60 ps、1030 ps final read 與來源條件。原錯碼10／12、Σ23、max5，span113.918／127 LSB。

index 0 sar7_08_tt_cml_common_ref：只將共同 Vref span 乘 1.1148351553658304 至 63.74673330525213 mV，電容不變。對原案只應有兩條 reference source 變化。
index 1 sar7_09_tt_cml_main_ratio：只重配高四位比例、總量仍15 units；低位與 dummy 不變。Bridge 與兩個 shunt 同比縮至 nominal B/Cl=1/8，參考 span 63.74163008917902 mV。對原案只應有兩條 reference 與30條指定電容值變化，雙側鏡像。這是線性 MOM 等效模型的診斷，不是實際版圖／PDK 幾何驗證。

planner 使用既有去識別 summary 的84點和 audit 擬合，推估等效取樣輸入，非直接 sample 測量。零門檻模型預估 index0 Σ6／max1、index1 Σ3／max1，僅供 pilot 設計。原模型只逐碼重現4／12、最多差2碼；pre_s hold符號與最後 bit僅75／84一致，不能斷言全部錯碼都非 comparator，也不能保證新案達標。固定負載 surrogate、sample與settling的不確定性已寫在 Guide／PREDICTION，不再為其新增掃描。

## 本機驗證與凍結識別

七項測試、兩案 verify、planner 預估逐位元組重現、獨立科學／程式／範圍審查均通過；ZIP的9項manifest檔、10個payload entries、sidecar及目錄逐位元吻合。PLAN的修正向量與PREDICTION完全一致，不能臨場改數值。

- manifest SHA256: bb97b973466cc63a8d6c282b7ab142e35b4af911e107d01da0efa51ef3005153
- PREDICTION SHA256: 614dfd90d74d1d852d961ef03a50bfb65730983a04e37e6e66030e3ffdab11bf
- index0 portable SHA256: 0103266aeabb74abc86aeba0999e2b638876a9b4d786c321822485784e3b6368
- index1 portable SHA256: f2231b54d5138538c57102e5cd25dcc1047829ed71f02d79ab3d37d5726a6153

沿用760348原 wrapper 的既有 SAR7／relaxed／CML_RDEG／私有模型環境；只加新 CDAC_FIX_PACKAGE／ROOT／APPROVAL。approval-template 綁定新 root、兩個case、manifest及每案deck SHA，只改 approved=true。stage0／送出／等待完成／gate 的步驟見 Guide；不送 array、不預先stage1。stage與run都會拒絕不符gate的index1。

## 實測 gate 與收尾

必須零未解析、12筆 comparator／registered可讀且一致、CDAC共模下降絕對值≤10mV。STOP_TARGET 是 max≤1，STOP_CONVERGED 是 max≤2且Σ≤8；兩者一律不送第二案。只有有效、未收斂、且不劣於基準Σ23／max5才得到ALLOW_INDEX1。其餘STOP_REVIEW也不送第二案。第二案執行後不論結果都停止，不追加第三案或改值重送。

回報每案實際job、完整summary／measurements／tran SHA、wrong／Σ／max、unresolved、registered一致性、sample／CM／resolve／sense、資源與gate證據。原錯碼數需單獨列出：STOP_TARGET只代表max≤1，不能直接宣稱全數碼正確或完整SAR smoke通過。未執行的case標skipped；不得把模型預估填成實測。新舊raw全部保留。完整性失敗依原規則停下並回報Needs user decision: yes，不能修改證據避過。

溝通只走本機，不用codex queue，不啟用archived steering command，transcript monitor僅唯讀。Claude單獨操作repo；只存無deck程式、去識別指標及handoff。ZIP、deck、模型與raw留核准OneDrive／Olympus。
