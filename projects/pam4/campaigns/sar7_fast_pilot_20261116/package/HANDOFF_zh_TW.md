# SAR7 1.75 GS/s 單案時序驗證

以 Olympus 已完成的 761279（`sar7_10_tt_matched_q_load`）作為電路來源。保留互補 NOR 負載、原生比較器與 CDAC/CML、參考電壓、模型、輸入與 save。761279 在約 0.926 GS/s 下測得 84/84 bit 解析、最大碼差 1 LSB、6/12 個碼有 ±1 LSB 誤差，最慢 buffered 比較判決 45.5 ps。

新案 `sar7_12_tt_175gs_matched_q` 使用已跑過的 760002 earlycmp42 時序，週期 571.428571 ps。取樣 67 ps，每碼七步間隔 66 ps，試碼後 21 ps 開比較器，比較器有 42 ps 到讀取，最後碼在 554 ps 讀取。來源電壓序列固定，移動其時間網格。移植的 25 條卡片包含 22 條脈波、兩條輸入 PWL 的時間、暫態停止時間。保留原 100 mVppd、0.756855 V 共模、TT／25 °C／0.9 V 與 12 個碼。42 ps 時序曾在較早版本解析全部 84 個 bit，這次電路的餘裕要重新量。

[Bheemisetti 等，IEEE JSSC，10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) 的 3 nm 實測原型採七個 double-tail feed-backward 比較器與非同步時序。該文在 1.75 GS/s 及近 Nyquist 報 37 dB SNDR、49 dB SFDR，並用低頻正弦波直方圖量 DNL/INL。本次用固定時序量原有 28 nm 電路在相同採樣速率的 12 個固定碼。若有 late bit，將讀取餘裕和比較前至讀取的 CDAC 差動變化並列，區分 buffered rail 未及時形成與 CDAC 殘差仍在移動。若通過，下一步先做獨立的動態測量和轉移曲線，再開始交錯整合。

## Olympus

使用 761279 的既有環境和依賴，包含 `PAM4_SAR7_CDAC_FIX_PACKAGE`、rdeg、relaxed、原 SAR7、C0、SWITCH64、r5 及私有模型 root。上傳新 ZIP 和 sidecar 到核准位置，先核對本地與 Olympus SHA，再解壓至新的資料夾。每案 1 CPU、6 GiB、Slurm 12 分鐘，solver 540 秒逾時，預估 2–5 分鐘、raw 約 60–120 MB。

```bash
export PAM4_SAR7_OFFSET_PACKAGE='/absolute/path/PAM4_SAR7_OFFSET_PILOT_20261116'
export PAM4_SAR7_FAST_PACKAGE='/absolute/path/PAM4_SAR7_FAST_PILOT_20261116'
export PAM4_SAR7_FAST_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_fast_pilot_20261116.XXXXXX")"
export PAM4_SAR7_FAST_APPROVAL="$PAM4_SAR7_FAST_ROOT/approval.json"
cd "$PAM4_SAR7_FAST_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_fast.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_fast.py approval-template --root "$PAM4_SAR7_FAST_ROOT" --approval "$PAM4_SAR7_FAST_APPROVAL"
```

核對交接中的唯一 case、run root、portable deck SHA 與 manifest，依使用者授權只將 `approved` 設為 `true`。stage 後對 761279 的同模型根目錄 bench 做逐行 diff，確認唯有 25 條時間卡片不同，再送一案。

```bash
/usr/bin/python3.11 -B sar7_fast.py stage --root "$PAM4_SAR7_FAST_ROOT" --approval "$PAM4_SAR7_FAST_APPROVAL" --model-root "$PAM4_PDK_ROOT"
sbatch --export=ALL --output="$PAM4_SAR7_FAST_ROOT/slurm-%j.out" sar7_fast.sbatch
```

若 Spectre 已完成、收集受阻，跑 `sar7_fast.py collect-only` 並傳原 root 與 approval，採用既有波形。若 solver 失敗或超時，回報本案，保留資料與 log。這包只有一個 solver，跑完回交 Codex。完整 deck、模型、raw 及逐 trial 原資料留核准 OneDrive／Olympus 位置；repo 只收去識別摘要及合規的無網表程式。

## 事先固定的判讀

`screen_pass` 要求 84 bit 全數解析、12 個 comparator 和 registered 碼都可讀且一致、末端 CDAC 共模變化不超過 ±10 mV，最大碼差 ≤1 LSB，錯碼數不超過原案的 6/12。`logic_smoke_pass` 使用原 scorer 的零錯、零未解析判準並另列。若任一條未達成，照實回報 bit、clock 截止、DAC 殘差及同順序逐碼差異判斷，不直接往 112 GS/s。即使 `screen_pass=true`，這批只驗證同一組固定碼的 TT 定速操作，DNL/INL、動態 SNDR/SFDR 和整合端負載另驗。

回報實際 task ID、job 完成狀態、summary/measurements/tran SHA、每 bit 最短讀取餘裕與 DAC 殘差變化、sample/CM 跟 761279 的差異和逐碼結果。請留原始證據供後續判讀。
