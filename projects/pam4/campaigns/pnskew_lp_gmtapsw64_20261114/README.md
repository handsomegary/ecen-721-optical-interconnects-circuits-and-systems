# PN skew 補償 LP_GMTAP SWITCH64：FF 密頻 AC 複核與短切碼暫態（2026-11-14）

第二十六版。沿用 COMMON64 已通過的 55 碼、±60 端點與 375 Ω／14.125 kΩ、2 pF 分壓器。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA 63d0272a…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_gm_switch64_dense.json` | 官方 `gm_switch64.py --mode summarize` 輸出：incomplete_dense_evidence（check_grid 擋掉 150 GHz 截短的最後一格）。 |
| `results/lp_gm_switch64_dense_diag_endpointgrid.json` | 診斷重算：只放寬最後一格，其餘照原碼；passes_nominal_dense_recheck。 |
| `results/dense_endpoint_diag.py` | 上述診斷用的 monkeypatch 包裝，不修改套件。 |
| `package_recovery/` | 復原包原始碼（ZIP SHA f648e60c…）：修正 check_grid、串流 PSF、collect-only。 |
| `results/lp_gm_switch64_dense_rechecked.json` | 復原包正式重算密頻：passes_nominal_dense_recheck。 |
| `results/lp_gm_switch64_smoke_recovered.json` | 48／49 collect-only 後的 summary。 |
| `results/lp_gm_switch64_full_0_86.json` | 0–86 全部 summary。 |

## 密頻 AC 0–47（48 案，job 757442）

- FF 0→±1：base100 0.4947919、grid200 0.4947883、grid400／tight400 0.4947874 ps；對 0.50 ps 的餘量 5.21 fs，網格收斂代理 0.0009 fs。
- tight400 與 grid400 的解逐位元相同（容差已套用，OP 不變）。
- XT2 全部 region 2，最小 193.35 mV。
- 待 Codex 修 check_grid 後正式重算 summary。

## 動態 smoke 48、49（job 757441）

- Spectre 0 errors，solver 272 s，峰值 230 MB。
- codeSwitch PSF 353／361 MiB，超過 collector 的 320 MiB 上限，兩案 FAILED、沒有 measurements。
- 50–86 未送；raw 全部保留，等修正版。

## 復原包 f648e60c 與 50–86（job 757597）

- 密頻 AC 正式通過（passes_nominal_dense_recheck），數值和診斷版相同。
- 48／49 collect-only 復原：2 分 10 秒，峰值 RSS 300 MB；49 對 48 在 66 ps 恢復。
- 50–86：35／37 完成。19 組切碼全部 observed_recovery、settled：
  - 小碼距 ≤0.6 ns；
  - 0→+32 為 1.97 ns；
  - 端點跳碼 2.48–2.65 ns（Vb1 偏差 22–28 mV）。
- SS 時域 XT2 有 16–37% 時間不在飽和區（最小 −8.9 mV），參考 hold 完全相同，是訊號擺幅本身造成的；交給 C0 SER 判斷。
- 84、86（偏斜的端點跳碼）撞到 512 MiB 單檔上限，Spectre 中止，等 Codex 修。
- raw：0–82 已分析的部分在 commit 後退役；83–86 保留。

## 端點補跑 b4efaeb7（84、86，job 757729）

- `package_endpoint_retry/`：補跑包原始碼；`results/lp_gm_switch64_full_0_86_endpoint_retry.json` 是合併 summary（家目錄路徑已遮成 `~`）。
- Spectre 兩案都完整跑完（0 errors，PSF 549.7／534.3 MiB，有 END），但 `native/collect_r5.py` 仍是 512 MiB 上限，收集失敗。
- 不需重跑模擬；等 Codex 修上限並提供 collect-only。raw 全部保留。

## 端點 collect-only addf8004（2026-11-15）

- `package_endpoint_collect/`：collect-only 包原始碼。
- 收集在開頭的核對就被擋下：程式預期原失敗案的 status 是 `spectre_failed_or_source_changed`、exit≠0，但實檔是 `spectre_evidence_incomplete`、exit 0（Spectre 在 FATAL 後仍回傳 0）。沒有寫出任何檔案，raw 全部保留。

## collect-only 修正版 94aff417：SWITCH64 完成（2026-11-15）

- `package_endpoint_collect_fix/`：修正版原始碼；`results/lp_gm_switch64_full_0_86_endpoint_collect_20261115.json` 是最終合併 summary（家目錄路徑已遮成 `~`）。
- 84、86 用 collect-only 收成：3 分 8 秒，峰值 RSS 404 MB。
- 總計：87 案有效、39 個動態案，21／21 組切碼恢復，ready_to_design_C0＝true。
- 84 恢復 2.484 ns、86 恢復 2.620 ns，和無偏斜的同一切碼相同；最長 2.648 ns。
- raw：summary commit 後退役 83–86 與補跑 root 的 raw。
