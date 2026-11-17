# PN skew 補償 LP_BIAS：replica 定電流偏壓（2026-11-13）

第九版。保留共用驅動 shared14lo120z50 與兩條 50 Ω 延遲線，以 1:14 replica 設定每腿電流，掃描 4.2／4.5／4.7／5.0 mA，目標是讓驅動功耗不再隨 corner 上升。使用者批准 0–77。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼與設計說明；生成的 deck 未收錄，SHA 記在 `SHA256SUMS.txt`。 |
| `prompts/` | 結果與錯誤回饋。 |
| `results/bias_ref_0_29.json` | 30 個參考案的 `bias_summary.py` 輸出。 |
| `recovery_package/` | Codex 的 collect-only 復原套件中新增或修改的原始碼（ZIP SHA 4ff14e3d…；netlist 與 portable_review 未收錄）。 |
| `results/bias_0_77_recovered.json` | 復原後 0–77 的合併摘要（39 列，invalid 0；78–93 未批准，列為 missing）。 |

## 結果

- 0–29（bypass、理想驅動、原固定偏壓）：30/30 完成，數值與 LP_NEXT 逐值一致。
- 30–77（偏壓掃描）：48 案的 Spectre 都正常完成，但 bench 用 `GMSRIREF:p` 存理想電流源的端電流。Spectre 不接受這個 save 名稱並跳過，收集器讀不到這個量，每案都以 KeyError 失敗。
- 所以「是否有單一電流設定能同時滿足 2 dB 與 +10／+14 mW」仍未回答。已請 Codex 修正，最好提供只重新收集的模式。

30 個完成案的 raw（329 MB）已退休；48 個失敗案的 raw（約 290 MB）保留在 Olympus，供修正後重新收集。

## 復原（collect-only 30–77）

- 修正 save 名稱後，使用者批准 collect-only 30–77。從保留的 raw 重新收集，不重跑 Spectre；48/48 recovered。
- raw inventory 綁定了 st_dev，而 Olympus 家目錄在 n02-hera 上是 61、在 n01-zeus 與 login 上是 55。所以原本在 n02-hera 跑的 9 案改用 `srun -w n02-hera` 在原節點收集，程式沒有改。
- 結果：replica 偏壓 4.2 與 4.5 mA/腿在 SS／TT／FF、單組與雙組都同時通過 2 dB 與 +10／+14 mW。4.7 與 5.0 只因 FF 單組含保留後超過 10 mW 而不通過。
  - 4.5 mA：最差增益為 SS −1.58 dB（相對理想），FF 單組含保留 9.92 mW（餘裕 0.08 mW）。
  - 4.2 mA：最差增益為 SS −1.79 dB，FF 單組含保留 9.29 mW。
- 每腿電流在三個角落都落在目標的 0.35% 內。Iref 仍是理想電流源（`actual_bias_OTA_verified: false`），所以以上屬暫定結果。
- 48 案的 raw（216 個檔、約 232 MB）已核對後退休，每案留有收據。

