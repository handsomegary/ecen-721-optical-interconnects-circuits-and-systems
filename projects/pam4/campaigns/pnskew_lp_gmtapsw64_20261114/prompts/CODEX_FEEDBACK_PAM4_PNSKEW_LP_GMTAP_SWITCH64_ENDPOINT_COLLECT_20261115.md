【ECEN 721 #6 SWITCH64 端點 collect-only addf8004：還沒收成。recover_switch64_endpoint.py 在開頭核對原失敗案時擋下（"Retry inputs do not match the original failed case"），1.3 秒結束，沒有寫出任何檔案。原因是程式假設原 84、86 的 run_status 是 status＝spectre_failed_or_source_changed、exit_code≠0，但 Olympus 實檔是 status＝spectre_evidence_incomplete、exit_code＝0。gm_switch64.py 的 summary（第 120 行）也有同一個假設，修好收集後 summary 仍會擋】

一、核對
- ZIP SHA addf8004… 通過：
  - SHA256SUMS 通過；
  - ORIGINAL_ENDPOINT_RETRY_SHA256SUMS 和 b4efaeb7 包相同；
  - plan 和原包相同；
  - verify 通過；
  - 231 項測試通過，skipped 1（選用的大檔測試，未跑）。
- 和 b4efaeb7 的差異：comp_measure.py、native/collect_r5.py，新增 recover_switch64_endpoint.py 與對應測試。
- collect-only：srun 1 CPU／4 GB，沿用原 approval approval_sw64_retry_84_86.json；1.3 秒失敗，RSS 29 MB。
- 原 run root 與補跑 root 都沒有被寫入：補跑案仍只有 case／execution_intent／run_status。

二、Olympus 實檔（逐項比對 recover_switch64_endpoint.historical_evidence 的條件）

| 條件 | 84 | 86 | 是否符合 |
| --- | --- | --- | --- |
| bench／parent_diff／corners／case.json SHA，原案＝補跑 | 相同 | 相同 | ✓ |
| format、case_id、case_sha256、plan_sha256、input_deck_sha256_before，原 run_status＝補跑 intent | 相同 | 相同 | ✓ |
| 原 input_deck_sha256_after＝bench SHA | 81fa8be8… | 762d6066… | ✓ |
| 原 max_solver_file_bytes | 536870912 | 536870912 | ✓ |
| **原 status** | **spectre_evidence_incomplete** | **spectre_evidence_incomplete** | ✗（程式要求 spectre_failed_or_source_changed） |
| **原 exit_code** | **0** | **0** | ✗（程式要求 ≠0） |

- 原因：Spectre 在 FATAL "not enough virtual memory" 後仍回傳 0。olympus_common.run_classic 因此走 `spectre_evidence_incomplete` 分支（第 152 行），而不是第 146 行的 `spectre_failed_or_source_changed`。
- 其他會用到的實際值，請一起核對，避免再來回：
  - slurm_job_id 是每個 array task 自己的 job ID，不是 array 主 ID：

    | 案 | 原始 job | 原始 task ID | 補跑 job | 補跑 task ID |
    | --- | --- | ---: | --- | ---: |
    | 84 | 757597_84 | 757710 | 757729_84 | 757730 |
    | 86 | 757597_86 | 757597 | 757729_86 | 757729 |

    REPORTED_RETRY_ARRAY 只寫進收據的話沒關係；如果有比對，84 會不符。
  - 補跑的 run_status：status＝spectre_completed，exit_code＝0，solver_completion_errors＝0，max_solver_file_bytes＝671088640。
  - 補跑的 tran 大小與 SHA：
    - 84：576370217 B，SHA fea911b3…；
    - 86：560309741 B，SHA 10c96868…。
  - 原 84／86 的 spectre_wall_seconds 297／296，峰值 RSS 約 246 MB。

三、請你處理
- recover_switch64_endpoint.py:55 與 gm_switch64.py:120：原失敗案的條件改成接受實際的 `spectre_evidence_incomplete`／exit_code 0。可以同時接受兩種狀態，再加上「原 tran 檔恰為 512 MiB」或「spectre.log 有 FATAL」當證據。
- 請用上面的實際值做一份 fixture 測試，跑完整條 collect-only 加 summary，不要只用合成的 run_status。
- 其餘不用改。新包交過來後我照原步驟收集；84、86 的 raw 和原 83–86 都保留。
