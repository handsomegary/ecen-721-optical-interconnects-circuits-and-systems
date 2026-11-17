# ECEN 721 SAR7 · 一輪 CDAC span／比例修正

本包依 20261116T0005_user_authorizes_sar7_cdac_fix.md 記載的新授權「Authorize CDAC fix」，只執行本輪最多兩個固定短案。11/15 的委派時窗已結束；本次是新的有界單輪，不沿用已過期的 21:45:37 截止，也不開放無限背景迭代。不包含 C1／C2、全 PVT、1.75 GS/s 正式驗證、其他專案或刪除 raw。

## 既有證據與設計

760348 的有效 span 是 113.918／127 LSB，錯碼 10／12、Σ|Δcode| 23、max 5；實體感測已隔離共模負載，未解析 bit 為零。本包保留該 CML＋250 Ω source bridge、12 個原碼、來源／供應／偏壓、取樣開關、1,080 ps 週期、60／60 ps 以及 1030 ps final read。

| index | case | 變動 | Reference span |
| --- | --- | --- | --- |
| 0 | sar7_08_tt_cml_common_ref | 只改共同差動 Vref；全部電容不變 | 63.74673330525213 mV |
| 1（有條件） | sar7_09_tt_cml_main_ratio | 主陣列比例、bridge 與其 shunt；低位與 dummy 不變 | 63.74163008917902 mV |

首案 Vref 倍率為 127／113.9181872663＝1.11483515537。第二案主陣列 b6→b3 改為 8.14714044、3.88717554、1.94505875、1.02062527 units，總量仍是 15；各支 Cunit／Ctop／Cbott 一起同比例調整。Bridge 及兩個 bridge shunt 同乘 0.927941320376，使名義低／主單位耦合為 1／8。依雙節點電荷矩陣與描述性固定負載估值調共同 Vref。修正向量全部凍結在 PLAN.json，不能在執行端另調。

這仍是既有線性 MOM 等效模型的慢速診斷，不是實際 MOM 版圖／PDK 幾何驗證。推導的固定負載約 3.195 fF 只是一個 surrogate，不是已辨識的實測寄生。保持低位電容不變可避免以小樣本逐位過度校正。

## 離線推估與限制

`planning.py` 只讀包內去識別的原 summary／audit 指標，並核對原完整 SHA。它用既有 84 個比較前 hold 值及實際已接受的高位前綴推估各轉換的等效取樣輸入；這不是直接的 sample 測量，沒有重新擬合原 raw，也沒有修改原計分。

`PREDICTION.json` 的零門檻 affine 模型預估首案 Σ6／max1，第二案 Σ3／max1。預估不是新模擬結果。原模型只能逐碼重現 4／12，與實測碼最多差 2；原 pre_s hold 符號和最後 bit 只有 75／84 一致。原留一 RMSE 0.861 LSB、取樣誤差最高 1.595 LSB，且 MOS 電壓相依與新路徑 settling 變化未辨識。因此不能宣稱錯碼全由 CDAC 造成，也不能保證達標。感測級零交越不是 comparator offset；planner 的門檻變體只是敏感度檢查，不用來校正電路。

## Olympus 準備與完整性

上傳 ZIP／sidecar 到既有核准 Olympus 位置。沿用 760348 wrapper 的 SAR7／relaxed／CML_RDEG 與既有私有模型環境；PAM4_SAR7_CML_RDEG_PACKAGE 必須仍指向原 760348 套件，不是新包。無需引入新的模型、修改原套件或重新執行舊案。

```bash
export PAM4_SAR7_CDAC_FIX_PACKAGE='/absolute/path/PAM4_SAR7_CDAC_FIX_20261116'
export PAM4_SAR7_CDAC_FIX_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_cdac_fix_20261116.XXXXXX")"
export PAM4_SAR7_CDAC_FIX_APPROVAL="$PAM4_SAR7_CDAC_FIX_ROOT/approval.json"
cd "$PAM4_SAR7_CDAC_FIX_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_cdac_fix.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B planning.py --output "$PAM4_SAR7_CDAC_FIX_ROOT/prediction_check.json"
cmp PREDICTION.json "$PAM4_SAR7_CDAC_FIX_ROOT/prediction_check.json"
/usr/bin/python3.11 -B sar7_cdac_fix.py approval-template \
  --root "$PAM4_SAR7_CDAC_FIX_ROOT" --approval "$PAM4_SAR7_CDAC_FIX_APPROVAL"
```

核對 approval 綁定新 root、兩個固定 case IDs、manifest SHA 與每案 portable SHA。依本次已授權範圍，只將 `approved` 改為 true；不能增加欄位或放寬 case 清單。模板容許第二案不代表可跳過 gate。ZIP／manifest／verify／測試／預測重現若失敗，停下回報，不能修改證據或重跑避過。

## 先執行 index 0

```bash
/usr/bin/python3.11 -B sar7_cdac_fix.py stage --index 0 \
  --root "$PAM4_SAR7_CDAC_FIX_ROOT" --approval "$PAM4_SAR7_CDAC_FIX_APPROVAL" \
  --model-root "$PAM4_PDK_ROOT"
sbatch --export=ALL --output="$PAM4_SAR7_CDAC_FIX_ROOT/case0-%j.out" \
  "$PAM4_SAR7_CDAC_FIX_PACKAGE/sar7_cdac_fix.sbatch" 0
```

stage 後對 760348 的 portable 差異必須是兩條共同參考 source，沒有其他變動。先等該 job 結束；不要送 array，不要預先 stage／送 index 1。每案 1 CPU／6 GiB／Slurm 10 分鐘，solver 上限 540 秒，預估 3–6 分鐘與 raw 80–110 MB。最多並行一案、最多兩個新 solver，遠低於共用 QOS 6 CPU 上限；不碰其他對話的 job。

正常 run 會產生每案 `sar7_cdac_fix_summary.json` 與 SHA record。若 solver 已完成但後處理中斷，可對同一案用 `collect-only`，不得重新送 solver。然後執行：

```bash
/usr/bin/python3.11 -B sar7_cdac_fix.py gate --root "$PAM4_SAR7_CDAC_FIX_ROOT"
```

Gate 會從既有 measurements、run status、raw 和 summary SHA 重建驗證，不接受手寫 gate。所有 84 個 bit 必須解析、12 個 comparator／registered 都可讀且一致，末端 CDAC 共模下降絕對值不超過 10 mV，才算有效。

| recommendation | 執行端動作 |
| --- | --- |
| STOP_TARGET | max≤1 LSB，停止並回報，不能送 index 1 |
| STOP_CONVERGED | max≤2 且 Σ≤8，已明顯收斂；停止並如實報尚未達 max≤1 |
| ALLOW_INDEX1 | 有效但尚未收斂，且不劣於原 Σ23／max5；才可執行唯一第二案 |
| STOP_REVIEW | 缺資料、未解析、新失敗、失去隔離或誤差惡化；停下回報，不自行救火 |

## 唯一條件式第二案

只有 `ALLOW_INDEX1` 才執行以下步驟；stage 和 run 都會再驗證 gate，且保存來源 summary／raw／manifest SHA。若前案已收斂，程式會拒絕第二案。

```bash
/usr/bin/python3.11 -B sar7_cdac_fix.py stage --index 1 \
  --root "$PAM4_SAR7_CDAC_FIX_ROOT" --approval "$PAM4_SAR7_CDAC_FIX_APPROVAL" \
  --model-root "$PAM4_PDK_ROOT"
sbatch --export=ALL --output="$PAM4_SAR7_CDAC_FIX_ROOT/case1-%j.out" \
  "$PAM4_SAR7_CDAC_FIX_PACKAGE/sar7_cdac_fix.sbatch" 1
```

對 760348 的差異應為兩條共同 Vref 與 PLAN 指定的 30 條電容值；兩側鏡像，高四位總電容不變，低位與 dummy 不變，時序與 scoring 不變。第二案結束後本輪一定停止，不論是否達標，不追加第三案或重新調值。

## 本機結果與保存

回 outbox 報每個實際執行 case 的 job ID、完整 summary／measurements／tran SHA、兩種碼的錯碼數／Σ／max、84-bit unresolved、registered 一致性、sample error、解析時間、共模下降、sense gain／符號／電流、solver／raw 大小，以及首案 gate 和第二案有無執行。保留新舊 raw；沒有執行的 case 標 skipped，不填預測當實測。回報目標和明顯收斂要分開，不能宣稱 1.75 GS/s 或完整 ADC 驗證通過。

通道維持本機 inbox／outbox，不使用 codex queue，不啟用 archived steering command，transcript monitor 僅唯讀。Claude 單獨操作 repo；只存無 deck 的程式、去識別摘要和 handoff。ZIP、deck、私有模型與 raw 留核准 OneDrive／Olympus，不放 GitHub、回報文字或其他服務。
