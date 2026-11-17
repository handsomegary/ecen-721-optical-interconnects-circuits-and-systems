# PN skew 補償 LP_GMTAP Trim32：半單元微調與獨立 Vb1（2026-11-14）

第二十二版。延續 coarse3：
- 每組 bank 的尾管改成 15 顆 1.5 µm 加 2 顆 0.75 µm（32 份）；
- 第一級尾管改用獨立 Vb1（GMSKVBIAS），XT2 仍用 Vb2 = 0.580 V。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA c53ec738…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_gm_taptrim_ss_0_81.json` | SS 0–81 的 `gm_taptrim_summary.py` 輸出。 |

## SS 0–81（82 案，job 755625／755629）

- Vb1 = 570 mV 通過局部端點驗證（local_trim_pass）：
  - 帶權延遲：28:4 4.169、29:3 4.389、30:2 4.714 ps；
  - 往外步階 0.220／0.325 ps，兩方向都涵蓋 4.464 ps；
  - 16 顆 XT2 全部原生 region 2，最小裕度 5.25 mV；
  - 尾電流碼間峰對峰 2.4%；
  - 相對對照 −0.45 dB，增量 8.2–8.3 mW。
- Vb1 = 580 mV：XT2 在 28:4 為 −0.06 mV，不通過。
- raw 890 MB，保留在 Olympus。
