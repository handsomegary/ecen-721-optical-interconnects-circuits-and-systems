Stage: case18 summary collector 修正（761649 既有波形 collect-only，0 新 solver）
Status: done
Decision: STOP — 修正後完整 summary：565 screen_pass=false（registered 12/12 可讀但 7 錯 Σ7/max1；cmp 10/12、4 bit 未解析；cmp/reg 不一致）
Summary: collector 761658 COMPLETED 0:24；summary 121d50d9…cca19、receipt 0ef32f07…4f4f；psf_parse_count=1；來源 before==after；0 solver/0 new raw/0 source writes
Run paths: ~/ecen720_28nm/runs/pam4_sar7_read_overlap_collect_fix_20261117.ScC8GU（輸出根＝run root 本身）；來源 ~/ecen720_28nm/runs/pam4_sar7_read_overlap_pilot_20261117.3abvDG（未改）
Commit: 見 state.json / 下方
Needs user decision: no

## 執行
- 收到 inbox `20261117T0047_sar7_overlap_collect_only_fix.md`。ZIP `ECEN721_PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_20261117.zip` SHA256 `72ce4fe5e1ebb00b34b94eab26c5611a606f6aa10ee1d3f0ff870e910d6568fb` 相符；上傳新 mktemp root；`sha256sum -c` 5/5 OK；SHA256SUMS.txt = manifest `cafe5b467a7063e31e1ec32f73e7b44602721ffc5417c364ad449ea4053abb60` 相符。
- `verify` rc0（"Immutable case18 verified; collect-only, zero solver"）；unittest 5/5 OK。
- **Slurm 提交紀錄（如實）**：共 3 個 collector job，前兩個都是我設定 output root 錯誤，在參數檢查時就退出，未讀任何來源、未 parse PSF：
  - 761656 FAILED 0:03：`checked_root(--output-root)` FileNotFoundError（我指定的 `<root>/out` 尚未建立）。
  - 761657 FAILED 0:03：`Use a fresh collector output root`（basename 須以 `pam4_sar7_read_overlap_collect_fix_` 開頭；Guide 的 output root 就是 run root 本身，是我看錯）。
  - 761658 COMPLETED 0:24：output root = `pam4_sar7_read_overlap_collect_fix_20261117.ScC8GU`。這是唯一有效的 collector，PSF 只 parse 1 次。
  - 每次重送前都比對原 case18 檔案 inventory（size+path md5），結果都沒變；原 measurements.json 仍是 `1729b55e…ad37`。receipt 記錄 source_before == source_after，original_report_and_raw_unchanged=true，new_solver_jobs=0，new_raw_files=0，source_writes=0。
- 輸出：`sar7_read_overlap_summary.json` 3,397,685 B，SHA `121d50d9324627f4326149b17217f49dbbd9e4113076cced38919ac6127cca19`；`sar7_read_overlap_collect_fix_receipt.json` 32,685 B，SHA `0ef32f07eb1c4c0d7c1b336605a8c204d977edefa06f151a3594caf9a7204f4f`。Repo 只收 compact 摘要（26.7 KB）和 receipt。

## 正式 screen（原 case18 函式與門檻不變）
| read | screen | reg avail/wrong/Σ/max | cmp avail/wrong/max | unresolved bits | cmp=reg | final DAC CM (mV) | phys window |
|---|---|---|---|---|---|---|---|
| 565 | **FAIL** | 12/7/7/1 | 10/5/1 | 4 | no | −9.15 / +5.39 | valid |
| 563 | FAIL | 12/7/7/1 | 10/5/1 | 4 | no | −7.60 / +4.63 | valid |
| 554 | FAIL | 12/8/10/2 | 10/5/1 | 4 | no | −4.12 / −4.05 | valid |
| 557 | FAIL | 5/3/3/1（7 缺） | 10/5/1 | 4 | no | −3.97 / −3.68 | valid |

- 最後一次比較的 active CM：trigger −4.17/−3.67 mV，read −4.05/−3.99 mV → active_last_read_cm_pass=true（552 CM ≤10 mV PASS）。post565 final DAC CM −9.15/+5.39 mV 也在 10 mV 內。
- 失敗的條件：84 bit 沒有全部解析（4 bit 未解析）、12 碼 cmp/reg 不一致、wrong 7 > 6。max1 和 CM 兩項通過。
- 碼（expected→cmp/reg565）：0:64→64/64，1:0→0/0，2:127→127/127，3:31→31/31，4:96→95/95，5:63→64/64，6:65→64/64，7:85→None/86，8:42→None/43，9:1→0/0，10:126→127/127，11:64→64/64。錯誤都是 ±1 LSB，其中 cmp 有 5 個錯，conv7/8 的 cmp 不可讀。
- **未解析的 4 bit 正好在兩個碼裡**：conv7 b2、b1，conv8 b2、b1（decision=None）。所以「兩個 code 不可讀」= 4 bit，不是 2 bit。
- max_abs_sample_error 1.673 LSB。

## 72 邊界 prior-latch 診斷
- observed 72/72 boundaries；prior_read_internal_class_available 70；**prior_latch_unresolved_during_overlap = 2**；opposite_rail = 0；min |x−y| 0.330 V。
- 兩個 unresolved 都在 conv8（expected 42 → reg 43）：
  - conv8 b2→b1：initial_internal_class=None，14 個 unresolved 樣本，min|xy| 0.330 V；
  - conv8 b1→b0：initial_internal_class=None，2 個 unresolved 樣本，min|xy| 0.55 V。
- 沒有任何 boundary 出現 opposite-rail。

## 時序餘裕
- **max observed 44.82 ps = conv8 b0**（timing[62]，q_buffer raw_stable_rail_delay_ps 44.821，decision 1）。sampled margin 1.18 ps。raw gate 半 VDD 交越在 compare +38.96 ps（rise）／+72.46 ps（fall），mid 在 +45.85，decode 在 +51.26 ps。我沒有先假設它屬於 b0，這是逐 bit 搜尋後確認的。
- b0 sampled margin（ps，conv0..11）：7.00, 6.68, 7.36, 7.29, 6.71, 7.89, **1.82**, 4.25, **1.18**, 6.36, 4.79, 5.21 → 最小 1.18 ps（conv8）。
- 全部 80 個已解析 bit 的最小 sampled margin：**0.071 ps（conv6 b2）**；<1 ps 的有 4 個（conv6 b2 0.07、conv10 b2 0.54、conv5 b6 0.89、conv11 b2 0.96）。b2 是最常見的薄 margin 位元。
- receipt 的 supplemental_diagnostics 已記錄 12 次 b6 在 launch+30/+35/+38/+41 ps 的 48 點 held/sense、x/y、rawq；只做紀錄，沒有分析或改計畫。

## 與前一輪比較
- 母包 761649 的 measurement 只能說 reg 12/12 可讀、7 錯、max1，cmp 10/12。這次 summary 確認了同一組數字，並補上完整 gate：仍然 FAIL（4 bit 未解析／wrong 7／cmp≠reg），CM 和 window 通過。
- 和 refpath2 761632（reg 8/12 wrong、max 32 LSB）相比，max 誤差大幅改善到 1 LSB，但 screen 仍未過。

## 資料保留
- 761649 raw（118 MB）保留：本包不刪除。依 sar7_raw_retire_after_window_20261117，等 07:37 時窗結束、最後結果 commit 後再處理。
- C2 761525 沒有任何更動：3/95 COMPLETED，_3–_5 RUNNING，6–94 PENDING。
- 下一個物理 case 由 Codex 決定，本輪沒有送新的 Spectre。
