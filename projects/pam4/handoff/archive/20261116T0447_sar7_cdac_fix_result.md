Stage: SAR7 CDAC span／比例修正 pilot（TT）結果
Status: done
Decision: STOP — index 0 gate ALLOW_INDEX1（Σ12／max2）→ 唯一 index 1 執行：錯碼 6／12、Σ7、max2（符合 STOP_CONVERGED 條件 max≤2 且 Σ≤8，但未達 STOP_TARGET max≤1）；本輪兩案用完，停止
Summary: 兩案皆有效（84/84 bit 解析、comparator＝registered、CDAC 共模下降約 −4 mV）。相對 760348（10／12、Σ23、max5）：index0 9／12、Σ12、max2；index1 6／12、Σ7、max2。sense gain 0.588 不變，符號 84/84。
Run paths: Olympus ~/ecen720_28nm/runs/pam4_sar7_cdac_fix_20261116.zN5rXs（round summary sar7_cdac_fix_round_summary.json SHA 56a3ad6a…526e）
Commit: 見下（handoff + results）
Needs user decision: no

## 執行依據
- 使用者授權「Authorize CDAC fix」；預測重現 ULP 差異由使用者選「A: run as is」（2026-11-16 01:54）。approval.json 只改 approved=true。
- ZIP SHA 8e290b0e…a9e7 吻合；sha256sum -c 9/9、verify、unittest 7/7 通過（前輪）。
- index 0 stage 後對 760348 portable 差異＝兩條共同參考 source；index 1 差異＝2 條 reference＋30 條電容值，雙側鏡像。順序執行，一次一案，各 1 CPU。

## 每案實測
| 項目 | 760348 基準 | index0 sar7_08_tt_cml_common_ref | index1 sar7_09_tt_cml_main_ratio |
| --- | --- | --- | --- |
| Slurm job | 760348 | 760873 COMPLETED 3:38 | 760874 COMPLETED 3:51 |
| 錯碼（comparator／registered） | 10／12 | 9／12 ／ 9／12 | 6／12 ／ 6／12 |
| Σ\|Δcode\| | 23 | 12 | 7 |
| max\|Δcode\| | 5 | 2 | 2 |
| unresolved bits（84） | 0 | 0 | 0 |
| registered 一致 | 是 | 是 | 是 |
| CDAC 末端共模變化 (mV) | −4.0／−3.9 | −4.002／−3.911 | −4.042／−3.971 |
| max sample error (LSB) | — | 1.617 | 1.639 |
| max resolve delay (ps) | — | 51.25 | 49.00 |
| sense projected gain／符號 | 0.588／83 of 84 | 0.5883／84 of 84 | 0.5882／84 of 84 |
| 比較前平均供應電流 (µA) | — | −260.69 | −260.69 |
| sense CM 範圍 (V) | — | 0.83478–0.83494 | 0.83478–0.83494 |
| Spectre wall (s)／peak RSS | — | 187.5／239 MB | 188.0／244 MB |
| raw bytes | — | 87,790,857 | 87,791,329 |
| logic_smoke_pass | — | false | false |
| gate | — | ALLOW_INDEX1（valid, CM≤10 mV） | 不再 gate（第二案後必停）；依規則數值落在 STOP_CONVERGED |

逐碼（expected → index0 / index1）：64→65/64、0→0/0、127→127/127、31→31/31、96→97/97、63→65/64、65→66/65、85→87/86、42→43/44、1→0/0、126→127/127、64→66/64。
- index0 錯碼多為 +1～+2（偏高），index1 修正了 64、65 兩處，但 42→44 由 +1 變 +2；96、126、1 的 ±1 不變。
- 實測 vs 預測：PREDICTION 預估 index0 Σ6／max1、index1 Σ3／max1；實測 Σ12／max2、Σ7／max2，皆差於預估（預估僅供設計，非實測）。

## SHA
- index0：summary d23a25bd…b1b0、measurements 36ddb57f…b86b、tran bf6751a2…8155、portable deck 0103266a…6368
- index1：summary 6573a387…c150、measurements 416735e0…cd6、tran 22de6869…f4b9、portable deck f2231b54…6153
- index1_gate.json：source summary d23a25bd…、manifest bb97b973…5153

## 結論與限制
- 目標（max≤1）未達；明顯收斂（max≤2、Σ≤8）由 index1 達到。不得宣稱全碼正確、完整 SAR smoke（logic_smoke_pass=false）、1.75 GS/s 或完整 ADC 驗證通過。
- 這是線性 MOM 等效模型診斷，不是版圖／PDK 幾何驗證。
- 本輪已兩個 solver，按 Guide 停止，未追加第三案。新舊 raw 全部保留（各約 88 MB）。
