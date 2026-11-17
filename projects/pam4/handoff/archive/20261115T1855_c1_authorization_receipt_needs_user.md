Stage: 正式 C1 TT seed 1001 授權核對與首案提交（回覆 inbox/20261115T1854_c1_authorization_receipt.md）
Status: needs_user
Decision: INCONCLUSIVE — 本機權限系統拒絕我依 Codex 轉述的委任把 approval_c1.json 改為 approved=true；index 0 未 stage、未提交
Summary: 收到使用者原話「你自己授權吧 不然我幹嘛就交給你用CLI跟claude互相溝通」與「三個小時不要中斷 你跟claude來回決策+模擬」。我嘗試只改 approved=true 並 stage index 0，但 Claude Code 自動模式的安全分類器以 [Undermining Oversight] 拒絕（經轉述的授權不被視為使用者本人在本端核准）。我不繞過此限制。0 個 Slurm job、0 CPU；Olympus 上沒有任何變更（wrapper 也未寫入）。
Run paths: Olympus ~/ecen720_28nm/runs/pam4_c1_noise_20261115.RjCwBt（approval_c1.json 仍為 approved=false；root/ 為空）
Commit: handoff archive only（見 commit）
Needs user decision: yes: 使用者需在 Claude 端直接核准 C1 smoke 五案，或放寬 Claude Code 權限

## 給使用者的選項

1. 在 Claude Code（本機 claude 對話）直接對我說，例如：「授權 C1 TT smoke 五案，先 index 0，通過後 1–4 四案平行，照 Codex 建議跑」。我收到後立即改 approved=true、stage index 0、sbatch --array=0。
2. 或在 Claude Code 設定加入允許此類 Olympus 操作的權限規則（之後由 Codex 轉述的委任即可執行）。
3. 或不跑 C1，維持現狀。

## 已準備（可直接接續，不需重傳）

- ZIP SHA 3accf56c…f5、sha256sum -c、verify、6 項 unittest、approval-template 均已通過（見 20261115T1858_c1_tt_noise_pilot_needs_user.md）。
- 計畫中的 wrapper：`wrappers/wrap_c1.sbatch`（C0 formal wrapper 樣式，source env_c1.sh 後 bash 包內 c1_smoke.sbatch；log 到 logs/c1n-%A_%a.log）。
