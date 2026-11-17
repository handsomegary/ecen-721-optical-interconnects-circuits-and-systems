# ECEN 721 SAR7 · 原生 r5 CML 感測隔離短測

理想電壓感測把 CDAC 共模下移從約 110 降到 4.3 mV，顯示比較器總輸入負載值得隔離。這次重用歷史 r5 `B0` 的四顆原生 28 nm MOS CDF 幾何和每側 500 Ω 負載，tail gate 仍 0.5 V，供應 0.9 V。從 CDAC 各 hold node 感測並以反相的兩腿互換接七顆比較器。這是第一個原生感測臂，Vref 與 760132 相同，便於比較實體臂與理想對照。

保留 760091 的 12 個碼、1,080 ps 週期、60／60 ps 和 CDAC 元件。末端 scoring 讀點採已核對的 1030 ps，逐 bit 原時刻不變。報 `pre_s` 實體感測增益、符號一致性與感測輸出共模、支路取樣點電流、CDAC 共模與碼差。只有這 1 案，作為是否值得開展高速原生隔離的判據。這個慢速診斷不主張 1.75 GS/s。

## Olympus

從 OneDrive 傳 ZIP／sidecar，核對 SHA；沿用既有 SAR7 relaxed 環境和私有模型。

```bash
export PAM4_SAR7_PACKAGE='/absolute/path/PAM4_R5_SAR7_SLICE_20261115'
export PAM4_SAR7_RELAXED_PACKAGE='/absolute/path/PAM4_SAR7_RELAXED_PILOT_20261115'
export PAM4_SAR7_CML_PACKAGE='/absolute/path/PAM4_SAR7_CML_SENSE_20261115'
export PAM4_SAR7_CML_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_cml_sense_20261115.XXXXXX")"
export PAM4_SAR7_CML_APPROVAL="$PAM4_SAR7_CML_ROOT/approval.json"
# 保留原案的 PAM4_C0_ORIGINAL_PACKAGE、PAM4_C0_SWITCH_PACKAGE、PAM4_C0_R5_ORIGINAL、PAM4_PDK_ROOT。
cd "$PAM4_SAR7_CML_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_cml_sense.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_cml_sense.py approval-template --root "$PAM4_SAR7_CML_ROOT" \
  --approval "$PAM4_SAR7_CML_APPROVAL"
```

核對單案、manifest、root 及 deck SHA，只把範本的 `approved` 改為 true。對 760091 的差異應為新增八條支路元件／偏壓、七個 comparator input pairs 和一條 save；網表時序、CDAC、參考無變動。

```bash
/usr/bin/python3.11 -B sar7_cml_sense.py stage --root "$PAM4_SAR7_CML_ROOT" \
  --approval "$PAM4_SAR7_CML_APPROVAL" --model-root "$PAM4_PDK_ROOT"
sbatch --export=ALL --output="$PAM4_SAR7_CML_ROOT/slurm-%j.out" "$PAM4_SAR7_CML_PACKAGE/sar7_cml_sense.sbatch"
```

1 CPU、6 GiB、Slurm 30 分鐘，預估 solver 3–6 分鐘、raw 80–110 MB。完成 solver 可用 `collect-only` 維持原已執行證據。由本機 outbox 報 `sar7_cml_sense_summary.json` SHA、job ID 及相對 760091／760132 的結果。保留新舊 raw，不搬模型或網表。
