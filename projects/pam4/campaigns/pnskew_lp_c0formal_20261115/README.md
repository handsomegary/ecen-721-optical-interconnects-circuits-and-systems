# PN skew 補償正式 C0：共同相位、端點選碼、獨立 payload（2026-11-15）

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 正式 C0 包（ZIP SHA db4f9209…）。 |
| `results/` | c0_formal_summary.json、selected_phase.json、selected_codes.json。 |
| `prompts/` | 回饋（同 handoff/to_codex/20261115T1640_c0_formal_payload.md）。 |

- 相位選 −1/8 UI；選碼 P 晚＝0、N 晚＝+60；補錯方向一律 74–82 個錯誤。
- payload（496 個符號）：零偏斜 24／28 個錯誤、P 晚碼 0 102／102、N 晚碼 0 41／69 → +60 43／48。
- 零偏斜基準就退步，錯誤全是單向偏高一階，推測 payload 窗含啟動暫態（從 1.37 ns 開始；training 從 4.2 ns 才計分）。等 Codex 驗證並調整計分窗，raw 保留。

## P 晚 −60 單案與共同偏移查核（job 759160）

- `package/p_late_m60/`：Codex 單案包（ZIP SHA 851f26df…，不含 deck）。
- `results/c0_formal_plate_m60_summary.json`：P 晚 −60 與碼 0 同 payload 配對。full 496 錯誤 102→45（primary）／102→53（secondary）；晚窗 176 錯誤 29→5／34→10。
- `results/c0_formal_offset_audit.json`：零偏斜 training 對 payload 的唯讀查核。payload 標籤均值 −0.364，但 FFE 輸出均值幾乎不動，因此出現 +0.365 殘差。
- 回饋：`prompts/20261115T1730_plate_m60_result.md`。
