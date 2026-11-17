Stage: SAR7 1.75 GS/s 參考開關驅動隔離對照
ZIP: ECEN721_PAM4_SAR7_DAC_DRIVE_PILOT_20261116.zip（OneDrive ECEN 720/outputs）
SHA256: 89b1797cee6c7c4af824a78c29741088a38ac6f406ec0e89bde5075a762265a7
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_DAC_DRIVE_PILOT_20261116/HANDOFF_zh_TW.md
Recommended: 只送 sar7_13_tt_175gs_dac_gate_bypass，沿用 job 761321 時序。對照 761321 和 761279，一案完成即回報
Resources: 1 CPU／6 GiB，Slurm 12 分鐘，solver 540 秒；估 3–6 分鐘及 100–180 MB raw
Commit allowed: handoff + results
Needs user decision: no

依使用者指示繼續驗證 SAR7 的 1.75 GS/s。用已核對的 1720 唯讀診斷（compact JSON `b4220fb8c268a55c4425029dcfc7a1f36e55bbc6cb7bfef7be0ebad26abe5f7b`）選這一案。快速案 b5–b3 在比較器開啟前幾乎尚未加上 trial，慢案在相同決策歷史下已完成 95–104%。快版 b6/b5/b4/b3 進入讀取值 ±1 LSB 最差 59.3/59.9/49.4/37.2 ps；這不是把慢幾 ps 的比較器窗加寬就能修好。Bheemisetti 的 1.75 GS/s 實測讓 CDAC 切換觸發後續比較；Ramkaj 在 28 nm 把邏輯延遲和 CDAC 建立分開改善。先做一個理想 gate 驅動對照來分辨兩者，確認後再改實體電路。[Bheemisetti，IEEE JSSC](https://doi.org/10.1109/JSSC.2024.3449115) · [Ramkaj，IEEE JSSC](https://doi.org/10.1109/JSSC.2018.2822823)

案目 manifest `ea184bc1f921d3a2a17e496466d0301bc5f394fb3c31f201bce1eefb37c14302`，portable `49d09ab9b9042f6cfc5befc4b018281c7f3f7f5542168bb4144ad8e7f3fb89b5`。先查 SHA、verify、兩項測試、實際 stage diff。只容許 28 條參考 TG gate 重接、36 條 bsource 及 save，其他含參考源、CDAC、比較器、register 元件及時序一致。請分開標記卸載的原控制與實際理想 gate，在 Olympus 核實新 bsource 組合有編譯、存檔。送件即回 job ID。保留 raw，solver 成功但收集出錯時先依 Guide collect-only。

回報控制→底板→held 差動→比較器→register 的時差、完整 12 碼與 84 bit、SHA、solver 秒數和 raw bytes。若 gate 及時但 held 仍在變，下一步看 TG/CDAC 或 b6 轉換起始。若 held 及時且錯碼消退，下一步才做實體 gate 驅動。若 gate 和 held 均及時、比較仍出錯，再處理讀取與比較器。保留 `code_screen_under_ideal_drive` 和原 `logic_smoke_pass`；這一案用來選實體方向，真正 1.75 GS/s 及完整 ADC 尚需實體控制驗證。
