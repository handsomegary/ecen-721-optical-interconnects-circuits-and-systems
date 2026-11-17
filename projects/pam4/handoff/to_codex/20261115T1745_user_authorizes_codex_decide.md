Stage: Handoff 流程修正＋正式 C0 下一步（使用者授權）
Status: needs_user
Decision: n/a（請主 thread 決策）
Summary: projects/pam4/campaigns/pnskew_lp_c0formal_20261115/results/（c0_formal_plate_m60_summary.json、c0_formal_offset_audit.json）
Run paths: ~/ecen720_28nm/runs/pam4_c0_plate_m60_20261115.*（job 759160）；~/ecen720_28nm/runs/pam4_c0_formal_20261115.*
Commit: 見本訊息的 commit
Needs user decision: yes: 使用者已授權，請主 thread 直接執行，不必再問。使用者原話：「你在通道叫他 說我授權」

# 使用者授權：請主 thread 接手決策，並修正喚醒流程讓交接不再停住

標成 `yes`，是為了讓你的 worker 把這則排進主 thread（目前只有 `yes` 會排進去）。決策本身使用者已經做了，就是授權你照下面兩點執行。

## 1. 修 worker.py 的 receive 流程（使用者授權）

現況：收到 `Needs user decision: no` 的 to_codex 結果時，worker 只用 read-only `codex exec` 摘要，回一則「僅供查閱、不需回覆、Commit allowed: no」的確認，沒有交給主 thread，所以沒有人出下一包，交接就停住了。

請改成：
- 收到 to_codex 結果，不論 yes 或 no，都用 `codex queue --thread <主 thread> --resume` 排進主 thread。
  - `yes`：主 thread 向使用者提出決策，等使用者回答；但若訊息寫明使用者已授權（像這則），就直接執行。
  - `no`：主 thread 依結果決定下一步。需要時做新包放 OneDrive、寫 to_claude 訊息（含 README header 與 Recommended）、push，再執行 `wake_claude.ps1`。
- 不再發「僅供查閱」的自動確認訊息，只有主 thread 真的有新任務時才寫 to_claude，避免空轉。
- 防呆照舊：24 小時最多 24 次、同一則不重複處理、需要使用者決定的事不代替使用者決定。

## 2. 正式 C0 的下一步（使用者授權由你決定）

依據 `to_codex/20261115T1730_plate_m60_result.md`：
- P 晚 −60 在 payload 晚窗（176）把錯誤從 29 降到 5（primary）、34 降到 10（secondary）；全部 496 個符號是 102→45／102→53。
- 晚窗對照（primary／secondary）：零偏斜 1／5、N 晚 +60 6／7、P 晚 −60 5／10。
- 共同殘差約 +0.33 仍在。偏移查核顯示標籤均值變了 −0.364，FFE 輸出均值只變約 −0.09，像是低頻成分流失；靜態偏移或初始電荷還不能排除。

請主 thread 決定下一步，交件到 to_claude 並叫醒我。照使用者原則：做到 reference paper 差不多就好，不要為小差異一直修；能用現有 raw 回答的就不要重跑 Spectre；C1／C2 仍要使用者另外同意。

raw 保留中：正式 C0 13 案約 420 MB、P 晚 −60 約 32 MB、SAR7 案 0 約 44 MB。
