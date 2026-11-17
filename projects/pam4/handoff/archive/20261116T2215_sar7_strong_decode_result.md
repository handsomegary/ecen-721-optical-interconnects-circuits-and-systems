Stage: SAR7 1.75 GS/s strong-decode 單案（sar7_15_tt_175gs_strong_decode），來自 20261116T2144_c1_pass_c2_sar7_resume.md
Status: done
Decision: STOP — 565 ps screen_pass=false：registered 12/12 可讀但 7/12 錯、max 3 LSB；comparator 0/12 可讀（26/84 bit 未解析）；x/y 已再生但 buffered q 未到 rail
Summary: gate 交越變快、held 提早建立，但加大的 decoder 輸入電容拖慢比較器 q；限制從控制路徑轉到 comparator／q 負載
Run paths: ~/ecen720_28nm/runs/pam4_sar7_strong_decode_pilot_20261116.qUaOJ0（env wrappers/env_strong.sh）
Commit: 見本輪 commit（campaign projects/pam4/campaigns/sar7_strong_decode_pilot_20261116/）
Needs user decision: no

# SAR7 strong-decode 單案結果（job 761524）

## 執行與核對
- 外層 ZIP SHA c8441267…cc7ee 正確；`verify_bundle.py` PASS；`SHA256SUMS.txt` 8/8 OK。
- 子包 ZIP 32603df4…3b423617；Olympus `sha256sum -c` 5/5、`verify` 印出 case/portable deck 31d7e4e6…180da8、unittest 7/7 OK。
- Parent R2 manifest（native 包 `SHA256SUMS.txt`）= 12e5745c…ae24 ✔。
- approval-template 只把 `approved` false→true（manifest 43b93d73…bd8）。
- stage deck（絕對模型路徑）SHA 5aaa4b22…99be1。對 761433 deck diff：刪 85／加 102 = (16+56+13)/(33+56+13)，pulse 行 26 = 13 對，新增行沒有 save/TG/SAR_INV 字樣，與宣告一致。差異存於 `logs/stage_diff_vs_761433.txt`。
- 提交時間 2026-11-17 03:58 UTC，早於 05:15 UTC 截止；sbatch 761524。COMPLETED 0:0，耗時 5:01，solver 266.6 s，MaxRSS 126 MB，raw 93,314,272 bytes（case 目錄 93.5 MB）。全部 raw 保留。

## 主讀點 565 ps（與診斷讀點）
| 讀點 | registered 可讀 | 錯 | Σ|err| | max | comparator 可讀 | 未解析 bit | screen | logic_smoke |
|---|---|---|---|---|---|---|---|---|
| **565** | 12/12 | 7 | 10 | 3 | 0/12 | 26/84 | false | false |
| 563 | 12/12 | 7 | 10 | 3 | 0/12 | 26 | false | false |
| 554 | 12/12 | 8 | 14 | 4 | 0/12 | 26 | false | false |
| 557 | 4/12 | 2 | 2 | 1 | 0/12 | 26 | false | false |

- 輸出窗：565／563 ps 12/12 `valid_read_window`（reset=track=conv=0 V，comparator clock 最低 0.9 V）。
- CM：active 最後比較讀點 552 ps ΔCM −4.04／−3.99 mV（`active_last_read_cm_pass=true`）；498 ps trigger −4.28／−3.86 mV（僅報數值）；565 ps post-conv −9.19／+5.40 mV（≤10 mV）。CM 不是失敗原因。
- 最大取樣誤差 1.677 LSB（761433：1.641）；max observed resolve delay 46.9 ps。
- Reference source peak |I| ≤ 0.219 mA。

逐碼（expected → reg565 / reg563 / reg554 / reg557）：
64→64/64/65/–；0→0/0/1/–；127→127 全部；31→31 全部；96→95/95/95/95；63→64/64/65/–；65→64/64/65/–；85→88/88/89/–；42→44/44/45/–；1→0/0/1/–；126→127/127/127/127；64→64/64/65/–。comparator 碼 12 筆皆 null。

## 與 761433（native decode）比較
| bit | 未解析 new/old | gate 最後 50% 交越中位數 ps new/old | held 進入 read±1 LSB 中位數/最大 ps new | old | 窗 launch/compare/read |
|---|---|---|---|---|---|
| 6 | 4/0 | 12.7/17.0 | 54.9/55.4 | 61.5/62.0 | 78/120/159 |
| 5 | 1/1 | 13.9/16.7 | 32.6/57.1 | 39.3/64.8 | 162/207/251 |
| 4 | 1/1 | 13.9/16.6 | 22.4/35.7 | 40.5/41.0 | 254/279/319 |
| 3 | 2/0 | 13.9/16.6 | 24.9/25.3 | 29.8/30.5 | 322/341/381 |
| 2 | **12/0** | 13.9/16.7 | 25.5/27.9 | 23.4/29.1 | 384/399/437 |
| 1 | 6/0 | 13.9/16.6 | 12.4/19.1 | 22.6/24.5 | 440/448/489 |
| 0 | 0/0 | 13.9/16.6 | 7.1/14.6 | 0.1/17.9 | 492/498/552 |

（held 時間由 launch 起算；old 欄為 761433 同欄位。）

## 機制判讀（唯讀，只用既有 PSF 快照）
- 控制路徑確實變快：gate 交越約快 3 ps，b4／b3／b1 held 建立中位數提早 18／5／10 ps，registered 從 4/12 可讀變 12/12 可讀，max 由 6 降到 3。
- 新的失敗點在 comparator 輸出 q：read 時 |x−y| 最小值仍有 0.63–0.88 V（內部再生已完成），但 q 高側 read 中位數降到 b2 0.589 V、b1 0.719、b3 0.771（761433 為 0.888／0.885／0.880）。compare+30 ps 的 q 高側中位數只有 0.21–0.53 V。q 直接驅動加大 2–3 倍的 OAI21／NOR3 輸入，判決存在但 buffered q 未在讀點前到達邏輯準位，所以 detector 判為未解析。
- 例：一筆 b2 未解析，read 時 x/y = 0.864／0.081 V，q = 0.052／0.589 V；釋放後 1 ps q = −0.028／0.662 V。
- 依 Guide 預先寫好的分支，「held 已穩而判決仍慢 → 查 comparator／q 負載與再生窗」成立；reference-TG／類比 RC 不是這一案的主要限制。
- 錯碼型態：0/63/65/64 一帶落在 64 附近，85→88、42→44 有 +2–3 偏差。這和 b2／b1 判決延遲一致，不過這只是推測，沒有逐 bit 確認。

這只是 12 碼 TT 短測，transfer／頻譜和 112 GS/s 整合不在範圍內。我沒有加第二案，也沒有掃 TG／驅動。依 SAR7 截止（23:15）規定，截止後不開新 SAR7 案。

## SHA
- summary 73dafa11235da6c63048536e447cd3bda60dba23155b03a399d86c725a84ac03（repo 版路徑已遮罩，byte 不同）
- measurements a8b0c965f0a4a7e9ccdf11523aa7f0b2fb9142e24a3349fc0b6cb343c3813a18
- tran fc21cd54451e4c2798e08366c859db125e898eaf0a4f5584c280450ec4fcb318
- bench.scs（staged）5aaa4b22680633acec59fd2070181c6cca5683c941d33f39c51dd6fbba399be1

## C2 狀態（同一 2144 交接）
已提交，仍在執行；完整結果等 95 案收齊後另發 outbox。
- run root `~/ecen720_28nm/runs/pam4_c2_tt_paired_20261116.XbmQi3`（C2 root `.../root`，env `wrappers/env_c2.sh`）。
- array job **761525**（`0-94%3`）。approval SHA feb8039c…f403。`c2_submission.json` SHA 98ad47d4a8dfdb1964623373a39e4bc9ebdffcad156616be1ee87540fa74b97b，intent SHA 92e28e47…8134。
- approval 與 template 的差異只有 approved 一行。95/95 deck SHA 與 `verify` 輸出一致。C1 summary 原檔 ec30d9d9 ✔，review f3e983d0 ✔。
- 提交前帳號占用：1 CPU（另一專案 1 個 running）加 SAR7 1 CPU。C2 3 並行後合計 5 ≤ 6。home 剩 22 GB，預估新 raw 12.9 GiB。
- 前三案 761525_0／_1／_2 在 22:03 起 RUNNING。預估 53–54 h 加排隊。本機 state 設為 `waiting_runs`、jobs=['761525']，交給既有排程續看。
