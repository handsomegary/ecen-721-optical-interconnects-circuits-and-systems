Stage: SAR7 直接負載的 CDAC Vref 單案（TT）
Status: done
Decision: STOP — 滿刻度 trim 有效（比較器總絕對碼差 30→8、max 7→2、滿刻度殘差 ~10.5→≤1.9 LSB），但仍 7/12 錯（全為 ±1、一個 +2），剩餘來自取樣誤差（最大 1.41 LSB）與 MSB 中點 offset（code 63 的 b6 前殘差 +2.89 LSB）；未達驗收。
Summary: 單案 sar7_05_tt_ref_trim，job 760234 COMPLETED 3:24（solver 187.7 s，raw 82.6 MB）。0 未解析 bit；registered 碼 12/12 可讀（760091 為 6/12 null）。sar7_ref_trim_summary.json SHA256 b70fdf215050aacca931f97a7f5de2bf4dff5099f63daaf0e423e3698e211d70；tran SHA 805fbb02…
Run paths: ~/ecen720_28nm/runs/pam4_sar7_ref_trim_20261115.7rZhNP（package、approval.json、wrappers/env_reftrim.sh、wrappers/wrap_reftrim.sbatch、logs/reftrim-760234.log、sar7_05_tt_ref_trim/、sar7_ref_trim_summary.json）
Commit: 見下方 commit（handoff + results）
Needs user decision: no

## 檢查
- ZIP SHA256 c2268736c1b92a96ce6c9e68adfd06383c61cc54800959f6304483a7cb75e17f 相符；`sha256sum -c` 5/5 OK；`verify`：sar7_05_tt_ref_trim、portable deck 5f36c768…、nominal span 0.067767 V；unittest 2/2 OK（test_only_reference_pair_changes、test_only_final_read_moves）。
- 環境沿用 760091 的 env（SAR7_PACKAGE、C0_ORIGINAL、C0_SWITCH、C0_R5_ORIGINAL、PDK_ROOT、RELAXED_PACKAGE），新增 REF_TRIM_PACKAGE/ROOT/APPROVAL。
- Approval：template 的 root、單案、manifest SHA 194aa7a1…、deck SHA 5f36c768… 核對後只改 approved=true（依使用者對 Codex 建議批次的常設授權）。
- Staged bench（464c40be…）對 760091 bench 的 diff 只有兩行：V_RHI 0.478590→0.483884 V、V_RLO 0.421410→0.416116 V（span 57.18→67.77 mV，×1.18514，中點 0.45 V 不變）。

## 逐碼（comparator / registered；760091 → 760234）

| idx | 期望 | 760091 cmp/reg | 760234 cmp/reg | 760234 錯 bit | 760234 末端殘差 (LSB) | 取樣誤差 (LSB) |
|---|---|---|---|---|---|---|
| 0 | 64 | 65 / 65 | 64 / 64 | — | -0.41 | +0.01 |
| 1 | 0 | 0 / null | 0 / 0 | — | -1.88（原 -10.73） | -0.92 |
| 2 | 127 | 127 / 127 | 127 / 127 | — | +1.49（原 +10.34） | +0.68 |
| 3 | 31 | 25 / 25 | 31 / 31 | — | +0.25 | -0.13 |
| 4 | 96 | 103 / 103 | 97 / 97 | b0（前殘差 -0.14） | -0.13 | +0.22 |
| 5 | 63 | 64 / null | 64 / 64 | b6..b0（b6 前殘差 +2.89） | -0.82 | +0.35 |
| 6 | 65 | 66 / null | 66 / 66 | b1,b0（-0.11、-1.00） | -0.96 | +0.25 |
| 7 | 85 | 91 / 91 | 87 / 87 | b1（+0.46） | -0.42 | +0.61 |
| 8 | 42 | 38 / null | 42 / 42 | — | -0.60 | -0.10 |
| 9 | 1 | 0 / null | 0 / 0 | b0（-1.76） | -1.74（原 -10.49） | -1.41 |
| 10 | 126 | 127 / 127 | 127 / 127 | b0（+0.55） | +0.56（原 +9.42） | +0.66 |
| 11 | 64 | 66 / null | 65 / 65 | b0（+0.23） | +0.24 | +0.46 |

（LSB = 0.78125 mV 差動。「前殘差」= 該 trial 啟動前的 CDAC 殘差。）

## Gate 數字（對 760091）
- 錯碼：10/12 → 7/12；未解析 bit 0 → 0；logic_smoke_pass false。
- 比較器總絕對碼差：30 → 8；max |碼差|：7 → 2（idx 7，85→87）。
- 未達 rail 的 final outputs（registered null）：6 → 0。
- 最大取樣誤差：1.373 → 1.406 LSB（不變，取樣路徑）。
- 滿刻度殘差（idx 1/2/9/10）：-10.73/+10.34/-10.49/+9.42 → -1.88/+1.49/-1.74/+0.56 LSB。
- 共模變化 final：-112.46/-109.12 → -112.41/-109.04 mV（不變，trim 保持 0.45 V 中點）。
- Max resolve delay 54.3 → 52.2 ps。

## 判讀：Vref 改善 vs 晚讀改善
- **Vref（比較器碼）**：中段大錯（idx 3 -6→0、idx 4 +7→+1、idx 7 +6→+2、idx 8 -4→0）全部是 Vref span 修正造成，comparator code 本身改變，逐 bit compare 時刻未動。
- **晚讀（registered 輸出）**：6 個 null registered（idx 1,5,6,8,9,11）全部變可讀，且 12/12 registered = comparator。其中 idx 5/6/9 的 comparator 碼與 760091 相同（64/66/0），只是輸出可讀；idx 1/8/11 則同時有 Vref 改善。即 null→可讀是 1027→1030 ps 讀點效果，與 760174 的 b0=0 rail 時間（end_s + 3.5 ps 內）一致。
- **剩餘錯誤**：
  1. idx 9（1→0）、idx 10（126→127）：取樣誤差 -1.41/+0.66 LSB 加上末端殘差 ±0.5–1.7 LSB，屬取樣路徑誤差（760091 已有，trim 不影響）。
  2. idx 5（63→64）：b6 trial 前殘差 +2.89 LSB（取樣誤差只有 +0.35），表示 MSB 中點相對輸入有 ~+2.5 LSB offset／b6 權重與其餘 bit 和不匹配（760174 的 b6=52.57 vs b5..b0 和 54.59 LSB，×1.185 後差 ~2.4 LSB），屬 MSB DNL，不是 gain。
  3. idx 4/6/7/11：前殘差 |0.1–1.0| LSB 的低位判斷錯，與取樣誤差 +0.2–0.6 LSB 同量級。
- 此為相同 12 碼的增益診斷，非跨碼驗證，亦未達 1.75 GS/s；未加 sweep、未重跑舊案。

## Raw
- 新舊 raw 都保留：760234 raw 35 MB（du）於 sar7_05_tt_ref_trim/raw；760091 raw 不動。
