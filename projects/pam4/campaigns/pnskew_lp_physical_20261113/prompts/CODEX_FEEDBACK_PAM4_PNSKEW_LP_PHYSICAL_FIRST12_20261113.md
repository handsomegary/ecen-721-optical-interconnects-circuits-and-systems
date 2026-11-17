【ECEN 721 #6 P/N deskew LP_PHYSICAL 首批 12 案：全部完成，但原生 Iref 偏離目標太多（SS +68%、FF +215%），整合版在 SS／FF 都超出功耗預算。依停止條件，沒有擴跑】

一、執行
- 套件（ZIP SHA 16a3beb3…）：SHA256SUMS 全部通過，`physical_bias.py --mode verify` 通過，54 項離線測試通過。
- 審查 deck 索引 0、12、54、62：bench.scs 與 portable_review 完全相同，corner 與 parent_diff 只差模型根路徑，case.json 只多了 model_preflight 與 staged_source_sha256。
- 054 的原生網表（beta multiplier、1:10 鏡、啟動支路、OTA、Miller 3 kΩ／2 pF、RF 100 kΩ／10 pF）與 DESIGN 一致。所有 `:p` save 都在 vsource 上，GF_CTL 已移除。小事：區塊註解仍寫「ideal reference and servo」。
- 使用者批准 0–3、12–15、54–55、62–63（stage core）。job 753906 共 12 案 COMPLETED，每案 2–6 秒，12 案都有 completion，summary 沒有 invalid。
- Spectre：0 errors，3 warnings 都是模型檔 scalefactor 重複指定（SFE-1131），與過去相同。
- raw 依你的指示保留在 Olympus，沒有退休。

二、結果
1. 參考案：SS bypass −25.353 dB、SS idealz50 −22.966 dB、FF bypass −21.376 dB、FF idealz50 −18.915 dB，與 LP_BIAS 逐值一致。
2. 整合版 native_both（目標 4.35 mA/腿，Iref 310.7 µA）：

| corner | Iref | 每腿電流 | 追蹤誤差 | 56 GHz Hdd | 相對理想 | 56/7 GHz | GFVDD | 增量（相對 r3） | 預算 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| SS/85/0.81 | 521.7 µA | 6.96 mA | +60% | −23.48 dB | −0.51 dB | −2.37 dB | 12.23 mW | +12.23 mW | 超出 10 |
| FF/−40/0.99 | 978.1 µA | 13.49 mA | +210% | −18.72 dB | +0.19 dB | −3.20 dB | 28.86 mW | +28.86 mW | 超出 10 |

- 偏壓支路本身（non_main_driver_rail）：SS 0.95 mW，FF 2.14 mW，都比舊的 0.4 mW 預留大。
- 增益看起來好，只是因為電流變大，不能當作通過。

三、哪裡出錯（工作點）

| 位置 | SS | FF |
| --- | --- | --- |
| beta multiplier 核心（GMSQRS／1.8 kΩ） | 41.8 µA（目標 31.07 µA 的 1.35 倍） | 48.9 µA（1.57 倍） |
| PMOS 1:1 鏡（RPD 對 RPM，每指） | 20.9 → 23.7 µA（+13.5%），VDS 0.354 對 0.421 V | 24.5 → 45.9 µA（+88%），VDS 0.350 對 0.549 V |
| NMOS 1:10 鏡（RND0 對 RNM，每顆） | 47.5 → 52.2 µA（+10%），VDS 0.389 對 0.569 V | 91.8 → 97.8 µA（+6.6%），VDS 0.441 對 0.538 V |
| 最後的 Iref | 521.7 µA | 978.1 µA |

- 誤差的來源有三個，而且會相乘：
  - 核心電流本身就偏高。
  - L = 30 nm 的 PMOS 1:1 鏡因 VDS 不相等，有很大的 DIBL／CLM 誤差；FF 時幾乎加倍，是最大的單一來源。
  - NMOS 1:10 鏡的 VDS 不相等。
  這正是 DESIGN 預先提到的短通道 VDS 風險，而且比預期大很多。
- 整個 beta multiplier 和 OTA 都在 region 3（次臨界），所以電流對 Vth 和溫度很敏感。
- replica 迴路本身正常：GMSR_D 對 GMSR_REF 只差 11.3 mV（SS）和 6.5 mV（FF），每腿電流對 Iref 的比值約 13.3–13.8（設計值 14）。問題在參考電流，不在 OTA。
- 啟動支路有退出：GMSQSTON0 的 Vgs 只有 2–3 mV，kick current 小於 0.01 µA。但 GMSQSTOFF0 一直吃約 1.6–2.0 µA，請確認這是否是預期的靜態漏電。
- SS 的 XT2 裕度仍是 6.6 mV（cb=0），FF 為 191 mV。

四、判讀
1. 依停止條件（工作點不成立），這批停在首批，沒有擴跑 TT、cb=2、trim 66–89 或補償 90–101。startup／STB 的診斷 deck 也還沒有審查。
2. 架構上，原生參考的「絕對值」和「跨角落的變化」都無法接受。只調 R trim 救不回 FF 的 +210%，因為 PMOS 鏡會隨 corner 改變比例。

五、請你處理（設計工作）
- 把 PMOS 1:1 鏡和 NMOS 1:10 鏡改成長通道（例如 L ≥ 4–10 倍最小值）或疊接（cascode），並讓兩邊的 VDS 相等（例如加 VDS 匹配的疊接，或用 OTA 強制）。先在單獨的 Iref deck 量 SS／TT／FF 的 Iref，目標是誤差在 ±2–5% 以內。
- 重新計算 beta multiplier 的 R，讓核心電流在 TT 等於 Iref／10。如果要把 Iref 做成近似與溫度無關，可以考慮 bandgap 或 PTAT＋CTAT 組合，或改用「外部（或校正後）參考加 1 個 trim」的方案，並寫明 trim 的範圍。
- 偏壓支路本身在 FF 吃 2.14 mW。請在修正後重估 SS／TT／FF 的 non-main 功耗。如果超過約 0.4 mW，請說明它要怎麼放進 +10／+14 mW 的預算。
- 考慮先跑 native_ref only（30–41）和 native_ota only（42–53）分開驗證，以分清楚誤差來源。下一批請只提出修正後的少數 smoke 案，需要使用者另外批准。
- 請確認 GMSQSTOFF0 的 1.6–2.0 µA 靜態電流是否可以接受。
