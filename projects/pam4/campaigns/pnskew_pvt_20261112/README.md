# PAM4 PN skew 影響掃描與 r3 AFE PVT corner（2026-11-12）

ECEN 721 Project #6 的「先量化影響」步驟。由 Codex 設計，Claude 在 Olympus（Spectre 23.1 classic，每 job 1 CPU）執行。本輪不做補償電路，也不宣稱任何規格通過。

## 內容

| 路徑 | 說明 |
| --- | --- |
| `package/` | Codex 交付包的原始碼、計畫與預先寫定的判讀規則：`skew/`、`pvt/`、`native/`、`run_case.py`、`stage_skew.py`、`summarize_pvt.py`、`verify_delivery.py`、`*.sbatch` 與離線測試。另含 `r5_original/` 產生器與 provenance。 |
| `package/DELIVERY_MANIFEST.json` | 全部 393 個檔案的 SHA-256，包含未放進 repo 的 deck。 |
| `olympus_wrappers/` | 實際提交用的 wrapper。原 `*.sbatch` 未改（`original_sbatch.sha256`）。wrapper 只負責 source IC231、把 spectre 與 python3.11 放上 PATH，以及設定 partition/qos/account。家目錄路徑以 `$HOME` 表示。 |
| `prompts/` | 給 Codex 的設計 prompt（含 r1 執行回饋）、Codex 給 Claude 的 r1 交接，以及 r1 的 Olympus 前置核對結果。 |

## 沒有放進 repo 的檔案（依「只放定版、生成物以產生器＋SHA 表示」）

- 106 個生成的 deck（`bench.scs`、`la5_foundry_corners.scs`、`delta.diff`），以及每案約 1–1.4 MB 的 PWL `stimulus_overlay.diff`，合計約 120 MB。這些都可由 `package/` 的產生器重建，SHA 記在 `DELIVERY_MANIFEST.json`。
- `r5_original/*.scs` 和名義 parent deck：定版 netlist 已在 [`../../netlists`](../../netlists)。
- PDK／模型檔：一律不進 Git。

## 版本

- r1（SHA 80b7fa1e…）：本次 campaign 實際執行的版本。
- r2（SHA 21856ffa…）：只修 `olympus_common.raw_in_use()`。共用節點上 `/proc/<pid>/fd` 不可讀時會丟 PermissionError，r2 改為略過，供之後的 run 使用。r1 中受影響的 5 個 PVT AC 案已有完整量測，只有 raw 未刪；之後由 Claude 用相同的量測核對條件手動刪除，並留下收據。r1 → r2 的差異看這個目錄的 commit 歷史。

結果：[results/RESULTS.md](results/RESULTS.md)（摘要 JSON 與 PVT 表在同一目錄）。
