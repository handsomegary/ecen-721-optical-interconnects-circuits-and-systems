# C0 五案固定碼診斷：Olympus 執行交接

這包把已逐位元核對的五份 C0 deck 補成可執行套件。deck、刺激、凍結 r5 量化器與 FFE 均不變。依既有授權先做五個固定碼診斷；這輪不訓練、不選共同相位，也不宣稱已完成不依賴真實 skew 的自動校正。±60 是預設診斷碼，不是訓練得出的控制碼。

不需要已刪除的 SWITCH64 84／86 raw。前次實檔復原與 summary 已完成，這次從 C0 第 0 案檢查新增的取樣／計分流程。

| index | case | PN skew | 固定碼 |
| --- | --- | ---: | ---: |
| 0 | c0_00_tt_zero | 0 | 0 |
| 1 | c0_01_tt_p_late_code0 | +4.464285714 ps | 0 |
| 2 | c0_02_tt_p_late_preset | +4.464285714 ps | −60 |
| 3 | c0_03_tt_n_late_code0 | −4.464285714 ps | 0 |
| 4 | c0_04_tt_n_late_preset | −4.464285714 ps | +60 |

## 執行範圍與資源

每案 classic Spectre 23.1、`+mt=1`，Slurm 1 CPU／6 GiB／60 分鐘；solver timeout 3300 秒，保留時間給收集。估計每案 20–45 分鐘、raw 約 65–115 MiB；五案總計約 2–4 CPU-h、raw 小於 600 MiB。這是估計，完成後用 summary 的 `resources` 實測 wall time、峰值 RSS、raw bytes 更新。

五案均為 TT、無 transient noise、14 ns，控制碼從 t=0 固定，並無中途切碼。payload 起點約 10.485714 ns，取 256 個輸入符號、17-tap FFE 後各端計 240 個符號；保留歷史凍結相位和 FFE，不在驗證窗擬合。之後若加入切碼，切碼後至少排除 3 ns；本包不另加切碼。

## 既有依賴與路徑

以下路徑須由 Olympus 執行者填入實際絕對路徑。沿用已安裝並驗證的 Spectre 與私有模型，不搬移 PDK，也不更動原依賴套件。`PAM4_C0_RUN_ROOT` 必須是 `~/ecen720_28nm/runs` 下已建立的獨立真實目錄，不能是 symlink；先確認 filesystem 與 quota 的可用空間，runner 要求至少 2 GiB filesystem free。

```bash
export PAM4_C0_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_C0_RUN_20261115'
export PAM4_C0_SWITCH_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_SWITCH64_ENDPOINT_COLLECT_FIX_20261115'
export PAM4_C0_R5_ORIGINAL='/absolute/path/PAM4_PNSKEW_COMP_20261113/r5_original'
export PAM4_PDK_ROOT="$HOME/ecen720_28nm/tools/local_replay_migration_20261108/private_models/r7_vm_shrink"
export PAM4_C0_RUN_ROOT="$HOME/ecen720_28nm/runs/pam4_c0_fixed_20261115"
export PAM4_C0_APPROVAL='/absolute/path/approved/project/c0_approval.json'
export SPECTRE_DEFAULTS=-E
# 新 campaign 第一次建立；不要重用不同批次的目錄。
mkdir -- "$PAM4_C0_RUN_ROOT"
```

SWITCH64 依賴為最後 collect-fix 版（ZIP SHA 前綴 `94aff417`），其 `SHA256SUMS.txt` SHA 必須是 `55d13973cf50c19cb281582bf9132e8cf7dea166895f30bb57659e186c1ed683`。r5 `frozen.json` SHA 必須是 `4cda4c9ec967f2af4bf4f89eacdd1beae372668877c358cf6aa26092597482eb`，並核對原 `quiet.scs` 與 `source_dir`。模型只做可逆根目錄替換，私有 preflight 核對 TT 與 shrink；不可移除 shrink 或改模型。

## 核對、批准與預先 stage

```bash
cd "$PAM4_C0_PACKAGE"
sha256sum --check SHA256SUMS.txt
/usr/bin/python3.11 -B c0_run.py --mode verify
/usr/bin/python3.11 -B -m unittest discover -v
```

`approval_TEMPLATE.json` 的 `approved` 刻意保留 `false`。下面只填入本包 plan 與 manifest 的精確 SHA，產生外部 approval 檔，不會自動批准，也不修改套件檔案。執行者確認現有常態授權確實涵蓋這五案後，才可在外部 approval 以 Python 將 `approved` 設為 `true`，並留下授權依據；如果現有授權不涵蓋，則等待使用者確認。不可冒稱使用者已批准。

```bash
/usr/bin/python3.11 - <<'PY'
import hashlib, json, os
from pathlib import Path
p = Path(os.environ['PAM4_C0_PACKAGE'])
a = json.loads((p/'approval_TEMPLATE.json').read_text())
a['plan_sha256'] = hashlib.sha256((p/'c0_review_plan.json').read_bytes()).hexdigest()
a['design_source_sha256'] = hashlib.sha256((p/'SHA256SUMS.txt').read_bytes()).hexdigest()
with Path(os.environ['PAM4_C0_APPROVAL']).open('x', encoding='utf-8') as f:
    json.dump(a, f, indent=2)
    f.write('\n')
PY
```

approval 必須綁本包 SHA、`stages=["c0_fixed"]` 與明列的五案，`retire_new_raw=false`。變更 source、plan 或 manifest 都需要重核對綁定，不能沿用舊 approval。

可先 stage 五案，確認私有路徑替換；這一步不呼叫 Spectre。隨後 `run` 可沿用同一 stage，逐位元一致才繼續，不覆寫不同的舊 stage：

```bash
/usr/bin/python3.11 -B "$PAM4_C0_PACKAGE/c0_run.py" --mode stage \
  --root "$PAM4_C0_RUN_ROOT" --model-root "$PAM4_PDK_ROOT" \
  --index 0 --index 1 --index 2 --index 3 --index 4
```

## 首案與其餘四案

在既有 Olympus 排程設定下先送 index 0。必要的 account／partition／QOS 使用現有授權值；不要猜值。

```bash
sbatch --export=ALL --array=0 "$PAM4_C0_PACKAGE/c0_classic.sbatch"
```

第 0 案完成後核對 `run_status.json`、`measurements.json`、`recovery.json`、`completion.json`。Spectre exit 0 本身不足以視為成功；runner 也核對完成時間、classic log、FATAL／漏存訊號、raw SHA、時鐘及來源。

保留第一案 raw，確認 `clock_audit` 與 178 個必要 trace、8 相時鐘、primary／secondary 各 256 個 ADC 輸入及 240 個 FFE 計分符號；`validation_fitting_performed` 必須為 `false`。獨立核對第一案計分窗與幾個樣本後再展開其餘四案。若首案資料不完整或計分異常，停下診斷，不將缺量當作通過。

```bash
sbatch --export=ALL --array=1-4%4 "$PAM4_C0_PACKAGE/c0_classic.sbatch"
```

## 只收集與彙整

若 Spectre 已完整完成而收集失敗，保留原目錄並使用 `collect-only`；它不啟動 solver，不改原 execution intent／run status，不需要 Slurm array 主 ID。執行證據使用每案實際 task job ID；搬移後會重新核對本機檔案身分與原大小／SHA，沒有寫死跨主機 device number。

```bash
/usr/bin/python3.11 -B "$PAM4_C0_PACKAGE/c0_run.py" --mode collect-only \
  --root "$PAM4_C0_RUN_ROOT" --approval "$PAM4_C0_APPROVAL" --index 0
```

可重複 `--index` 收多案；已完整收集且所有收據一致時回報 `already_collected`。未完整的 solver 紀錄不會被自動覆寫或重跑，先診斷原因。收集採原套件的原子發布，保留量測與來源收據。

五案全部完成後寫入一個新的 summary 路徑：

```bash
/usr/bin/python3.11 -B "$PAM4_C0_PACKAGE/c0_run.py" --mode summarize \
  --root "$PAM4_C0_RUN_ROOT" --output "$PAM4_C0_RUN_ROOT/c0_fixed_summary.json"
```

summary 驗證執行及收集來源鏈，列出 primary／secondary 的 SER、符號錯誤、Gray bit errors、RMSE，以及 P-late／N-late 補償前後 `paired_delta_SER`（負值代表改善）。`status=fixed_endpoint_diagnostic` 只表示五案固定碼診斷；不等同正式訓練校正、BER 驗證或 C1／C2 放行。不可從 240 個符號零錯誤推論低 BER。

這包不會刪 raw。尤其第一案 raw 要留到計分核對完成、量測及來源 commit 之後，再依既有清理規則處理，保留摘要和清理收據。程式開發端未在本機啟動 Spectre，也未提交 Olympus 工作；本地測試使用受控 solver stub 與原生格式的測試波形驗證執行→收集→summary，不宣稱為新的電路模擬證據。
