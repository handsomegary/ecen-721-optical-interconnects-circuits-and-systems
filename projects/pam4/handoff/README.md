# PAM4 handoff：Codex ↔ Claude（本機 CLI 通道；repo 只放 Claude 的存檔）

使用者決定（2026-11-15）：Codex 和 Claude 的溝通全部在本機進行，用檔案加 CLI 喚醒。GitHub 只用來 commit／push，而且只由 Claude 執行。這個 repo 是 `<owner>/ecen-721-optical-interconnects-circuits-and-systems`（私人，branch `main`）。

## 通道（本機，不經過 GitHub）

任務資料夾：`C:\Users\User\.claude\scheduled-tasks\ecen721-pam4-handoff-check\`

| 資料夾 | 誰寫 | 內容 |
| --- | --- | --- |
| `inbox\` | Codex | 交件與決策訊息 |
| `outbox\` | Claude | 執行結果與回饋 |
| `inbox\done\`、`outbox\done\` | 處理完的一方 | 已處理的訊息（只搬移，不刪） |

- 檔名 `YYYYMMDDTHHMM_<topic>.md`（本機時間），一則訊息一個檔，不修改舊檔；更正另發新檔並寫明取代哪一則。
- 進度：Claude 的 `state.json`（同資料夾，不進 repo）。

### 喚醒

- **Codex → Claude：** Codex 把訊息寫進 `inbox\` 後執行：

  ```
  powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\User\.claude\scheduled-tasks\ecen721-pam4-handoff-check\wake_claude.ps1" -Reason "<inbox 檔名>"
  ```

  - 腳本立刻返回，在背景啟動一輪無人值守的 Claude（`claude -p`），讀 `inbox\<檔名>`。檔案不在 `inbox\` 就不啟動。
  - 若 Claude 已在執行（`run.lock` 未滿 45 分鐘）就跳過；那一輪結束前會再看一次 `inbox\`。
- **Claude → Codex：** Claude 把結果寫進 `outbox\` 後執行同資料夾的 `wake_codex.ps1 -Msg "<檔名>"`。這個腳本會執行 Codex 寫在 `codex_wake_cmd.txt` 的那一行指令，`{MSG}` 會換成檔名；檔案空的就什麼都不執行。
- **防呆：** 每個方向 24 小時最多 24 次；Claude 一次只跑一輪；`Needs user decision: yes` 時雙方都要等使用者回答。
- **保底：** Claude 的本機排程 `ecen721-pam4-handoff-check` 每 30 分鐘檢查本機 `inbox\`，不做 git pull。

## 訊息 header

Codex（`inbox\`）：

```
Stage: <批次與階段>
ZIP: <OneDrive `ECEN 720/outputs/` 檔名，或 "this message">
SHA256: <64 字元或 n/a>
Guide: <交接指引路徑>
Recommended: <建議執行的 stage／index，以及 smoke>
Resources: <最大並行數、每案 CPU／記憶體／walltime、solver 與 raw 估計>
Commit allowed: <no | handoff only | handoff + results>
Needs user decision: <no | yes: 什麼>
```

Claude（`outbox\`）：

```
Stage: <批次與階段>
Status: <done | running | needs_user | blocked>
Decision: <PROCEED | STOP | INCONCLUSIVE + 一行理由>
Summary: <Olympus summary JSON 與 repo campaigns/<name>/results 路徑>
Run paths: <Olympus run root 與 job ID>
Commit: <SHA 或 "not committed">
Needs user decision: <no | yes: 什麼>
```

## repo 裡有什麼（只有 Claude commit／push）

- `archive/`：Claude 依 `Commit allowed` 存檔的本機訊息副本（與 `inbox\`／`outbox\` 同名）。這是單向紀錄，不是通道；雙方都不從這裡讀任務。
- `../campaigns/<name>/`：結果摘要 JSON（家目錄遮成 `~`）、campaign README、不含 deck 的原始碼、回饋副本。
- `to_claude/`、`to_codex/`：2026-11-15 之前 GitHub 通道時期的歷史紀錄，已凍結。
- **不進 repo：** PDK、模型、deck／網表（`*.scs`）、批次 ZIP、Spectre raw、金鑰、私人路徑、使用者的 email。ZIP 與 deck 放 OneDrive `ECEN 720/outputs/` 或 Olympus。

## 權限（不變）

- Codex 決定設計方向；Claude 執行並回報。Codex 不 pull、commit 或 push 這個 repo。
- Claude 在 `Recommended` 範圍內自行核准；超出範圍、C1／C2 長測、刪除未分析資料、`Needs user decision: yes`、SHA／verify／測試失敗時，都先問使用者。
- Olympus：Slurm QOS 上限 6 CPU（帳號共用）；不碰其他專案或其他對話的 job。
