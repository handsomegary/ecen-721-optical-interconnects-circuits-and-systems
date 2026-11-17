# ECEN 721 正式 C1 · TT transient-noise smoke

C1 以原 Project #6 的整合 gm-tap、r3、r5 和 COMMON64 控制字檢查長窗含雜訊的量測流程。沿用正式 C0 鎖定的 −1/8 UI 相位、lag、極性、理想 7-bit ADC 範圍和 17-tap FFE。29.414285714 ns 長窗使用原 r5 前導資料 seed `2026101301` 和驗證資料 seed `2026101302`。每面計入 TX `[1152,3200)` 的 2,048 個 ADC 輸入和 `[1160,3192)` 的 2,032 個 FFE 中心。五案使用相同刺激序列、共同相位與同一個 Spectre transient-noise seed 1001。頻率範圍沿用原 r5 的 500 MHz 至 150 GHz。

| 索引 | 注入 skew | COMMON64 碼 | 配對角色 |
| ---: | --- | ---: | --- |
| 0 | 0 | 0 | 整合零偏斜基準及流程首案 |
| 1 | P 晚 4.464285714 ps | 0 | P 晚基準 |
| 2 | P 晚 4.464285714 ps | −60 | 延續 C0 核准的固定碼診斷 |
| 3 | N 晚 4.464285714 ps | 0 | N 晚基準 |
| 4 | N 晚 4.464285714 ps | +60 | N 晚已補償臂 |

正式 C0 的訓練選碼照原紀錄保存。C1 的 P 晚 −60 是固定端點配對。全批直接使用凍結計分，保留符號錯誤數與分母、SER、7-bit clipping、Gray 位錯、RMSE 及量測失敗情況。單一 noise seed 只能檢查配對和收尾流程。即使首批兩方向改善，正式多 seed C2 仍需依此批實際時間、時鐘、雜訊、資源與結果另訂範圍。

## Olympus 準備

從 OneDrive 傳送這一批 ZIP 和 SHA。核對 ZIP 的 sidecar 及解壓後的 manifest。保留正式 C0 環境中的 `PAM4_C0_ALIGN_PACKAGE`、`PAM4_C0_ORIGINAL_PACKAGE`、`PAM4_C0_SWITCH_PACKAGE`、`PAM4_C0_R5_ORIGINAL` 和 `PAM4_PDK_ROOT`。`PAM4_C0_FORMAL_ROOT` 指向有原始 `selected_phase.json` 與 `selected_codes.json` 的已驗證正式 C0 run root。各歷史依賴和私有模型留在 Olympus 既有位置。

```bash
export PAM4_C1_PACKAGE='/absolute/path/PAM4_C1_NOISE_SMOKE_20261115'
export PAM4_C0_FORMAL_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_C0_FORMAL_20261115'
export PAM4_C0_FORMAL_ROOT='/absolute/path/to/original/formal/c0/run/root'
export PAM4_C1_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_c1_noise_20261115.XXXXXX")"
export PAM4_C1_APPROVAL="$PAM4_C1_ROOT/approval_c1.json"

cd "$PAM4_C1_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B c1_run.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B c1_run.py list
/usr/bin/python3.11 -B c1_run.py approval-template \
  --c0-root "$PAM4_C0_FORMAL_ROOT" --root "$PAM4_C1_ROOT" --approval "$PAM4_C1_APPROVAL"
```

核對 `approval-template` 產生的 manifest、run root、五案、各 deck SHA 與正式 C0 選擇檔。依本次使用者委任與 Codex 本機交接，確認後只將 `approved` 設為 `true`。先 stage 首案並看 `bench.scs`、選擇檔雜湊和 run root。

```bash
/usr/bin/python3.11 -B c1_run.py stage \
  --c0-root "$PAM4_C0_FORMAL_ROOT" --root "$PAM4_C1_ROOT" \
  --approval "$PAM4_C1_APPROVAL" --model-root "$PAM4_PDK_ROOT" --index 0
sbatch --export=ALL --array=0 "$PAM4_C1_PACKAGE/c1_smoke.sbatch"
```

每案 Spectre Classic `+mt=1`、1 CPU、6 GiB，Slurm 預留 5 小時，solver timeout 16,200 秒。歷史同長度雜訊案約 70.5–94.3 分鐘及 133 MiB raw，整合版工時與 raw 以實際首案估算。批次原始檔與執行日誌保留在指定 run root。

## 首案放行與續跑

首案要有完整的 Slurm／solver 成功紀錄、可核對的 noise seed 與 C0 選擇檔、有效的時鐘與完整長窗，以及 primary、secondary 各 2,032 個計分符號和有效的 compact 量測。首案即時回報 job ID、solver wall、Slurm MaxRSS、raw bytes、兩面的錯誤分子／分母及 clipping。這是技術有效性門檻，零偏斜 SER 數值作為對照。首案尚未通過時停在 index 0，先用既有日誌和輸出診斷。solver 已成功且輸出完整時可以 `collect-only` 復原量測。

```bash
# 已完成 solver 且需要補收時
/usr/bin/python3.11 -B c1_run.py collect-only \
  --c0-root "$PAM4_C0_FORMAL_ROOT" --root "$PAM4_C1_ROOT" \
  --approval "$PAM4_C1_APPROVAL" --index 0

# 首案通過後送其餘四案。帳號的 Olympus QOS 同時上限為 6 CPU。
sbatch --export=ALL --array=1-4%4 "$PAM4_C1_PACKAGE/c1_smoke.sbatch"

# 五案完成、量測核對後
/usr/bin/python3.11 -B c1_run.py summarize \
  --c0-root "$PAM4_C0_FORMAL_ROOT" --root "$PAM4_C1_ROOT" \
  --approval "$PAM4_C1_APPROVAL"
```

摘要輸出為 `c1_noise_smoke_summary.json`。分別回報 P 晚與 N 晚的配對 ΔSER（補償臂減基準臂）及零偏斜剩餘差，每一面列出分子和分母。若某面變差，保留完整對照和 seed 1001，讓 Codex 依據可核對的數字判讀。每案保留 job ID、失敗或缺案原因、wall time、MaxRSS、raw bytes 與摘要 SHA。Claude 經本機 `outbox` 回報，依本機交接的 `Commit allowed` 存放可分享的 compact 結果。這一輪保留 raw；ZIP、PDK、網表、raw 與憑證留在核准位置。
