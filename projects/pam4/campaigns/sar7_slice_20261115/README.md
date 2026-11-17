# ECEN 721 · 7-bit SAR 單路原型

狀態為 **Olympus 案 0 已完成（job 759069），未通過短測，案 1 暫停**。這是 1.75 GS/s 的單路驗證，使用 r5 StrongARM、原生 MOS 開關和 4+3 等效 CDAC。七項離線測試已通過。

- SAR7 套件在 OneDrive `ECEN 720/outputs/ECEN721_PAM4_R5_SAR7_SLICE_20261115.zip` · [ZIP SHA-256](ECEN721_PAM4_R5_SAR7_SLICE_20261115.zip.sha256)
- [Olympus 跑案說明](OLYMPUS_zh_TW.md) · [給 Claude 的本批交接](../../handoff/to_claude/20261115T1624_sar7_zip_onedrive.md)

在 Olympus 指向先前已驗證的 C0、SWITCH64 和 r5 原始上傳目錄。先依說明核對 SHA、離線測試與網表，再依既有授權流程跑 `sar7_00_tt_pilot`。案 0 的 `logic_smoke_pass` 通過後再評估案 1。正式 PN-skew C0 的 payload 是另一批工作。

後續結果與問題寫到 [to_codex](../../handoff/to_codex/)，並連回本批量測摘要。raw 與私有模型留在 Olympus。
