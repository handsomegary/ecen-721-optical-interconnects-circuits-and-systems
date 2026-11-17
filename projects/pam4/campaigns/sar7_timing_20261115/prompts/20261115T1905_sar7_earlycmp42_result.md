Stage: SAR7 單案比較器時序 pilot（TT、42 ps）（回覆 inbox/20261115T1856_sar7_earlycmp42_pilot.md）
Status: done
Decision: STOP — 比較器已全部解析（未解析 84→0 bit），但錯碼 5→10／12；決策跟隨 DAC 試碼前殘差（83/84），21 ps DAC 等待不足，logic_smoke_pass=false
Summary: job 760002 COMPLETED（2:06，exit 0），solver 114.8 s、raw 43.8 MB（du 20M）。12 筆轉換全部 scored，0 筆含未解析 bit，10 筆碼錯。最大取樣誤差 1.016 LSB（原 1.375）。解析時間 22.1／25.6／38.1 ps（min／med／max），58／84 個 bit > 25 ps，全部 < 42 ps。末端 CDAC 共模相對取樣 −112.4～−107.3 mV（原 −111.9～−106.7）。
Run paths: Olympus ~/ecen720_28nm/runs/pam4_sar7_timing_20261115.hcOXIX（summary：sar7_timing_summary.json sha 9a0d93d7…6b54；measurements.json sha e3e19829…269b；tran sha adf338dd…7676）
Commit: handoff + results（projects/pam4/campaigns/sar7_timing_20261115/、handoff/archive/）
Needs user decision: no

## 核對
- ZIP SHA 8d4c53e7…a3 相符；`sha256sum -c` 5/5 OK；`verify` OK（deck 2470badd…4829）；unittest 3/3 OK。
- approval.json：approved=true，design_source_sha256 = SHA256SUMS.txt 的 sha 8a94e290…595e，authorization_basis = 使用者對 Codex 建議批次的常設授權（本案為 Recommended 單一短測、Needs user decision: no）。
- stage 後與原案 bench.scs 比對（model root 遮蔽後）：只有 7 行 `V_clk6..0` 不同；delay −17 ps、width +17 ps（下降緣不變），其餘完全相同。
- 只送 sar7_02_tt_earlycmp42；沒有送案 1 或其他 sweep。原案 raw 與新案 raw 都保留。

## 逐筆結果（expected bits → 新／舊）

| # | exp | obs | exp bits | 新 bits | 舊 bits | 取樣誤差 LSB | 末端殘差 mV |
|---|---|---|---|---|---|---|---|
| 0 | 64 | 96 | 1000000 | 1100000 | ??????? | +0.012 | −19.13 |
| 1 | 0 | 0 ✓ | 0000000 | 0000000 | 000???? | −0.946 | −8.55 |
| 2 | 127 | 127 ✓ | 1111111 | 1111111 | 11????? | +0.670 | +8.21 |
| 3 | 31 | 15 | 0011111 | 0001111 | ??????? | −0.132 | +5.92 |
| 4 | 96 | 112 | 1100000 | 1110000 | 1?????? | +0.261 | −5.78 |
| 5 | 63 | 96 | 0111111 | 1100000 | ??????? | +0.300 | −19.48 |
| 6 | 65 | 96 | 1000001 | 1100000 | ??????? | +0.199 | −18.19 |
| 7 | 85 | 96 | 1010101 | 1100000 | ??????? | +0.559 | −3.69 |
| 8 | 42 | 64 | 0101010 | 1000000 | ??????? | −0.096 | −15.82 |
| 9 | 1 | 0 | 0000001 | 0000000 | 000???? | −1.016 | −7.93 |
| 10 | 126 | 127 | 1111110 | 1111111 | 11????? | +0.657 | +7.49 |
| 11 | 64 | 96 | 1000000 | 1100000 | ??????? | +0.440 | −18.61 |

每 bit 未解析數：新 6..0 = 0/0/0/0/0/0/0（舊 7/8/10/12/12/12/12）。
每 bit 與 expected 不符：b6 2、b5 5、b4 4、b3 2、b2 2、b1 2、b0 5。第一個錯 bit：b5 → #0,6,7,11；b4 → #3,4；b6 → #5,8；b0 → #9,10。

## 判讀（唯讀診斷，未改 Codex 程式）
1. **比較器解析已不是瓶頸**：0/84 未解析，最慢 38.1 ps < 42 ps。
2. **DAC 在比較時尚未 settle**：84 個決策中 83 個與「試碼前殘差」同號，只有 76 個與「讀取時殘差」同號。7 個 trial 的試碼前／讀取時殘差異號，7 個全都跟隨試碼前的符號。例：#0 b5 試碼前 +1.17 mV、讀取時 −19.69 mV，判 1（應 0），解析 37.0 ps；#6、#11 b5 同型。b5 試碼期間 DAC 峰值擾動達 21.9 mV，b6／b4 約 12 mV，b3 以下 ≤ 6.4 mV。所以錯碼集中在 MSB 段（b6–b4），而這些錯會傳到後續 bit。
3. **#9、#10 的 b0 錯是取樣誤差造成的**：試碼前與讀取時殘差同號（−8.6/−7.9、+8.2/+7.5 mV），決策與殘差一致，但取樣誤差為 −1.016／+0.657 LSB，CDAC 殘差本身就落在錯的一側；與時序無關。
4. #8 b6 是唯一與試碼前殘差異號的決策（試碼前 −4.87、讀取時 −15.11 mV，判 1）：兩個符號都不支持判 1，可能是 kickback／偏移，需看波形。
5. 共模：讀取時 CDAC 共模從 b6 的 746–748 mV 逐 bit 下降到 b0 的 654–659 mV；末端相對取樣 −107～−112 mV，與原案幾乎相同（提早時脈沒改變共模漂移）。

結論：25 ps 時比較器不夠時間；42 ps／21 ps 時 DAC 不夠時間。兩者在 66 ps/bit 內無法同時滿足。下一步需要 Codex 決定，例如：延長每 bit 時間（降取樣率或非均勻 bit 時序，給 MSB 較長 DAC 等待）、加快 CDAC 試碼 settle（開關／驅動），或掃描中間點（例如 33／30 ps）。我不會自行送其他時序案。

## 資源
1 CPU、6 GB、Slurm 30 min；實際 elapsed 2:06、solver 114.8 s、raw_bytes 43,822,549。node n03。
