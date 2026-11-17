【ECEN 721 #6 P/N deskew LP_GMTAP SWITCH64：兩個結果，都要你修程式。
(1) 密頻 AC 0–47：48 案全部完成，數值本身通過。tight400 下 FF 0→±1 是 0.494787 ps，餘量 5.21 fs；網格收斂代理 0.00086 fs。但官方 summary 判 incomplete_dense_evidence，原因是 check_grid 擋掉 Spectre 在 150 GHz 終點截短的最後一格。
(2) 動態 smoke 48、49：Spectre 0 errors，solver 4 分 32 秒；但 codeSwitch PSF 有 353／361 MiB，超過 collector 的 SWEEP_BYTES_MAX 320 MiB，兩案都 FAILED、沒有 measurements。已停在這裡，50–86 未送】

一、執行
- 套件（ZIP SHA 63d0272a…）在 Olympus 上核對：
  - SHA256SUMS 全部通過；
  - `gm_switch64.py --mode verify` 通過（87 份 deck）；
  - 205 項離線測試全部通過。
- 新 run root：pnskew_lp_gmtapsw64_20261114.*。
- 審查 deck 0、2、36、38、48、49、50、51：
  - 0、49 的 bench 和 portable_review 逐位元相同；corners 檔只差模型路徑。
  - 2（base100 p00）和 COMMON64 的 442（ff_div_p00_p）逐位元相同。
  - 0→36、2→38 只差兩處：`reltol=1e-4 vabstol=1u iabstol=1p` 換成 `1e-5／0.1u／0.1p`，以及 `dec=100` 換成 `dec=400`。
  - 48（hold +1）→49（switch 0→+1）只差：
    - GMSK11VE17 由 0 換成 PWL（0.81 V，3 ns 降到 0）；
    - GMSK16VE16 由 0.81 換成 PWL（0，3 ns 升到 0.81）；
    - save 加上這兩個 enable。
  - 48→50、49→51 只差對應的致能電壓與 PWL。
- 依常態授權，自行核准 0–86（87 案，stages dense、hold、switch），approval 綁定 plan SHA a2f8774d… 與 SHA256SUMS SHA e4a1b61d…。
- 送出：
  - smoke 48、49：job 757441，--mem=6G；
  - 密頻 0–47：job 757442，%4。

二、密頻 AC（0–47，48／48 COMPLETED，每案 2–15 秒）

1. 官方 summary（lp_gm_switch64_dense.json）判 status＝incomplete_dense_evidence，invalid_cases 是 grid200、grid400、tight400：「Incomplete N-point/decade refinement grid」。
   - 原因：Spectre 的 dec 網格停在 stop=150G。最後一點前一點和 150 GHz 之間的間距大於一格，例如 grid200 的 147.91→150 GHz（比值 1.01412，上限 10^(1.001/200)＝1.01159）、grid400 的 148.76→150 GHz（比值 1.00830，上限 1.00578）。
   - 其餘每一格都在上限內。點數 819／1636／3271，都 ≥ count_minimum（816／1632／3264）。
   - base100 剛好過，是因為它的最後一格（1.01412）小於 10^(1.001/100)＝1.02331。
   - 請修 check_grid：例如最後一格只要求 grid[-1]≥145e9，或把 stop 設在十倍頻的格點上。
2. 診斷重算（未改套件）：另寫 `dense_endpoint_diag.py`，只把 check_grid 的最後一格放寬，其餘照原碼 monkeypatch 後執行 `--mode summarize`，輸出 lp_gm_switch64_dense_diag_endpointgrid.json。結果是 status＝passes_nominal_dense_recheck、verified_nominal_dense_steps＝true。

| 邊 | base100 | grid200 | grid400 | tight400 | tight400 對 0.50 的餘量 | 網格收斂代理 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| −2→−1 | 0.2631103 | 0.2631089 | 0.2631085 | 0.2631085 | 236.9 fs | 0.0003 fs |
| −1→0 | 0.4947919 | 0.4947883 | 0.4947874 | 0.4947874 | **5.213 fs** | 0.0009 fs |
| 0→+1 | 0.4947919 | 0.4947883 | 0.4947874 | 0.4947874 | **5.213 fs** | 0.0009 fs |
| +1→+2 | 0.2631103 | 0.2631089 | 0.2631085 | 0.2631085 | 236.9 fs | 0.0003 fs |

（單位 ps，另有標示者除外。）

- base100 重現 COMMON64 的 0.49479191568842／…830 ps，到 1e−16。
- 加密網格只讓中心步階變小 4.5 as（0.0045 fs）。grid200→grid400 再變 0.86 as，收斂代理 ≪1 fs。
- tight400 和 grid400 的延遲逐位元相同，solver_tolerance_delta＝0：
  - raw 檔只有 options／tolerance 標頭和日期不同，所以新容差確實套用了；
  - DC OP 和 AC 解在列印精度內完全一樣（Newton 已收斂到遠低於容差）。
- FF 五個碼的 16 顆 XT2 都是 region 2，最小 193.35 mV（±1）。擬合 weighted phase RMS 是 0.075（±1）／0.100 ps（±2）。
- 判讀：5.2 fs 是真實的名義數值餘量，不是網格或容差造成的假象。剩下的風險只在失配與版圖寄生。

三、動態 smoke（48、49）

| 案 | Spectre | solver | 峰值記憶體 | codeSwitch.tran.tran（psfascii） | 磁碟實占 | 結果 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 48 ss_hold_p01_p01_zero | 0 errors，3 warnings（scalefactor） | 272 s | 230 MB | 369,909,297 B（352.8 MiB） | 135 MB | FAILED |
| 49 ss_switch_p00_p01_zero | 0 errors | 約 272 s | 約 230 MB | 378,504,236 B（361.0 MiB） | 136 MB | FAILED |

- 錯誤：`gm_switch64_metrics.parse_transient` 的 `need(0<len(blob)<=SWEEP_BYTES_MAX ...)`，訊息是 "Missing, oversized, or binary code-switch PSF"。SWEEP_BYTES_MAX＝320 MiB。PSF 仍在 512 MiB 的 solver 上限內。
- 沒有 measurements.json。dcOp、dcOpInfo 與 tran PSF 都保留在 run/gmsw_048*、gmsw_049*/raw，沒有退役。
- 磁碟實占約是檔案大小的 37%，因為 NFS 有壓縮。以這個比例推估，39 個動態案的 raw 約 5.3 GB，可用空間足夠（家目錄約 26 GB）。
- 依你的指引（smoke 要先驗 PSF、八路取樣與 hold 配對），smoke 沒過，所以 50–86 沒有送。

四、請你處理
1. check_grid：容許 stop 截短的最後一格（或改 stop），讓 grid200／400／tight400 正式通過。密頻 measurements.json 都在，只需要重跑 summarize，不必重跑模擬。
2. 動態 PSF 超過 320 MiB，可以選一個做法：
   - 把 SWEEP_BYTES_MAX 提高到 ≤512 MiB（PSF 解析時的 RSS 也要估）；
   - 縮小 save 清單或改用 strobeperiod 降低輸出點數；
   - 改用 psfbin 並更新讀取器。
   最好再加一個只做 collect 的模式（不重跑 Spectre），直接收 48、49 現有的 raw。這兩案已經用掉約 9 分鐘 CPU，PSF 也完整。
3. 修好後請給新的 ZIP。我會照常態授權：
   - 重跑密頻 summary；
   - 先收或重跑 48、49；
   - 通過後再送 50–86。

五、空間與保留
- run root 目前 1.3 GB：密頻 48 案約 1.0 GB，smoke 約 0.27 GB。
- 官方 summary 還不是通過狀態，所以密頻與 smoke 的 raw 先全部保留，等你修好的版本重算後再退役。
