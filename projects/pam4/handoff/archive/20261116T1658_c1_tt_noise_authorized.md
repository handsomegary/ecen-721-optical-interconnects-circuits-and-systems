Stage: Project #6 PAM4 deskew C1 TT，seed 1001
ZIP: ECEN721_PAM4_C1_NOISE_SMOKE_20261115.zip（OneDrive ECEN 720/outputs）
SHA256: 3accf56c45b49bfd162a87dba4331295df2f157406a127ada06b27f0bec5c8f5
Guide: OneDrive ECEN 720/outputs/PAM4_C1_NOISE_SMOKE_20261115/HANDOFF_zh_TW.md
Recommended: 先送 index 0。在零偏斜長窗的完整性門檻通過後才送 1–4；五案結果回到本機 outbox 判斷 C2
Resources: Classic +mt=1，每案 1 CPU／6 GiB、Slurm 5 小時、solver 4.5 小時；歷史 71–94 分鐘／約 133 MiB 每案；配對階段最多 4 並行，遵守共用 6 CPU 上限
Commit allowed: handoff + results
Needs user decision: no

使用者在 Codex 主對話直接指示：「那你跟 Claude 繼續把 Project #6 做完，先驗證 SAR7 能不能到 1.75 GS/s，再往完整 112 GS/s ADC 整合。PAM4 deskew 先跑 C1，通過再跑 C2。性能跟 IEEE reference paper 差不多就好。」本信是 C1 的執行交接，適用既有五案。沿用已核對的 Olympus `~/ecen720_28nm/runs/pam4_c1_noise_20261115.RjCwBt` 和現有 approval-template、manifest `abc945cc5c34a8fea340b71bde3b56be6199fd28892f37fdb075fb17f08959fe`。先查既有提交和檔案，若已送過就追該案，勿重送。按 Claude 本端的正常核准流程執行；如本端要求本人再確認，回報實際提示與未送狀態。

先確認 index 0 solver／時鐘／長窗與 C0 凍結設定完整，seed 1001，每個讀出有 2,032 個計分符號、有效量測和 clipping 計數。首案有效才跑 1–4。收集失敗時先按 Guide 用已完成 raw 做 collect-only。提交後請回覆 job ID，再於整批完成回傳五案分子／分母、clipping、RMSE、配對差值、solver wall time、RSS、raw 大小、摘要 SHA。保留 raw 和原結果供查核；敏感輸入留原位。

C1 用作 C2 前的工程篩選：兩個方向的 primary 均需改善，secondary 不可變差；證據須完整，且無 clipping 或影響計分的異常。P 晚 −60 仍是固定碼診斷，和原 C0 選碼分開報。結果若不清楚，用現有資料定位原因。先回報再凍結 C2 的多 seed 範圍，別提前排 C2。
