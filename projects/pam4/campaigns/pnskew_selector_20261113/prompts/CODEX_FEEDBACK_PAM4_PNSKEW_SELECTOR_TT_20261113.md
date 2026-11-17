【ECEN 721 #6 P/N deskew SELECTOR：TT 0–11 與 28–61 的 Olympus 結果。選擇器仍損失約 19.5 dB，SS/FF 先不跑】

一、執行
- 套件（ZIP SHA ac6431a6…）：SHA256SUMS 全部通過，`selector.py --mode verify` 通過，5 項離線測試通過。
- 審查 deck 索引 0、4、8、28、38、42、54：只差模型根路徑；case.json 只多了 model_preflight 與 staged_source_sha256。
- 使用者批准全部 90 案，依分段順序執行，並事先約定：TT 接負載的等長損失仍在十幾 dB 以上，或範圍不到 ±4.464 ps，就停下回報。
- 已跑：0–11（job 752380）與 28–61（752392），共 46 案全部 COMPLETED，selector_summary 沒有 invalid 案例。每案 3–4 秒。
- 未跑：SS/FF 的 12–27 與 62–89，共 44 案。
- raw（201 個檔、198 MB）已用相同的量測核對條件退休，每案留有收據。
- 摘要：selector_tt_summary.json。

二、單顆開關（TT，等效轉移阻抗）

| bias | 並聯數 | ON：1 kHz | ON：56 GHz | 56 GHz 互電容（ON / OFF） |
| --- | --- | ---: | ---: | ---: |
| native（原共模） | f1 | 170.7 Ω | 174.7−8.8j Ω | 0.82 / 0.29 fF |
| mid（VDD/2） | f1 | 272.4 Ω | 283.9−28.7j Ω | 1.00 / 0.28 fF |
| mid | f4 | 68.1 Ω | 71.0−7.2j Ω | 4.01 / 1.12 fF |

- 單顆 TG 移到 VDD/2 後，Ron 從 171 Ω 變成 272 Ω，反而更差。在 0.9 V 下 NMOS 與 PMOS 在中點都只有約 0.45 V 的過驅，這是預期內的；原共模 0.7 V 時，PMOS 的過驅較大。
- 4 顆並聯才把 Ron 降到 68 Ω，同時 Coff 與互電容約變為 4 倍。

三、接上 r3 負載（TT/25 °C/0.9 V；7–56 GHz 加權有效延遲；56 GHz Hdd 相對同端接 bypass）

| 變體 | bias／並聯 | 06/06 損失 | 06/16、16/06 的 τ_eff | RMS／最差 | 09/13 τ_eff |
| --- | --- | ---: | ---: | ---: | ---: |
| ttd_selected（理想） | native | −0.33 dB | ±5.245 ps | 0.012 / 0.019 ps | −2.100 ps |
| ttd_mid_direct（理想選路加 AC 耦合） | mid | −0.34 dB | ±5.249 ps | 0.010 / 0.030 ps | −2.102 ps |
| ttd_switch（原生 TG mux） | native f1 | −30.11 dB | – | – | – |
| ttd_on_only（只留導通支路） | native f1 | −30.03 dB | – | – | – |
| ttd_mid_mux | mid f1 | −37.75 dB | – | – | – |
| ttd_mid_on_only | mid f4 | −19.06 dB | – | – | – |
| ttd_mid_mux | mid f4 | −19.51 dB | ±4.397 ps | 1.038 / 4.086 ps | −1.691 ps（RMS 0.434） |

- AC 耦合的理想選路與原理想選路一致（−0.34 dB、±5.249 ps），所以耦合電容本身在 AC 上沒問題。1 kHz 下 −154 dB 是隔直流的預期結果。
- 「只留導通支路」與「完整 mux」只差約 0.1–0.5 dB，所以損失幾乎全來自導通路徑的 Ron，未選路徑的 Coff 影響很小。這和你的 Ron 診斷一致。
- 最好的 mid f4：等長 −19.5 dB；範圍 ±4.397 ps，略低於 ±4.464 ps；頻帶 RMS 1.04 ps，最差 4.09 ps。仍不能用。
- 雜訊：bypass 0.151 mVrms，理想選路 0.153，mid f4 mux 約 0.18，mid f1 mux 0.202。
- 理想路徑的中間碼 09/13 為 −2.10 ps、RMS 0.007 ps，固定長短路徑的中間碼行為良好。

四、判讀
在 50 Ω 等級的 r3 輸入節點串聯開關，即使 Ron 降到 68 Ω 仍損失約 19.5 dB。要把 56 GHz 等長損失壓到幾 dB 以內，串聯 Ron 必須遠小於端接阻抗，但 Coff 與互電容也會隨尺寸線性增加。從 f1 到 f4 的變化看，單靠加大 TG 很難兩全。

五、請你判斷並給下一版（設計工作）
- 不讓訊號串聯通過開關的選路方式。例如：
  - 兩條固定路徑都接 CML／source-follower buffer，用 tail 電流開關選擇（current-steering combiner）；
  - 用開關切換分流到地的 stub，而不是串聯；
  - 選擇點放在 r3 第一級電晶體的 gate 之後，改用兩組並聯的輸入對切換。
  請說明 56 GHz 損失、範圍、功耗、雜訊與 SS/FF 的預期。
- 若仍用 TG，請給出 Ron×Coff 與 56 GHz 損失的關係曲線，並找出最佳點，證明是否存在能同時滿足 < 3 dB 損失與 ±4.464 ps 範圍的尺寸；若不存在，請明確說明。
- 已批准但未跑的 SS/FF 44 案綁定這版 plan SHA；換新套件需要使用者重新批准。
