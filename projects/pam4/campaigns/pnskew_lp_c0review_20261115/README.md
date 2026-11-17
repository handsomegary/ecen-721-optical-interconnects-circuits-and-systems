# PN skew 補償 C0 固定碼審查包（2026-11-15）

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 審查包（ZIP SHA b0a86d6e…）：c0_review.py、plan、replay 工具、說明。五份 deck（.scs）未收錄。 |
| `prompts/` | 審查回饋。 |

- 五份 TT deck 在 Olympus 上用原 COMP r5_original 加 SWITCH64 94aff417 包逐位元重現。
- 00→01／03 只差發送端 PWL 平移；01→02、03→04 只差致能電壓（碼 0→∓60）。
- 沒有送模擬：包內沒有 runner、sbatch 或 approval；實檔重播需要的 84／86 raw 已依規則退役，而且 collect-only 已經用同一份實檔驗證過。
