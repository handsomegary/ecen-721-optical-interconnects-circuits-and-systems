【ECEN 721 #6 C0 第 0 案（TT 零偏斜、碼 0）：模擬與收集都正常，但計分是隨機猜測的程度。primary SER 0.721（173／240），secondary 0.729，四階 ≈0.75 是亂猜。
診斷：凍結的歷史 lag 不適用於插入 gm-tap 之後的路徑。
- primary：凍結 lag 1 的取樣與符號相關係數只有 0.005；lag 3 時是 +0.753。
- secondary：凍結 lag 3 的相關係數是 −0.735，強相關但符號相反。
已停下，1–4 未送。請修對齊（和 secondary 的極性）】

一、執行
- ZIP SHA 05ec8f03…：
  - SHA256SUMS 通過；
  - ORIGINAL_C0_REVIEW_SHA256SUMS 和審查包相同；
  - 五份 deck 與 plan 逐位元不變（c0_review.py 改 23 行）；
  - `c0_run.py --mode verify` 通過；6 項測試通過。
- approval：五案，stages ["c0_fixed"]，plan SHA 14d5d7ca…，SHA256SUMS SHA 35d3c9d5…，依常態授權核准，並在 authorization_basis 註明。
- 五案都已 stage，模型根目錄已替換成私有 shrink 路徑。
- 第 0 案：job 757899（1 CPU／6 GiB／60 min）COMPLETED：
  - Spectre wall 2373 s（39.5 分鐘）；
  - 峰值 RSS 283 MB；
  - tranResponse.tran.tran 69.4 MB；
  - 0 errors，3 warnings（scalefactor），6 notices（GminDC 1 pS）；
  - runner 收集成功：measurements、recovery、completion 都有，measurement_complete＝true。

二、通過的檢查
- clock_audit：
  - 第一個 CK0 下降緣 138.50 ps，預期 138.45 ps；
  - 主時鐘 195 個下降緣，週期最大誤差 4.45 fs；
  - 次時鐘三組下降緣誤差 ≤0.118 ps；
  - 保留 1542 筆 primary＋secondary 紀錄。
- primary／secondary 各 256 個 ADC 輸入、240 個 FFE 計分符號，clipping 0，validation_fitting_performed＝false。

三、計分異常

| 讀出平面 | 凍結 lag | FFE 後 SER | 三門檻 SER | RMSE（符號單位） | 峰對峰 |
| --- | ---: | ---: | ---: | ---: | ---: |
| primary | 1 | 0.721（raw）／0.725（7-bit） | 0.721 | 2.55 | 51 mV |
| secondary | 3 | 0.729／0.729 | 0.542 | 2.48 | 28 mV |

- primary 各符號的取樣平均：
  - 0：−0.28 mV；
  - 1：−1.02 mV；
  - 2：−2.46 mV；
  - 3：+0.82 mV。
  四階完全沒有分開，標準差 9.5–11.3 mV；混淆矩陣接近均勻；detector_training_class_order_valid＝false。

四、診斷（唯讀，未改套件；diag/lag_scan.py）
- 方法：用 c0_review 同一套 extract_records 與 aligned_window，對 lag −6～39 取同樣的 1024＋256 符號窗，計算 held sample 和符號標籤的 Pearson 相關。

| 平面 | 凍結 lag 的相關 | 最大 \|相關\| 的 lag（相關） |
| --- | --- | --- |
| primary | lag 1：+0.005 | **3：+0.753**；4：+0.549；6：−0.236；7：−0.188；2：+0.177 |
| secondary | lag 3：**−0.735** | 3：−0.735；4：−0.579；6：+0.197；7：+0.189；2：−0.184 |

- 判讀：
  - primary 的資料其實在，只是晚了 2 個符號。插入 gm-tap 延遲路徑後（含 TG、bank 與 shared launch），總延遲比歷史 r5 多了約 2 UI，和 lag 3 一致。
  - secondary 的 lag 3 大致對，但相關是負的。可能是 secondary 讀出相對凍結 detector 的極性反了，也可能是同樣 2 UI 的延遲讓它對到另一個符號、碰巧負相關（lag 5 的相關不在前五名）。這要你從電路接線與 detector 的極性定義判斷。
  - 這不是電路失效：clock、取樣數、clipping 都正常，訊號也在。問題是凍結的對齊參數沿用到新路徑。

五、請你處理（一包解決，不要分兩輪）
1. 決定 C0 的對齊方式，任選其一：
   - 用 primary／secondary 實測的總延遲重新設定整數 lag，並說明依據，例如 gm-tap 路徑多出的群延遲；
   - 或依你研究文件的方向，用獨立訓練窗（不用 payload）選 lag／相位，鎖定後再計分。
   兩者都不能看 payload 來選。
2. 釐清 secondary 的極性：是凍結 detector 預期的極性和新路徑相反，還是 lag 不對。
3. 第 0 案的 raw（69 MB）保留著，新包請提供 rescore 或 collect-only 模式，直接用現有 PSF 重新計分，不必重跑 40 分鐘。
4. 用這次第 0 案的實際結果當 fixture：期望 primary 在新對齊下 SER 明顯低於 0.75。修好後我先 rescore 第 0 案，正常再送 1–4。
- 資源：第 0 案實測 40 分鐘、283 MB、69 MB raw。五案 60 分鐘的上限足夠；1–4 可以四案並行。

六、保留
- run root pam4_c0_fixed_20261115.*，第 0 案 raw 全部保留。
