Stage: SAR7 放寬時序單案診斷（TT，60 ps + 60 ps）（回覆 inbox/20261115T1906_sar7_relaxed_pilot.md）
Status: done
Decision: STOP — 放寬到 60 ps DAC 等待＋60 ps 比較後，比較器 0/84 未解析，但錯碼仍是 10／12。錯誤從 MSB 大錯變成 ±1～7 code 的小錯，而且 CDAC 末端殘差大多 < 1 LSB，所以不是時序問題，比較像 CDAC 權重或增益的靜態誤差；另有 6 筆暫存輸出未落到 rail，logic_smoke_pass=false
Summary: job 760091 COMPLETED（3:22，exit 0），solver 185.5 s，raw 82.6 MB（du 36M）。12 筆全部 scored；比較器 bit 未解析 0/84（6..0 全 0），錯碼 10/12（與 760002 相同）。套件的 unresolved_conversions=6，原因是暫存輸出碼無法判讀（registered=null，#1,5,6,8,9,11），不是比較器未解析。解析時間 21.8／30.0／54.3 ps（min／med／max），其中 6 個 bit > 42 ps，但全部 < 60 ps。最大取樣誤差 1.373 LSB（760002 為 1.016，759069 為 1.375）。末端 CDAC 共模相對取樣 −112.5～−109.1 mV（760002 為 −112.4～−107.3）。
Run paths: Olympus ~/ecen720_28nm/runs/pam4_sar7_relaxed_20261115.SvCNXK（summary：sar7_relaxed_summary.json sha e52348a1…76c9；measurements.json sha c5d9cac3…0290；tran sha 1ce73eae…873a）
Commit: handoff + results（projects/pam4/campaigns/sar7_relaxed_20261115/、handoff/archive/）
Needs user decision: no

## 核對
- ZIP SHA 55ec7f5d…de64 相符；`sha256sum -c` 5/5 OK；`verify` OK（portable deck ab1d6316…12f3）；unittest 3/3 OK。
- approval.json 由 `approval-template` 生成，root 與 case 各一個（sar7_03_tt_relaxed），design_source_sha256 7bb2bb49…1040，deck_sha256 ab1d6316…12f3；只把 `approved` 改成 true。授權依據（使用者對 Codex 建議批次的常設授權；本案為 Recommended 單一短測、Needs user decision: no）只記在本機 state。
- stage 後的 bench.scs（sha 63acdf64…8473，執行前後相同）與原案 sar7_00_tt_pilot/bench.scs 逐行比對，共 25 行不同：8 條 track／lowtrack／reset／conv 脈波、14 條 trial／clk 脈波（共 22 條）、srcp／srcn 兩條 PWL 的時間軸，以及 tran stop（6.85075 ns → 12.92 ns）。週期 571.4 → 1080 ps，trial width 64 → 121 ps，clk 比 trial 晚 60 ps。PWL 電壓值與參考電壓由 unittest 確認不變。
- 只送 sar7_03_tt_relaxed，沒有重跑 759069 或 760002。全部 raw 保留。

## 逐筆結果

| # | exp | 比較器碼 | 暫存碼 | exp bits | obs bits | Δcode | 取樣誤差 LSB | 末端殘差 LSB |
|---|---|---|---|---|---|---|---|---|
| 0 | 64 | 65 | 65 | 1000000 | 1000001 | +1 | +0.012 | −0.34 |
| 1 | 0 | 0 ✓ | null | 0000000 | 0000000 | 0 | −0.953 | −10.73 |
| 2 | 127 | 127 ✓ | 127 | 1111111 | 1111111 | 0 | +0.698 | +10.34 |
| 3 | 31 | 25 | 25 | 0011111 | 0011001 | −6 | −0.150 | +0.11 |
| 4 | 96 | 103 | 103 | 1100000 | 1100111 | +7 | +0.268 | +0.04 |
| 5 | 63 | 64 | null | 0111111 | 1000000 | +1 | +0.305 | −0.72 |
| 6 | 65 | 66 | null | 1000001 | 1000010 | +1 | +0.211 | −0.56 |
| 7 | 85 | 91 | 91 | 1010101 | 1011011 | +6 | +0.574 | −0.29 |
| 8 | 42 | 38 | null | 0101010 | 0100110 | −4 | −0.133 | −0.52 |
| 9 | 1 | 0 | null | 0000001 | 0000000 | −1 | −1.373 | −10.49 |
| 10 | 126 | 127 | 127 | 1111110 | 1111111 | +1 | +0.681 | +9.42 |
| 11 | 64 | 66 | null | 1000000 | 1000010 | +2 | +0.434 | −1.13 |

每個 bit 與 expected 不符的次數：b6 1、b5 1、b4 1、b3 3、b2 5、b1 6、b0 6（760002 則集中在 MSB：b6 2、b5 5、b4 4）。

## 判讀（唯讀診斷，未改 Codex 程式）
1. **時序已不是主因**：84 個決策中，80 個與讀取時殘差同號，81 個與試碼前殘差同號。和讀取時殘差反號的 4 個決策，殘差都只有 0.01～0.25 mV（約 0.3 LSB 以內）：#0 b0、#4 b0、#7 b0，以及 #5 b6（試碼前 +1.88 mV、讀取時 −0.01 mV）。這些是在零點附近，受比較器偏移或 kickback 影響，不是 DAC 沒有 settle。試碼期間 DAC 殘差的峰值擾動從 760002 的 21.9 mV 降到 2.8 mV（b6）及 ≤ 1.8 mV（其他 bit）。
2. **SAR 迴路有收斂，但碼不對**：#3、#4、#7、#8 的末端殘差只有 +0.11、+0.04、−0.29、−0.52 LSB，也就是 CDAC 已把輸入逼近到 1 LSB 內，輸出碼卻差 −6、+7、+6、−4。這表示 CDAC 實際的 bit 權重和理想二進位權重不同（靜態權重或增益誤差），問題不在比較器判斷。可能的成因包括：寄生電容改變了權重；末端共模下降約 110 mV，可能改變開關或電容的有效電壓。這兩點只是推測，未驗證。
3. **滿刻度端**：#1、#2、#9、#10 末端殘差約 ±9.4～10.7 LSB，表示在 ±49.6 mV 輸入下，CDAC 滿刻度差了約 10 LSB（約 8 mV）。#9（exp 1 → 0）與 #10（exp 126 → 127）同時受這個滿刻度差和 ~1 LSB 取樣誤差影響。
4. **暫存輸出**：#1、5、6、8、9、11 的 registered code = null，代表某些輸出 bit pair 在 conversion end_s 未達 0.18／0.72 V rail。比較器碼都已決定。這可能是 1,080 ps 週期下，輸出暫存讀取點與新時序不對齊，或暫存器本身有問題，需要 Codex 看 end_s 的定義。我沒有改 scorer。
5. 共模：讀取時 CDAC 共模每個 bit 下降約 15～16 mV，從 b6 的 746～747 mV 降到 b0 的 654～657 mV，和 760002 幾乎一樣。漂移與時序無關。

結論：60/60 ps 的充裕時序下錯碼仍是 10/12，而且錯誤是 SAR 收斂後的靜態碼誤差，所以下一步應先查 CDAC 權重、滿刻度與共模漂移，以及暫存輸出的讀取點，而不是再掃時序。依交接，我不會自行送其他案。

## 資源
1 CPU、6 GB、Slurm 30 min；實際 elapsed 3:22、solver 185.5 s、child peak RSS 236 MB、raw_bytes 82,624,492。node n03。
