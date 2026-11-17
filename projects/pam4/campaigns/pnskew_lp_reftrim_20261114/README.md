# PN skew 補償 LP_REFTRIM：核心電阻、N 側疊接與對稱 OTA（2026-11-14）

第十二版。主線仍是 4.35 mA/腿。這版處理 REFSMOKE 找到的三個問題：

- 用 TT 等 VDS 下的 1.80 與 2.05 kΩ，內插出核心電流 31.07 µA 所需的電阻；
- 在 N 側加疊接，用理想控制迴路量出所需的閘壓與裕度；
- OTA 第一級改成對稱 39 kΩ 負載，輸入對與第二級改用 L120。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA bfbf6a61…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_reftrim_summary.json` | `ref_summary.py --plan trim_plan.json` 輸出（0–6）。 |

## 結果（0–6，job 754007、754009）

- 核心電阻：I ∝ R^−1.28，內插得 R ≈ 1934 Ω。
- N 側疊接：NMOS 鏡比為 0.9997。但疊接閘極要 0.880 V，TT 的 VDD 只有 0.9 V，SS（0.81 V）應該放不進去。
- 對稱 39 kΩ OTA 比 REFSMOKE 的鏡負載版差：
  - SS：每腿 3.05 mA（−30%），相對理想 −2.83 dB，超出 2 dB 判準。
  - FF：每腿 4.00 mA（−8%）。
  - 原因是兩端汲極電壓不平衡（相差 88–209 mV），加上增益不足。
- raw 保留在 Olympus。
