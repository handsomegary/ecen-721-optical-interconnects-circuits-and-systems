# PN skew 補償 LP_GMTAP MIDBIAS：中段碼、PVT 端點與實體 Vb1（2026-11-14）

第二十三版。延續 Trim32，以 Vb1 = 570 mV 為基準：
- 量 SS 全碼表（中段碼）；
- 量 TT／FF 的端點；
- 試 1 kΩ／57 kΩ 加 2 pF 的分壓器作為實體 Vb1，另有 250 Ω／14.25 kΩ 的低阻對照。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA 402cf4a8…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_gm_tapmid_ss_0_295.json` | 0–295 的 `gm_tapmid_summary.py` 輸出（SS 只有偶數碼）。 |
| `results/lp_gm_tapmid_ss_0_295_odd13.json` | 同上，加 SS 奇數碼 ±1、±3（344–359）。 |

## 0–295 加 344–359（312 案，job 755817／755831／756122）

- 端點（±28、±29、±30）：SS、TT、FF 三個角落，理想 Vb1 與分壓器都通過：
  - 兩向都涵蓋 4.464 ps，步階 ≤0.362 ps；
  - 16 顆 XT2 都是 region 2；
  - 相對對照 −0.29～−0.47 dB；
  - 增量 8.2–9.3 mW。
- SS 全碼表：0→30 單調，但有兩個 blocker：
  - 中心 0→±1 的步階 0.606 ps，沒有更細的碼；
  - 中段 ±8～±24 的總尾電流比 legacy 中心高 3.4–4.8%，XT2 掉到 native region 1（裕度 +2.4～+3.6 mV），靜態篩選不通過。
- 分壓器的受載 Vb1：SS 567.35、TT 569.02、FF 569.75 mV。SS 的偏差來自約 2.7 µA 的閘極漏電；Hdd、噪聲與功耗的差異都可以忽略。
- raw 3.4 GB，保留在 Olympus。
