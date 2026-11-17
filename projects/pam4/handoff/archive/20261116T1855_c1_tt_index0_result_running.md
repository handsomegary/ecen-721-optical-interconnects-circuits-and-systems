Stage: Project #6 PAM4 deskew C1 TT seed 1001 — index 0 首案結果與 1–4 已送出（回覆 20261116T1658_c1_tt_noise_authorized.md，進度報告）
Status: running
Decision: PROCEED — index 0 通過 Guide 的技術有效性門檻，所以送出 1–4（job 761421，array 1–4%4）。另外要注意：零偏斜 secondary 的 SER 為 776/2032（38.2%），遠高於 C0 無雜訊時的 28/496（5.6%）。
Summary: 761319_0 COMPLETED（exit 0:0），Slurm 耗時 1:41:29，solver 6,060 s。run_status=spectre_completed，solver_completion_errors 0。noise seed 1001（bench 為 noiseseed=1001，頻寬 500M–150G）。selection pins 與 C0 正式選擇檔相符。primary 與 secondary 各計分 2,032 個符號，clipping 皆為 0/2048。compact measurements 有效，不需要 collect-only。
Run paths: ~/ecen720_28nm/runs/pam4_c1_noise_20261115.RjCwBt（root/c1n_zero_cp00_phm1_s1001/，logs/slurm-761319_0.out、logs/ 下的 761421_*）
Commit: 未 commit（進度報告；五案完成後再依 handoff + results 一起 commit）
Needs user decision: no

## index 0（零偏斜，碼 0，seed 1001）
| 項目 | 值 |
|---|---|
| job | 761319_0，n01-zeus，COMPLETED 0:0 |
| Slurm 耗時／solver 時間 | 1:41:29／6,059.97 s（歷史範圍 70.5–94.3 min；本案較長） |
| Slurm MaxRSS／child peak RSS | 167,848 KiB／285,240 KiB |
| raw bytes | 145,748,408（tran 145,739,540） |
| tran SHA | ea516f9f1d86550a58d1af658581f33ce4776f01347413758196d51d82f8e15a |
| measurements SHA | d38721b739f22dbf3255a43b140e5b4c07cb581d605c2a3ac9da96b1c30788fd |
| 時鐘 audit | 410 個 master falls，最大週期誤差 9.15 fs；secondary 最大 fall 誤差 0.118 ps，容差 1.116 ps |
| 長窗 | TX [1152,3200)，FFE center [1160,3192)，primary 與 secondary 的 lag 都是 2 |
| clipping | primary 0/2048，secondary 0/2048 |

## 計分（凍結 metric = ideal7bit_ADC_then_FFE）
| 面 | C1 錯誤/分母 | SER | RMSE | C0 無雜訊零偏斜（c0f_payload_zero_cp00） |
|---|---|---|---|---|
| primary | 113/2032 | 5.56% | 0.539 | 24/496（4.84%），RMSE 0.513 |
| secondary | 776/2032 | 38.19% | 1.429 | 28/496（5.65%），RMSE 0.552 |

其他 secondary 指標：raw_held_FFE 794/2032；ADC 三門檻（無 FFE）1122/2032；Gray BER 20.4%。

## secondary 偏高的唯讀初判（沒有修改 Codex 程式）
- 不是對位或收集錯誤：
  - 四個符號的 FFE 輸出平均值是 −2.67、−0.91、+0.96、+2.89，和目標 ±1、±3 對齊，和 C0 一致；
  - 混淆矩陣只錯到相鄰的位準；
  - lag 和時鐘都正常。
- FFE 前的 secondary 原始位準標準差（4.35–4.62 mV）和 C0（4.06–4.67 mV）差不多，但 FFE 後每個符號的標準差從 0.30–0.37 增加到 1.38–1.46（約 4 倍）。primary 只從 0.29–0.31 增加到 0.50–0.53。
- 這看起來像凍結的 secondary FFE（fullscale 0.075 Vpp）把不相關的 transient noise 大幅放大（noise enhancement）。不過 FFE 權重不在 measurements.json 裡，所以這只是推測，未經驗證。
- 依 Guide，零偏斜 SER 只作對照；配對 Δ 使用同一個 seed，仍可計算。所以照常送出 1–4，判讀交給 Codex。

## 已送出
- `sbatch --export=ALL --array=1-4%4 c1_smoke.sbatch`（在 run root 的 logs 目錄，先 source env_c1.sh），job 761421。
- 4 案同時跑，每案 1 CPU、6G、5 小時上限，全部 RUNNING。
- 依首案時間估計約 20:40 CST 完成。完成後跑 summarize，回報五案的分子／分母、clipping、RMSE、配對 Δ、wall time、RSS、raw 和摘要 SHA。C2 沒有排程。
