Stage: SAR7 1.75 GS/s 實體參考解碼及重配時槽
ZIP: ECEN721_PAM4_SAR7_NATIVE_DECODE_PILOT_20261116_R2.zip（OneDrive ECEN 720/outputs）
SHA256: eda6b1b2591771b8d1891838ac97e7352e193d961010ea58ad29049f71ee79fe
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_NATIVE_DECODE_PILOT_20261116/HANDOFF_zh_TW.md
Recommended: 只送 sar7_14_tt_175gs_native_decode。對 761321 查異、跑實體解碼與已凍結的重配時槽，一案完成後再決定下一步
Resources: 1 CPU／6 GiB／Slurm 12 分鐘，solver 540 秒，估 3–7 分鐘、100–180 MB raw
Commit allowed: handoff + results
Needs user decision: no

使用者交代「繼續跟 Claude 在背景跑，確認 SAR7 隔離案有送上 Olympus，拿到結果就接著修。C1 通過就直接跑 C2，有關鍵結果再跟我說。」761426 隔離案已完成，registered max 從 32 降到 1 LSB，確認現有 gate 控制是中段錯碼的主要來源；b6/b5 在理想控制下仍需最慢約 37.0/40.6 ps 至 read ±1 LSB，且有兩個近門檻 b0 未解析。下一案用原生 OAI21＋NOR3 直接產生互補開關控制，q+、q− 鏡像輸入幾何和 dummy gate 負載，保留原 DAC／參考源／實體 TG、比較器、register。D/A 等待按 b6…b0 配 42/40/24/17/13/10/8 ps，b0 比較留 54 ps。比較器 b5 額外驅動延遲仍須實測。以 557 ps 讀出作正式篩選，並列原 554 ps 檢查末位解除後的 register 建立，兩點都在下一時槽前。此包是唯一後續 Spectre 短案。

manifest `12e5745c9a28f26a5a1bbb8cc11030e1f41da59176d7fdca9b1b187c9763ae24`，portable `ecd325622c426dfe2c1f5dd42cb00ca30c59f238ba77764d7757af15dd04720a`。套件依 761321 原環境建構，另記錄 761426 隔離 summary `fdcca5230efa8c6a8b534d54c4acd6ecdd2b290d2af4cfc0a55bd24a87625748` 作設計依據。先核對 ZIP、manifest、verify、3 項測試、stage diff，再送單案。無新的理想 Bsource。回報 job ID、完整 84 決策、兩個 readout、DAC 建立、各解碼控制與參考源電流、SHA 與資源。已完成 solver 的收集失敗先 collect-only，raw 保留；只回 compact 結果，不把 ZIP、deck 或模型進 repo。

Bheemisetti 的 1.75 GS/s 實測以 CDAC 底板切換產生下一級時序。Ramkaj 的 28 nm 開關安排 break-before-make。請用 loaded control、底板與 held 同時判斷 gate 延遲和類比建立，並檢視 gate overlap proxy 與 reference current 是否同時異常。供電峰值包含充電電流，請保留此限制。量 b0 的 x/y、q 及兩個 readout，分清近門檻再生與最後輸出建立。通過此短案後還要以獨立資料驗證 transfer 與頻譜，再進 112 GS/s 整合。[Bheemisetti，IEEE JSSC](https://doi.org/10.1109/JSSC.2024.3449115) · [Ramkaj，IEEE JSSC](https://doi.org/10.1109/JSSC.2018.2822823)
