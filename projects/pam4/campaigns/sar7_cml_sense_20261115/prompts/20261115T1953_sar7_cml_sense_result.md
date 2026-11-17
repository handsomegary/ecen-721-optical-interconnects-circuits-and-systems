Stage: SAR7 原生 r5 CML 感測隔離單案（TT）（回覆 inbox/20261115T1946_sar7_cml_sense_pilot.md）
Status: done
Decision: STOP。實體感測臂的極性正確，CDAC 共模下降也降到和理想隔離相同（約 −4 mV）。但差動增益只有 0.033，輸入等效門檻偏移約 −14.5 mV（約 −18.6 LSB），結果錯碼 11/12，Σ|Δcode| 197。可能原因：本案沒有包含歷史 r5 B0 兩腿 source 之間的 250 Ω `B0_RDEG`。
Summary: job 760254 COMPLETED 3:40（n02-hera，solver 188.8 s，raw 87.8 MB／du 39M）。sar7_cml_sense_summary.json SHA256 a9670002152a3a9f4d16adbdc2f19db8376205fe8ac1691bf6f5d107b4a8518c；measurements.json SHA256 3663ae22…bc81；tran SHA256 73518bb0…cf71；staged bench 5d81cb98…f5b4（執行前後相同）。
Run paths: ~/ecen720_28nm/runs/pam4_sar7_cml_sense_20261115.SJl3lN（package、approval.json、wrappers/env_cml.sh、wrappers/wrap_cml.sbatch、logs/cml-760254.log、sar7_06_tt_r5_cml_sense/、sar7_cml_sense_summary.json）
Commit: handoff + results（projects/pam4/campaigns/sar7_cml_sense_20261115/、handoff/archive/）
Needs user decision: no

## 核對
- ZIP SHA256 8a8d5556…cb26cb 相符；`sha256sum -c` 5/5 OK；`verify` 顯示 sar7_06_tt_r5_cml_sense，portable deck 7c11149e…e170；unittest 2/2 OK（test_cml_does_not_modify_cdac_or_comparison_events、test_native_cards_have_explicit_body_and_inversion）。
- 環境沿用 760091／760234 的 env（SAR7_PACKAGE、C0_ORIGINAL、C0_SWITCH、C0_R5_ORIGINAL、PDK_ROOT、RELAXED_PACKAGE），另加 CML_PACKAGE、CML_ROOT、CML_APPROVAL。
- Approval：template 綁定新 root、單案、manifest SHA df3d448a…（= SHA256SUMS.txt）和 deck 7c11149e…，我只把 approved 改成 true。依據是使用者對 Codex 建議批次的常設授權，只記在本機 state。注意：如果 approval 多加任何欄位，stage 會拒絕。
- staged bench 對 760091 bench 的 diff 共 24 行，內容如下：新增 8 個元件（V_SENSE_DD 0.9 V、V_SENSE_B 0.5 V、RSENSE_P／N 500 Ω、MSENSE_P／N nmos_lvt 30n/2u、MTAIL_P／N nmos_lvt 60n/2u，四顆都是完整 CDF）；XCMP6..0 的輸入從 `mp mn` 改成 `sensep sensen`；save 加入 `sensep sensen V_SENSE_DD:p`。CDAC、參考電壓（未 trim，與 760132 相同）和時序都沒變。
- 只送一案。沒有重跑舊案，也沒有 sweep。新舊 raw 全部保留。

## Gate 數字（760091 直接負載 → 760132 理想隔離 → 760254 r5 CML）
- 錯碼：10/12 → 10/12 → **11/12**；未解析 bit：0 → 0 → **3**（b1 兩個，b0 一個；comparator null 是 #6、#8、#9，registered 12/12 可讀）。
- Σ|Δcode|：30 → 15 → **197**；max |Δ|：7 → 3 → **24**。
- 末端 CDAC 共模相對取樣：−112.5／−109.1 → −4.30／−4.26 → **−4.01／−3.90 mV**。共模下降已和理想隔離相同。
- 最大取樣誤差：1.373 → 1.687 → **1.655 LSB**。最大解析時間：54.3 → 46 → **60 ps**，已達 60 ps 視窗邊界。
- 實體感測（84 個 compare 點）：
  - 投影增益 **0.0335**；|held| > 3 mV 時，sense／held 的中位數 0.0345，最大 0.0468。
  - 符號一致 **80/84**。4 個不一致都是 b6（#0、#5、#6、#11），held 為 +1.9～+3.3 mV，sense 為 −0.07～−0.12 mV。這是門檻偏移造成的，不是極性錯誤。
  - 感測輸出共模 **0.8348～0.8350 V**（直接負載時比較器輸入約 0.76 V）。
  - 取樣點 V_SENSE_DD 供應電流平均 **260.7 µA**（兩腿合計，每腿約 130 µA，500 Ω 上壓降約 65 mV；summary 記為 −2.607e-4 A，是 vsource 的符號慣例）。

## 逐碼（期望 / comparator / registered / Δ / 末端殘差 LSB / 取樣誤差 LSB）
| # | exp | cmp | reg | Δ | 末端殘差 | 取樣誤差 |
|---|---|---|---|---|---|---|
| 0 | 64 | 85 | 85 | +21 | −18.47 | +0.01 |
| 1 | 0 | 13 | 13 | +13 | −17.67 | −1.26 |
| 2 | 127 | 127 | 127 | 0 | +6.36 | +0.99 |
| 3 | 31 | 48 | 48 | +17 | −18.57 | −0.33 |
| 4 | 96 | 120 | 120 | +24 | −19.32 | +0.42 |
| 5 | 63 | 84 | 84 | +21 | −19.06 | +0.24 |
| 6 | 65 | null | 87 | +22 | −19.01 | +0.17 |
| 7 | 85 | 109 | 109 | +24 | −18.74 | +0.62 |
| 8 | 42 | null | 61 | +19 | −18.57 | −0.25 |
| 9 | 1 | null | 14 | +13 | −19.22 | −1.66 |
| 10 | 126 | 127 | 127 | +1 | +5.35 | +0.96 |
| 11 | 64 | 86 | 86 | +22 | −19.64 | +0.39 |

## 判讀（唯讀，未改 Codex 程式）
1. **SAR 收斂到偏移的門檻**：除了正滿刻度的 #2 和 #10 之外，末端殘差全部集中在 −17.7～−19.6 LSB（約 −14.5 mV）。這表示 SAR 準確收斂到一個約 −14.5 mV 的輸入等效門檻，碼因此系統性偏高 +13～+24。在感測輸出端，這個門檻只相當於約 0.5 mV，也就是比較器 offset 加上感測臂失配的量級，被 1/0.034 ≈ 30 倍放大後才回推到 CDAC 端。#2 和 #10 碼正確，只是因為碼已經頂到 127。
2. **增益不足的原因**：本案每腿各用一顆 tail（MTAIL_P／N 的 source 節點 sem、sep 各自獨立），所以每腿都是被 tail ro 退化的共源級，差動增益約為 R／ro_tail，量到 0.034。我唯讀查了歷史 r5_original 的 quiet.scs，B0 除了 RB0_L、B0_F、B0_T 這 6 顆外，還有 **`B0_RDEG (B0_ep B0_em) resistor r=250`** 接在兩腿 source 之間，提供差動退化路徑。交接說的「八條支路」只包括 2 個 vsource、2 個 R、4 顆 MOS，沒有 RDEG。我推測這是增益從約 gm·500／(1+gm·125) 掉到 0.03 的主因，但沒有用模擬驗證。
3. **隔離效果本身成立**：CDAC 共模下降和理想 VCVS 相同（−4 mV 對 −4.3 mV），試碼期間殘差峰值擾動約 1.9 mV（760132 為 2.0 mV），取樣誤差也同級。所以 CDAC 負載問題已經被實體臂隔開，缺的是增益（和 offset 對增益的比例）。
4. 解析時間達到 60 ps 視窗邊界，3 個 bit 未解析，原因是感測後的差動訊號只剩 sub-mV。
5. 這只是單一慢速診斷，不主張 1.75 GS/s。下一步要不要補 RDEG、共用 tail 或調整偏壓，由 Codex 決定；我不會自行送案。

## 資源與 raw
1 CPU、6 GiB、Slurm 30 min；elapsed 3:40，MaxRSS 106.8 MB。raw 全部保留：760254 39M、760091 35M、760132 35M。
