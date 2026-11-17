# PN skew 補償 LP_DIAG：啟動與迴路穩定度診斷（2026-11-14）

第十五版。針對 LP_INTEGRATE 通過的 1934 Ω 直連偏壓，做三項診斷：

- 快／慢上電與掉電重啟（tran 500 µs）；
- replica 迴路與 beta multiplier 的 STB；
- SS cb2 的 XT2 有限擺幅（這部分另外批准）。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA ab266cb1…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lpdiag_11_measurements.json` | 11（SS cb2 replica STB）的原始 measurements（status review）。 |
| `recovery_package/` | 修正收集器的復原套件中新增或修改的原始碼（ZIP SHA b57df58f…）。 |
| `results/lpdiag_00_recovered.json`、`lpdiag_11_recovered.json` | collect-only 的正式結果。 |
| `results/diag_snapshot_0_11.json` | 收集前的原案快照。 |

## 首批（批准 0–2、11–12；只跑了 0、11，job 754102）

- 11：Spectre 完成，原生 margin 為 PM 84.0°（10.3 MHz）、GM 19.6 dB（513 MHz）。但收集器讀不到頻率單位，PM／GM 留空（status review）。
- 0：Spectre 完成（tran 27.5 s），但收集器不認得 `biasStartup.tran.tran` 這個 PSF 檔名，結果是 FAILED。從 raw 直接讀，Iref 約 2 µs 收斂到 338.3 µA，啟動支路也有退出。
- 兩個都是收集器問題，所以 1、2、12 沒有提交；raw 保留在 Olympus，等 Codex 修正。

## 復原（collect-only 0／11）

- Codex 修正收集器後，使用者批准 collect-only。從保留的 raw 重新收集，不重跑 Spectre；兩案都 pass。
- 0（SS 快速上電）：Iref 338.335 µA，伺服誤差 −0.155%，啟動 kick 0.0047 µA，五項檢查全部通過。
- 11（SS cb2 replica STB）：PM 84.03°（10.34 MHz），GM 19.63 dB（513 MHz），與 Spectre 原生 margin 一致。
- 1、2、12 需要另外批准。

## 1、2、12（修正後的收集器，run2，job 754148）

- 1（SS 慢速上電）、2（SS 掉電重啟）：pass。都收斂到 338.335 µA，啟動支路有退出；重啟案的斷電約 50 µs，之後重新收斂。
- 12（SS cb2 beta STB）：review。max |T| 為 0.505（儲備 5.94 dB），min |1−T| 為 0.495，Spectre 判定「always stable」。但未達 10 dB 保守篩選，掃頻到 1 GHz 也還沒看到完整的高頻衰減。
- 第一次提交（job 754145）因 wrapper 路徑錯誤（run22），三案 0 秒 FAILED，沒有執行 Spectre；修正後重送。
- `results/` 另有 1、2、12 的 measurements 和 `lp_diag_recovered_summary.json`。

