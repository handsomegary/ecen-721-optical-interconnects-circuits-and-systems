【ECEN 721 #6 P/N deskew LP_GMTAP SWITCH64 復原包 f648e60c：
- 密頻 AC 正式通過：FF 0↔±1 是 0.4947874 ps，餘量 5.21 fs。
- 48／49 只做收集，復原成功。
- 50–86 共 37 案：35 案完成。19 個有對照的切碼全部 observed_recovery、settled＝true，最長恢復 2.65 ns（FF 0→−60 這類端點跳碼）。
- 84、86（帶 ±4.46 ps 偏斜的端點跳碼）在 13.0／13.4 ns 撞到 runner 的 512 MiB 單檔上限，Spectre 中止，沒有量測。
- 建議：靜態碼表加切碼到此視為足夠。只補 84、86 這兩案，就可以進 C0，不另開其他補驗】

一、執行
- 套件 SHA f648e60c…：SHA256SUMS、verify（87 份 deck）、217 項測試都通過；plan 和舊包逐位元相同，ORIGINAL_SWITCH64_SHA256SUMS 和舊包的 SHA256SUMS 相同。
- 和舊包的差異只在這些檔：
  - gm_switch64_dense.py、gm_switch64_metrics.py；
  - 新增 gm_switch64_psf.py、recover_switch64.py；
  - 對應的測試與文件。
- 密頻：`--mode summarize` 輸出 lp_gm_switch64_dense_rechecked.json，沒有重跑模擬。
- 48／49：
  - snapshot 後在計算節點串行 collect-only（srun 1 CPU／4 GB）：兩案共 2 分 10 秒，峰值 RSS 300 MB；
  - 用原本的 approval_sw64_0_86.json；
  - 輸出 lp_gm_switch64_smoke_recovered.json。
- 50–86：
  - 新 approval 綁定同一個 plan SHA a2f8774d… 與新的 SHA256SUMS SHA 759c951d…，stages 是 hold、switch；
  - job 757597，--array=50-86%6，--mem=6G；
  - 35 案 COMPLETED（每案 5.6–6.5 分鐘），84、86 FAILED。
- 全部 summary：lp_gm_switch64_full_0_86.json。

二、密頻 AC（正式）
- FF_dense.status＝passes_nominal_dense_recheck，四個 profile 都有效，invalid／missing 都是空的。

| 邊 | base100 | grid200 | grid400 | tight400 | 餘量 | 最後密度差 | solver 容差差 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ±1↔0 | 0.4947919 | 0.4947883 | 0.4947874 | 0.4947874 | 5.213 fs | 0.0009 fs | 0 |
| ±2↔±1 | 0.2631103 | 0.2631089 | 0.2631085 | 0.2631085 | 236.9 fs | 0.0003 fs | 0 |

- 和診斷版逐值相同。名義數值餘量是真的；失配與版圖寄生留到後面另外處理。

三、切碼暫態（19 組有對照的切碼；hold 參考全部 stationary）

| 切碼 | 角落 | 恢復（事件後） | Vb1 最大偏差 | held 最大差 | 恢復後最少取樣／lane |
| --- | --- | ---: | ---: | ---: | ---: |
| 0→+1、0→−1 | SS | 66 ps | 1.03 mV | 1.5 mV | 153 |
| +1→+2 | SS | 151 ps | 1.17 mV | 0.7 mV | 151 |
| +2→+1 | SS | 594 ps | 2.07 mV | 0.6 mV | 145 |
| +52→+56 | SS | 306 ps | 1.40 mV | 0.7 mV | 149 |
| 0→+32 | SS | 1.97 ns | 11.6 mV | 6.9 mV | 126 |
| 0→+60、+60→−60、−60→0 | SS | 2.48–2.52 ns | 22.3–23.2 mV | 4.0–6.6 mV | 118–119 |
| 同上 | TT | 2.55–2.58 ns | 24.4–25.3 mV | 6.0–11.7 mV | 117–118 |
| 同上 | FF | 2.62–2.65 ns | 26.7–27.6 mV | 9.7–14.1 mV | 116–117 |
| 0→+1、+1→+2 | FF | 203／303 ps | 1.25／1.44 mV | 3.9／1.5 mV | 149–151 |
| +60→−60＋2 ps offset | SS | 2.49 ns | 22.3 mV | 6.3 mV | 119 |
| +1→+2＋2 ps offset | FF | 303 ps | 1.44 mV | 1.7 mV | 149 |

- largest_observed_recovery_after_last_edge_s＝2.648 ns（FF −60→0）。
- 小碼距（±1、±2、52→56）在 0.6 ns 內恢復。大跳碼的恢復時間由 Vb1 的 2 pF／分壓器 RC 決定（偏差 22–28 mV）。
- C0 的切碼空窗建議用 ≥3 ns，或規定只切相鄰碼。這由你決定，不用再為此加跑。
- XT2 時域：
  - SS 的 16 顆 XT2 在時域大訊號下有 16–37% 的時間不在飽和區，最小裕度到 −8.9 mV（+32）、−4.0 mV（+56）；TT／FF 都是 0%，最小 87／172 mV。
  - 參考 hold 案的數字逐位元相同（差 <0.001 mV）。所以這是 SS 訊號擺幅本身的特性，不是切碼造成的；靜態 OP 仍是 region 2。
  - 不建議為此再改偏壓。C0 的 SER 會直接反映它有沒有影響，到時以 SER 判斷。

四、84、86 失敗
- 84 ss_switch_p00_m60_latep、86 ff_switch_p00_p60_laten：codeSwitch.tran.tran 剛好 536,870,912 B（512 MiB）時，Spectre 在 13.04／13.41 ns 報 USIMUWI-20006 "not enough virtual memory"，接著 FATAL 中止。
- 對照 83、85（同樣偏斜的 hold）有完成，也有 measurements。
- 原因：偏斜讓時間步變多，PSF 超過 runner 的單檔上限。
- 請只修這一點，擇一：
  - 把這兩案的單檔上限提高到約 640 MiB（collector 已經改成串流，RSS 只有約 300 MB）；
  - 或只對這兩案降低輸出點數。
  其餘 35 案不用重跑。

五、判讀與建議
1. 密頻 AC 和 17 組無偏斜加 2 組偏移的切碼都通過，靜態碼表與切碼行為到此視為足夠。
2. 剩下的 84、86 只是確認偏斜下的端點跳碼。預期會和無偏斜的 2.5–2.65 ns 相近，補跑一次就好。
3. 使用者的原則：不要為了很小的差異一直修。所以：
   - FF 5.2 fs 餘量接受，不加 1/128；
   - SS XT2 時域裕度交給 C0 SER 判斷；
   - 尾電流維持只作診斷。
4. C0 不急。84、86 補完後，請在準備好時提 C0，附每案時間、raw 大小與切碼空窗的設定。

六、空間
- run root 7.1 GB，家目錄只剩 7.4 GB（共用配額）。
- commit 後依規則退役已分析的 raw：
  - 密頻 0–47；
  - 有 measurements 的 48–82；
  - 保留 83–86（失敗案與它們的對照）。
- 預計可回收約 6 GB。
