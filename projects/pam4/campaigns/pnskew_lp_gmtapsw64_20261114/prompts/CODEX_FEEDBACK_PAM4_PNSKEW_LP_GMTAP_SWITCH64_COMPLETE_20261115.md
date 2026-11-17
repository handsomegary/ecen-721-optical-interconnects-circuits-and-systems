【ECEN 721 #6 SWITCH64 完成：collect-only 修正版 94aff417 收成 84、86。合併 summary：total_measured 87、dynamic 39，21／21 組有對照的切碼都是 observed_recovery 且 settled，all_planned_transitions_recovered_in_window＝true，FF_dense＝passes_nominal_dense_recheck，ready_to_design_C0＝true。最長恢復 2.648 ns（FF −60→0）】

一、執行
- ZIP SHA 94aff417… 通過：
  - SHA256SUMS 通過；
  - ORIGINAL_ENDPOINT_RETRY_SHA256SUMS 和 b4efaeb7 包相同；
  - plan 和原包相同；
  - verify 通過；
  - 233 項測試通過，skipped 1（選用的大檔測試，未跑）。
- 和 addf8004 的差異只在 gm_switch64.py、recover_switch64_endpoint.py 與對應測試。
- collect-only：srun 1 CPU／4 GB，沿用原 approval；兩案串行共 3 分 8 秒，峰值 RSS 404 MB，沒有重跑 Spectre。兩案都有 measurements、recovery、completion。
- summary：lp_gm_switch64_full_0_86_endpoint_collect_20261115.json。

二、兩個端點補跑

| 案 | 對照 | status | settled | 恢復 | Vb1 偏差 | held 最大差 | XT2 時域 | 恢復後取樣／lane |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: |
| 84 SS 0→−60，P 晚 4.46 ps | 83 | observed_recovery | true | 2.484 ns | 22.31 mV | 6.86 mV | 非飽和 25.3%，最小 −1.32 mV | 119 |
| 86 FF 0→+60，N 晚 4.46 ps | 85 | observed_recovery | true | 2.620 ns | 26.84 mV | 14.47 mV | 0%，最小 172.8 mV | 117 |

- 和無偏斜的同一切碼幾乎一樣：SS 0→+60 是 2.485 ns／22.32 mV，FF 0→+60 是 2.619 ns／26.81 mV。偏斜不影響恢復。

三、SWITCH64 結論
- 密頻 AC：FF 0↔±1 是 0.4947874 ps，餘量 5.21 fs，名義通過。
- 切碼：
  - 小碼距（±1、±2、52→56）≤0.6 ns；
  - 0→+32 是 1.97 ns；
  - 端點跳碼 2.48–2.65 ns；
  - 21 組全部恢復。
- 照你的 C0 設計，評分期間固定控制碼；若在前導段切碼，空窗至少 3 ns，比實測最長的 2.65 ns 多約 0.35 ns。
- 照使用者「不要為小差異一直修」的原則，以下維持原狀，不另開補驗：
  - FF 5.2 fs 餘量；
  - SS XT2 時域非飽和（參考 hold 完全相同，交給 C0 SER 判斷）；
  - 尾電流只作診斷。
- 失配與版圖寄生仍待後面處理，不擋 C0。

四、請你處理
- C0 不急，準備好再提。請附：
  - 5 案的 deck；
  - 每案的 solver 時間與 raw 估計；
  - 切碼空窗的設定。
- 這幾次的問題都出在收集與核對程式對 Olympus 實檔的假設，模擬本身沒有出錯。C0 交件前，請用這次的實際 run_status、task ID 與大檔路徑當 fixture 測一次 run→collect→summary，避免同樣的來回。

五、空間
- summary commit 後，退役 83–86 的 raw：原 run root 的 83–86，加上補跑 root 的 84、86。其中原 84、86 是 512 MiB 截斷的失敗 PSF，已經被補跑取代。
- measurements、completion、recovery、run_status 與網表都保留。
