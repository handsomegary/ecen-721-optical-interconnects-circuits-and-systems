【ECEN 721 #6 P/N deskew LP_GMTAP SS pilot 0–31：無 TG 的 gm-select 可行。coarse3（tap 6／11／16）相對最小負載對照，中心 −1.88 dB、端點（注入 ±4.464 ps）−1.54 dB，通過 2 dB；範圍 ±5.71 ps，功耗 8.24／10 mW。coarse5（−3.70／−3.28 dB）與 coarse7（−5.01／−5.08 dB）不通過。關閉的 bank 閘極仍負載延遲線，每多一對 bank 約多損 1.5–1.8 dB】

一、執行
- 套件（ZIP SHA 423b2883…）：SHA256SUMS 全部通過，`gm_tap.py --mode verify` 通過（96 份 deck）。Olympus 上 130 項離線測試全部通過。
- 審查 deck 0、2、8、10、26、28：
  - bench 與 portable 相同；corner 只差模型路徑；case.json 只多了 model_preflight 與 staged_source_sha256。
  - 8 與 10 開的是同一組 tap-11 的 8 個單元。差異只有新增、全關的 bank 06／16 元件，以及 save 列多了它們的節點。
  - 0–31 的 P deck 中，每個 gm-tap 組合都恆定開 8 個尾單元；r3 與舊固定路徑沒有這些 bank。
  - AC 掃 1 kHz–150 GHz，DC／支路節點都有保存。
- 使用者批准 0–31（stages baseline／fixed／oracle／pilot）。
  - 先跑案 0（job 755423，3 秒）確認，再展開 1–31（job 755424，%6，最長 10 秒）。
  - 32／32 COMPLETED，32 份 completion 都有寫出；raw 304 MB，保留在 Olympus。
- gm_tap_summary 輸出 lp_gm_tap_ss_pilot.json：16 列 P/N 配對，invalid 為 0；missing 64 是未批准的 32–95。global_code_map_verified 與 dynamic_switching_verified 都是 false。

二、結果（SS，56 GHz；「相對 oracle」是同路徑、只掛一組 bank 的最小負載對照）

| 組合 | 點 | Hdd | 相對 r3 | 相對 oracle | 2 dB | tilt（56/7） | 延遲 | 增量 |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| r3 | – | −25.35 | 0 | – | – | +0.17 | – | – |
| 舊固定路徑 | 中心 | −24.17 | +1.18 | – | – | −1.98 | 0 | – |
| 舊固定路徑 | 端點 | −28.61 | −3.25 | – | – | −6.36 | ±5.23 ps | – |
| oracle 11×8 | 中心 | −20.23 | +5.13 | – | – | −1.09 | 0 | – |
| oracle 6×8／16×8 | 端點 | −24.52 | +0.83 | – | – | −5.33 | ±5.10 ps | – |
| coarse3 | 中心 | −22.10 | +3.25 | −1.88 | 通過 | −2.70 | 0 | 8.24／10 mW |
| coarse3 | 端點 | −26.94 | −1.59 | −1.54（不注入 −2.41） | 通過 | −7.46 | ±5.71 ps | 8.24／10 |
| coarse5 | 中心 | −23.92 | +1.43 | −3.70 | 不通過 | −4.25 | 0 | 8.24／10 |
| coarse5 | 端點 | −28.77 | −3.42 | −3.28 | 不通過 | −9.01 | ±6.01 ps | 8.24／10 |
| coarse7 | 中心 | −25.24 | +0.11 | −5.01 | 不通過 | −5.29 | 0 | 8.24／10 |
| coarse7 | 端點 | −30.40 | −5.05 | −5.08 | 不通過 | −10.34 | ±6.21 ps | 8.24／10 |

（Hdd、相對值、tilt 單位 dB；「相對 oracle」的端點列已注入 ±4.464 ps。）

- 正負方向逐值對稱。
- 三組的極限都涵蓋 ±0.5 UI（coarse3 ±5.71 ps）。
- 功耗全部 8.24／10 mW；XT2 最差裕度 6.6 mV，與先前相同。
- 端點補償（known_endpoint_skew，注入 4.464 ps）：

| 組合 | 補償後 Hdd | 相同硬體未補償 | 殘差 | 補償後 CM→DM |
| --- | ---: | ---: | ---: | ---: |
| coarse3 | −21.90 dB | −25.11 dB | −1.25 ps | 0.50 |
| coarse5 | −23.64 | −26.93 | −1.55 | 0.70 |
| coarse7 | −25.44 | −28.25 | −1.74 | 1.01 |

  殘差是因為極限 tap 比 4.464 ps 多走了 1.25 ps，要靠相鄰 bank 的電流內插（near 點）補足。
- 相對舊固定路徑：coarse3 中心 +2.07 dB、端點 +2.33 dB。
- 和上一輪原生 TG 比：G40 −9.7 dB 改善到 −1.88 dB。
- 45–80 GHz 的最低點都在 80 GHz 掃描邊界，沒有內部 notch（branch_null_frequencies 為空）。

三、負載定位（AC_path_diagnostics，coarse3 中心）
- 關閉的 bank 閘極導納仍有 1.77＋j2.21 mS（tap 6）、2.02＋j2.95 mS（tap 16），開啟的 tap 11 為 2.11＋j2.74 mS。也就是說，bank 關掉後閘極電容幾乎沒有變小（約 6–8 fF／bank）。
- tap→launch 傳輸：tap 6 −0.55、tap 11 −1.66、tap 16 −1.88 dB。
- 每多一對 bank，中心約多損 1.8 dB（coarse3 → 5 → 7：−1.88 → −3.70 → −5.01），與每顆閘極的固定負載一致。

四、舊 TG 低谷診斷（inspect_old_tg.py，只讀舊量測，沒有跑 Spectre）
- 原生 TG 的每條支路傳輸只有理想的約 1/3（0.015–0.020 對 0.055–0.058），是 G40 掉約 10 dB 的主因。
- 不注入 skew 時，G00 4× 兩支路在 56 GHz 的相位差為 179.6°，幾乎完全抵消（−66.3 dB），這就是 −37.5 dB 極限數字的來源。
- 注入 4.464 ps 後，4× 為 −37.73 dB，對同狀態理想（−24.97 dB）低 12.76 dB，與你的說明一致。

五、判讀
- 無 TG 的 gm-select 解決了上一輪的問題。coarse3 是唯一通過 2 dB 的組合，範圍與功耗都通過。
- coarse5／coarse7 的額外 bank 雖然改善步階解析度，但關閉的閘極負載讓 56 GHz 損失超過 2 dB，也讓 tilt 惡化到 −9～−10 dB。
- coarse3 每段 5.7 ps，內插精度完全依賴相鄰 bank 的電流分配（7:1、1:7…），需要 near 點驗證線性與損失。
- 端點 tilt（−7.46 dB）比舊固定路徑（−6.36 dB）更差，時域 FFE 時要注意。

六、建議下一批（需使用者批准）
- coarse3 的近端點與對照：32–39（8 案）。
- coarse3 的 launch 50 Ω 對照：52–71（20 案）。
- coarse5／coarse7 的 near 與 match 部分（40–51、72–95）建議先不跑，除非你能降低關閉 bank 的閘極負載。例如：
  - 縮小每個 bank 的輸入對；
  - 在閘極前加串聯隔離；
  - 只在 coarse3 tap 之間用更細的電流比例內插。
- 也請說明 coarse3 在 7:1 這類不均勻分配時，延遲與 Hdd 的預期非線性。

七、Olympus 空間
- 這輪 raw 304 MB，家目錄已用約 24 GB，剩 27 GB。
- 歷史 raw 盤點（review_historical_raw.py）還沒跑；使用者同意後再產生審查 JSON。清除需要另外批准。
