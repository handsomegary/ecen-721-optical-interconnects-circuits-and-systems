# ECEN 721 SAR7 · 慢速直接負載的 CDAC Vref 單案

760174 的 retained-raw 查核量到直接負載 span 107.16 LSB、目標 127 LSB、留一 RMSE 0.748 LSB。用這個權重估值將原 `V_RHI`、`V_RLO` 差動 span 乘以 `127/107.16`，共同參考 0.45 V 保持。只動這兩條 source。原比較器直接掛 CDAC，沿用相同 12 個碼、100 mVppd、1 Ω、1,080 ps／cycle 和 60 ps／60 ps 時序。其它權重、開關及比較器照原案。

查核亦顯示原 b0=0 路徑約在 trial release 後 12.5 ps 才達原 rail 門檻。這案的 scoring final read 從週期內 1027 ps 移至 1030 ps，早於 conv 下降開始點。逐 bit comparator 讀點全部維持原本設定，故判讀時分別比較比較器碼差和末端輸出 undefined 改變。保留原試驗的分數。觀察全幅 trim 能解決多少錯碼，低位比值誤差與共模仍單獨記錄。這是同 12 碼的增益診斷，不代表跨碼驗證或達到 1.75 GS/s。

## Olympus

從 OneDrive 傳 ZIP／sidecar，核對 SHA；沿用 760091 的環境及私有模型路徑。

```bash
export PAM4_SAR7_PACKAGE='/absolute/path/PAM4_R5_SAR7_SLICE_20261115'
export PAM4_SAR7_RELAXED_PACKAGE='/absolute/path/PAM4_SAR7_RELAXED_PILOT_20261115'
export PAM4_SAR7_REF_TRIM_PACKAGE='/absolute/path/PAM4_SAR7_REF_TRIM_20261115'
export PAM4_SAR7_REF_TRIM_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_ref_trim_20261115.XXXXXX")"
export PAM4_SAR7_REF_TRIM_APPROVAL="$PAM4_SAR7_REF_TRIM_ROOT/approval.json"
# 保留原案的 PAM4_C0_ORIGINAL_PACKAGE、PAM4_C0_SWITCH_PACKAGE、PAM4_C0_R5_ORIGINAL、PAM4_PDK_ROOT。
cd "$PAM4_SAR7_REF_TRIM_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_ref_trim.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_ref_trim.py approval-template --root "$PAM4_SAR7_REF_TRIM_ROOT" \
  --approval "$PAM4_SAR7_REF_TRIM_APPROVAL"
```

核對新 root、單案、manifest 與 deck SHA，只將 `approved` 改為 `true`。確認與 760091 的網表差異只有兩條參考源。

```bash
/usr/bin/python3.11 -B sar7_ref_trim.py stage --root "$PAM4_SAR7_REF_TRIM_ROOT" \
  --approval "$PAM4_SAR7_REF_TRIM_APPROVAL" --model-root "$PAM4_PDK_ROOT"
sbatch --export=ALL --output="$PAM4_SAR7_REF_TRIM_ROOT/slurm-%j.out" "$PAM4_SAR7_REF_TRIM_PACKAGE/sar7_ref_trim.sbatch"
```

1 CPU、6 GiB、Slurm 30 分鐘，預估 solver 3–6 分鐘、80–100 MB raw。已完成 solver 後可 `collect-only`。本機 outbox 報新 job、逐碼、比較器最大碼差與總絕對碼差、未解析、末端輸出、取樣誤差、滿刻度殘差與共模，以及 `sar7_ref_trim_summary.json` SHA。原始 PSF 和輸入留 Olympus。
