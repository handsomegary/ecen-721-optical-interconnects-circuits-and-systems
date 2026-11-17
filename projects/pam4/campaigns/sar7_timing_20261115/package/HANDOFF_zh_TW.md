# ECEN 721 SAR7 · 單案比較器時序

## 問題與本案範圍

原 TT pilot（job 759069）在 25 ps 比較窗有 12／12 筆轉換含未解析 bit，五筆碼錯。最大取樣誤差是 1.375 LSB。可解析的 bit 多在數十 mV 殘差，已接近原讀取時限。最終 CDAC 主節點共模相對取樣點下移約 107–112 mV，後段小殘差因而可能更難解析。

這次保留原 12 個輸入碼、0.756855 V 共模、100 mVppd、1 Ω、1.75 GS/s、模型與電路。只將七個 `V_clk` 比較器脈波的上升中點提前 17 ps，維持下降中點、其他開關事件及取樣時刻。比較到讀取增為 **42 ps**，代價是試碼後的 DAC 等待從 **38 ps 降到 21 ps**。請把比較器解析差、取樣誤差、共模和 bit 殘差一起判讀。更長比較窗不保證 CDAC 已 settle，也不會單獨確認 kickback 來源。

只送 case `sar7_02_tt_earlycmp42`。原案的 `logic_smoke_pass` 判準沿用，報 12 筆匹配結果、各 bit 未解析數、錯碼和末端共模差範圍。若仍失敗，優先判斷小殘差解析及切換共模，先回報資料。這包沒有案 1 或其他 timing sweep。

## Olympus

從 OneDrive 上傳 ZIP，核對 ZIP SHA 與解壓後的 `SHA256SUMS.txt`。既有父包採原案 0 同一份 `PAM4_R5_SAR7_SLICE_20261115`，依舊需原 C0、SWITCH64、r5 和 private shrink 的環境。完整依賴請沿用原案設定。

```bash
export PAM4_SAR7_PACKAGE='/absolute/path/PAM4_R5_SAR7_SLICE_20261115'
export PAM4_SAR7_TIMING_PACKAGE='/absolute/path/PAM4_SAR7_TIMING_PILOT_20261115'
# Along with existing PAM4_C0_ORIGINAL_PACKAGE, PAM4_C0_SWITCH_PACKAGE,
# PAM4_C0_R5_ORIGINAL and PAM4_PDK_ROOT from the original SAR7 job.
export PAM4_SAR7_TIMING_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_timing_20261115.XXXXXX")"
export PAM4_SAR7_TIMING_APPROVAL="$PAM4_SAR7_TIMING_ROOT/approval.json"
cd "$PAM4_SAR7_TIMING_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_timing.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_timing.py approval-template --root "$PAM4_SAR7_TIMING_ROOT" --approval "$PAM4_SAR7_TIMING_APPROVAL"
```

確認新根目錄、單案名稱及 manifest，依使用者的本機交接把 `approved` 改為 `true`。先 stage，核對相對原案只有七條 `V_clk` 時序來源的 `delay`、`width` 不同；private kit 根目錄替換照原流程。

```bash
/usr/bin/python3.11 -B sar7_timing.py stage --root "$PAM4_SAR7_TIMING_ROOT" \
  --approval "$PAM4_SAR7_TIMING_APPROVAL" --model-root "$PAM4_PDK_ROOT"
sbatch --export=ALL --output="$PAM4_SAR7_TIMING_ROOT/slurm-%j.out" "$PAM4_SAR7_TIMING_PACKAGE/sar7_timing.sbatch"
```

每案 1 CPU、Spectre classic `+mt=1`，6 GB，Slurm 30 分鐘。原案 solver 113.6 秒，raw 43.8 MB。若 solver 成功但未收到量測，保留 raw，使用原根目錄、approval 與 `sar7_timing.py collect-only`。`sar7_timing_summary.json` 會比較 baseline／candidate 的未解析、錯碼、共模及實際資源。回報包含 job ID、完成狀態、兩案 summary SHA。私有模型、網表及 raw 留在 Olympus。
