Stage: SAR7 CDAC 第二輪：760874 保留證據查核（零新 solver）
ZIP: ECEN721_PAM4_SAR7_CDAC_ROUND2_AUDIT_20261116.zip（OneDrive ECEN 720/outputs）
SHA256: 7f72ce581b3d8a5aa50b26564271fca3cba7ff71031eda4a07ffc5ef5611a598
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_CDAC_ROUND2_AUDIT_20261116/HANDOFF_zh_TW.md
Recommended: 核對完整性、verify、三項測試後，只查已完成的 760874 原 PSF／measurements／summary，回傳實際 sample 與 pre_s 控制字及 #8 b2；不得 stage 或送新案
Resources: 最多一個 Python collector，1 CPU／6 GiB／10 min，PSF 只 parse 一次；零新增 raw／零 solver；本輪兩個新 solver 額度仍為 0／2
Commit allowed: handoff + results
Needs user decision: no
authorization_basis: 使用者於2026-11-16 15:14原話「授權再修一輪 SAR7 到 max ≤ 1」；本輪 approved=true 已由該新授權涵蓋，本步沒有 approval 變更

## 接續的新授權與本步界線

已讀 20261116T1514_user_authorizes_sar7_cdac_round2.md。其 yes 明載使用者已授權，依本次使用者指定規則接續，不再問。本輪仍最多兩案順序 solver、每案1CPU；不含 C1／C2、全 PVT、1.75 GS/s正式驗證、其他專案或刪raw。上輪已收尾，本次是新的第二輪。這個先行資料步驟不消耗solver額度；完成後回本機，由Codex根據實際資料凍結pilot，不自行調值或先送案。

## IEEE primary-paper 對照先於新設計

已依新版AGENTS讀兩篇原文文字／相關圖說並檢查拓樸、操作條件及驗證方法；PDF raster存取失敗，沒有從未見圖面取值。詳細差異與條件在Guide。

- Um et al., A-SSCC 2011：[DOI 10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608)。其split-CDAC方法隔離電容切換殘差，且先校比較器offset；bridge／LSB-bank寄生是候選原因，不能僅因hold／sense同號就排除比較器。
- Bheemisetti et al., JSSC：[DOI 10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115)，[指定paper頁](https://ieeexplore.ieee.org/document/10723273)。其DTFB、底板觸發非同步控制及共模下的offset校正，與我們固定60／60ps的StrongARM＋CML不同；不能以七顆比較器相同就移植速度／精度結論。

## 哪個結果會區分原因

760874只有#8的42→44超過1LSB；0101|010→0101|100保留高四位，第一個分歧為LSB-bank b2。因此bridge／LSB-bank值得查，但max sample error已約1.64LSB，舊planner又用推估sample／最終碼前綴，尚不能確定原因。

本步讀真正sample與真正pre_s控制對，對#8 b2檢查trigger前後hold／sense與原決策：sample已正偏約1.5LSB可支持acquisition；把實際sample納入後仍有穩定低位步階錯誤可支持CDAC／bridge；trigger附近輸入支持0但決策為1則支持有效offset／動態／時序問題。稀疏點與0.25ps儲存間距仍可能漏掉更快擾動，沒有看到跳動不能排除kickback。所有fit都屬描述性，不在這步選任何trim或新電路。

## 套件與執行證據

包內只有collector、三項測試、Guide與manifest。verify、測試、獨立程式審查、ZIP／sidecar／三項manifest檔與目錄核對全部通過。collector只有verify／audit入口，不呼叫base.collect、不建立approval、不stage或run solver。原summary／measurements必須存在，不能為了通過而改寫來源或重跑。

綁定parent CDAC_FIX manifest bb97b973466cc63a8d6c282b7ab142e35b4af911e107d01da0efa51ef3005153；來源760874／sar7_09_tt_cml_main_ratio／zN5rXs，summary 6573a387cf24fccfad5ffbaa98016b59f22d21402b7b59cfbba8ef72527fc150、measurements 416735e041446ec7e596498ae5ca537b5851139a42e030b899437e260ee47cd6、tran 22de6869fca439d446ad6e04de2e1e1809708fce82081c8b40215ef7061fb4f9。先後驗證原證據及inventory不變；只在分離新root寫分析JSON和byte-exact JSON複本。

沿用760874原環境及舊CDAC_AUDIT wrapper依賴，尤其PAM4_SAR7_ISOLATE_PACKAGE；parent與舊audit包不可指到新包。若需Slurm，只准一個1CPU／6GiB／10min的collector，不是solver。

## 交回資料與之後的額度

將完整新分析JSON、source_summary.json、source_measurements.json（原檔byte-exact複本）放回核准OneDrive ECEN 720/outputs/PAM4_SAR7_CDAC_ROUND2_EVIDENCE_20261116/，回outbox給完整SHA與#8 sample/b2核心指標、實際控制字是否符合舊prefix假設、fit／留一誤差及仍無法區分之處。完整trial／有限時間點資料留OneDrive／Olympus；repo僅放聚合摘要與無deck程式／handoff，不放原波形、PDK／模型或deck。

新資料回來後本輪仍最多兩個新solver，採實測gate、達標或收斂就停；兩案後不論結果都收尾，不開第三輪。未得Codex固定pilot前不要自行占用任何solver額度。未來預估數值用具名容差比較，來源檔與核准deck的完整SHA仍用精確檔案核對；不要把跨平台ULP差異混同來源完整性失敗。

本機通道與read-only transcript monitor不變，不用codex queue，不啟用archived steering command。Claude單獨操作repo；SHA／證據完整性實際失敗依原規則停下回報Needs user decision: yes。
