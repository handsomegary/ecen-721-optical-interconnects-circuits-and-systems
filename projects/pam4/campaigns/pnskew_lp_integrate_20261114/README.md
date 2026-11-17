# PN skew 補償 LP_INTEGRATE：原生直連偏壓整合（2026-11-14）

第十四版。把前幾版驗證過的部分組在一起：

- shared14lo120z50 驅動；
- 核心電阻 1934 Ω，L120 直連 Iref；
- 啟動支路；
- L120 鏡負載 OTA。

主線標稱 4.35 mA/腿。功耗直接加總所有電源。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA 8dc842ec…）；生成的 deck、portable_review／diagnostics 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_integrate_summary.json` | `integration_summary.py` 輸出（0–33，17 列）。 |

## 結果（job 754057、754059，34／34 完成）

| corner | cb | 相對理想 | 增量／預算 | 每腿電流 | 伺服誤差 |
| --- | ---: | ---: | --- | ---: | ---: |
| SS | 0／2 | −1.42／−1.43 dB | 8.30／10、8.46／14 mW | 4.729 mA（+8.7%） | −0.16% |
| TT | 0／2 | −1.08／−1.05 dB | 8.87／10、9.04／14 mW | 4.547 mA（+4.5%） | 0.00% |
| FF | 0／2 | −0.82／−0.74 dB | 9.24／10、9.44／14 mW | 4.306 mA（−1.0%） | +0.16% |

- 六個條件全部同時通過 2 dB 與 +10／+14 mW。
- 最小餘裕：增益是 SS 的 0.57 dB，功耗是 FF cb0 的 0.76 mW。
- SS cb2 的 XT2 只有 2.3 mV。
- startup 與 STB 還沒驗證。raw 保留在 Olympus。
