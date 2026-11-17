# PN skew 補償 LP_GMTAP COMMON64：三角落共同碼表（2026-11-14）

第二十五版。以 Split64、Vb1 565 mV 為基準：
- 補齊 SS 的過渡段與端點；
- 準備 TT／FF 與 375 Ω／14.125 kΩ、2 pF 分壓器的共同碼表。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA 979ddb50…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_gmtap_common64_ss_ideal.json` | SS 0–159 的 `gm_gmtap_common_summary.py` 輸出。 |
| `results/lp_gmtap_common64_rep_0_507.json` | 0–507 的輸出（加上 TT／FF 理想與三角落分壓器代表碼）。 |
| `results/lp_gmtap_common64_div_0_963.json` | 0–963 的輸出：三角落共同碼表與 ordered_control_words。 |

## SS 0–159（160 案，job 756361／756369）

- SS 理想 565 mV 通過：
  - 0→60/64 單調；中心 0.367 ps，過渡段 ±3～±11 每步 ≤0.235 ps，端點段 ≤0.364 ps；
  - ±58／±59 為 4.402／4.538 ps，兩向都涵蓋 4.464 ps；
  - 16 顆 XT2 全部是 region 2，最小 +5.27 mV；
  - 相對對照 −0.43～−0.46 dB，增量 8.1–8.3 mW。
- raw 1.6 GB；summary commit 後已退役，measurements 保留。

## 160–507（348 案，job 756536／756544）

- TT／FF 理想 565 mV 與三角落 375 Ω／14.125 kΩ、2 pF 分壓器的代表碼全部通過：
  - XT2 全部 region 2；
  - 相對對照 −0.23～−0.47 dB；增量 8.1–9.2 mW。
- 受載 Vb1：SS 563.96、TT 564.62、FF 564.90 mV。
- 共同端點用 ±60（FF ±59 = 4.392 ps，不足）；FF 中心 0→±1 為 0.495 ps，最緊。
- raw 3.1 GB；summary commit 後已退役。

## 508–963（456 案，job 756927）

- 三角落共同靜態碼表通過（common_static_map.status＝verified_static_screen）：
  - 55 個碼在 SS／TT／FF 分壓器下都單調、每步 ≤0.50 ps、兩向涵蓋 4.464 ps；
  - XT2 全部 region 2（最小 SS 5.86 mV）；
  - 相對對照 −0.23～−0.47 dB；增量 8.1–9.2 mW。
- 最緊一步：FF 0→±1 = 0.4948 ps（餘量 5.2 fs），待密頻 AC 與失配複核。
- raw 4.1 GB；summary commit 後已退役。
