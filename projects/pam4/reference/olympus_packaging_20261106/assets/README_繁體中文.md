# ECEN 720 Project 6：Olympus 手動轉移包

本包整理自使用者自己的 Project 6 工作，提供給使用者自行上傳到 Olympus。它是**來源與歷史資料的封裝**：不會自行啟動 Virtuoso、Spectre、舊排程或模擬。

## 包含的內容

- `vm_project/p6_224g_lib/`：VM 中使用者建立的 Virtuoso OA 設計 library 快照，包括 CTLE、sampler 與部分 testbench。這不是完整 ADC 的證明；跨 IC618／IC231 開啟與 PCell 展開仍需實際檢查。
- `vm_project/scripts/`：VM 專案中的 Python、SKILL、OCEAN 和 shell 程式，按原內容保留。
- `vm_project/runs/` 和 `vm_project/simulations/`：歷史案例中的自寫 `.scs`、`.ocn`、`.il`，保留相對路徑。原本指向專案內其他案例的符號連結可能已在封裝時物化成普通檔案；詳細記錄見 `vm_project_snapshot_manifest.json`。
- `local_reference/`：本機 Project 6／MOS 自寫來源及先前已交付的 Project 6 數值摘要和圖。`project6_r5_handoff.json` 僅供歷史背景，其 IP、路徑、排程與授權描述可能已過期。
- `olympus/`：建立獨立 `cds.lib` 和準備新網表副本的輔助程式。兩者都不會啟動 GUI 或模擬。
- `MANIFEST.sha256`：每個檔案的 SHA-256，供上傳和解壓後核對。

封裝沒有納入 PDK、foundry 模型、原始波形／PSF、native card JSON、frozen detector／FFE 係數、decision TSV／ViVA XY、授權檔或 SSH 金鑰。VM 中的原始資料都沒有刪除或修改。這表示**部分歷史分析、固定係數驗證及相位眼圖不能只靠本包完整重現**。

## 1. 手動上傳與驗證

使用 MobaXterm 的 SFTP 將 ZIP 上傳到：

```text
~/ECEN720/
```

在 Olympus 終端機進入該目錄，先確認同名資料夾不存在，再使用 `unzip`。下方 ZIP 檔名以實際收到的檔案名稱為準：

```bash
cd "$HOME/ECEN720"
unzip -l Project6_ECEN720_Olympus_transfer_20261106.zip | head -30
unzip -n Project6_ECEN720_Olympus_transfer_20261106.zip
cd project6_olympus_transfer_20261106
sha256sum -c MANIFEST.sha256
```

檔案若已存在，`unzip -n` 會跳過既有檔案；核對失敗時先檢查，不要把舊檔當成新封裝。建議在 ECEN 720 計算節點進行後續 Cadence 操作。

## 2. 建立獨立的 library 參照

進入 `load-ecen-720` 計算節點，設定 IC231，並在本包根目錄執行：

```bash
source /opt/coe/cadence/IC231/setup.IC231.linux.bash
python3 olympus/create_cds_lib.py
```

預設 PDK 目錄為使用者先前在 Olympus 設定的 `$HOME/pdks/28nm/pdk_kit.0_2p2a_20160226_all/28nm_pdk`。不同位置可先設定 `PROJECT6_PDK_ROOT`。程式只建立 `olympus_workspace/cds.lib`；如果它已存在會拒絕覆寫。

之後可由使用者自行從 `olympus_workspace` 啟動 Virtuoso，並在 Library Manager 檢查 `p6_224g_lib`、`28nm` 的 cell 與 schematic。這是未在 Olympus 實測的移植步驟；原 VM 使用 IC618，Olympus 使用 IC231，PCell、CDF、technology 與模型版本差異都可能需要調整。

## 3. 檢查並準備歷史 Spectre 網表副本

歷史網表多數引用 `<PDK_ROOT>`，不能直接假設在 Olympus 可用。可先選一個本包 `vm_project/` 中的 `.scs` 檔，檢查已知路徑替換：

```bash
python3 olympus/prepare_spectre_deck.py \
  vm_project/runs/secondary_cap_validation_r7_20261022/noiseless_baseline_r5/bench.scs \
  --dry-run
```

確認輸出與 PDK 路徑後，移除 `--dry-run` 可在 `olympus_runs/prepared-*` 寫入一份新的 `input.scs` 和 `adaptation.json`。原始網表不會改動，程式**不會執行 Spectre**。若原網表有未映射的 VM 路徑、相對 include 或找不到的 include，它會停止並要求人工檢查。

轉換器只處理已知的兩個路徑前綴，並不檢查所有可能的模型依賴、外部激勵、工具選項或數值結果。某些歷史案例還引用另一個 LA5 專案的檔案；本包沒有包含該獨立專案。不要把路徑改完視為模擬、模型或晶片已驗證。

## 注意事項

- `vm_project/scripts/` 裡的舊排程、resume、重試、最佳化與訓練程式只作歷史來源；不要自行批次啟動或恢復它們。
- 每次執行新的電路分析前，先確認資源、模型版本、網表、結果位置與使用者意圖；切勿覆寫原案例。
- 先前 Spectre 測試報過 `scalefactor=0.9` 的重複設定警告；正式比較尺寸與電流前需依 PDK 確認。不可直接修改 foundry 模型消除警告。
- 數值 FFE、理想量化器和 reset 比較器不構成完整 7-bit、112 GS/s ADC 的證明；CDAC、參考、控制與相依判決仍需完整驗證。
