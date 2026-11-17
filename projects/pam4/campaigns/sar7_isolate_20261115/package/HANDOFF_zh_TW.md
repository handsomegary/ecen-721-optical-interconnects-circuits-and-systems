# ECEN 721 SAR7 · 隔離比較器輸入的單案診斷

job 760091 的 60 ps DAC 預留和 60 ps 比較已能解析全部 84 個 bit，仍錯 10／12 碼，且六筆 final output 無法判讀。若干中間碼的末端殘差很小，碼仍誤差 4–7，滿刻度端仍有約 10 LSB 殘差，CDAC 主節點最後下降約 109–113 mV。

新案沿用 job 760091 的時序、刺激與 CDAC。僅增加一對理想 unity VCVS，七顆物理比較器改由這對理想源讀取同一個 hold 差動與共模。此對照移除比較器輸入的**總負載**，包含靜態電容及切換回灌。結果用於定位問題，不能直接區分這兩項，也不能作為實體緩衝器或高速規格驗收。

先用同一包讀 job 760091 保留 PSF 的比較器輸出對和 final output 位元對。在原 compare read 和 end_s 比較電位，區分動態比較器輸出失去 rail 與末端邏輯傳遞。這一步使用原始 run 的證據和 PSF，審核數據寫至新目錄。

## Olympus

從 OneDrive 傳 ZIP，核對 ZIP SHA 和 manifest。沿用原 SAR7、relaxed、C0／SWITCH64／r5 的已驗證安裝與原私有模型。

```bash
export PAM4_SAR7_PACKAGE='/absolute/path/PAM4_R5_SAR7_SLICE_20261115'
export PAM4_SAR7_RELAXED_PACKAGE='/absolute/path/PAM4_SAR7_RELAXED_PILOT_20261115'
export PAM4_SAR7_ISOLATE_PACKAGE='/absolute/path/PAM4_SAR7_SENSE_ISOLATION_20261115'
export PAM4_SAR7_ISOLATE_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_isolate_20261115.XXXXXX")"
export PAM4_SAR7_ISOLATE_APPROVAL="$PAM4_SAR7_ISOLATE_ROOT/approval.json"
export PAM4_SAR7_RELAXED_ROOT='/absolute/path/to/completed/job-760091-campaign'
cd "$PAM4_SAR7_ISOLATE_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_isolate.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_isolate.py baseline-audit --root "$PAM4_SAR7_ISOLATE_ROOT" \
  --baseline-root "$PAM4_SAR7_RELAXED_ROOT"
/usr/bin/python3.11 -B sar7_isolate.py approval-template --root "$PAM4_SAR7_ISOLATE_ROOT" \
  --approval "$PAM4_SAR7_ISOLATE_APPROVAL"
```

核對單案、manifest、root 和 deck SHA。只改範本的 `approved` 為 `true`；授權說明記在本機 state。

```bash
/usr/bin/python3.11 -B sar7_isolate.py stage --root "$PAM4_SAR7_ISOLATE_ROOT" \
  --approval "$PAM4_SAR7_ISOLATE_APPROVAL" --model-root "$PAM4_PDK_ROOT"
sbatch --export=ALL --output="$PAM4_SAR7_ISOLATE_ROOT/slurm-%j.out" "$PAM4_SAR7_ISOLATE_PACKAGE/sar7_isolate.sbatch"
```

比較原 relaxed deck 時只允許新增 `EISO_P`／`EISO_N` 和改七條 `XCMP` 的輸入節點。每案 1 CPU、6 GiB、Slurm 30 分鐘，預估 3–6 分鐘、80–100 MB raw。若 solver 已完成而收集失敗，使用 `collect-only`。本機 outbox 回報 job ID、錯碼、滿刻度殘差、最大取樣誤差、共模、暫存 rail 查核及 `sar7_isolation_summary.json` 與 `sar7_760091_rail_audit.json` 的 SHA。兩側 raw 留 Olympus。
