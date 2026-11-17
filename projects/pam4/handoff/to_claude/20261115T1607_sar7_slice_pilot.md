ZIP: OneDrive `ECEN 720/outputs/ECEN721_PAM4_R5_SAR7_SLICE_20261115.zip`（[更正](20261115T1624_sar7_zip_onedrive.md)）
SHA256: `20ec7c8d999df48fd503b7e812de37b82e8112c737ab45c0488c848bccf16e77`
Guide: [Olympus 跑案說明](../../campaigns/sar7_slice_20261115/OLYMPUS_zh_TW.md)
Recommended: 先跑 index 0 `sar7_00_tt_pilot`，拿到 `logic_smoke_pass` 後再依說明評估 index 1
Resources: 每案 1 CPU（Spectre Classic `+mt=1`）／6 GiB／Slurm 30 分鐘，solver 估 1–10 分鐘，raw 估 50–90 MiB
Needs user decision: no（依既有 Olympus 授權流程處理案 0，交接訊息本身不變更授權範圍）

## 7-bit SAR 首案

核對 ZIP SHA、套件 manifest、`verify` 和七項離線測試，再使用既有 Olympus 的 C0、SWITCH64 與 r5 原始套件。收完案 0 後，請在 [to_codex](../to_codex/) 放 job ID、實際耗時、raw 大小、`logic_smoke_pass`、最大取樣誤差與最慢 bit。如果收集出錯，先留 raw 用 `collect-only`。正式 PN-skew C0 的 payload 照原批次收尾。
