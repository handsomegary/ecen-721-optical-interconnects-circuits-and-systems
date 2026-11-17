【ECEN 721 #6 P/N deskew LP_NEXT power（0–53）：shared14lo120z50 的增益最好、雙組功耗不加倍，但 TT／FF 的驅動功耗超出已核定預算】

一、執行
- 套件（ZIP SHA 0c8a8ef3…）：SHA256SUMS 全部通過，`lp_next.py --mode verify` 通過，24 項離線測試通過。
- 審查 deck 索引 0、6、8、14、16、18、36：bench.scs 與 portable 相同（018 只差路徑），corner 與 parent_diff 只差模型根路徑，case.json 只多了 model_preflight 與 staged_source_sha256。
- 使用者批准 0–53（stage power），預算維持：以各 corner 的原 r3 AFE 為基準，單組 +10 mW、雙組 +14 mW。
- 第一次提交（job 753476）的 54 案全部 FAILED：Olympus 家目錄 50 GB 配額被其他專案用滿，與本套件無關，也沒有產生任何輸出。空間釋放到 35 GB 後，重新核對套件 SHA，以同一份 approval 重送（job 753611），54/54 COMPLETED，next_summary 沒有 invalid 案例。
- raw（243 個檔、652 MB）已用相同的量測核對條件退休，每案留有收據。
- 摘要：next_power.json（27 列，P/N 成對）。

二、結果（Rs = 25 Ω；「相對理想」指同 corner、同 cb、同 Z0 的理想驅動）

| corner | 驅動 | Z0 | cb | 56 GHz Hdd | 相對理想 | 56/7 GHz | 增加功耗（相對 bypass） | 預算 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| SS | lp14lo120 | 25 | 0 | −24.71 dB | −1.75 dB | −2.91 dB | +9.68 mW | 通過（單組） |
| SS | shared14lo120z50 | 50 | 0 | −23.80 dB | −0.83 dB | −2.19 dB | +9.63 mW | 通過（單組） |
| SS | lp14lo120 | 25 | 2 | −22.85 dB | −2.05 dB | −4.66 dB | +19.43 mW | 超出（雙組 14） |
| SS | shared14lo120z50 | 50 | 2 | −21.66 dB | −0.84 dB | −3.79 dB | +9.80 mW | 通過（雙組） |
| TT | lp14lo120 | 25 | 0 | −21.69 dB | −0.84 dB | −2.66 dB | +13.37 mW | 超出（單組 10） |
| TT | shared14lo120z50 | 50 | 0 | −20.85 dB | +0.02 dB | −2.02 dB | +13.33 mW | 超出（單組 10） |
| TT | lp14lo120 | 25 | 2 | −19.85 dB | −1.17 dB | −4.65 dB | +26.85 mW | 超出 |
| TT | shared14lo120z50 | 50 | 2 | −18.66 dB | +0.06 dB | −3.80 dB | +13.51 mW | 通過（雙組） |
| FF | lp14lo120 | 25 | 0 | −18.98 dB | −0.11 dB | −2.78 dB | +18.67 mW | 超出 |
| FF | shared14lo120z50 | 50 | 0 | −18.21 dB | +0.70 dB | −2.22 dB | +18.65 mW | 超出 |
| FF | lp14lo120 | 25 | 2 | −17.12 dB | −0.45 dB | −4.92 dB | +37.49 mW | 超出 |
| FF | shared14lo120z50 | 50 | 2 | −15.95 dB | +0.77 dB | −4.12 dB | +18.84 mW | 超出 |

- 各 corner 的 bypass 總功耗：SS 7.79、TT 10.08、FF 13.23 mW。理想驅動 cb=2 只多約 0.17–0.19 mW（尾電流）。
- 最差導通裕度：SS 為原 r3 第二級尾管 XT2p0／XT2m0（cb=0 時 6.6 mV，cb=2 時 2.3 mV）；TT／FF 為新輸入對尾管 GMSAPT0／GMSAMT0（51–111 mV）。SS 在 cb=2 時只剩 2.3 mV，需要注意。
- codebooks 為空，這批沒有細調。

三、判讀
1. 增益：shared14lo120z50 在三個角落都優於 lp14lo120。相對理想，SS 約 −0.83 dB，TT 約 0，FF 約 +0.7 dB，也都在 2 dB 判準內。lp14lo120 在 SS cb=2 為 −2.05 dB，已略超過判準。
2. 功耗：shared 版雙組與單組幾乎相同（共用一個驅動），這是正確方向。lp14lo120 雙組則接近加倍。
3. 但驅動電流會隨 corner 上升：SS +9.6 mW、TT +13.3 mW、FF +18.7 mW。所以即使是 shared 版，在 TT／FF 的單組啟用也超出 +10 mW，FF 的雙組也超出 +14 mW。目前沒有任何候選在三個角落都通過預算。
4. 高頻 tilt：驅動版的 56/7 GHz 比理想差約 2–3 dB（cb=2 時約 3–4 dB）。這部分最後要在時域用 FFE 後的 SER 確認。

四、請你判斷（設計工作）
- 讓驅動功耗不隨 corner 上升：例如以參考電流或 replica 偏壓固定驅動電流，或用 corner 追蹤的尾電流，使 TT／FF 的增量也落在預算內；同時確認 SS 下的增益與頻寬仍可接受。
- 以 shared14lo120z50 為主線（增益最好、雙組不加倍），把它的單組與雙組功耗壓進 +10/+14 mW。若做不到，請明確說明理由，並提出需要使用者重新核定的預算數字。
- SS cb=2 的 r3 第二級尾管只剩 2.3 mV 裕度，請評估是否需要調整。
- 下一批（endpoint、passive 電感、細調）建議等功耗問題解決後再提出，屆時需要使用者另外批准。
