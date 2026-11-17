# PN skew 補償 C0 固定碼診斷（2026-11-15）

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 可執行包（ZIP SHA 05ec8f03…），含 RESEARCH_DECISIONS；deck（.scs）未收錄。 |
| `results/c0_00_measurements.json` | 第 0 案（TT 零偏斜、碼 0）的 runner 量測。 |
| `results/lag_scan.py`、`lag_scan_c0_00.txt` | 唯讀診斷：held sample 與符號在各 lag 的相關係數。 |
| `prompts/` | 回饋。 |

- 第 0 案（job 757899）：Spectre 39.5 分鐘、283 MB、69 MB raw；時鐘、取樣數、clipping 都正常。
- primary SER 0.721、secondary 0.729（亂猜約 0.75）。
- 原因：凍結的 lag 不適用於插入 gm-tap 之後的路徑。primary 在 lag 1 的相關是 0.005、lag 3 是 0.753；secondary 在 lag 3 的相關是 −0.735。
- 1–4 未送，等 Codex 修對齊與極性，並提供 rescore 模式。第 0 案 raw 保留。

## 對齊修正 3b60a876 與五案結果

- `package_align/`：修正包；`results/c0_aligned_summary.json`（五案）、`results/c0_00_aligned_measurements.json`（第 0 案重算）。
- 校準只用第 0 案 payload 前的資料：primary lag 3（+0.749）、secondary lag 3（−0.730，極性與電路一致）。

| 案 | 偏斜 | 碼 | primary 錯誤／240 | secondary 錯誤／240 |
| --- | ---: | ---: | ---: | ---: |
| 00 | 0 | 0 | 0 | 0 |
| 01 | P 晚 | 0 | 11 | 9 |
| 02 | P 晚 | −60 | 1 | 4 |
| 03 | N 晚 | 0 | 11 | 25 |
| 04 | N 晚 | +60 | 2 | 5 |

- 固定端點碼補償在兩個方向都降低錯誤。這是診斷結果，不推論 BER。
- solver 每案 40–54 分鐘，最慢的一案只比 3300 s timeout 少 79 s。
