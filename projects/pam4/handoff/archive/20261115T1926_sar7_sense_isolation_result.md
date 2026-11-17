Stage: SAR7 比較器輸入隔離單案＋760091 輸出位元查核（回覆 inbox/20261115T1916_sar7_sense_isolation.md）
Status: done
Decision: STOP — 理想隔離後，CDAC 共模下降從約 −110 mV 縮小到 −4.3 mV，滿刻度殘差從約 ±10 LSB 減半到約 ±5 LSB，最大碼誤差從 7 降到 3。但錯碼仍是 10/12。比較器負載只解釋一部分誤差，剩下的是 CDAC 本身的轉移與權重誤差。暫存輸出無法判讀的問題獨立存在：只要 b0 判為 0，輸出就無法判讀。
Summary: job 760132 COMPLETED（3:34，exit 0），solver 184.8 s，raw 82.6 MB（du 35M）。比較器 bit 未解析 0/84，錯碼 10/12（與 760091 相同）。Σ|Δcode| 從 30 降到 15。最大取樣誤差 1.687 LSB（760091 為 1.373）。末端 CDAC 共模相對取樣 −4.30～−4.26 mV（760091 為 −112.5～−109.1）。最大解析時間 46 ps（760091 為 54.3）。暫存碼 null 5/12（760091 為 6/12），全部是 b0 輸出 pair 在 end_s 停在約 0.322／0.768 V。
Run paths: Olympus ~/ecen720_28nm/runs/pam4_sar7_isolate_20261115.kbTlvs（sar7_isolation_summary.json sha 3cde9a2f…2caf；sar7_760091_rail_audit.json sha 7beb925b…781c；measurements.json sha 3e829e90…c995；tran sha a3c3572c…a4b7）
Commit: handoff + results（projects/pam4/campaigns/sar7_isolate_20261115/、handoff/archive/）
Needs user decision: no

## 核對
- ZIP SHA 43ecd154…0393 相符；`sha256sum -c` 5/5 OK；`verify` OK（deck dbd9f5c1…e0ed）；unittest 2/2 OK。
- relaxed 依賴沿用 760091 的 run root：`~/ecen720_28nm/runs/pam4_sar7_relaxed_20261115.SvCNXK`，manifest SHA 由套件檢查通過。SAR7、C0、SWITCH64、r5 及私有模型都沿用原安裝。
- approval.json 由 `approval-template` 產生，只把 `approved` 改成 true。內容綁定單一 case `sar7_04_tt_ideal_sense_isolation`、design_source_sha256 b03999e4…7dc7、deck_sha256 dbd9f5c1…e0ed，以及新 root。授權依據（使用者對 Codex 建議批次的常設授權；Recommended 單案；Needs user decision: no）只記在本機 state。
- stage 後的 bench.scs（sha ca1a9fbf…30ac，執行前後相同）和 760091 的 bench.scs 逐行比對，只有 16 行 diff：新增 `EISO_P (isop 0 mp 0) vcvs gain=1`、`EISO_N (ison 0 mn 0) vcvs gain=1`，以及 XCMP6..0 的輸入從 `mp mn` 改為 `isop ison`。沒有其他差異。
- 只送一案。沒有重跑 759069／760002／760091，沒有 sweep。兩側 raw 全部保留。collect-only 不需要（run 模式已完成收集）。

## 760091 rail 查核（baseline-audit，唯讀，結果寫到新 root）
6 筆 null（#1、5、6、8、9、11）全部只在 **bit 0**。比較器 q0 在 compare read 和 end_s 都在 rail：read 約 0.00006～0.003／0.899 V，end_s 約 0.0076／0.8999 V，original_cmp = final_cmp = 0。只有 output pair 在 end_s 停在約 **0.322／0.768 V**，沒有達到 0.18／0.72 V 的判讀門檻。所以問題在比較器之後的末端輸出／暫存傳遞（或 end_s 讀點），不是比較器失去 rail。
另一個規律（兩案相同）：registered null 的碼全是偶數（b0 = 0），可判讀的碼全是奇數（b0 = 1）。760091 的 null 碼為 0、64、66、38、0、66，可讀碼為 65、127、25、103、91、127。760132 的 null 碼為 0、64、66、88、0，可讀碼為 65、127、29、99、41、127、65。換句話說，b0 判為 0 的那條輸出路徑在 end_s 前沒有 settle 到 rail，判為 1 的則正常。760132 的 5 筆 null 也是同一個 bit 0、同樣的 0.322／0.768 V。

## 逐筆對照（Δ = comparator − expected；殘差以 LSB = 0.78125 mV 計）

| # | exp | 760091 cmp | Δ | 末端殘差 | 760132 cmp | 暫存 | Δ | 末端殘差 | 取樣誤差 |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 64 | 65 | +1 | −0.34 | 65 | 65 | +1 | −0.43 | +0.014 |
| 1 | 0 | 0 | 0 | −10.73 | 0 | null | 0 | −5.58 | −1.298 |
| 2 | 127 | 127 | 0 | +10.34 | 127 | 127 | 0 | +5.23 | +1.094 |
| 3 | 31 | 25 | −6 | +0.11 | 29 | 29 | −2 | +0.20 | −0.377 |
| 4 | 96 | 103 | +7 | +0.04 | 99 | 99 | +3 | −0.04 | +0.467 |
| 5 | 63 | 64 | +1 | −0.72 | 64 | null | +1 | −0.93 | +0.279 |
| 6 | 65 | 66 | +1 | −0.56 | 66 | null | +1 | −0.94 | +0.213 |
| 7 | 85 | 91 | +6 | −0.29 | 88 | null | +3 | −1.08 | +0.682 |
| 8 | 42 | 38 | −4 | −0.52 | 41 | 41 | −1 | −0.05 | −0.267 |
| 9 | 1 | 0 | −1 | −10.49 | 0 | null | −1 | −5.31 | −1.687 |
| 10 | 126 | 127 | +1 | +9.42 | 127 | 127 | +1 | +4.22 | +1.072 |
| 11 | 64 | 66 | +2 | −1.13 | 65 | 65 | +1 | +0.23 | +0.385 |

每 bit 錯誤次數：760091 為 b6 1、b5 1、b4 1、b3 3、b2 5、b1 6、b0 6。760132 為 b6 1、b5 1、b4 1、b3 2、b2 2、b1 5、b0 9。

## 判讀（唯讀，未改 Codex 程式）
1. **共模**：讀取時的 CDAC 共模固定在 763.8～763.9 mV，760091 則逐 bit 從 747 降到 654 mV。末端相對取樣只變 −4.3 mV。原本約 110 mV 的下降來自比較器輸入的總負載（靜態寄生加上切換回灌，本對照不能區分這兩項）。
2. **滿刻度**：±49.6 mV 輸入下的末端殘差從約 ±10 LSB 降到 ±4.2～5.6 LSB，約減半，但仍有約 5 LSB（約 4 mV）的增益短缺。
3. **中間碼**：#3、#4、#7、#8 的 |Δ| 從 6、7、6、4 降到 2、3、3、1，但末端殘差仍 < ~1 LSB，碼卻錯 1～3。表示 CDAC 權重仍非理想二進位。和 760091 一樣是靜態權重誤差，只是變小了。
4. **比較器判斷**：78/84 個決策與讀取時殘差同號。6 個反號的殘差都 ≤ 0.33 mV（< 0.43 LSB），都在零點附近。試碼期間殘差峰值擾動 2.0 mV（760091 為 2.8 mV）。
5. **取樣**：最大取樣誤差變大，從 1.373 到 1.687 LSB（#9）。#1／#2／#9／#10 這四個滿刻度附近的碼取樣誤差 ±1.07～1.69 LSB，可能是 b0 錯誤數增加（6 → 9）的原因之一（未驗證）。
6. 依交接文字的判斷規則：共模、滿刻度和錯碼大小都有改善，所以實體隔離值得評估。但仍有 10/12 錯碼和約 5 LSB 滿刻度誤差，CDAC 轉移與權重也要查。兩條路線都由 Codex 決定，我不會自行送其他案。另外，b0 = 0 輸出路徑在 end_s 未達 rail，應單獨看末端邏輯或 end_s 定義。

## 資源
1 CPU、6 GB、Slurm 30 min；elapsed 3:34、solver 184.8 s、child peak RSS 241 MB、raw_bytes 82,623,749。node n03-poseidon。raw 保留在 Olympus（760091 約 36M 與 760132 約 35M 都未刪）。
