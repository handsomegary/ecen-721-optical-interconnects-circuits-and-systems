【ECEN 721 #6 P/N deskew LP_INTEGRATE 0–33：原生直連整合版在 SS／TT／FF、cb0／cb2 六個條件全部同時通過 2 dB 與 +10／+14 mW；伺服追蹤 ≤0.16%；最小餘裕為 FF cb0 的 0.76 mW 和 SS 的 0.57 dB】

一、執行
- 套件（ZIP SHA 8dc842ec…）：SHA256SUMS 全部通過，`lp_integrate.py --mode verify` 通過，68 項離線測試通過。
- 審查 deck 索引 0、18、20、30：
  - 0／18／20 的 bench 與 portable_review 完全相同，corner 只差模型根路徑；30 的 bench 只差 model include 那一行。
  - case.json 只多了 model_preflight 與 staged_source_sha256。
  - 18 的偏壓區塊：1934 Ω、L120 直連鏡（PMOS 2:2、NMOS 1:10）、啟動支路，以及 L120 鏡負載 OTA（第二級 PMOS 4 顆、NMOS 1 顆）。沒有 isource，所有 `:p` 都在 vsource 上。
  - 30 的理想 isource 沒有存 `:p`，Iref 由 GMSR_REF 推算。
- 使用者批准 0–33（stage integration）：
  - 先跑 18（job 754057）。GMSR_REF 為 0.6537 V，推算 Iref 338.3 µA，與 REFMIRROR 直連版一致；GMSR_D 與 GMSR_REF 相差 0.24 mV；GFVDD:p 和 PSF 齊全，completion 也有寫出。
  - 再跑其餘 33 案（job 754059）。
  - 34／34 COMPLETED，17 列，invalid 與 missing 都是 0。
- raw 依指示保留在 Olympus。

二、對照組：與先前批次逐值一致
- SS：bypass −25.353 dB；idealz50 cb0 −22.966 dB，cb2 −20.817 dB。
- TT：bypass −23.301 dB；idealz50 cb0 −20.873 dB，cb2 −18.720 dB。
- FF：bypass −21.376 dB；idealz50 cb0 −18.915 dB，cb2 −16.725 dB。

三、原生直連整合版（Rs = 25 Ω；「相對理想」指同角落、同 cb 的 idealz50；功耗增量包含所有電源，也就是參考、啟動與 OTA）

| corner | cb | 56 GHz Hdd | 相對理想 | 額外 tilt | 增量 | 預算 | 功耗餘裕 | Iref | 每腿電流 | 相對 4.35 mA | 伺服誤差 | replica − ref | 偏壓支路 | XT2 裕度 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SS | 0 | −24.38 | −1.42 dB | −1.31 | 8.30 mW | 10 | 1.70 | 338.3 µA | 4.729 mA | +8.71% | −0.16% | +0.24 mV | 0.64 mW | 6.6 mV |
| SS | 2 | −22.25 | −1.43 dB | −1.42 | 8.46 mW | 14 | 5.54 | 338.3 | 4.729 | +8.71% | −0.16% | +0.24 | 0.64 | 2.3 mV |
| TT | 0 | −21.96 | −1.08 dB | −1.84 | 8.87 mW | 10 | 1.13 | 324.8 | 4.547 | +4.53% | 0.00% | −0.01 | 0.68 | 100.5 mV |
| TT | 2 | −19.77 | −1.05 dB | −1.91 | 9.04 mW | 14 | 4.96 | 324.8 | 4.547 | +4.53% | 0.00% | −0.01 | 0.68 | 96.3 mV |
| FF | 0 | −19.73 | −0.82 dB | −2.44 | 9.24 mW | 10 | 0.76 | 307.1 | 4.306 | −1.00% | +0.16% | −0.23 | 0.72 | 191.2 mV |
| FF | 2 | −17.46 | −0.74 dB | −2.48 | 9.44 mW | 14 | 4.56 | 307.1 | 4.306 | −1.00% | +0.16% | −0.23 | 0.72 | 186.9 mV |

- summary 的判定：
  - all_six_gain_and_power_pass：true；
  - all_six_servo_within_2_percent：true；
  - all_six_replica_voltage_within_2_percent：true；
  - all_six_nominal_current_within_2_percent：false（SS +8.7%、TT +4.5%）。
- 最小餘裕：增益是 SS 的 0.57 dB（−1.43 dB 對 2 dB），功耗是 FF cb0 的 0.76 mW。
- 額外共同群延遲在 55 GHz 約 2.2–2.7 ps。
- TT OTA-only（理想 Iref）：
  - cb0：每腿 4.351 mA，相對理想 −1.21 dB，增量 +8.43 mW；
  - cb2：相對理想 −1.17 dB，增量 +8.61 mW；
  - 伺服誤差 0.016%，與 SS／FF 的 OTA 結果一致。

四、判讀
1. 整合版第一次在所有角落、單組與雙組都以實體偏壓（不靠理想元件或預留估計）同時通過損失與功耗判準。上一版的推算在這裡得到實測確認：Iref 的角落誤差方向（SS 高、FF 低）對預算有利。
2. 標稱電流相對 4.35 mA 偏離 −1.0%～+8.7%。若要把標稱電流也鎖在 ±2%，需要你預留的 1.80–2.20 kΩ、32 檔 trim。但 trim 往下調時，SS 的增益餘裕會變小：SS 若回到 4.35 mA，增益約 −1.69 dB，仍可通過。
3. 剩下的風險：
   - SS cb2 的 XT2 只有 2.3 mV（原 r3 第二級，不是新電路造成的）；
   - FF cb0 的功耗餘裕只有 0.76 mW；
   - 額外 tilt −1.3～−2.5 dB 要在時域 FFE 後確認；
   - startup 與 STB 都還沒驗證（startup_verified、stability_verified 都是 false）。

五、請你處理（下一階段）
- startup（慢／快電源斜坡、cold restart、確認啟動支路有退出）與 replica 迴路 STB（PM ≥60°、GM ≥10 dB），用 portable_diagnostics 實體化。
- SS cb2 的 XT2：在有限輸入擺幅下量第二級的最小裕度與 region，再決定是否調 Vb2。
- 之後依序是非理想電感（Q、SRF）、正負 ±4.464 ps 端點、細碼與接縫、時域 SER。請分批提出，每批需要使用者另外批准。
- trim 是否實作請一併判斷：若 2% 只用於伺服追蹤，可以先不做。
