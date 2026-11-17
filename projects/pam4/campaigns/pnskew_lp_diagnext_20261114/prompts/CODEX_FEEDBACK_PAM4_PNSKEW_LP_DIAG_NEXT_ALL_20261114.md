【ECEN 721 #6 P/N deskew LP_DIAG NEXT 0–21：22 案全部完成。TT／FF 啟動 6 案與三角落擾動 3 案都通過；replica STB 在 TT／FF 穩定（PM 90.6°／101.4°），但 1 GHz 掃頻內沒有 GM，被標為 review；beta 六案 max |T| 為 0.498–0.505（儲備約 6 dB），仍是 review；XT2 在 0.4／0.2 Vppd 下會短暫進入 triode（−7.7／−2.9 mV），但全幅對半幅的增益只差 0.10 dB】

一、執行
- 套件（ZIP SHA 68d23418…）：SHA256SUMS 全部通過，`diag_next.py --mode verify` 通過，88 項離線測試通過。
- 審查 deck 0、19：bench 與 portable_review 完全相同，corner 只差模型根路徑，case.json 只多了 model_preflight 與 staged_source_sha256。
  - 0 和舊 DIAG 12 比：只把掃頻從 1 GHz 改成 20 GHz（每十倍頻 100 點）。
  - 19：電源保持額定，在 GMSR_REF 注入 +5 µA（5 µs）與 −5 µA（15 µs），各約 200 ns，tran 25 µs。這是注入在 replica 的參考節點，不是 beta 核心內部。
- 使用者先批准 0、19（job 754151），之後批准其餘 1–18、20–21：
  - 1–17、20–21：job 754153；
  - XT2 18：job 754172。我先確認 17 的 16 顆尾管 OP 都有收到，再送 18。
  - 22／22 COMPLETED，22 份 completion 都有寫出，invalid 與 missing 都是 0。
  - 執行時間：STB 約 2 秒；啟動 31–32 秒；重啟 63–64 秒；XT2 33–34 秒；擾動 8 秒。
- run root 在送出前就建好，路徑直接傳入，沒有再出錯。raw 保留在 Olympus。

二、結果
1. 啟動（11–16，TT／FF 的快速、慢速、重啟，cb0）：6／6 pass，所有檢查都是 true。
   - TT：Iref 324.78 µA（目標 324.8），伺服誤差 0.006%，kick 0.0006 µA。
   - FF：Iref 307.10 µA（目標 307.1），伺服誤差 0.16%，kick 約 0。
   - 重啟案的斷電約 50.4 µs，之後重新收斂。
   - 加上先前 SS 的 0／1／2，三角落的啟動都驗證完成。
2. 擾動（19–21，cb2）：3／3 pass。正負脈衝前、後的參考誤差與伺服誤差都和擾動前相同，啟動支路沒有被重新觸發。
   - 脈衝期間的參考電流範圍：SS 333.5–343.2 µA，TT 319.9–329.6 µA，FF 302.2–312.0 µA。
3. replica STB（6–10）：

| 案 | 狀態 | PM（頻率） | GM | Spectre 原生判定 |
| --- | --- | --- | --- | --- |
| 06 SS cb0 | pass | 84.03°（10.34 MHz） | 19.63 dB（513 MHz） | stable，兩個 margin 都有 |
| 07 TT cb0 | review | 90.58°（14.83 MHz） | nan | stable，no gain margin（相位沒有到 0°） |
| 08 TT cb2 | review | 90.58°（14.83 MHz） | nan | 同上 |
| 09 FF cb0 | review | 101.42°（21.42 MHz） | nan | 同上 |
| 10 FF cb2 | review | 101.42°（21.42 MHz） | nan | 同上 |

   - 07–10 被標為 review，原因是收集器的 "Expected a finite real value"：replica STB 仍只掃到 1 GHz，而 TT／FF 的相位在 1 GHz 內沒有到 0°，所以 GM 是 nan。這是掃頻範圍和收集器判準的問題，不是不穩定。請把 replica STB 也延伸到 20 GHz，或定義「掃頻內相位沒到 0°」時的判定方式（例如回報 1 GHz 處的 |T| 與相位）。
4. beta STB（0–5，延伸到 20 GHz）：6／6 review。

| corner | max \|T\| | 儲備 | min \|1−T\| | 20 GHz 的 \|T\| |
| --- | ---: | ---: | ---: | ---: |
| SS（cb0／cb2） | 0.5048 | 5.94 dB | 0.4952 | 0.0137 |
| TT（cb0／cb2） | 0.5050 | 5.93 dB | 0.4950 | 0.0148 |
| FF（cb0／cb2） | 0.4983 | 6.05 dB | 0.5017 | 0.0159 |

   - 掃頻已涵蓋低頻平台與高頻衰減（high_frequency_rolloff 為 true），Spectre 原生判定都是「always stable」。
   - 但三角落的儲備都只有約 6 dB，沒達到 10 dB 篩選。cb0 與 cb2 的結果完全相同。
   - summary 的 beta_formal_stability_verified 為 false。
   - 擾動案（19–21）與重啟案顯示偏壓受擾動後會恢復。
5. XT2（17／18，SS cb2，原 Vb2）：

| 擺幅 | 最小裕度 | 位置 | region | 負裕度的時間比例 |
| --- | ---: | --- | --- | ---: |
| 0.4 Vppd | −7.7 mV | XT2m0–7（p 側 −6.4 mV） | 1（triode） | 32.4% |
| 0.2 Vppd | −2.9 mV | XT2m0–7（p 側 −2.3 mV） | 1 | 26.5% |

   - 全幅對半幅的增益變化只有約 −0.10 dB（X_c、X_o、held_at_clock_fall 三個平面都一樣），看不出明顯的壓縮。
   - 依你的條件「低裕度伴隨可重現的壓縮或取樣失真，才試 0.575／0.570 V」，目前看來不需要調 Vb2。請確認 0.10 dB 是否在你的接受範圍內，再一併檢查取樣後的失真指標。

三、判讀
- 啟動與擾動恢復：三角落全部通過。
- replica 迴路：SS 正式通過；TT／FF 實際上穩定（PM ≥90°），只差掃頻／判準。
- beta：電路行為一致（|T| 約 0.5，是 beta multiplier 的特性），剩下的是判準問題：10 dB 篩選要保留還是調整。若保留，就需要改電路來降低迴路增益。
- XT2：雖然短暫進入 triode，但對增益影響約 0.1 dB。

四、請你處理
- replica STB 延伸到 20 GHz，或定義沒有 GM 時的判定方式，再用 collect-only 或重跑 07–10（需要新的批准）。
- 對 beta 給出最終判準（例如以 min |1−T| ≥ 0.4 加上擾動恢復），或提出降低迴路增益的修改。
- XT2：說明 0.1 dB 的增益差是否可以接受。若可以，就維持 0.580 V。
- 之後進入非理想電感、正負端點、細碼接縫、時域 SER（長案）。請分批提出，需要使用者另外批准。
