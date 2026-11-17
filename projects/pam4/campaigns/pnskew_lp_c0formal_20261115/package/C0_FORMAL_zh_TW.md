# ECEN 721 正式 C0：共同相位、端點選碼及獨立 payload

上一輪五案已證實在 TT 無雜訊條件下，固定端點碼使兩個偏斜方向的錯誤下降。這一包用實際 clock aperture 和接收端訓練誤差選設定，繼續用同一顆 gm-tap、r3、r5 與 COMMON64 控制字。第 0 案的舊 raw 退役後仍可執行本包。

| 階段 | Olympus 案數 | 擬合與判讀 |
| --- | ---: | --- |
| Phase | 3 | 零偏斜、碼 0，實際 clock delays 同步移 `0、−1/8、+1/8 UI`。每案在 TX `[128,384)` 選兩平面的整數 lag 並擬合 17-tap FFE。保留 64 個訓練間隔符號，使用 `[448,640)` 的 176 個 FFE 中心，以 primary 7-bit FFE 後、決策前 RMSE 選相位。 |
| Code | 6 | 同一相位、lag、理想 ADC 範圍、FFE。兩種偏斜各跑 `0、−60、+60`，都依 primary 在同一訓練窗的 RMSE 選碼。分數相同時按列出的候選順序取第一個。 |
| Payload | 3–5 | 另一組 PRNG 種子，跑零偏斜碼 0，再各做「碼 0／訓練選碼」配對。選碼等於 0 時重用同條件碼 0。每平面 512 個 ADC 輸入及 496 個 FFE 計分符號。 |

Phase 移動的是 8 組 primary 與 64 組 secondary 的 clock 和反相 clock，實體孔徑一起改變。每個相位分開校準 lag，可處理時鐘跨原符號索引的情形。相位與 FFE 鎖定後，沒有按碼變更相位、等化器或量化範圍。ADC full-scale 沿用 100／75 mVppd。

電路產生器將 profile `a` 與 `b` 分別注入 P 晚與 N 晚 4.464285714 ps。選碼函式收到兩組各三個候選的接收端分數，兩組使用同一套排序。這是對端點的三碼 acquisition screen。55 碼的靜態單調與 PVT 範圍繼續由 COMMON64 的 AC 結果提供。

Payload 結果分別列 primary／secondary 的錯誤數、SER、RMSE 與 clipping。如果兩個方向 primary 都減少錯誤，即在這次資料窗驗證了訓練後的端點補償；同為零錯時一起看 RMSE。某一方向不改善，先看選碼、共同相位與接收端分數，保留原配對。496 個無雜訊符號的結果用於這一階段的比較，作品集的 BER、噪聲與實體 ADC 指標仍需對應的量測。

## 資源與停止點

五案舊 C0 的 14 ns 運行經驗是單跑 2373 s、四案同時 3161–3221 s、每案約 69.4 MB raw。這批 6.5 ns 約 20–35 分鐘／案，raw 約 30–40 MB／案。預估最多 14 案、4.7–8.2 CPU-h、raw 約 0.42–0.56 GB；以最多兩案並行約 3–5 小時，另計排隊。

向 Slurm 申請 1 CPU／6 GiB／90 分鐘，classic `+mt=1`，solver timeout 4200 s。先單跑 phase index 0，用實際 walltime、sample coverage 和 raw 大小更新估計。上一輪最慢只剩 79 s，本包新增餘裕給 solver 和收集。若後續 C1／C2 加長窗口，按首案每 ns 實測時間另算 timeout 和 quota。C1／C2 由使用者另外決定是否提交。

每個案子碼固定在 t=0，所有 fit 和 score 都在 warmup 之後。套件支援已完成 Spectre 而未收集的 `collect-only`。保留原始執行紀錄和量測；raw 依既有量測核對、提交與退役規則處理。

## 上機

指向新正式 C0 解壓目錄、先前兩個 C0 package、原 SWITCH64 與 COMP 依賴，以及原 private-kit。用新的 run root，保留原批准文件供舊五案稽核。

```bash
export PAM4_C0_FORMAL_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_C0_FORMAL_20261115'
export PAM4_C0_ALIGN_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_C0_ALIGN_20261115'
export PAM4_C0_ORIGINAL_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_C0_RUN_20261115'
export PAM4_C0_SWITCH_PACKAGE='/absolute/path/PAM4_PNSKEW_LP_GMTAP_SWITCH64_ENDPOINT_COLLECT_FIX_20261115'
export PAM4_C0_R5_ORIGINAL='/absolute/path/PAM4_PNSKEW_COMP_20261113/r5_original'
export PAM4_PDK_ROOT="$HOME/ecen720_28nm/tools/local_replay_migration_20261108/private_models/r7_vm_shrink"
export PAM4_C0_FORMAL_ROOT="$HOME/ecen720_28nm/runs/pam4_c0_formal_20261115"
export PAM4_C0_FORMAL_APPROVAL='/absolute/path/c0_formal_approval.json'
mkdir -- "$PAM4_C0_FORMAL_ROOT"
cd "$PAM4_C0_FORMAL_PACKAGE"
sha256sum --check SHA256SUMS.txt
/usr/bin/python3.11 -B c0_formal.py verify
/usr/bin/python3.11 -B -m unittest discover -v
sha256sum SHA256SUMS.txt
```

用 `approval_TEMPLATE.json` 產生外部 approval，將上方輸出的 manifest SHA 填入 `design_source_sha256`。依既有授權範圍記錄 `authorization_basis`，符合時將 `approved` 設為 `true`。舊 approval 綁的是固定碼五案，這包使用獨立 manifest SHA。

各批收集完成後再執行相應 `select`，其輸出包含控制設定和來源 SHA。以下 `list` 顯示實際索引、case ID、SHA。

```bash
/usr/bin/python3.11 -B c0_formal.py list --stage phase --root "$PAM4_C0_FORMAL_ROOT"
PAM4_C0_STAGE=phase sbatch --export=ALL --array=0 c0_formal.sbatch
```

第 0 案查看 `measurements.json` 的 clock audit、兩平面 lag／Pearson、fit 和 verify 讀取區間、176 個 FFE 中心。首案確認後提交剩下兩個相位。三案完成後，選共同相位並列出 code 批。

```bash
PAM4_C0_STAGE=phase sbatch --export=ALL --array=1-2%2 c0_formal.sbatch
# Wait for the two phase trials to finish.
/usr/bin/python3.11 -B c0_formal.py select-phase --root "$PAM4_C0_FORMAL_ROOT"
/usr/bin/python3.11 -B c0_formal.py list --stage code --root "$PAM4_C0_FORMAL_ROOT"
PAM4_C0_STAGE=code sbatch --export=ALL --array=0-5%2 c0_formal.sbatch
# Wait for all six code trials to finish.
/usr/bin/python3.11 -B c0_formal.py select-codes --root "$PAM4_C0_FORMAL_ROOT"
/usr/bin/python3.11 -B c0_formal.py list --stage payload --root "$PAM4_C0_FORMAL_ROOT"
```

依 payload `list` 的最大索引形成 array。例：兩個 profile 都選到非零碼時為 `0-4%2`。

```bash
PAM4_C0_STAGE=payload sbatch --export=ALL --array=0-4%2 c0_formal.sbatch
# Wait for all listed payload trials to finish.
/usr/bin/python3.11 -B c0_formal.py summarize --root "$PAM4_C0_FORMAL_ROOT"
```

若已有完整的新 Spectre 產出，對應 stage 和 index 可直接補收。例如第一個 phase 案如下。

```bash
/usr/bin/python3.11 -B c0_formal.py collect-only --stage phase --index 0 --root "$PAM4_C0_FORMAL_ROOT"
```

摘要寫入 `c0_formal_summary.json`，並保留 `selected_phase.json`、`selected_codes.json`、各案 `measurements.json` 和原始 run status。所有成對結果須用同一份相位與選碼檔案的雜湊，才會進摘要。
