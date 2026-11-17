# ECEN 721 SAR7 · 放寬時序的單案診斷

job 760002 用 21 ps DAC 等待、42 ps 比較窗，84 個 bit 全數解析，最慢 38.1 ps；12 筆仍有 10 筆碼錯，末端共模下降約 107–112 mV。這次在 1,080 ps 週期（約 0.926 GS/s）給每步 60 ps DAC 等待及 60 ps 比較窗。用同一電路、輸入共模和 12 個碼中心，觀察錯誤在充裕時序下是否仍存在。

只送 `sar7_03_tt_relaxed`。沿用 65／55 ps 的 track close、相同的取樣時刻（各週期 67 ps）和參考電壓。只改 22 條週期脈波、兩條 PWL 的時間軸及 transient stop，共 25 行。報未解析 bit、錯碼、最慢比較、取樣誤差和末端 CDAC 共模差。若錯誤仍多，保留資料，下一步先定位 DAC／比較器的耦合及靜態誤差。這是慢速診斷，1.75 GS/s 的原規格另以原時序驗證。

## Olympus

從 OneDrive 傳 ZIP 並核對 ZIP SHA 與 manifest。依賴沿用原案 SAR7 與 C0／SWITCH64／r5，模型留在原位。

```bash
export PAM4_SAR7_PACKAGE='/absolute/path/PAM4_R5_SAR7_SLICE_20261115'
export PAM4_SAR7_RELAXED_PACKAGE='/absolute/path/PAM4_SAR7_RELAXED_PILOT_20261115'
export PAM4_SAR7_RELAXED_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_relaxed_20261115.XXXXXX")"
export PAM4_SAR7_RELAXED_APPROVAL="$PAM4_SAR7_RELAXED_ROOT/approval.json"
# 保留原案的 PAM4_C0_ORIGINAL_PACKAGE、PAM4_C0_SWITCH_PACKAGE、PAM4_C0_R5_ORIGINAL 與 PAM4_PDK_ROOT。
cd "$PAM4_SAR7_RELAXED_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_relaxed.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_relaxed.py approval-template --root "$PAM4_SAR7_RELAXED_ROOT" \
  --approval "$PAM4_SAR7_RELAXED_APPROVAL"
```

核對新 root、單案、manifest 與 deck SHA。只把範本的 `approved` 改為 `true`，授權說明留在本機 state／交接紀錄。

```bash
/usr/bin/python3.11 -B sar7_relaxed.py stage --root "$PAM4_SAR7_RELAXED_ROOT" \
  --approval "$PAM4_SAR7_RELAXED_APPROVAL" --model-root "$PAM4_PDK_ROOT"
sbatch --export=ALL --output="$PAM4_SAR7_RELAXED_ROOT/slurm-%j.out" "$PAM4_SAR7_RELAXED_PACKAGE/sar7_relaxed.sbatch"
```

1 CPU、6 GiB、Slurm 30 分鐘；預估 solver 3–6 分鐘，raw 約 80–100 MB。若已完成 solver，使用 `collect-only` 恢復量測。新摘要為 `sar7_relaxed_summary.json`，透過本機 outbox 回報，依照交接權限存放 compact 數據。保留全部原始波形，新舊網表與模型留 Olympus／OneDrive。
