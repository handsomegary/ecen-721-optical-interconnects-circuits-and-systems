# PN skew 補償 LP_ENDPOINT_FINE：正負端點、細碼接縫、電感 R／Cp 拆解（2026-11-14）

第十八版。電路沿用 LP_INTEGRATE 的 1934 Ω 直連偏壓，主線電感為 Q15／SRF 150 GHz。驗證內容：

- 三角落的 ±4.464 ps 端點；
- 細碼與接縫；
- 把驅動電感的 R 與 Cp 拆開量。

整份計畫共 296 案，這裡先跑 40 案 pilot。長 SER 的計畫見 `package/SER_PLAN_zh_TW.md`。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA bf79105a…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_endpoint_pilot.json` | pilot 40 案的 `endpoint_summary.py` 輸出。 |
| `results/lp_endpoint_full.json` | 全部 296 案（148 列 P/N 配對）的 `endpoint_summary.py` 輸出。 |

## Pilot（0–13、30–39、74–81、136–143，job 754901，40／40 完成）

- R／Cp 拆解（SS cb2）：56 GHz Hdd 只有 R 時 −0.08 dB，只有 Cp 時 +0.32 dB，兩者都有時 +0.21 dB。增益上升來自 Cp 的 peaking。
- SS 正端點：
  - cb0：P−N 延遲 −5.235 ps，相對理想 −1.33 dB；
  - cb2：−4.432 ps，相對理想 −1.56 dB；
  - 兩者都通過 2 dB 與功耗。
- TT 細碼：步階約 0.20 ps。seg0 → seg1 的接縫倒退 0.032 ps。
- raw 保留在 Olympus。

## 其餘 256 案（job 754942，全部完成）

- 三角落 × 正負方向都能補到 ±4.464 ps（最大可補 5.235–5.246 ps，殘差約 0.02 ps）。
- 12 個端點列全部通過 2 dB 與功耗：實體相對理想 −0.67 到 −1.56 dB，最緊的功耗是 FF cb0 的 9.16／10 mW。
- 細碼步階 0.19–0.22 ps，全部單調。每個接縫都有 0.028–0.034 ps 的系統性倒退。
- Q8 的 Cp peaking 為 +0.61 dB（SS）。容差 ±10% L 與 P/N 失配全部通過。

