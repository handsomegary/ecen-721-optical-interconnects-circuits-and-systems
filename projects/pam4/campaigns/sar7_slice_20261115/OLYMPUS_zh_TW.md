# ECEN 721 Project #6 · 7-bit SAR 單路原型

先在 Olympus 跑案 0。它驗證現有 28 nm StrongARM 能否在一個 1.75 GS/s 週期內依序完成七次判決，以及 4+3 split CDAC 在比較器負載下能否產生預期碼。案 1 將輸入改成高共模與有限源阻抗，檢查下一步接 r5 次取樣端時的負載風險。

| 案 | 輸入條件 | 用途 |
| --- | --- | --- |
| `sar7_00_tt_pilot` | 0.756855 V 共模、100 mVppd、每腿 1 Ω | 先驗證判決、回授和 CDAC 時序 |
| `sar7_01_tt_secondary_stress` | 0.843164 V 共模、75 mVppd、每腿 500 Ω | 檢查近電源軌和有限輸出阻抗下的取樣誤差 |

0.843164 V 取自歷史 r7 次取樣共模。500 Ω 是源阻抗替代模型，參考 r5 隔離級負載電阻。案 1 同時改了三個輸入條件，結果只適合判斷是否需要直接接實際緩衝級進一步隔離原因。

## 電路和判讀

- [Bheemisetti 等人的 JSSC 論文](https://ieeexplore.ieee.org/document/10723273)提供單路 1.75 GS/s、兩級交錯取樣和七顆比較器展開的參考。這版使用歷史 r5 `in100_tail3` StrongARM、28nm 原生 MOS 傳輸閘和理想時序。前一 bit 的實際比較器判決決定後續 CDAC 狀態。
- 4+3 split CDAC 用歷史 N6 單位電容和 N8 橋接電容的量測等效值。原生 MOM 元件卡留在私有 VM，這版以等效電容驗證電路。參考電壓和控制時序由測試平台提供，功耗需等時脈、控制和參考驅動實體化後再估。
- 兩案用相同的 12 個名義碼中心，包含兩端、中心及交錯位元。每個已計分樣本的七次比較須在對應讀出時刻前達到 20%／80% 互補電位，最終碼須符合輸入名義碼。這是首輪短測的判讀規則。DNL、INL、SNDR、失配、雜訊與完整 112 GS/s 交錯整合都需另外驗證。
- 收集器逐碼留下取樣誤差、CDAC 共模與殘差、各 bit 比較器解析時間、判決和輸出碼。若碼錯，先核對取樣時的 CDAC 誤差，再看判決是否和當時殘差的正負一致。若 DAC 已穩定而比較器未在時限內解析，才回到比較器輸入負載、共模或時序。案 0 未達判讀規則時先交量測回來，避免案 1 一次引入多個變因。

## Olympus 執行

Spectre Classic 23.1.0.722.isr15，`+mt=1`。每案一顆 CPU、6 GiB 記憶體、Slurm 保留 30 分鐘，Spectre 上限 20 分鐘。首輪規劃每案約 1–10 分鐘，6.85 ns 暫態以 0.25 ps 間距存 54 條訊號，ASCII raw 粗估 50–90 MiB。實測以案 0 為準，raw 留在 Olympus 供核對。

先核對 ZIP SHA，再把壓縮包解開至新目錄。下列四個路徑使用 Olympus 現有原始依賴與本次解壓位置。原始 C0 runner 的 `SHA256SUMS.txt` 已綁定，SWITCH64 和 r5 依賴由原始 runner 核對。

```bash
export PAM4_SAR7_PACKAGE='/absolute/path/PAM4_R5_SAR7_SLICE_20261115'
export PAM4_C0_ORIGINAL_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_C0_RUN_20261115'
export PAM4_C0_SWITCH_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_SWITCH64_ENDPOINT_COLLECT_FIX_20261115'
export PAM4_C0_R5_ORIGINAL='/absolute/path/PAM4_PNSKEW_COMP_20261113/r5_original'
export PAM4_PDK_ROOT="$HOME/ecen720_28nm/tools/local_replay_migration_20261108/private_models/r7_vm_shrink"
export PAM4_SAR7_RUN_ROOT="$HOME/ecen720_28nm/runs/pam4_r5_sar7_slice_20261115"
mkdir "$PAM4_SAR7_RUN_ROOT"
export PAM4_SAR7_APPROVAL="$PAM4_SAR7_RUN_ROOT/approval_case0.json"

cd "$PAM4_SAR7_PACKAGE"
sha256sum -c SHA256SUMS.txt
python3 -B sar7_run.py verify
python3 -B -m unittest discover -p 'test_sar7_*.py'
python3 -B sar7_run.py list
sha256sum SHA256SUMS.txt
```

依現有 Olympus 授權流程，在 run root 從 `approval_TEMPLATE.json` 建立案 0 的紀錄，填入上一步 `SHA256SUMS.txt` 的 SHA。載入原 C0 使用的 Spectre 環境後送出。

```bash
sbatch --output="$PAM4_SAR7_RUN_ROOT/slurm-%j.out" "$PAM4_SAR7_PACKAGE/sar7_slice.sbatch" 0
```

先回報案 0 的 `measurements.json`、最慢比較器和最大取樣誤差，以及 job ID、耗時、raw 大小。若執行成功但收集有問題，保留 raw 用 `collect-only` 恢復。

```bash
python3 -B "$PAM4_SAR7_PACKAGE/sar7_run.py" collect-only --index 0 --root "$PAM4_SAR7_RUN_ROOT"
```

案 0 先確認 `logic_smoke_pass`。若通過，再用案 1 的授權紀錄與 `sbatch` 參數 `1`。兩案都完成後，下一步先接一個實際 r5 次取樣緩衝級重驗，再決定交錯陣列及校準。
