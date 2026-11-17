# PN skew 補償 LP_GMTAP CENTER64：Vb1 565 mV 與 1/64 中心單元（2026-11-14）

第二十四版。修正 MIDBIAS 的兩個 blocker：
- Split32 把 Vb1 從 570 降到 565 mV，修正中段 XT2；
- Split64 把每組 bank 的一支 0.75 µm 尾管拆成兩支 375 nm，修正中心碼距。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA b660a6c5…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_gm_center64_ss_primary.json` | SS 0–123 的 `gm_center64_summary.py` 輸出。 |

## SS 0–123（124 案，job 756209／756221）

- 兩個修正都通過（both_local_repairs_pass）：
  - 565 mV：中段 ±12～±52/64 的 16 顆 XT2 全部是 region 2，最差 +5.27 mV（16:16）；中段步階 0.161～0.271 ps；
  - Split64：中心 0→±1/64→±2/64 為 0.367／0.229 ps。
- 相對對照 −0.43～−0.44 dB，增量 8.1–8.3 mW。
- 尚未驗證：565 mV 下的 ±3～±11/64 與端點、分壓器、PVT。
- raw 1.1 GB；summary commit 後已退役，measurements 保留。
