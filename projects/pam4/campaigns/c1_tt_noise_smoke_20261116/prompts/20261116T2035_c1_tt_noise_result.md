Stage: Project #6 PAM4 deskew C1 TT seed 1001 五案完成（回覆 20261116T1658_c1_tt_noise_authorized.md；接續進度報告 20261116T1855）
Status: done
Decision: PROCEED（C1 工程篩選條件符合）— P 晚、N 晚兩個方向，primary 和 secondary 的配對 Δ 都改善：
- P 晚 −60：primary −125、secondary −173 個錯誤；
- N 晚 +60：primary −278、secondary −224 個錯誤。
五案 clipping 全為 0，量測完整，沒有收集失敗。注意：五案的 secondary 絕對 SER 都在 34–45%（C0 無雜訊時約 5.6%），只能看配對差，不宜當絕對性能。C2 沒有排程，等 Codex 凍結範圍。
Summary: 5/5 COMPLETED（exit 0:0），都沒有用 collect-only。summarize 輸出 c1_noise_smoke_summary.json，status=c1_complete，noise seed 1001，C0 訓練選碼 P_late 0／N_late 60，approval 與選擇檔 pins 和首案相同。
Run paths: ~/ecen720_28nm/runs/pam4_c1_noise_20261115.RjCwBt（root/c1_noise_smoke_summary.json，root/c1n_*/，logs/）
Commit: 見下方「Commit」段
Needs user decision: no

## 五案（凍結 metric = ideal7bit_ADC_then_FFE；分母每面 2,032）
| idx | case | 注入／碼 | job（array） | primary 錯/SER/RMSE | secondary 錯/SER/RMSE | clip P/S |
|---|---|---|---|---|---|---|
| 0 | c1n_zero_cp00 | 0 skew／0 | 761319（761319_0） | 113／5.56%／0.539 | 776／38.19%／1.429 | 0/0 |
| 1 | c1n_a_cp00 | P 晚／0 | 761422（761421_1） | 235／11.56%／0.642 | 862／42.42%／1.487 | 0/0 |
| 2 | c1n_a_cm60 | P 晚／−60 | 761423（761421_2） | 110／5.41%／0.614 | 689／33.91%／1.469 | 0/0 |
| 3 | c1n_b_cp00 | N 晚／0 | 761424（761421_3） | 380／18.70%／0.748 | 916／45.08%／1.535 | 0/0 |
| 4 | c1n_b_cp60 | N 晚／+60 | 761421（761421_4） | 102／5.02%／0.612 | 692／34.06%／1.462 | 0/0 |

Gray bit errors（primary/secondary）：113/828、235/929、110/732、380/999、102/730。

## 配對差（補償臂 − 基準臂）
| 配對 | primary Δ 錯誤（ΔSER） | secondary Δ 錯誤（ΔSER） |
|---|---|---|
| P 晚 −60（固定碼診斷，和 C0 選碼分開） | −125（−6.15%） | −173（−8.51%） |
| N 晚 +60（C0 凍結選碼） | −278（−13.68%） | −224（−11.02%） |

補償臂相對零偏斜的剩餘差：
- P −60：primary −3（110 vs 113），secondary −87；
- N +60：primary −11（102 vs 113），secondary −84。
兩個補償臂的 primary 都回到零偏斜的水準。

和 C0 正式（無雜訊，分母 496）的方向一致：
- N 晚 0→+60：primary 41→43、secondary 69→48；
- 零偏斜：24／28。
C1 的 primary 改善幅度比 C0 大，原因是 C1 基準臂在雜訊下劣化較多（380/2032）。

## 資源
| idx | Slurm 耗時 | solver s | Slurm MaxRSS | child peak RSS | raw bytes |
|---|---|---|---|---|---|
| 0 | 1:41:29 | 6,060 | 167,848 KiB | 285,240 KiB | 145,748,408 |
| 1 | 1:40:07 | 5,977 | 166,252 KiB | 283,168 KiB | 145,748,407 |
| 2 | 1:42:02 | 6,092 | 166,764 KiB | 282,828 KiB | 145,748,410 |
| 3 | 1:39:59 | 5,968 | 165,604 KiB | 283,280 KiB | 145,748,404 |
| 4 | 1:40:57 | 6,027 | 166,424 KiB | 282,880 KiB | 145,748,408 |

- 每案約 100 分鐘，比歷史的 70.5–94.3 分鐘長約 7–40%。
- raw 約 139 MiB／案，共約 729 MB，全部保留。
- 1–4 四案同時跑，加上其他專案原有的 1 個 job，未超過 6 CPU。

## SHA
- summary `ec30d9d95c29e3dcfb3cede5f0b83e48ae3e2354011a8fd841f1b8d6f4549fc9`
- measurements：
  - zero `d38721b7…88fd`
  - a_cp00 `ef5337bc…cc3c`
  - a_cm60 `6e0f8ec4…99fd`
  - b_cp00 `1922b133…8660`
  - b_cp60 `9c5d3f82…f846`

## secondary 絕對 SER 偏高（沿用 1855 的唯讀初判）
- 五案的 secondary 都在 34–45%，RMSE 1.43–1.54。FFE 輸出的類別平均值正確，錯誤只在相鄰位準，對位和時鐘都正常，所以不是收集錯誤。
- FFE 前的位準標準差和 C0 相當，FFE 後放大約 4 倍。推測是凍結的 secondary FFE 對 transient noise 有 noise enhancement；權重未存，這點未經驗證。
- 配對 Δ 用同一個 seed、同一組 FFE，可比較。但 secondary 的絕對性能不能代表「差不多 IEEE 參考」，C2 範圍和 secondary 處理方式請 Codex 決定。

## 判讀
- C1 的篩選條件都符合：
  - 兩個方向的 primary 都改善；
  - secondary 沒有變差（兩個方向都改善）；
  - clipping 0，沒有量測失敗；
  - 證據完整（5 案 job、SHA、資源都齊）。
- 單一 noise seed 只能檢查配對和收尾流程；多 seed C2 的範圍依 Guide 另訂。本輪沒有排 C2。

## Commit
handoff + results：
- `projects/pam4/handoff/archive/`：收到的 inbox 訊息、1855 進度回覆和本封回覆。
- `projects/pam4/campaigns/c1_tt_noise_smoke_20261116/`：`package/`（Codex 原始碼，不含 deck／ZIP）、`results/`（summary）、`prompts/`、`README.md`。
