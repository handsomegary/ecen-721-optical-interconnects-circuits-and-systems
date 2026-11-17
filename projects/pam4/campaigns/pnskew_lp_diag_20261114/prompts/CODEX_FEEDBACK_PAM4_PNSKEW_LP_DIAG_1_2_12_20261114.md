【ECEN 721 #6 P/N deskew LP_DIAG 1／2／12：SS 慢速上電與掉電重啟都通過；beta multiplier STB 為 review：max |T| = 0.505（儲備 5.94 dB），未達 10 dB 保守篩選，掃頻也沒涵蓋高頻衰減】

一、執行
- 使用者批准以修正後的收集器執行 1、2、12（stages startup、stb）。
  - 套件：recovery_pkg（manifest 0f709eb9…）；plan：diagnostic_plan（b74093eb…）。
  - 新的 run root 是 campaign 下的 run2；approval 放在套件外。
- 第一次提交（job 754145）時，我的 wrapper sed 寫錯，RUN_ROOT 變成不存在的 run22。三案在 0 秒內 FAILED（realpath FileNotFoundError），沒有執行 Spectre，也沒有建立任何檔案。已 scancel，改用明確路徑重寫 wrapper。
- 重送（job 754148）：
  - 1：COMPLETED，32 秒；
  - 2：COMPLETED，1 分 4 秒；
  - 12：COMPLETED，3 秒。
  三案 Spectre 都是 0 errors，completion 也都有寫出。
- `diag_summary.py --run-root run2 --recovery-root run` 已執行，invalid 為 0；其餘 PVT 案列為 missing。
- raw 保留在 Olympus。

二、結果
1. 案 1（SS 慢速上電，cb0）：pass。
   - 五項檢查全部 true。
   - 判定窗 475–500 µs：Iref 338.335 µA，replica 337.812 µA，伺服誤差 −0.155%，kick 0.00465 µA。
   - 初始 kick 峰值 0.0145 µA，發生在 24.4 µs；當時 GF_VDD 0.198 V，GMSQST 0.121 V。
2. 案 2（SS 掉電重啟，cb0）：pass。
   - 七項檢查全部 true，包含 first_plateau_settled 與 restart_off_observed。
   - 第一次上電的平台（475–500 µs）就已收斂。之後斷電約 50.4 µs（2528 點）。
   - 重啟 kick 峰值 0.0512 µA，發生在 570.3 µs；當時 GF_VDD 0.222 V。
   - 重啟後的判定窗 1.025–1.05 ms：Iref 338.335 µA，伺服誤差 −0.155%，kick 0.00465 µA。
3. 案 12（SS cb2 beta multiplier STB）：review（依 BETA_CRITERIA 不算通過）。
   - 原生判定：「Gain(dB) is always less than zero. The loop is always stable. No gain margin or phase margin.」
   - 收集器：
     - 低頻 return 為 0.50476，相位 0°；
     - max |T| 為 0.50476（約 1.1 kHz）；
     - min |1−T| 為 0.4952；
     - sampled_gain_reserve 5.94 dB；
     - low_frequency_plateau 為 true，high_frequency_rolloff 為 false；
     - sampled_screen_pass 為 false。
   - 我從 betaSTB.stb 抽樣的 |T|：

| 頻率 | \|T\| | 相位 | \|1−T\| |
| ---: | ---: | ---: | ---: |
| 1 Hz–1 MHz | 0.5048 | 0° | 0.4952 |
| 10 MHz | 0.5047 | −0.7° | 0.4953 |
| 100 MHz | 0.5024 | −7.0° | 0.5050 |
| 302 MHz | 0.4840 | −20.6° | 0.5730 |
| 1 GHz | 0.3574 | −58.4° | 0.8681 |

   - DC Iref 338.335 µA，與整合版一致，啟動已釋放。

三、判讀
- 啟動：SS 的快速上電、慢速上電、掉電重啟三種情況都會離開零電流狀態，收斂到與 DC 相同的工作點，而且啟動支路會退出。SS 的啟動驗證完成。
- replica 迴路（案 11）通過。beta multiplier（案 12）：
  - 正回授迴路在非零工作點的增益約 0.5，與 beta multiplier 的理論一致（迴路增益小於 1，非零工作點才穩定）。
  - 因為整個掃頻範圍內 |T| ≤ 0.505，Nyquist 曲線不可能到達 +1，依 small-gain 理論是穩定的，Spectre 原生判定也是穩定。
  - 但儲備只有 5.94 dB，沒達到你設定的 10 dB（|T| ≤ 0.316）保守篩選；而且 1 GHz 時 |T| 仍有 0.357，掃頻沒涵蓋完整的高頻衰減。依 BETA_CRITERIA，這案維持 review。

四、請你判斷
- beta 的判準：
  - 10 dB small-gain 篩選對 beta multiplier 是否合理？它的非零工作點迴路增益本來就約 0.5，大約是 6 dB。
  - 或改用 |1−T| 的最小值（目前 0.495）作為主要指標，加上擾動後恢復（啟動的重啟案已顯示可以恢復）。
  - 若維持 10 dB，就需要改電路，例如加大退化電阻比或改變鏡比，來降低迴路增益。
- 掃頻上限延伸到 10–20 GHz，讓 high_frequency_rolloff 成立，並確認高頻沒有寄生路徑讓 |T| 回升。
- 下一批：TT／FF 的啟動（3–8）、其餘 STB（9、10、13–20）、XT2 有限擺幅（21–22）。請依上面的判準決定是否修改 deck，再提出，需要使用者另外批准。
