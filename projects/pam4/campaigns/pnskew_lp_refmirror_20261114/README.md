# PN skew 補償 LP_REFMIRROR：1934 Ω 核心、PMOS pass 與 L120 鏡負載 OTA（2026-11-14）

第十三版。主線仍是 4.35 mA/腿。這版驗證三件事：

- 同一個 1934 Ω 核心電阻在 SS／TT／FF 的直連參考；
- 用 PMOS 串聯調節 NMOS 鏡的輸出（理想控制器，限幅 50 mV～VDD−50 mV）；
- 回到 PMOS 鏡負載的 OTA，元件全部改用 L120，並重配第二級的電流比例。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA 1ac9d7d0…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_refmirror_summary.json` | `ref_summary.py --plan mirror_plan.json` 輸出（0–9）。 |

## 結果（0–9，job 754039、754040）

- OTA（理想 Iref）完全通過：
  - SS：每腿 4.343 mA，追蹤誤差 0.16%，相對理想 −1.67 dB，增量 +7.57 mW。
  - FF：每腿 4.357 mA，追蹤誤差 0.15%，相對理想 −0.79 dB，增量 +9.29 mW。
  - replica 壓差 ±0.22 mV。
- PMOS pass 在 SS 0.81 V 下可以運作：閘極 0.15–0.34 V，NMOS 鏡比 0.9999。
- Iref 剩下的問題是核心電流隨角落變動：SS +7.2%、TT −1.4%、FF −11.4%。
  - 直連版 Iref：+8.9%／+4.5%／−1.2%。
  - PMOS pass 版 Iref：+3.5%／−2.7%／−10.2%。
- raw 保留在 Olympus。
