Stage: SAR7 CDAC span／比例修正 pilot（TT）— 回覆 inbox 20261116T0019_sar7_cdac_fix_pilot.md
Status: needs_user
Decision: STOP（完整性前置檢查 `cmp PREDICTION.json prediction_check.json` 不一致；依 Guide 停下，未 stage、未送任何 solver）
Summary: 差異只在 8 個浮點數最後一位（≤7e-15），來源是 Olympus /usr/bin/python3.11 與本機 Python 3.14 的 statistics.mean／pstdev 實作差異；PLAN 修正向量與兩案 deck SHA 不受影響
Run paths: ~/ecen720_28nm/runs/pam4_sar7_cdac_fix_20261116.zN5rXs（無 job）
Commit: 見下方（handoff + 前置檢查紀錄）
Needs user decision: yes: 是否接受這個 Python 版本造成的最後一位浮點差異，照原包直接執行 index 0（A），或請 Codex 重新凍結 PREDICTION／放寬比對後重新交件（B）

## 已完成（全部通過）
- ZIP SHA-256 8e290b0e44137488c27a3631e1246453f654ef345bb0fed3c090618cc922a9e7 與 header、sidecar 一致（本機與 Olympus 都核對）。
- 上傳到新的 mktemp run root `~/ecen720_28nm/runs/pam4_sar7_cdac_fix_20261116.zN5rXs`，解壓 `PAM4_SAR7_CDAC_FIX_20261116/`。
- `sha256sum -c SHA256SUMS.txt`：9/9 OK；SHA256SUMS.txt 本身 = bb97b973…5153（= header manifest SHA）。
- `sar7_cdac_fix.py verify`：index0 portable 0103266a…6368、index1 f2231b54…6153，與 header 一致。
- `unittest discover`：7/7 OK。
- `approval-template`：產生 approval.json，綁定新 root、兩個 case IDs、manifest SHA 及兩案 deck SHA；**仍為 approved=false**（因下一項失敗，未改成 true）。
- Wrapper 環境：`wrappers/env_cdacfix.sh` 沿用 760348 的 env，`PAM4_SAR7_CML_RDEG_PACKAGE` 指向原 760348 套件，新增 CDAC_FIX_PACKAGE／ROOT／APPROVAL。尚未建立 sbatch wrapper、未 stage、未 sbatch。

## 失敗項目：planner 預估重現
`/usr/bin/python3.11 -B planning.py --output $ROOT/prediction_check.json` 成功（rc 0），但 `cmp` 不一致：
- PREDICTION.json（包內）SHA 614dfd90d74d1d852d961ef03a50bfb65730983a04e37e6e66030e3ffdab11bf
- prediction_check.json（Olympus）SHA 17c2e8299003eb264b1ad437ede815aada96ae6a593e34ac03d4b01e7019b59c
- 檔案大小相同 36,439 bytes；diff 只有 8 行，全部是最後一位 ULP：
  - intercept_std_lsb 0.8061139336235399 → …398；0.8036284423627775 → …774
  - intercept_lsb 58.36472938281774 → …775；57.72098755794589 → 57.7209875579459
  - trajectory_residual_lsb -0.1395545186437559 → …7488；-0.1388032754847046 → …6975
  - predicted_span_lsb 127.00000000000001 → 127.00000000000003；offset_lsb 63.6622474227485 → 63.66224742274851
- 唯讀診斷：
  - 本機以 Python 3.14.4（`python -I -B planning.py`）重跑，與包內 PREDICTION.json **逐位元組相同**；Olympus 是 Python 3.11.13（無 numpy）。planning.py 只用標準庫，差異集中在 `statistics.mean`／`statistics.pstdev`，這兩個函式在 3.11 與 3.12+ 的累加實作不同。
  - 兩個 Vref span（63.74673330525213、63.74163008917902 mV）與 30 條電容值都不在 diff 中；`sar7_cdac_fix.py` 不讀 PREDICTION.json，gate 也不依賴它。verify 的 deck SHA 已與 header 一致。
  - 所以差異不影響要模擬的電路，但 Guide 明定「預測重現若失敗，停下回報，不能修改證據或重跑避過」，所以我停下，沒有修改任何檔案。

## 給使用者的選項
- **A（建議）**：認定這是 Python 3.11／3.14 的浮點最後一位差異、不影響 PLAN／deck／gate，照原包執行：approval 改 approved=true → stage index 0 → 送 1 案（1 CPU／6 GiB／10 min）→ gate，只有 ALLOW_INDEX1 才送 index 1。
- **B**：請 Codex 改成以 Olympus python3.11 凍結 PREDICTION.json，或在比對時對浮點數用容差，重新交新 ZIP，我再從頭驗證後執行。

## 保存
新 root 內只有 ZIP／sidecar、解壓套件、approval.json（approved=false）、prediction_check.json、wrappers/env_cdacfix.sh。沒有 raw；舊 raw 全部保留。未喚醒 Codex（此訊息仍等使用者決定）。
