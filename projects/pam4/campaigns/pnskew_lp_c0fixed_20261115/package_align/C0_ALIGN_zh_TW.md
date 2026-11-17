# ECEN 721 C0 第 0 案重計分與其餘四案

此包接續已在 Olympus 執行的 C0 原包 `05ec8f03…`，使用同一個 run root、五份 deck、Spectre classic 設定與既有 approval。第 0 案直接讀 job `757899` 保留的 PSF。新分數寫入每案的 `c0_aligned_measurements.json`，其中含原輸出身分與校準雜湊。原 `measurements.json`、`recovery.json`、`completion.json` 和 PSF 都保留。

## 對齊與極性

第 0 案的 173／240（primary raw FFE）、174／240（primary ideal 7-bit + FFE）和 175／240（secondary 兩者）是舊計分。原回饋的相關峰 lag 3、`r=+0.753／−0.735` 使用較長診斷窗。本包把那些實測數字保留在 `CASE0_OBSERVED.json`，供核對舊分數與極性。實際設定由前段資料重新計算。

Primary 與 secondary 都用 P−N 讀出。C0 的 shared launch 與 tap 輸入級各反相一次，r3 第二級用交叉 gate 維持該方向。Secondary 的 `B0_Fp/B0_Fm` 是同側驅動的 NMOS 共源電阻負載，後面的 TG 也同側接線，所以 secondary 預期是負相關。原版 r5 也用這個共源級，歷史門檻 `polarity=-1`。保留 native P−N，讓新擬合的 detector 處理符號。相關峰是樣本索引，舊 FFE 的 tap 也吸收了部分延遲，不能從兩個 lag 直接算出物理群延遲差。

只使用第 0 案零 skew、碼 0 的 TX 索引 `[128,1088)`，每平面掃 `−6…39` 的整數 lag，以最大絕對 Pearson 相關選 lag，另外核對預期符號。讀樣時間需早於 payload 起點約 10.485714 ns。對選定 lag 擬合原 17-tap ridge FFE 和三門檻 detector。全五案共用同一份校準，理想 ADC 的 full-scale 沿用 primary 100 mVppd、secondary 75 mVppd。共同時鐘相位沿用網表設定。

計分仍使用 TX `[1152,1408)`，每平面 256 個 ADC 輸入與 240 個 FFE 中心 `[1160,1400)`。原始 payload 曾供故障診斷，這次是訓練與計分分開的回溯試驗。固定端點碼仍供電路比較，正式接收端選碼或相位訓練需做獨立驗證。

## Olympus 指令

把 ZIP 解壓至獨立目錄。將 `PAM4_C0_ORIGINAL_PACKAGE` 指向先前的原包，`PAM4_C0_RUN_ROOT` 指向包含 job 757899 第 0 案及 stage 1–4 的實際目錄。保留之前使用的 `PAM4_C0_SWITCH_PACKAGE`、`PAM4_C0_R5_ORIGINAL`、`PAM4_PDK_ROOT` 和 `PAM4_C0_APPROVAL`。

```bash
export PAM4_C0_ALIGN_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_C0_ALIGN_20261115'
export PAM4_C0_ORIGINAL_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_C0_RUN_20261115'
export PAM4_C0_RUN_ROOT='/absolute/path/to/existing/run/root'
cd "$PAM4_C0_ALIGN_PACKAGE"
sha256sum --check SHA256SUMS.txt
/usr/bin/python3.11 -B c0_rescore.py --mode verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B c0_rescore.py --mode collect-only --root "$PAM4_C0_RUN_ROOT" --index 0
```

先看 `c0_00_tt_zero/c0_aligned_measurements.json` 的兩個 lag、相關值、極性、clipping、SER 和 RMSE。以 primary ideal 7-bit + FFE 的分數判斷是否已離開亂猜區間，建議把 `SER≤0.65`（≤156／240）當本次 pilot 的人工續跑參考，同時回報 secondary。這是此輪排程判斷，課程與作品集仍沿用既有驗收口徑。如果 primary 仍在原本約 0.72 附近，先把兩端新舊分數、lag、相關和 clipping 回報。可重複 `collect-only` 讀取同一份已封存量測。

確認首案後，依原五案授權送 1–4。這支 sbatch 沿用原包 runner 產生原生執行紀錄，接著套用第 0 案校準。每案 1 CPU／6 GiB／60 分鐘。先例為 39.5 分鐘、峰值約 283 MB、raw 約 69.4 MB，四案並行的執行時間可用約 40 分鐘估計，另計 queue。

```bash
sbatch --export=ALL --array=1-4%4 "$PAM4_C0_ALIGN_PACKAGE/c0_aligned.sbatch"
```

若 Spectre 完成、後段收集失敗，對該案直接跑 `collect-only`。四案都有新量測後，合併寫到新的摘要檔。

```bash
/usr/bin/python3.11 -B c0_rescore.py --mode summarize --root "$PAM4_C0_RUN_ROOT" \
  --output "$PAM4_C0_RUN_ROOT/c0_aligned_summary.json"
```

本地測試採用回饋中的舊錯誤數、job ID 與相關方向作 fixture，另以合成波形測試重訓與 payload 隔離。新的 Olympus SER 由上面的實檔重計分產生。
