# 正式 C0 四案早晚窗重算

ZIP: OneDrive `ECEN 720/outputs/ECEN721_PAM4_C0_FORMAL_RESCORE_20261115.zip`
SHA256: `f27034073673b1b0f8d33a497342b9400800c1e20babde7eb59331a79c8652d1`
Guide: OneDrive `ECEN 720/outputs/PAM4_PNSKEW_LP_GMTAP_C0_FORMAL_RESCORE_20261115/HANDOFF_zh_TW.md`，ZIP 內也有一份
Recommended: 用正式 C0 的原 run root，對 job 759018 四案一次執行 `rescore`
Resources: 一個 Python 3.11 程序，讀四份各約 32 MB 的既有 PSF，估數分鐘，Spectre CPU 時間為 0
Needs user decision: no（只重算現有資料，P 晚 −60 維持暫停）

## 先同步乾淨的 main

應使用者更正，含 deck 的 SAR7 ZIP 已自 GitHub 的 `main` 及最近受影響的提交歷史移除，套件留在 OneDrive。若本機 clone 與新 `origin/main` 分岔，使用乾淨的新 clone 讀取和寫回交接，避免合併或推回舊歷史。既有 Olympus run root 和工作成果照常保留。

## 重算與回饋

核對 ZIP 和 manifest SHA，執行 `verify` 與六項離線測試，再以原本正式 C0 環境執行 `python3.11 -B c0_payload_rescore.py rescore --root "$PAM4_C0_FORMAL_ROOT"`。補上 `PAM4_C0_FORMAL_PACKAGE` 指向原本正式 C0 套件。

程式先重現四案各端 496 個 FFE 決策的原量測，再按實際取樣時刻拆成 4.2 ns 前、後，以及所有 17 個輸入均在晚段的固定 176 個中心。相位 −1/8 UI、lag、FFE、選碼 P 晚 0／N 晚 +60 全部沿用。寫出 `c0_formal_payload_rescore.json`，在 [to_codex](../to_codex/) 回報四案早晚錯誤數／分母、帶符號殘差、兩方向配對與新摘要 SHA。請保留 raw 供結果核對。原摘要照留，這一包沒有 Spectre 排程或 P 晚 −60 新案。

依使用者規則，GitHub 交接只寫檔名、SHA、指引和可分享的量測摘要。批次 ZIP 與 deck 留 OneDrive 或 Olympus。
