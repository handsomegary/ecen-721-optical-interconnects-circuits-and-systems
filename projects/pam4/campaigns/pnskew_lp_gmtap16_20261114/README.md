# PN skew 補償 LP_GMTAP Fine16：coarse3 的 16 份尾電流解析度（2026-11-14）

第二十一版。延續 coarse3（tap 6／11／16）：每組 bank 保留 8 顆 RF 輸入 MOS，尾管從 8 顆 3 µm 改成 16 顆 1.5 µm（總寬度不變），每案開 16 份。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA e37eeac1…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_gm_tap16_ss_pilot.json` | SS 0–47 的 `gm_tap16_summary.py` 輸出。 |

## SS pilot（48 案，job 755564／755565）

- 8 份 legacy 逐值重現。
- 7–56 GHz 帶權延遲：

| 碼 | 延遲 |
| --- | ---: |
| 16:0 | 5.726 ps |
| 15:1 | 4.688 ps |
| 14:2 | 4.142 ps |
| 13:3 | 3.785 ps |

- 目標 4.464 ps 落在 15↔14 之間，這一步 0.545 ps，略超 0.50 ps。16:0 可以裁掉。
- 15:1／14:2 相對對照 −0.46／−0.45 dB，功耗 8.45–8.50／14 mW。
- 分流越多，總尾電流越大：比 legacy 8:0 多 4.3%（16:0）到 8.8%（13:3）。
- XT2 裕度 14:2 為 −0.06 mV、13:3 為 −1.1 mV（SS），需要先修。
- raw 469 MB，保留在 Olympus。
