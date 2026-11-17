【ECEN 721 #6 P/N deskew LP_DIAG 首批：兩個收集器問題，所以先停在 0／11。Spectre 本身都正常完成；原生 margin 顯示 replica 迴路 PM 84.0°、GM 19.6 dB；啟動波形約 2 µs 收斂到 338.3 µA】

一、執行
- 套件（ZIP SHA ab266cb1…）：SHA256SUMS 全部通過，`lp_diagnostics.py --mode verify` 通過，79 項離線測試通過。
- 審查 deck 索引 0、11、12：
  - bench 與 portable_review 完全相同，corner 只差模型根路徑，case.json 只多了 model_preflight 與 staged_source_sha256。
  - 00 和 INTEGRATE 18 比：所有電源（XVs、XVcm、XVb、GFVDD、GMSAVE0–7）都改成在 1 µs 內從 0 升到額定值（pwl），分析是 tran 500 µs（maxstep 20 ns）。DESIGN 原本說只斜升新偏壓電源，這版連 AFE 一起斜升，我認為更接近實際。
  - 11：iprobe 斷在 OTA 輸出 GMSR_BIAS 與 replica 閘極 GMSQ_REPG 之間。
  - 12：iprobe 斷在 beta multiplier PMOS 輸出鏡的閘極。
- 使用者批准 0–2、11–12（stages startup、stb）。依指示先跑 0、11（job 754102）：
  - 11：COMPLETED，2 秒。completion 有寫出，但 status 是 review。
  - 0：FAILED，30 秒。Spectre 正常完成（tran CPU 27.5 s，0 errors），但收集器拋出 ValueError。
- 因為兩個收集器都有問題，依「首例核對後再擴跑」與「缺 trace 不替填、不當作通過」，1、2、12 沒有提交。raw 保留在 Olympus。

二、收集器問題
1. 啟動（lp_diagnostics 的 startup collector）：
   - 錯誤訊息：`ValueError: Unexpected native PSF files for raw/biasStartup\.tran`。
   - Spectre 23.1 的 psfascii tran 輸出檔名是 `biasStartup.tran.tran`（11.7 MB），不是 `biasStartup.tran`。raw 目錄的實際檔案是：biasStartup.tran.tran、dcOp.dc、dcOpInfo.info、logFile。
   - 請把預期檔名改成 `<name>.tran.tran`。
2. STB（replica）：
   - measurements 的 phase_margin_deg 與 gain_margin_db 都是 null，原因是「STB frequency unit does not establish Hz」。
   - 但 replicaSTB.stb 的 sweep 定義其實有寫單位：`"freq" "sweep" PROP( ... "units" "Hz" ... )`。
   - 原生的 replicaSTB.margin.stb 也有單位和數值：
     - gainMargin "dB" 19.625，頻率 513.16 MHz；
     - phaseMargin "Deg" 84.034，頻率 10.336 MHz；
     - stb_state 為 "The circuit is stable. Gain and phase margin are both found."
   - 請讓收集器讀 sweep PROP 的 units，並核對 margin.stb 的 dB／Deg／Hz。
   - 另外，loopGain 在 1 Hz 為 −451.17（實部為負），這是 Spectre 的符號慣例，原生 margin 已依此判定穩定。請確認你的 PM 計算採用相同慣例。

三、從 raw 看到的初步數據（只供參考，不算判定）
- 11 replica STB（SS cb2）：PM 84.0°、GM 19.6 dB，高於 60°／10 dB 的門檻。DC Iref 338.34 µA，與整合版一致（dc_iref_matches_integrated 為 true）。
- 0 SS 快速上電：我直接讀 tran raw（25,225 個點）：

| t | GMSR_REF | GMSR_D | GMSR_BIAS | GMSQST（啟動閘極） | GFVDD 電流 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 µs | 0.65359 | 0.64272 | 0.45531 | 1.7 mV | 11.95 mA |
| 2 µs | 0.65369 | 0.65390 | 0.44533 | 1.7 mV | 11.10 mA |
| 10 µs | 0.65369 | 0.65393 | 0.44530 | 1.7 mV | 10.30 mA |
| 500 µs | 0.65369 | 0.65393 | 0.44530 | 1.7 mV | 10.24 mA |

  - Iref 最終為 338.34 µA，與 DC 一致，約 2 µs 內收斂。
  - 啟動閘極 1.7 mV，所以啟動支路已退出。
  - GFVDD 電流在約 10–20 µs 內從 11.95 降到 10.24 mA，應該是 RF 閘極濾波（100 kΩ／10 pF，τ = 1 µs）等節點的穩定過程。
  - 目前沒有看到卡在零電流狀態的跡象。這些仍需要修正後的收集器正式判定。

四、請你處理
- 修正 startup 的 PSF 檔名比對，以及 STB 的頻率單位與原生 margin 讀取。最好提供 collect-only 模式，從保留的 0、11 raw 重新收集，並加上用實際 Spectre 23.1 檔名與 PROP 格式做的離線測試。
- 修正版需要新的使用者批准（SHA 會改變）。屆時可以一起提 1、2、12（若 0／11 的收集通過），之後再提其餘 PVT。
- 12 的 beta multiplier 是正回授迴路，在工作點的迴路增益可能一直小於 1、沒有交越點。請事先定義這種情況的判定方式（例如 |T| 的最大值與 1 的距離），不要只依 PM／GM。
