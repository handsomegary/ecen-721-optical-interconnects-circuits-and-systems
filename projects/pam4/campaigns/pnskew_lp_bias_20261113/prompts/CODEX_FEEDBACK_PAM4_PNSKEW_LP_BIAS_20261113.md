【ECEN 721 #6 P/N deskew LP_BIAS（0–77）：30 個參考案完成；48 個偏壓掃描案 Spectre 都完成，但收集器因 save 名稱錯誤而失敗，請修正】

一、執行
- 套件（ZIP SHA c818001f…）：SHA256SUMS 全部通過，`lp_bias.py --mode verify` 通過，30 項離線測試通過。
- 審查 deck 索引 0、6、30、42、50、54：bench.scs 與 portable 相同，corner 與 parent_diff 只差模型根路徑，case.json 只多了 model_preflight 與 staged_source_sha256。
- 提交前檢查：家目錄剩 35 GB。使用者批准 0–77（stage bias），預算維持 +10／+14 mW。
- job 753756 的結果：
  - 0–29 共 30 案 COMPLETED。
  - 30–77 共 48 案 FAILED，每案 2–3 秒。

二、失敗原因（48 案相同）
- Spectre 本身正常完成：「spectre completes with 0 errors, 5 warnings」，raw 也齊全（acResponse.ac、dcOp.dc、dcOpInfo.info、noiseResponse.noise）。
- spectre.log 的初始設定出現：
  - `WARNING (SPECTRE-8059): 'GMSRIREF': 'p' No such output parameter, terminal, or internal node name.`
  - `WARNING (SPECTRE-8282): In save statement, 'GMSRIREF:p' is not found and skipped. 'GMSRIREF' is not a valid instance.`
- bench 中 `GMSRIREF (GMSR_REF 0) isource dc=0.0003` 在頂層，但 Spectre 不接受用 `GMSRIREF:p` 存它的端電流，所以 dcOp.dc 裡沒有這個量。
- case.json 的 `DC_currents` 包含 `GMSRIREF:p`。`gm_select.collect` → `ac_next.trace(dc, 'GMSRIREF:p')` 因此 KeyError，measurements／completion 沒有寫出。
- 同時出現的 notice：`Only one connection to node 'GF_CTL'`，請一併確認是否預期。

三、處理
- 我沒有修改你的程式；approval 綁定這版 plan 與 manifest 的 SHA。
- 30 個完成案的 raw（135 個檔、329 MB）已核對量測後退休，每案留有收據。
- 48 個失敗案的 raw 保留在 Olympus（約 290 MB，目前剩 34 GB），讓修正後的收集器可以直接從 raw 重新收集，不必重跑 Spectre。

四、已完成的參考案（Rs = 25 Ω；與 LP_NEXT 0–53 逐值一致，可作重現確認）

| corner | 驅動 | cb | 56 GHz Hdd | 總功耗 |
| --- | --- | ---: | ---: | ---: |
| SS | bypass | 0 | −25.35 dB | 7.79 mW |
| SS | idealz50 | 0／2 | −22.97／−20.82 dB | 7.79／7.95 mW |
| SS | shared14lo120z50（原固定偏壓） | 0／2 | −23.80／−21.66 dB | 17.42／17.58 mW |
| TT | bypass | 0 | −23.30 dB | 10.08 mW |
| TT | idealz50 | 0／2 | −20.87／−18.72 dB | 10.08／10.25 mW |
| TT | shared14lo120z50 | 0／2 | −20.85／−18.66 dB | 23.41／23.59 mW |
| FF | bypass | 0 | −21.38 dB | 13.23 mW |
| FF | idealz50 | 0／2 | −18.91／−16.72 dB | 13.23／13.42 mW |
| FF | shared14lo120z50 | 0／2 | −18.21／−15.95 dB | 31.88／32.07 mW |

偏壓掃描（4.2／4.5／4.7／5.0 mA）的結果目前沒有，所以這批要回答的「是否有單一設定能同時滿足 2 dB 與 +10／+14 mW」仍未回答。

五、請你處理
- 修正 GMSRIREF 的電流量測，例如：
  - 從 DC_currents 移除 `GMSRIREF:p`，改記錄設定值 0.3 mA（理想電流源）；
  - 或在 iref 支路串一個 0 V vsource，改存它的電流；
  - 或改用 Spectre 可接受的 isource 端電流名稱。
  請一併檢查其他新增的 `:p` 存檔名稱。
- 最好提供只重新收集的模式（collect-only）：讀取保留的 48 個 raw，產生 measurements／completion，不重跑 Spectre。若不行，就給新套件與重跑方式。這兩種都需要新的使用者批准，因為 package SHA 會改變。
- 離線測試沒有抓到 save 名稱在 Spectre 中無效的問題；請考慮加一項測試，比對 save 名稱與 instance 型別。
