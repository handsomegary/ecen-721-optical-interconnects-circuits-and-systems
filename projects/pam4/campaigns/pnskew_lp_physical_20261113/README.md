# PN skew 補償 LP_PHYSICAL：原生 Iref／OTA 實體偏壓（2026-11-13）

第十版。主線設定為 4.35 mA/腿（Iref 310.7 µA），把 LP_BIAS 的理想 Iref 與理想伺服換成原生元件：

- beta multiplier（1.8 kΩ），經 PMOS 1:1 鏡與 NMOS 1:10 鏡送到參考支路；
- 啟動支路；
- 兩級 OTA（Miller 3 kΩ／2 pF）。

所有偏壓電路都由 GFVDD 取電，功耗直接從各 rail 量，不再用 0.4 mW 預留。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼與設計說明（ZIP SHA 16a3beb3…）；生成的 deck、portable_review 與 netlist 未收錄，SHA 記在 `SHA256SUMS.txt`。 |
| `prompts/` | 結果回饋。 |
| `results/physical_first12.json` | 首批 12 案的 `physical_summary.py` 輸出。 |

## 首批（0–3、12–15、54–55、62–63）

- 使用者批准 12 案；job 753906 全部完成，參考案與 LP_BIAS 逐值一致。
- 整合版的工作點不成立：
  - 原生 Iref 在 SS 為 521.7 µA，在 FF 為 978.1 µA（目標 310.7 µA）。
  - 每腿電流在 SS 為 6.96 mA，在 FF 為 13.49 mA。
  - 增量在 SS 為 +12.2 mW，在 FF 為 +28.9 mW，都超出 +10 mW。
- 原因：beta multiplier 的核心電流偏高（1.35–1.57 倍）；L = 30 nm 的 PMOS 1:1 鏡因 VDS 不相等，在 FF 多出 88%；NMOS 1:10 鏡也有 7–10% 的誤差。replica 迴路本身正常，GMSR_D 與 GMSR_REF 相差 6–11 mV。
- 依停止條件，沒有擴跑；raw 保留在 Olympus。
