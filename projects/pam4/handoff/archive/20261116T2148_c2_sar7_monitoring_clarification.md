Stage: 2144 交接的長短批次監看補充（沒有新增模擬）
ZIP: this message
SHA256: n/a
Guide: 本文；接續20261116T2144_c1_pass_c2_sar7_resume.md，原包與SHA不變
Recommended: 短SAR7先回報；C2保留waiting_runs及可被既有poll辨識的array parent ID，讓目前headless輪次結束後仍能自動收尾
Resources: 不增加solver／CPU／raw；沿用既有poll每5分鐘最多一次唯讀squeue；headless不等待53小時
Commit allowed: handoff only
Needs user decision: no

這是2144原交接的執行補充，不改原ZIP、電路、gate、seed、資源、授權或截止。剛核對既有 `poll_inbox.ps1`，它只掃 top-level inbox，且 `waiting_runs` 的 `jobs` 只接受純十進位 parent job ID。原碼保持唯讀，不修改監看或 steering 設定。

請先完成並回報已提交的短SAR7，然後讓C2長批次留給既有排程續看。C2 submit 本身是非阻塞的 sbatch（沒有--wait），接受後立即存 `c2_submission.json`，不需要為等95案而持住本輪。

1. 在本機 task `state.json.tasks['20261116T2144_c1_pass_c2_sar7_resume.md']` 保留真實狀態、run roots、submission receipts、所有已提交ID及各階段進度。C2未收完時，2144原訊息應留在 **top-level inbox**，不要搬done或標reported。這則補充確認收妥後可按原流程存檔，不必額外喚醒Codex。
2. 若SAR7已完成，先寫其獨立outbox結果並喚醒Codex，再把2144主 task設為 `status: waiting_runs`，`jobs: ['<C2 array parent純數字>']`。不要用 `761xxx_0`、附註字串或range描述。另存SAR7歷史ID／結果、C2 receipt與全部提交ID，避免遺失provenance。
3. 若短SAR7仍在排隊而本輪必須先結束，把監看的 `jobs` 暫時只列 **SAR7的純數字ID**，另存C2 parent到明確的 `c2_array_job_id` 及全部提交清單。SAR7離queue後，排程應先醒來收短結果，隨即將 `jobs` 切回C2 parent。不能把兩者一起當作唯一等待集合，否則會等C2約53小時才交SAR7結果。
4. 原poll只用squeue辨識「已離queue」，**不等於成功**。醒來後用sacct核對狀態、95案evidence及原runner summarize；95案未齊不能標complete。solver已完成但量測失敗時只用collect-only。intent有、receipt無時先查原提交／queue／accounting，不盲目重送。
5. C2完成後才交完整outbox、更新最終狀態並將2144原訊息存檔。C2可跨SAR7的23:15截止繼續執行；截止後不開新SAR7案。若遇到真實技術阻礙，回報證據並保留資料，不自行取消或重送別的工作。

本補充目的是確保同一交接中的短結果與長批次都能沿現有本機通道自動續行。不得為此改poll、transcript monitor、codex queue或其他專案。
