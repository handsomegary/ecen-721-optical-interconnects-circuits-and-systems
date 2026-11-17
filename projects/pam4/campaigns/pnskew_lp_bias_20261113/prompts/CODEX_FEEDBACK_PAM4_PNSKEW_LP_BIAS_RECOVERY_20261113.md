【ECEN 721 #6 P/N deskew LP_BIAS recovery（collect-only 30–77）：48 案全部復原；replica 偏壓 4.2 與 4.5 mA/腿在三個角落、單組與雙組都同時通過 2 dB 與 +10／+14 mW】

一、執行
- recovery 套件（ZIP SHA 4ff14e3d…）：SHA256SUMS 全部通過，`recover_bias.py --mode verify` 通過，43 項離線測試通過。
- 原 plan／manifest SHA（e1431e2c…／c12278bc…）與範本一致。recovery_manifest_sha256 為 606db7a3…，recovery_inputs_sha256 為 f96d08b9…。
- 使用者批准 collect-only 30–77。approval 放在套件外，case_ids 取自 RECOVERY_INPUTS（48 案）。沒有重跑 Spectre。
- 先跑 30／31：
  - 31 正常復原。
  - 30 被擋下：「Historical raw inventory differs」（原因見第二節）。
  - 依你給的檢查項核對 30 的 receipt：raw_files_verified = 5；completion.measurement_sha256 與 measurements.json 相符；GMSR_REF = 0.6714 V，與預期一致。
- 全部 48 案都已復原，78 案都有 completion.json。
- bias_summary 輸出 bias_0_77_recovered.json：39 列，invalid 為 0。missing 為 16 案（78–93 upper，未批准，符合預期）。
- raw（216 個檔、約 232 MB）已用相同的量測核對條件退休，每案留有收據。

二、問題：raw inventory 綁定了 st_dev，跨節點會失敗
- 30 的 raw 與紀錄只差 `device`（舊 61、現在 55）。bytes、sha256、mtime_ns、inode 全部相同，檔案沒有被動過。
- Olympus 家目錄是網路檔案系統，各節點看到的 st_dev 不同：
  - n02-hera = 61
  - n01-zeus 與 login = 55
- job 753756 的 78 案分配：n01-zeus 60 案、n02-hera 18 案。30–77 中有 9 案在 n02-hera 上跑：30、36、42、49、55、56、62、69、75。
- 處理方式：程式完全沒有改。
  - 這 9 案用 `srun -w n02-hera` 在原節點收集。
  - 其餘 39 案在 login（55）收集。
  - 兩邊都是同一份 approval 與套件，全部「recovered」。
- 建議：之後的 raw inventory 不要把 `device` 當作必要相等的欄位，只核對 bytes、sha256 與 mtime（必要時加 inode）。或者記錄節點名稱，在原節點收集。run_status.json 裡目前沒有 hostname，請一併加上。

三、結果（Rs = 25 Ω；「相對理想」指同 corner、同 cb 的 idealz50；增量是相對各 corner 原 r3 AFE；「含保留」是 bias_summary 加上 OVERHEAD_MW 之後的值）

| 目標 mA/腿 | corner | cb | 56 GHz Hdd | 相對理想 | 額外 tilt（56/7） | 增量 | 含保留 | 預算 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4.2 | SS | 0／2 | −24.74／−22.60 | −1.78／−1.79 | −1.20／−1.31 | 7.27／7.43 | 7.67／7.83 | 10／14 |
| 4.2 | TT | 0／2 | −22.19／−19.99 | −1.31／−1.27 | −1.77／−1.84 | 8.08／8.25 | 8.48／8.65 | 10／14 |
| 4.2 | FF | 0／2 | −19.81／−17.54 | −0.89／−0.81 | −2.42／−2.45 | 8.89／9.08 | 9.29／9.48 | 10／14 |
| 4.5 | SS | 0／2 | −24.54／−22.40 | −1.57／−1.58 | −1.26／−1.37 | 7.79／7.95 | 8.19／8.35 | 10／14 |
| 4.5 | TT | 0／2 | −21.99／−19.80 | −1.12／−1.08 | −1.83／−1.90 | 8.66／8.83 | 9.06／9.23 | 10／14 |
| 4.5 | FF | 0／2 | −19.63／−17.36 | −0.71／−0.63 | −2.48／−2.51 | 9.52／9.72 | 9.92／10.12 | 10／14 |
| 4.7 | FF | 0 | −19.52 | −0.61 | −2.51 | 9.95 | 10.35 | 超出 10 |
| 5.0 | FF | 0 | −19.37 | −0.45 | −2.57 | 10.58 | 10.98 | 超出 10 |

（4.7／5.0 的 SS、TT 與 FF cb=2 都在預算內。相對理想在 4.7 為 −1.44 到 −0.53 dB，在 5.0 為 −1.27 到 −0.38 dB。）

- tested_targets 的判定：
  - 4.2 與 4.5：all_six_provisionally_pass 為 true，all_six_meet_gain_and_tracking 為 true。
  - 4.7 與 5.0：provisional pass 為 false，只因 FF 單組含保留後超過 +10 mW。
- 電流追蹤：每腿實際電流在三個角落都是目標值的 99.66–99.7%（例如 4.186／4.187／4.188 mA），角落之間的差異小於 0.05%。偏壓閘極電壓會隨 corner 自動調整：4.5 mA 時 SS 0.437、TT 0.407、FF 0.374 V。驅動功耗隨 corner 上升的問題已解決。
- 和原固定偏壓（LP_NEXT）相比：
  - TT 單組增量從 +13.33 降到 +8.66 mW（4.5 mA）。
  - FF 單組從 +18.65 降到 +9.52 mW。
  - 代價是增益：相對理想，TT 從 +0.02 降到 −1.12 dB，FF 從 +0.70 降到 −0.71 dB。SS 在 4.5 mA 為 −1.57 dB，比固定偏壓的 −0.83 dB 差，因為 SS 的腿電流也被固定住了。
- 額外 group delay：7 GHz 時約 3.4–4.2 ps，55 GHz 時降到約 2.2–2.7 ps。這是兩腿的共同延遲。
- 最差導通裕度沒有改變：
  - SS 為原 r3 第二級尾管 XT2p0／XT2m0（cb=0 時 6.6 mV，cb=2 時 2.3 mV）。
  - TT／FF 為 GMSAPT0／GMSAMT0（51–111 mV）。

四、判讀
1. replica 定電流偏壓有效：驅動電流不再隨 corner 上升，4.2 與 4.5 mA/腿在 6 個條件都同時通過 2 dB 與 +10／+14 mW。這是第一次有單一設定在三個角落都通過兩項判準。
2. 4.5 mA 的增益較好（最差 SS −1.58 dB），但 FF 單組含保留只剩 0.08 mW 餘裕，任何寄生、真實 OTA 或電流鏡誤差都可能讓它超出預算。4.2 mA 的餘裕是 0.71 mW，最差增益為 SS −1.79 dB，距離 2 dB 判準只剩 0.21 dB。兩者都很接近邊界，只是邊界不同。
3. summary 標註 `actual_bias_OTA_verified: false`：Iref 是理想 300 µA 電流源，replica 迴路沒有用真實 OTA 或電流鏡驗證過。OVERHEAD_MW 只是估計值。上面的「通過」都屬於暫定。
4. SS cb=2 的 XT2 只剩 2.3 mV 裕度，這批沒有處理，仍然是風險點。
5. 先前提到的 notice「Only one connection to node 'GF_CTL'」：recover_bias.py 會刪除 GFVCTL 那一行，看起來你已經知道。請說明它在 driver／non-driver 兩種模式下是否都是預期行為。

五、請你判斷（設計工作）
- 選定主線電流（4.2 或 4.5 mA/腿，或兩者之間的值，例如 4.3–4.4），並說明理由：增益餘裕與功耗餘裕要怎麼取捨。
- 用真實元件實作 Iref／replica 迴路（OTA 或電流鏡、啟動電路），把它的功耗與 corner 下的追蹤誤差算進預算，取代 OVERHEAD_MW 估計值。
- 評估 SS cb=2 的 XT2 2.3 mV 裕度，是否需要調整原 r3 第二級的偏壓。
- upper 78–93 是否仍需要跑，請依這批結果決定。
- 之後的批次（endpoint、非理想電感、細調、時域 FFE 後的 SER）請照常提出，需要使用者另外批准。
- 請修正 raw inventory 的 st_dev 綁定（見第二節），並在 run_status 記錄 hostname。
