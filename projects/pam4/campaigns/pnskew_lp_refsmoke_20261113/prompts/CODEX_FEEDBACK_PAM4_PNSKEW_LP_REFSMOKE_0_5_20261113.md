【ECEN 721 #6 P/N deskew LP_REFSMOKE 0–5：L120 鏡的誤差已降到 ≤6%，剩下的主要誤差是核心電流（+25～28%）；原生 OTA 的追蹤誤差為 SS −6.1%、FF +4.0%，SS 增益只剩 0.15 dB 餘裕】

一、執行
- 套件（ZIP SHA dc67425b…）：SHA256SUMS 全部通過，`ref_smoke.py --mode verify` 通過，57 項離線測試通過。
- 審查 deck 索引 0、2、4、5：
  - 0／2 的 bench 與 portable_review 完全相同，corner 與 parent_diff 只差模型根路徑。
  - 4／5 的 bench 只差 model include 那一行。
  - case.json 只多了 model_preflight 與 staged_source_sha256。
  - 05 用兩個 vcvs（gain 1）強制 PD_OUT = VBP、ND_OUT = VBN，等 VDS 的設定正確。
- 使用者批准 0–5（stages ota、reference）：
  - 依指示先跑 4（job 753918）。確認 GMSQPALIGN:p、GMSQNALIGN:p、GFVDD:p 在 dcOp.dc 中齊全，completion 也有寫出。
  - 再跑 0–3、5（job 753919）。
  - 6／6 COMPLETED，每案 1–4 秒，summary 沒有 invalid。
- raw 依指示保留在 Olympus。

二、Iref only（TT/25 °C/0.9 V，L = 120 nm，核心 R = 1.6 kΩ；目標 Iref 310.714 µA，核心 31.07 µA）

| 案 | Iref | 誤差 | 核心電流 | PMOS 鏡比 | NMOS 鏡比／10 | PMOS ΔVDS | NMOS ΔVDS | 電源 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 04 直連 | 402.4 µA | +29.5% | 38.75 µA | 0.979 | 1.061 | 68 mV | 260 mV | 0.433 mW |
| 05 理想等 VDS | 397.2 µA | +27.8% | 39.72 µA | 1.000 | 1.000 | 0 | 0 | 0.431 mW |

- 長通道有效：PMOS 鏡從首批 FF 的 1.88:1 改善到 0.979，NMOS 鏡誤差約 +6%（ΔVDS 260 mV）。
- 剩下的主要誤差是核心電流：38.7–39.7 µA，比目標高 25–28%。就算等 VDS 也一樣，所以要重選 R。
  - 若核心在中度反轉（I ∝ 1/R²），R 約為 1.6 k × √1.28 ≈ 1.8 kΩ。
  - 若在弱反轉（I ∝ 1/R），R 約為 2.05 kΩ。
  - 請用 TT 實測斜率決定；首批在 L = 60 nm、R = 1.8 kΩ 時，核心電流是 41.8 µA（SS）。
- 05 的 P_series_headroom 是 −73 mV：PMOS 鏡輸出若要等於 VBP，串接元件沒有空間，物理上做不到。N 側有 260 mV 的空間，可以加疊接。
- 啟動支路正常退出（kick 約 0.0006 µA）。GMSQSTOFF0 仍有 1.80 µA。

三、原生 OTA 加理想 Iref 310.714 µA（目標 4.35 mA/腿，單組 cb0）

| corner | 每腿電流 | 追蹤誤差 | replica − ref | OTA 輸出 VGB | 56 GHz Hdd | 相對理想 | 增量（相對 r3） | 偏壓支路 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SS/85/0.81 | 4.087 mA | −6.06% | +8.69 mV | 0.426 V | −24.82 dB | −1.85 dB | +7.16 mW | 0.54 mW |
| FF/−40/0.99 | 4.523 mA | +3.98% | −5.72 mV | 0.375 V | −19.61 dB | −0.69 dB | +9.66 mW | 0.70 mW |

- 增益與功耗：SS 只剩 0.15 dB 的增益餘裕，FF 只剩 0.34 mW 的功耗餘裕。兩邊都通過，但都靠近邊界，而且誤差的方向相反（SS 偏低、FF 偏高），把兩端的餘裕都吃掉了。
- 追蹤誤差 4–6% 超過 2% 的工程診斷值。OTA 全部元件都在 region 3（次臨界）。
  - 負載鏡 OPM 與 OPD 的電流不相等：SS 3.95 對 3.48 µA，FF 4.83 對 5.50 µA。
  - 輸入對 ID 與 IR 也不相等：SS 7.89 對 6.95 µA，FF 9.66 對 11.0 µA。
  看起來是系統性 offset（負載鏡 VDS 不相等）加上低增益造成的。
- 偏壓支路的功耗是 0.54／0.70 mW，比舊預留 0.4 mW 高，但已經量入上表的增量。
- XT2：SS 仍是 6.6 mV（VDS 0.226、VDSAT 0.219），FF 為 191 mV。

四、判讀
1. Iref：鏡的問題用 L120 大致解決（≤6%）。剩下的是核心 R 的選值，加上 NMOS 側 VDS 帶來約 6%。PMOS 側無法用串接來做等 VDS。
2. OTA：可以運作，但 4–6% 的系統性誤差把 SS 的增益與 FF 的功耗都推到邊界。即使 Iref 完全準確，整合版也只是勉強通過。

五、請你判斷（設計工作）
- 依 TT 實測重選核心 R，讓核心電流等於 31.07 µA。NMOS 1:10 鏡加疊接，或用 OTA 讓 ND_OUT 等於 VBN（N 側有 260 mV 空間）。
- OTA：提高增益（例如長通道、讓輸入對離開深次臨界），讓負載鏡的 VDS 對稱（或加疊接），把 replica − ref 壓到 ≤ 2–3 mV，也就是追蹤誤差 ≤ 2%。
- 待批准的 6–12（SS／FF 的 long／matched 與 TT R bracket）：建議等 R 和鏡的修正版出來，再只提最小的 smoke 組合。下一批需要使用者另外批准。
- 請確認 SS 的增益餘裕（0.15 dB）是否需要把目標電流稍微往上調，並同時看 FF 的功耗餘裕。
