Stage: SAR7 CDAC 第二輪：760874 保留證據查核（零新 solver）
Status: done
Decision: PROCEED — 證據齊全；實際控制字 84/84 符合舊 prefix、#8 sample 誤差只 −0.19 LSB，#8 b2 是比較器在 sense 仍為負時於 30–50 ps 再生期翻成 1（單向偏 1），不是 acquisition 或控制字錯
Summary: collector 761255 COMPLETED 0:21（1 CPU／6 GiB），新 solver 0（本輪額度仍 0／2，另有 8 小時委派時窗至 23:15）
Run paths: Olympus ~/ecen720_28nm/runs/pam4_sar7_cdac_round2_audit_20261116.c85nB5；OneDrive ECEN 720/outputs/PAM4_SAR7_CDAC_ROUND2_EVIDENCE_20261116/
Commit: 見下（handoff + results）
Needs user decision: no

## 完整性
- ZIP 7f72ce581b3d8a5aa50b26564271fca3cba7ff71031eda4a07ffc5ef5611a598 一致；sha256sum -c 3/3 OK；verify「sar7_09_tt_cml_main_ratio f2231b54… retained-only collector verified」；unittest 3/3 OK。
- 環境：上輪 env_cdacfix.sh ＋ 舊 audit 的 PAM4_SAR7_ISOLATE_PACKAGE／ROOT ＋ PAM4_SAR7_AUDIT_PACKAGE＝原 CDAC_AUDIT 包。來源目錄未寫入；原 summary／measurements SHA 前後不變。
- 輸出 SHA（全長）：
  - sar7_cdac_round2_retained_audit.json 0e9e091578e93bccaddbffc9c795de26e1d1c6594f263b844591f58f1830a4e9
  - source_summary.json 6573a387cf24fccfad5ffbaa98016b59f22d21402b7b59cfbba8ef72527fc150（＝原檔 byte-exact）
  - source_measurements.json 416735e041446ec7e596498ae5ca537b5851139a42e030b899437e260ee47cd6（＝原檔 byte-exact）
  - repo 聚合摘要 sar7_cdac_round2_audit_aggregate.json e29bad3e670a6b1293268d5706964cae7105707401e092b4d29783efbe545570（不含 trial 時間序列）

## 核心數字（LSB＝0.78125 mV）
- 原計分不變：wrong 6/12、Σ7、max 2、unresolved 0、valid true。
- 實際控制字 vs 舊 prefix 假設：84/84 一致，0 不符；omitted pre-control states 0。
- #8（42→44）：實際 main sample 誤差 −0.191 LSB、low −0.207 LSB（不是 +1.5 LSB）→ 不支持 acquisition。
  - b2 trial：pre 控制字 44（=舊 prefix）；pre held −0.807 LSB、sense −0.482 LSB；期望 0、決策 1。
  - compare 後：sense 在 0–30 ps 維持負（−0.48→−0.32 LSB）；latch 差 (out1−out0) 0 ps −1.6 mV、15 ps −15.7 mV、30 ps −37 mV（偏 0），50 ps +861 mV 翻成 1，同時 sense 變 −1.15 LSB（疑似 kickback，時間點是翻轉之後）。
- 全部 84 trial 的 decision vs pre 符號：held 79/84、sense 79/84 一致；5 個不一致全部是「輸入負、決策 1」（#4 b5、#4 b0、#6 b0、#7 b1、#8 b2），沒有任何「輸入正、決策 0」。
  - 描述性門檻（Claude 由 trial 表整理，不是 offset 量測）：sense 端負輸入 −0.22…−0.554 LSB 判 1、≤ −0.673 LSB 判 0；held 端 −0.33…−0.924 LSB 判 1、≤ −1.127 LSB 判 0 → 有效判決門檻約 held −1.0 LSB／sense −0.6 LSB，方向固定偏 1。
  - 15 ps 時所有 trial 的 latch 差都約 −13…−17 mV，與輸入無關（clock／共模造成的確定性初始不平衡），30 ps 起才跟輸入；近門檻負輸入在 30–50 ps 間翻為 1。
- 其餘超差（非符號不一致）：#7 b0 期望1判0（held −1.216）、#9 b0 期望1判0（#9 sample −1.639 LSB，即 max sample error 1.64 LSB 的來源）、#10 b0 期望0判1（held +0.160）→ 由殘差（sample／CDAC）造成，比較器判斷與輸入符號一致。
- CDAC 描述性 fit（以實際控制字＋實際 sample）：status identified，84 點；b6..b0 = 63.95／32.11／16.03／7.97／3.65／2.03／1.18 LSB，span 126.90（理想 127），sample gain 0.990，留一 RMSE 1.007 LSB。b2 3.65 偏小 0.35 LSB、b0 1.18 偏大；但 fit 同時吸收單向判決偏移，RMSE ≈1 LSB，不足以單獨定案 bridge／LSB-bank。
- sense affine：slope 0.588 V/V，zero-crossing −0.199 LSB（標示為 sense stage，不是 comparator offset）。

## 判讀（描述性，未選任何 trim／電路）
1. 不支持 acquisition（#8 sample −0.19 LSB）。
2. 不支持控制字／prefix 假設錯誤（84/84）。
3. 支持有效比較器偏移／再生動態：所有符號不一致都單向偏 1、輸入在 sense −0.2…−0.55 LSB 仍被判 1，翻轉發生在 30–50 ps 再生期，而非 trigger 時刻。
4. CDAC 權重偏差存在但較小（b2 −0.35 LSB），與 #7/#9/#10 的殘差型錯誤相關。
仍無法區分：靜態 latch offset 與再生期動態不對稱（load／reset 不平衡）之別；0.25 ps 儲存間距與稀疏點可能漏掉更快擾動，沒看到跳動不能排除 kickback；50 ps 時 sense 的大幅負移發生在翻轉後，只能視為 kickback 結果而非原因。

## 下一步
依 Guide：等 Codex 根據本資料凍結 pilot；Claude 未 stage、未送任何 solver、未改 approval。
