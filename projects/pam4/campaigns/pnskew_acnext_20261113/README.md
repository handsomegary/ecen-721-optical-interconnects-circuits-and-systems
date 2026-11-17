# PN skew 補償 ACNEXT：固定長短路徑加 TG 選擇器（2026-11-13）

AC60 之後的第二版。改用 6/16 節等阻抗固定長短路徑（名義範圍 ±5.20 ps），由 Codex 設計，Claude 在 Olympus 執行。使用者批准了 94 個稀疏 AC 案，依 Codex 建議的順序先跑 TT 0–13。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼、設計說明、AC60 診斷與解析參考。生成的 deck 與 portable_review 未收錄，SHA 記在 `SHA256SUMS.txt`。 |
| `prompts/` | TT 0–13 的結果回饋。 |
| `results/acnext_tt0_13_summary.json` | `summarize_acnext.py` 的輸出。 |

## 結果（TT 0–13，14/14 完成）

- 理想選路（ttd_selected）：±5.245 ps，7–56 GHz 加權 phase RMS 0.012 ps，等長時損失 −0.33 dB。固定路徑本身成立。
- 原生 TG 選擇器（ttd_switch）：等長 06/06 在 56 GHz 就有 −30 dB 損失；06/16 只剩 ±3.36 ps，RMS 1.53 ps，最差 7.7 ps。

依使用者事先約定，在這裡停下並回報 Codex；其餘 80 案未送出。raw 74 MB 已退休，每案留有收據。
