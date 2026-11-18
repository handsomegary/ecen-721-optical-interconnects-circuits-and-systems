Stage: PAM4 deskew C2 TT 配對多 seed 批次（seeds 1002–1020，95 新案；seed 1001 = C1 僅描述）
Status: done
Decision: PROCEED — 95/95 COMPLETED、status c2_complete、clipping 全 0；兩個方向補償在 19/19 新 seed 的 primary 與 secondary 都改善，0 同分 0 退化，單尾配對符號檢定 p = 1.9×10⁻⁶（每項）
Summary: N 晚 +60（C0 正式選擇）primary 錯誤 7316→2042（ΔSER −13.66%）、secondary 16846→13168（−9.53%）；P 晚 −60 固定碼診斷 primary 4482→1811（−6.92%）、secondary 15868→12939（−7.59%）（新 19 seed、每臂 38,608 符號）
Run paths: Olympus ~/ecen720_28nm/runs/pam4_c2_tt_paired_20261116.XbmQi3/root/c2_tt_paired_summary.json（SHA a164336ee415c5e7d0c10e60db7a4e719c4bd269de528255a909ac41f8c27ede）；repo projects/pam4/campaigns/c2_tt_paired_20261116/results/
Commit: 見下方（handoff + results）
Needs user decision: no

## 執行收據

- Array 761525 `0-94`（%3，2026-11-17 07:52 依使用者「把剩下C2 seed全部排上去」改 %5；SAR7 租約期間 5→4→5），2026-11-16 21:59 CST 提交，最後一案 761525_94 於 2026-11-18 14:39:34 CST 完成。sacct 95/95 COMPLETED，無需 collect-only。
- solver 平均 6,723 s、最大 8,201 s，合計 177.4 CPU-h（估 159–161）；peak RSS 最大 287,572 KiB；新 raw 13,846,092,927 bytes（估上限 13,846,098,950）。
- `c2_run.py summarize`（原參數）rc0：`c2_complete`，fresh 95／total 100；C1 證據 summary `ec30d9d9…`、review `f3e983d0…`、C1 approval `3a0ad0e1…`、C1 manifest `abc945cc…`；C2 approval `feb8039c…`、manifest `603f03f0…`；C0 選擇 P 晚 0、N 晚 60。
- 每案每端 2,032 符號；100 案 × 2 端 clipped_count 全為 0。

## 1. 各條件總和（20 seed，各 40,640 符號／臂）

| 條件 | primary 錯 | primary SER | secondary 錯 | secondary SER |
|---|---|---|---|---|
| zero（無 skew） | 2490 | 6.13% | 15510 | 38.16% |
| P 晚 0（未補償） | 4717 | 11.61% | 16730 | 41.17% |
| P 晚 −60（固定碼診斷） | 1921 | 4.73% | 13628 | 33.53% |
| N 晚 0（未補償） | 7696 | 18.94% | 17762 | 43.71% |
| N 晚 +60（C0 正式選擇） | 2144 | 5.28% | 13860 | 34.10% |

## 2. 新 19 seed 配對推論（排除 C1 seed 1001）

| 方向 | 端 | 前→後 錯誤 | ΔSER | 改善/同分/退化 | 單尾符號檢定 p |
|---|---|---|---|---|---|
| P 晚 −60 | primary | 4482→1811 | −6.92% | 19/0/0 | 1.91e−6 |
| P 晚 −60 | secondary | 15868→12939 | −7.59% | 19/0/0 | 1.91e−6 |
| N 晚 +60 | primary | 7316→2042 | −13.66% | 19/0/0 | 1.91e−6 |
| N 晚 +60 | secondary | 16846→13168 | −9.53% | 19/0/0 | 1.91e−6 |

- 每 seed 差（新 19 seed）：P primary −116～−175、P secondary −111～−182、N primary −246～−335、N secondary −162～−213。seed 1001（C1）為 −125／−173／−278／−224，落在同一範圍。
- 限制（summary 原文）：seed 1001 由 C1 gate 選出，排除於推論；P 晚 −60 是固定碼診斷；長序列 ADC 計分仍用理想 7-bit 量化器。secondary 絕對 SER 33.5–43.7% 仍高，不等同參考論文的絕對性能；此批只證明固定刺激、TT、兩個 skew 端點下的配對方向。Gray BER 與參考實測 BER 條件不同。

## 3. RAW

- 依 `c2_raw_retire_after_summary_20261116`（使用者：「C2跑完分析完一樣工作站會刪除RAW吧」），commit／publish 之後刪除 95 案的 `raw/` PSF，以及 `bench.scs.tranResponse.srf`，收據寫在 `RAW_RETIRED_C2_*.txt`。結果見下方「RAW 清理結果」段。
