【ECEN 721 #6 P/N deskew SWITCH64 端點補跑 b4efaeb7：84、86 的 Spectre 都完整跑完（0 errors，PSF 結尾有 END），PSF 是 576,370,217 B（549.7 MiB）與 560,309,741 B（534.3 MiB），都在新的 640 MiB 上限內。但收集時被 `native/collect_r5.py` 的 `ensure_end` 擋下：MAX_RAW_BYTES 仍寫死 512 MiB，"Raw exceeds 512 MiB collector bound"。兩案 FAILED，沒有 measurements。不必重跑模擬，只要修這一行，再對補跑 root 做 collect-only】

一、執行
- ZIP SHA b4efaeb7…：
  - SHA256SUMS 通過；
  - `gm_switch64_retry.py --mode verify` 通過（84、86 和原網表一致）；
  - 226 項測試通過；
  - plan SHA a2f8774d… 與原包相同，ORIGINAL_RECOVERY_SHA256SUMS 和 f648e60c 的 SHA256SUMS 相同。
- 程式差異只是把單檔上限參數化：gm_drive、comp_measure、olympus_common、gm_switch64、gm_switch64_metrics，外加 retry 模組。
- approval：只有 84、86，stages ["switch"]，plan SHA a2f8774d…，SHA256SUMS SHA 3ca95ec2…。
- 獨立 run root：pnskew_lp_gmtapsw64e_20261114.*；報告與 log 放在原 campaign 的 retry_report/。
- job 757729（--array=84,86%2，6 GiB）：兩案都 FAILED，5 分 25 秒／5 分 14 秒。

二、證據

| 案 | Spectre | solver | 峰值 | codeSwitch.tran.tran | run_status | 失敗點 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| 84 ss 0→−60 P 晚 | 0 errors | 318 s | 237 MB | 549.7 MiB，有 END | spectre_completed，max_solver_file_bytes＝671088640 | collect_r5.ensure_end |
| 86 ff 0→+60 N 晚 | 0 errors | 308 s | 233 MB | 534.3 MiB，有 END | spectre_completed | 同上 |

- 合併 summary（lp_gm_switch64_full_0_86_endpoint_retry.json）：
  - total_measured 85、dynamic 37；
  - FF_dense 是 passes_nominal_dense_recheck；
  - 84、86 標成 "missing endpoint retry evidence"；
  - ready_to_design_C0 是 false。
- 套件裡仍寫死 512 MiB 的地方：
  - `native/collect_r5.py:22` 的 MAX_RAW_BYTES，這次就是卡在這裡；
  - `gm_switch64_psf.py:15` 的 MAX_BYTES（註解寫和 safe_raw 相同）——請確認串流讀取是否也已經改用 640 MiB 的參數；
  - `comp_measure.safe_raw` 的預設值與 `olympus_common.DEFAULT_SOLVER_FILE_BYTES`（已參數化，只要確認 retry 路徑有把參數傳到底）。

三、請你處理
- 修 collect_r5.ensure_end（以及 retry 路徑上任何仍是 512 MiB 的檢查），讓 84、86 走 640 MiB。
- 提供補跑 root 的 collect-only，同 recover_switch64 的做法：重讀現有 PSF、核對 SHA 與 END，不重跑 Spectre。新包交過來後，我收集兩案、跑合併 summary，確認 84／83、86／85 恢復。
- 為了不再來回，建議新包附一個用 ≥560 MiB 合成 PSF 測整條 collect 路徑的測試（run→collect→summary）。
- 其餘都不需要改。

四、保留
- 原 run root 的 83–86，以及補跑 root 的 84、86（367 MB 實占），raw 全部保留，等收集。家目錄約 22 GB 可用。
