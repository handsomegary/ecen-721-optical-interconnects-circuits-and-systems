# PN skew 補償 LP_GLOBAL_MAP：全域碼表與原生 TG tap 選擇器（2026-11-14）

第十九版。設計：每腿一條 50 Ω 延遲線，偶數 tap 接 A bank、奇數 tap 接 B bank，兩個 bank 共用 8 個尾電流單元，由 10-bit 控制字選 tap 並分配電流。包內有：

- 81 個候選碼與 9 個接縫替代狀態；
- 控制 RTL；
- 原生 TG 網表。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA 6d55e3e2…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_global_ss_pilot.json` | SS pilot 30 案的 `global_summary.py` 輸出。 |

## SS pilot（30 案，job 755249）

- 原生 TG 的 56 GHz 損失（相對同狀態理想）：
  - G40：−9.7～−10.8 dB；
  - G00／G80：1× −13.5、2× −16.9、4× −37.5 dB。
  全部未達 2 dB，SS 沒有可用尺寸。
- 範圍 ±5.8～7.8 ps，功耗 8.24／10 mW，這兩項都通過。
- 依指引停在 pilot。raw 保留在 Olympus。
