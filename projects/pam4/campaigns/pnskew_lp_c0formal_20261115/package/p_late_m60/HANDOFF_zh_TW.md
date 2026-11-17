# 正式 C0 payload · P 晚 −60 單案

已核准補一案 `c0f_payload_a_cm60_phm1`，和 job 759018 的 `c0f_payload_a_cp00_phm1` 配對。偏斜同為 P 晚 4.464285714 ps，兩案共用 payload seed `2026111502`、相位 −1/8 UI、lag、FFE 與 ADC 範圍。使用原正式 C0 產生器，逐行驗證只改 32 個 COMMON64 開關控制電壓。正式選碼仍為 P 晚 0、N 晚 +60。

預估 20 分鐘、約 30 MB raw。只送一個 Slurm job，1 CPU／6 GiB／90 min，Spectre classic `+mt=1`，solver timeout 4,200 秒。舊作業和原始選擇檔保留，新案使用獨立 run root。

## Olympus

將 OneDrive 的 ZIP 和 `.sha256` 傳到 Olympus。各依賴路徑沿用正式 C0 與其 rescore 的已核對套件。

```bash
sha256sum -c ECEN721_PAM4_P_LATE_M60_20261115.zip.sha256
export PAM4_C0_PLATE_PACKAGE='/absolute/path/PAM4_P_LATE_M60_20261115'
export PAM4_C0_FORMAL_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_C0_FORMAL_20261115'
export PAM4_C0_RESCORE_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_C0_FORMAL_RESCORE_20261115'
export PAM4_C0_FORMAL_ROOT='/absolute/path/to/original/formal/c0/run/root'
export PAM4_C0_PLATE_ROOT='/absolute/path/to/new/one_case/run/root'
export PAM4_C0_PLATE_APPROVAL="$PAM4_C0_PLATE_ROOT/approved_plate_m60.json"
# 保留原正式 C0 的 PAM4_PDK_ROOT 和既有依賴路徑設定

cd "$PAM4_C0_PLATE_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B c0_plate_m60.py verify
/usr/bin/python3.11 -B -m unittest discover -v -p 'test_plate_m60.py'
mkdir "$PAM4_C0_PLATE_ROOT"
/usr/bin/python3.11 -B c0_plate_m60.py approval-template --root "$PAM4_C0_FORMAL_ROOT" \
  --approval "$PAM4_C0_PLATE_APPROVAL"
# 確認單案範圍符合 20261115T1700_user_approves_plate_m60.md 後，將 approved 改為 true。
/usr/bin/python3.11 -B c0_plate_m60.py stage --root "$PAM4_C0_FORMAL_ROOT" \
  --run-root "$PAM4_C0_PLATE_ROOT" --model-root "$PAM4_PDK_ROOT" \
  --approval "$PAM4_C0_PLATE_APPROVAL"
sbatch "$PAM4_C0_PLATE_PACKAGE/c0_plate_m60.sbatch"
```

approval 鎖定此包 manifest、此案 deck SHA、原 phase／code 選擇檔、原晚窗 rescore SHA 與核准的單案 run root。若 solver 成功但收集失敗，使用 `collect-only`，沿用上述 `--root`、`--run-root`、`--approval`。只重新整理現有量測則用 `summarize`。新案的 `c0_formal_plate_m60_summary.json` 包含 original 496／late 176 的 primary 與 secondary 配對、錯誤數、SER、RMSE、帶符號殘差、候選 raw hash 和實際 job ID。基準是原發表的同階段同窗口的碼 0，報差值為 −60 減去 0。

## 共同殘差的唯讀診斷

正式 C0 晚窗仍有約 +0.36 符號單位的偏移。零偏斜對照裡，均等加權四個真值階後仍約 +0.337／+0.338（primary／secondary）。實際標籤頻率只額外貢獻約 +0.029／+0.033，因此目前數字不支持單靠 payload 各階比例解釋共同偏移。

零偏斜 training 和 payload 的真實輸入有兩種不同初值。第一個符號的差動源電壓分別約 +66.7 mV、−200 mV。名目 10 pF／10 kΩ AC 耦合路徑的時間尺度為約 100 ns，長於本次 6.5 ns。這是初始電荷／OP 相依性的可檢驗假說。已存的 raw 可對照 driver 前 `PNC_PREP/PNC_PREN` 和 AFE 輸出 `X_o_p/X_o_m`，但 post-cap gate 和 Vb1 不在原存檔，不能由此直接量出內部偏置。

```bash
/usr/bin/python3.11 -B c0_plate_m60.py offset-audit --root "$PAM4_C0_FORMAL_ROOT"
```

此模式只讀零偏斜 training 及原 payload 的既有 raw，另輸出 `c0_formal_offset_audit.json`。同一 late window 重現 176 個 FFE 結果，列 held/quantized 均值、固定截距、tap 加權均值、真值階中殘差、標籤分布貢獻、ADC 量化貢獻，以及已存類比節點的兩段均值。偏移成因仍待讀回量測，正式 −60 配對不用 payload 訓練、重調 FFE 或扣除偏移。

GitHub 回饋僅放可分享的配對摘要與 job ID，Spectre deck、套件 ZIP、raw 和模型留在 Olympus／OneDrive。
