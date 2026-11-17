# ECEN 721 #6｜C0 五案審查

SWITCH64 已完成 87 案，21 組切碼全部恢復。實測最長 2.648 ns。C0 五份審查網表由已驗證的 Split64 電路和 r5 原生取樣鏈產生，先檢查固定端點碼的資料路徑。這份是審查包，Olympus 實檔讀回仍待驗證。

## 五案與資源

五案共用 TT／25 °C／0.9 V、0.4 Vppd、112 GBd、56 GHz 20 dB 合成雙極點通道、1 ps 發送邊緣及原 r5 主、次取樣時序。時域 14 ns，保存 178 條訊號，維持 `maxstep=200f` 與 `strobeperiod=UI/8`。每案 1 CPU、6 GiB，以 classic Spectre `+mt=1` 為預估基礎。

| Deck | tP − tN | 固定碼 | Solver 暫估 | Raw 暫估 |
| --- | ---: | ---: | ---: | ---: |
| `c0_00_tt_zero.scs` | 0 ps | 0 | 20–45 min | 65–115 MiB |
| `c0_01_tt_p_late_code0.scs` | +4.464286 ps | 0 | 20–45 min | 65–115 MiB |
| `c0_02_tt_p_late_preset.scs` | +4.464286 ps | −60 | 20–45 min | 65–115 MiB |
| `c0_03_tt_n_late_code0.scs` | −4.464286 ps | 0 | 20–45 min | 65–115 MiB |
| `c0_04_tt_n_late_preset.scs` | −4.464286 ps | +60 | 20–45 min | 65–115 MiB |

Solver 範圍參考 29.414 ns 的 r5 歷史 quiet 案 61–75 分鐘，按 14 ns 比例約 29–36 分鐘，再留整合負載的變異。Raw 估算基於約 12,545 個 strobe timepoints、178 條訊號和 PSF ASCII 檔頭。五案合計暫估 1.67–3.75 CPU-h、325–575 MiB raw。首案實測後更新預估。

## 切碼與計分

- 五案全程固定碼。控制線用 DC，由初始工作點開始生效。第一個計分用 payload 標籤在約 10.486 ns；即使將控制碼設定視為從 t=0 生效，留給穩定的時間已超過 3 ns。往後若把切碼安排在前導段，從最後致能邊沿起排除至少 3 ns 的樣本。
- 五案使用同一段原 r5 驗證標籤。每個讀出平面取 256 個 held samples，17-tap FFE 丟掉兩側各八點後各計分 240 個符號。保留原凍結 FFE、7-bit 量化、門檻、對齊及時鐘相位。逐案報 primary／secondary 的錯數與分母、Gray 位錯、RMSE、clipping 和 FFE 前等級間距。補償差量以同一方向的兩案配對。
- ±60 是已驗證的端點控制碼，用於固定碼電路診斷。實體前景選碼仍需以獨立訓練資料，在兩個方向用同一組候選碼，依 primary 的固定 detector 決策前均方誤差選碼。共同相位也須以零偏斜訓練資料決定後，才用於所有 payload 臂。這五案的結果只能代表預設碼與歷史相位下的性能。
- FF 餘量、SS XT2 和尾電流沿用 SWITCH64 結案判讀。C0 無雜訊短窗的 SER 只作診斷，作品集可按相同測試條件列出觀察值。

## 用 Olympus 實檔重算

`replay_switch64_actual.py` 讀既有 83–86 紀錄及保留的兩份補跑 PSF。它以實際 array task ID 和檔案大小綁定 84、86，核對完整 PSF SHA-256，重做 END 檢查、解析和量測，再與已提交的量測 JSON、合併摘要逐項比對。此命令只讀取既有模擬資料。若 PSF 已按原清理方案退役，須先找到有相同 SHA 的保留副本才能重播。C0 新增的 r5 次取樣與計分，仍須以第一案的實際 PSF 核對一次。

在 Olympus 設定下列兩條路徑。`PAM4_C0_SWITCH_PACKAGE` 指 SHA `94aff417…` 的解壓目錄。`PAM4_C0_R5_ORIGINAL` 指原 COMP 套件的 `r5_original`，含 `quiet.scs`、`provenance.json`、`frozen.json` 和 `source_dir`。只在原私有 kit 路徑替換 deck 中的 `__pdk_root__`。

```bash
export PAM4_C0_SWITCH_PACKAGE PAM4_C0_R5_ORIGINAL
/usr/bin/python3.11 -B replay_switch64_actual.py --original-root "$SWITCH64_ORIGINAL_ROOT" --retry-root "$SWITCH64_RETRY_ROOT"
```

先核對實檔重播，再用首案完成原生 `tranResponse` 的 smoke。`c0_review.py --score-run RUN_ROOT/CASE_DIR --output RESULT.json` 會檢查 solver 狀態、網表及 raw SHA，量測兩個讀出平面。`c0_review.py --summary RESULT0.json RESULT1.json RESULT2.json RESULT3.json RESULT4.json --output SUMMARY.json` 需要五份完整個案輸出。審查包內含 deck 與雜湊；這次尚未產生新的 Olympus 模擬、校準或 SER 結果。
