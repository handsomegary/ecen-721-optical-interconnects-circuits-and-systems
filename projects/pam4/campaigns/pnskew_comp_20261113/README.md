# PN skew 補償 r0：第一版 LC trim cell（2026-11-13）

架構 A：在 r5 CHB2 之後、r3 第一級 X_ip/X_im 之前，每腿插入一個 4 節 LC ladder 加 6-bit 開關電容 bank（P=k、N=63−k）。由 Codex 設計，Claude 在 Olympus 執行。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex r0 交付的原始碼、設計說明（`DESIGN_zh_TW.txt`）、Claude 執行指引、核准模板與離線測試。未收錄生成的 deck 與 1 MB 以上的檔案；其中 `comp_plan.json` 可由 `comp_plan.py` 重建。SHA 記在 `SHA256SUMS.txt`。 |
| `prompts/` | 給 Codex 的設計 prompt，以及 AC 60 案的結果回饋。 |
| `results/ac60_summary.json` | 使用者批准的 60 個稀疏 AC 案（TT 36 案，加上 SS/85/0.81 與 FF/−40/0.99 各 12 案）的 `comp_summary.py` 輸出。 |

## 結果（稀疏 AC，60/60 完成）

56 GHz 下兩端碼的差動延遲只有 ±0.78 ps（SS）到 ±1.47 ps（FF），需求是 ±4.464 ps。

碼表不單調：k=16、32、48 都約為 −1 ps。同一個碼的 P−N phase delay 在 7–56 GHz 內變動 5–8 ps。結果也高度依賴源端阻抗：0 Ω、25 Ω、50 Ω 時，56 GHz Hdd 分別為 +7.35、+0.59、−2.65 dB。

依設計中預先寫定的停止條件，沒有展開完整碼表，也沒有進入 pilot 或整合；已回報 Codex，等待下一版設計。

raw 分析後已退休（440 MB），每案留有收據。compact 結果保留在本機。
