Stage: SAR7 有效判決門檻：互補負載與固定微調的獨立短案
Status: done
Decision: PROCEED — index0（互補 NOR 負載）gate STOP_TARGET：有效、12 碼 max 1 LSB、Σ6；依規則不跑 index1，本包收尾
Summary: 760874 基準 wrong6/12 Σ7 max2 → 761279 wrong6/12 Σ6 max1；84/84 bit 解析、registered 12/12 一致、CDAC CM −4.04/−3.97 mV；共同 sense 門檻區間由約 (−0.673, −0.554] 移到 (−0.220, +0.078] LSB
Run paths: ~/ecen720_28nm/runs/pam4_sar7_offset_pilot_20261116.oGLb07（pointer ~/ECEN721/.sar7_offset_base）；case sar7_10_tt_matched_q_load
Commit: 見本機 state.json（本訊息 commit 前寫成；repo projects/pam4/campaigns/sar7_offset_pilot_20261116/）
Needs user decision: no

## 處理的訊息與完整性

- Inbox：20261116T1556_sar7_offset_load_pilot.md。ZIP ECEN721_PAM4_SAR7_OFFSET_PILOT_20261116.zip SHA-256 e766d044…10f0（本機與 Olympus 皆相符，sidecar OK）。
- `sha256sum -c SHA256SUMS.txt` 9/9 OK；manifest SHA f04d9107…0e90。
- `verify`：index0 deck 2070f861…2347、index1 deck 9767e0cb…cf43，與 header 相符。
- unittest 14/14 OK；`planning.py --check PREDICTION.json`：「Prediction reproduced within numeric tolerance」。
- approval-template 綁定新 root、兩 case、manifest、兩 deck SHA、expires 2026-11-17T05:15:00Z；只把 approved 改 true，未加欄位。authorization_basis：使用者原話「八小時授權任何修正」（2026-11-16 15:15–23:15 Chicago）。
- 環境：沿用 760874 的 env（CDAC_FIX／CML_RDEG／RELAXED／SAR7／C0／私有模型 r7_vm_shrink），只加 OFFSET_PACKAGE／ROOT／APPROVAL 與 cutoff epoch（wrappers/env_offset.sh）。

## index0：sar7_10_tt_matched_q_load

- Stage 差異（對 760874 的 sar7_09 bench.scs）：恰好 7 行新增 `XQCOMPLOADk (trialk qkn dqloadk vdd) SAR_NOR`（與原 `XBitbk (trialk qkp bitkb vdd)` 同輸入角色），加上 save 行多 14 個 XCMPk.x/XCMPk.y；無其他電氣差異。
- 送件：`test "$(date -u +%s)" -lt cutoff && sbatch …` 通過；job **761279** Submit 2026-11-16T15:58:22 CST（21:58 UTC，早於截止），COMPLETED 0:0，Elapsed 4:07，solver 207.8 s，1 CPU，raw 110,961,727 bytes（du 53 MB）。
- Gate（由原始 evidence／measurements／summary SHA 重驗）：valid true、cdac_cm_within_10mV true、max 1、Σ6 → **STOP_TARGET**。gate 輸出另存 `index0_gate_result.json`。
- index1（sar7_11_tt_cml_load_trim）**未 stage、未送**（STOP_TARGET 規則）。

### 逐碼（expected → comparator／registered；括號為 760874）

| idx | exp | 761279 | err | 760874 err |
|---|---|---|---|---|
| 0 | 64 | 64/64 | 0 | 0 |
| 1 | 0 | 0/0 | 0 | 0 |
| 2 | 127 | 127/127 | 0 | 0 |
| 3 | 31 | 31/31 | 0 | 0 |
| 4 | 96 | 95/95 | −1 | +1 |
| 5 | 63 | 64/64 | +1 | +1 |
| 6 | 65 | 64/64 | **−1（新錯）** | 0 |
| 7 | 85 | 85/85 | **0（修正）** | +1 |
| 8 | 42 | 43/43 | +1 | +2 |
| 9 | 1 | 0/0 | −1 | −1 |
| 10 | 126 | 127/127 | +1 | +1 |
| 11 | 64 | 64/64 | 0 | 0 |

- comparator 與 registered：各 12/12 可讀、wrong 6、Σ6、max1，一致性 true。
- 原正確碼退化：**有一碼**，#6（65→64，−1）；#7 由 +1 變正確；#4 由 +1 翻成 −1；#8 由 +2 降為 +1。錯誤現在正負都有（+1×3、−1×3），不是單向門檻偏移殘差。
- 84 bit 全解析（unresolved 0）；held_diff 與 sense_diff 的符號都與決策 84/84 一致。
- sample：max |sample error| 1.634 LSB；末端 CDAC 共模變化 −4.042／−3.971 mV（與 760874 同）；max resolve delay 45.5 ps。
- `logic_smoke_pass` = False；760874 的 summary 同樣是 False（既有旗標，gate 不使用）。我沒有追查它的定義。

### Sense 與有效門檻

- sense affine：slope 0.5879 V/V（與 760874 的 0.588 同）、output intercept +90.74 µV、RMSE 260.5 µV、sense-stage zero crossing −0.198 LSB（程式標註：sense 級 affine 零點，不是 comparator offset）。
- 共同 sense 門檻區間（47 個 0、37 個 1；可分離）：(−0.2205, +0.0785] LSB。1545 回報的 760874 區間約 (−0.6734, −0.5538] LSB，所以有效門檻往零移約 +0.45…+0.63 LSB，且包含零。
- 各 bit 區間（lower open、upper closed，僅描述有限資料）：b6 (−10.73, 1.76]、b5 (−0.241, 5.42]、b4 (−2.93, 2.89]、b3 (−1.88, 1.64]、b2 (−0.477, 0.900]、b1 (−0.220, 0.589]、b0 (−0.289, 0.078]。

### #8 b2（expected 0，決策 0，compare 9.322 ns，read 9.382 ns）：內部 x/y 與 buffered q 分開

| t−compare | held mV | sense mV | x, y (V) | x−y mV | q_p, q_n (V) | q_p−q_n mV |
|---|---|---|---|---|---|---|
| −0.5 ps (pre) | −0.623 | −0.372 | 0.900, 0.900 | −0.000 | 0.000, 0.000 | −0.000 |
| 0 | −0.620 | −0.372 | 0.965, 0.965 | −0.0006 | 0.0064, 0.0064 | −0.008 |
| 0.5 | −0.617 | −0.373 | 1.041, 1.041 | −0.0007 | 0.013, 0.013 | −0.009 |
| 2 | −0.608 | −0.368 | 1.046, 1.046 | +0.0005 | 0.008, 0.008 | +0.005 |
| 5 | −0.592 | −0.341 | 1.026, 1.026 | −0.028 | 0.001, 0.001 | −0.003 |
| 15 | −0.559 | −0.344 | 0.486, 0.485 | +1.549 | 0.040, 0.040 | −0.583 |
| 30 | −0.537 | −0.521 | 0.478, 0.423 | +55.65 | 0.270, 0.329 | −58.56 |
| 50 | −0.553 | +0.390 | 0.890, 0.026 | +864.0 | 0.010, 0.897 | −887.0 |
| 60 | −0.537 | −0.165 | 0.899, 0.002 | +897.4 | 0.0005, 0.900 | −899.3 |

- 觀察：開窗後 x/y 先一起被推高到約 1.04–1.05 V（共模，高於 pre 的 0.90 V），差值在 ±1 µV 以內，到 5 ps 仍平衡；約 15 ps 才開始分離，x>y（+1.55 mV），30 ps 為 +55.7 mV，50 ps 完成再生（x 高、y 低）。buffered q 與 x/y 反相（q_p 低、q_n 高），決策 0 正確。這些點來自保存資料的內插，屬於有限、確定性的取樣，不是雜訊或靜態 offset 量測。

## 判讀（限於本包設計）

- 補互補 NOR 後，CDAC、Vref、CML、時序都不變，有效 sense 門檻區間從約 −0.6 LSB 移到包含零；max 從 2 降到 1，Σ 從 7 降到 6。這支持「qpositive 多出的第一級 NOR fanout 參與了有效門檻偏移」的假設。
- 錯碼數沒有減少（6/12），#6 是新錯，殘差改為 ±1 雙向。剩下的誤差看起來比較像 CDAC／取樣量化殘差（max sample error 1.63 LSB），不是單向門檻；這部分未在本包中驗證。
- 依 Guide，達標就停止，不追小差異；不宣稱全碼正確、1.75 GS/s、PVT 或版圖驗證。index1 的固定微調補償沒有實測。

## SHA 與保存

- summary sar7_offset_pilot_summary.json：84b051d79c71979637416674aeb17b851104b199e544d9035870f8116f761a0a（sidecar 相符）
- measurements.json：b3a514de93049c737b9c1c7c18cafda99be78373e0638255f8127ea8e5af8394
- tran：d2e900facf2c569801cfb61e0794e0420f7b5cf62129f2ab98cdc1fe1131bc00
- run_status.json：e1e89051e8adfca83413a7d99774b5f3e5f684a58df0797fbd22fe10eaae267a；executed bench.scs 8bb61028…b5d7
- Olympus summary：~/ecen720_28nm/runs/pam4_sar7_offset_pilot_20261116.oGLb07/sar7_10_tt_matched_q_load/sar7_offset_pilot_summary.json
- Repo（handoff + results）：projects/pam4/campaigns/sar7_offset_pilot_20261116/（package 無 deck、不含 evidence/source_features.json；results 為去除 84 筆 sense.points 的聚合摘要＋gate；使用者 home 路徑已遮罩為 ~）。
- 新舊 raw 全部保留，未刪除任何資料。
