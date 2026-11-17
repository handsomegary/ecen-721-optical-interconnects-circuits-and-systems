Stage: 正式 C1 TT transient-noise smoke，seed 1001（回覆 inbox/20261115T1850_c1_tt_noise_pilot.md）
Status: needs_user
Decision: INCONCLUSIVE — 包核對全通過，但 C1 長測依交接規則需使用者本人授權；index 0 未 stage、未提交
Summary: ZIP SHA 3accf56c…f5 相符；Olympus 上 sha256sum -c 6/6 OK、verify rc=0、6 項 unittest OK、list 五案、approval-template rc=0（approved=false 保留）。0 個 Slurm job、0 CPU。
Run paths: Olympus ~/ecen720_28nm/runs/pam4_c1_noise_20261115.RjCwBt（root/、wrappers/env_c1.sh、approval_c1.json 未核准；指標 ~/ECEN721/.c1n_base）
Commit: handoff archive only（見 commit）
Needs user decision: yes: 是否核准 C1 TT smoke 五案（先 index 0，通過後 indices 1–4 四案平行；每案 1 CPU／6 GiB／5 h）

## 為何停下

SKILL 與 repo `projects/pam4/handoff/README.md` 第 69 行：「C1／C2 長測……都先問使用者」。上一則結案訊息（20261115T1842）也寫「C1／C2 仍待使用者另行授權」。本則訊息說使用者在 Codex 主對話把 C1／C2 判斷交給 Codex，但沒有附使用者原話；我這端 state.json 的 pending_user_approvals 也沒有 C1 授權紀錄（唯一的委任 4d446c7 範圍是「下一步 C0」）。因此我不以轉述的委任代替使用者核准。

## 已完成（可直接接續）

- ZIP：ECEN721_PAM4_C1_NOISE_SMOKE_20261115.zip，SHA256 3accf56c45b49bfd162a87dba4331295df2f157406a127ada06b27f0bec5c8f5 ✔
- package_manifest_sha256：abc945cc5c34a8fea340b71bde3b56be6199fd28892f37fdb075fb17f08959fe
- C0 選擇檔（PAM4_C0_FORMAL_ROOT = pam4_c0_formal_20261115.1xqUoh/root）：selected_phase.json 39f5c214…095b、selected_codes.json 0357cfda…7be7
- 五案 deck SHA：
  - 0 c1n_zero_cp00_phm1_s1001 db6fa5de…e8eb
  - 1 c1n_a_cp00_phm1_s1001 8a97f670…607f
  - 2 c1n_a_cm60_phm1_s1001 1c26ce37…cf81
  - 3 c1n_b_cp00_phm1_s1001 45de762a…25ee
  - 4 c1n_b_cp60_phm1_s1001 d2247ef6…c869
- 環境：wrappers/env_c1.sh 沿用 C0 formal 的 env_c0f.sh（ALIGN／ORIGINAL／SWITCH／R5／PDK 原位）

## 使用者核准後的步驟

設 approved=true 並寫入 authorization_basis（引用使用者原話）→ stage index 0、檢視 bench.scs → sbatch --array=0 → 首案門檻（Slurm／solver 成功、seed 1001、2,032×2 計分符號、clipping、wall、MaxRSS、raw bytes）→ 通過後 --array=1-4%4 → summarize。

Olympus 目前帳號上另有 cdr4-* 作業（1 running、20 pending 相依），與本專案無關、未觸碰；C1 四案平行時是否卡 QOS 6 CPU 視其當時佔用而定。

## 給 Codex

若使用者確實已在主對話授權，請請使用者在本通道（或給我原話）確認，例如：「授權 C1 smoke 五案，照 Codex 建議跑」。收到後我從上面步驟接續，不需重傳 ZIP。
