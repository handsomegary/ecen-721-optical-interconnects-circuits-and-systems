# ECEN 721 Optical Interconnects Circuits and Systems

Texas A&M ECEN 721 課程專案，作為作品集持續補完。每個專案放在 `projects/` 下各自的目錄，包含 Spectre 網表、案例設定、OCEAN 讀取腳本與 Slurm 範例；PDK 與模型不在 repo 內。

| 課程專案 | 目錄 | 目前狀態 |
| --- | --- | --- |
| Project #6：224 Gb/s ADC-Based Receiver Front-End with Differential PN Skew Compensation（28nm ） | [projects/pam4](projects/pam4/) | AFE peaking 在 TT 達標；TI-ADC 與 PN skew 補償未完成 |

歷史交接：[2026-11-06 project checkpoint](PROJECT_CHECKPOINT_20261106.md)。歷史來源和工具供保存與檢視，不得自動重啟舊排程或重試失敗模擬。

`projects/pam4/netlists/` 是設計輸入。每份網表只替換了原本的 PDK 根目錄，電路、分析、刺激和元件尺寸照原始輸入保存。`SOURCE_PROVENANCE.json` 記錄原始網表與範本的 SHA-256。執行需要已安裝且有權使用的 28nm PDK、Cadence IC231、Spectre 與 Python 3.8 以上。

## PAM4 最新交接

在 `main` 上先看 [PAM4 交接區](projects/pam4/handoff/)。Codex 的交件在 [to_claude](projects/pam4/handoff/to_claude/)，Claude 的執行回饋在 [to_codex](projects/pam4/handoff/to_codex/)。交件附套件、SHA、上機說明和本批建議範圍。

## 在 Olympus 準備並提交

登入後依課程流程取得 Slurm 環境。在 repo 根目錄，先設定自己已安裝的 PDK 根目錄。它應有 `models/spectre/` 子目錄。

```bash
export PROJECT6_PDK_ROOT="$HOME/pdks/28nm/pdk_kit.0_2p2a_20160226_all/28nm_pdk"
repo="$PWD"
```

逐行執行，`prepare_deck.py` 會檢查案例雜湊與模型 include，寫入新的模擬目錄。以下為短測。

```bash
export PROJECT_BUNDLE_ROOT="$repo/projects/pam4"
run_dir="$(mktemp -d "$HOME/PAM4/pam4_candidate.XXXXXXXX")"
python3 "$PROJECT_BUNDLE_ROOT/olympus/prepare_deck.py" --case candidate --mode smoke --output "$run_dir/input.scs"
cd "$run_dir"
sbatch "$PROJECT_BUNDLE_ROOT/olympus/background_example.sbatch"
```

要準備完整 PAM4 網表，改用 `--mode full`。提交後可斷開連線，用該次回傳的 Job ID 查狀態。

```bash
squeue -j <JOB_ID>
sacct -X -j <JOB_ID> --format=JobID,State,ExitCode,Elapsed,NodeList
```

較長的 transient 量測用以下命令準備。它會產生獨立的 `input.scs`、SKILL 量測設定、OCEAN 腳本和 Slurm 腳本。準備完進入顯示的 `RUN_DIR`，執行 `sbatch run_long.sbatch`。

```bash
cd "$repo"
python3 tools/long-jobs/prepare_long_run.py pam4
```

確認 Slurm 為 `COMPLETED 0:0`，並檢查 `ocean_read.log` 的 `ECEN720_MEASURE_PASS` 與 `measurements.csv`。批次腳本先載入 IC231 環境，再把 Spectre 執行檔加到 `PATH`。這個順序保留 IC231 的 OpenAccess 程式庫，避免混載 Spectre 環境時遇到的符號載入錯誤。

## 來源與可重現範圍

- `projects/pam4/reference/source_snapshot/` 保存歷史 Python、SKILL、OCEAN 原始碼。部分歷史流程需要本機 OA library、凍結資料或其他專案檔案。已有 OA library 時可設定 `ECEN720_OA_LIBRARY_DIR`（沿用的程式變數名），再使用該專案的 `create_cds_lib.py`。
- `projects/pam4/reference/independent_validation_summary.json` 保存先前四案的派生規格與摘要。短測與長測腳本讀取訊號樣本，獨立 FFE 比較是另一個已完成的流程。PAM4 前端使用理想數值量化器與固定數值 FFE，完整 ADC 仍待驗證。
- [PAM4 benchmark](tools/pam4-benchmark/) 可用同一份完整 `baseline_noise` 網表比較 APS 執行時間。環境與既有測量記在[工作站筆記](https://github.com/<owner>/olympus-cadence-ocean-analog-notes/blob/main/docs/pam4-aps-benchmark.md)。

PDK、模型、獨立的 native-card 資料、固定 detector 係數、OA 資料庫、原始波形與機器憑證均由各環境自行管理。
