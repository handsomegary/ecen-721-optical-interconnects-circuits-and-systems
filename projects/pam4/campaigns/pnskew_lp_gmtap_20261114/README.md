# PN skew 補償 LP_GMTAP：無 TG 的 gm-select tap 選擇（2026-11-14）

第二十版。每個延遲線 tap 直接接一組差動輸入 bank，選碼只改尾電流分配，所有組合恆定開 8 個尾單元。比較 3／5／7 組 bank（coarse3／5／7）。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA 423b2883…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_gm_tap_ss_pilot.json` | SS pilot 0–31 的 `gm_tap_summary.py` 輸出。 |
| `results/lp_old_tg_notch_45_80.json` | 舊 GLOBAL TG 量測的唯讀低谷診斷（沒有重跑 Spectre）。 |

## SS pilot（32 案，job 755423／755424）

- coarse3（tap 6／11／16）相對最小負載對照：
  - 中心 −1.88 dB、端點 −1.54 dB，通過 2 dB；
  - 範圍 ±5.71 ps；
  - 功耗 8.24／10 mW。
- coarse5（−3.70／−3.28 dB）與 coarse7（−5.01／−5.08 dB）不通過。
- 原因：關閉的 bank 閘極仍以約 6–8 fF 負載延遲線。
- 舊 TG 診斷：每條支路傳輸只有理想的約 1/3。−37.5 dB 是不注入 skew 時兩支路相消造成；注入 4.464 ps 後為 −12.76 dB。
- raw 304 MB，保留在 Olympus。

## coarse3 近端點與 launch 50 Ω（28 案，job 755520）

- 7:1 是欠補，不是過補：
  - 帶權延遲 4.166 ps（殘差 +0.298 ps），56 GHz 相位延遲 4.496 ps；
  - 補償後 Hdd −21.11 dB，CM→DM 0.19，相對對照 −0.45 dB；
  - 功耗 8.34／14 mW。
- 8:0→7:1 一個尾單元就移動 1.55 ps，8 份權重不夠細，下一步試 16 份解析度（15:1、14:2…）。
- 加 launch 50 Ω：絕對 Hdd 全面差約 3.5 dB，延遲與噪聲幾乎不變，所以維持不加。
- 合併摘要：`results/lp_gm_tap_ss_coarse3_0_71.json`（30 組 P/N，0 invalid）。
