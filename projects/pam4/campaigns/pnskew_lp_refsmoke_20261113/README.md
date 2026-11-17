# PN skew 補償 LP_REFSMOKE：Iref 與 OTA 分開驗證（2026-11-13）

第十一版。LP_PHYSICAL 首批的原生 Iref 偏離目標太多，所以把它拆成兩部分分別驗證：

- **Iref only**（TT）：鏡改成 L = 120 nm，核心電阻 1.6 kΩ；比較直連與理想等 VDS 兩種接法。
- **OTA only**（SS／FF）：原生 OTA 配理想 310.714 µA 參考電流。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA dc67425b…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_refsmoke_summary.json` | `ref_summary.py` 輸出（0–5）。 |

## 結果（0–5，job 753918、753919）

- Iref（TT）：
  - 直連 402.4 µA（+29.5%），理想等 VDS 397.2 µA（+27.8%）。
  - L120 鏡的誤差已降到 ≤6%；剩下的主要是核心電流偏高 25–28%，需要重選 R。
  - PMOS 側沒有空間做串接式的等 VDS。
- OTA（理想 Iref）：
  - SS：每腿 4.087 mA（−6.1%），相對理想 −1.85 dB，增量 +7.16 mW。
  - FF：每腿 4.523 mA（+4.0%），相對理想 −0.69 dB，增量 +9.66 mW。
  - 兩者都通過，但增益與功耗餘裕都很小；追蹤誤差超過 2%。
- raw 保留在 Olympus。
