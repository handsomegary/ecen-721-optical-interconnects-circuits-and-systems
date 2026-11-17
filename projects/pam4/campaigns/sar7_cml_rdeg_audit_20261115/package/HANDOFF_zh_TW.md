# ECEN 721 SAR7 · 760348 保留資料的最後收尾查核

這是本輪最後一次、僅讀既有資料的收尾查核。工具只有 `verify`／`audit`，沒有 stage、run、approval、solver 或 subprocess 路徑；不送任何新 Spectre job，也不改任何原始結果、網表、raw 或執行證據。完成後停止調參，不自行建議或提交新模擬。

760348 已確認實體隔離與差動路徑恢復，但仍有 max 5 LSB／10 個錯碼，且只是約 0.926 GS/s 診斷。不能宣稱 SAR smoke 通過或達到參考論文。這次僅用同一原生 PSF 的既有 84 個比較前狀態，查 CDAC 有效權重、sample gain、span、offset、逐轉換留一 RMSE，以及感測級 affine slope／intercept。感測級擬合的零交越明確標記為 **SENSE STAGE ZERO CROSSING**，不是 comparator offset。

不做反事實碼預測、不提出或驗證 trim 值、不掃 b0 時刻；final read 已是 1030 ps，保留原計分。模型無法辨識時如實標記，不用增加樣本或重跑。

## Olympus 操作

沿用 760348 wrapper 的原 SAR7／relaxed／CML_RDEG 與私有模型環境；CML_RDEG_PACKAGE 必須指向原已執行包。另將 PAM4_SAR7_AUDIT_PACKAGE 指向舊 CDAC_AUDIT 包，供 SHA 綁定的 gain_record／coefficients 使用。不要更動原套件。

```bash
export PAM4_SAR7_CML_RDEG_PACKAGE='/absolute/path/PAM4_SAR7_CML_RDEG_20261115'
export PAM4_SAR7_AUDIT_PACKAGE='/absolute/path/PAM4_SAR7_CDAC_AUDIT_20261115'
export PAM4_SAR7_CML_RDEG_AUDIT_PACKAGE='/absolute/path/PAM4_SAR7_CML_RDEG_AUDIT_20261115'
export PAM4_SAR7_CML_RDEG_AUDIT_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_cml_rdeg_audit_20261115.XXXXXX")"
cd "$PAM4_SAR7_CML_RDEG_AUDIT_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_cml_rdeg_audit.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_cml_rdeg_audit.py audit \
  --source-root "$HOME/ecen720_28nm/runs/pam4_sar7_cml_rdeg_20261115.ot1Vbg" \
  --output-root "$PAM4_SAR7_CML_RDEG_AUDIT_ROOT"
```

若原 ZIP 仍可讀，可另加 `--source-zip /absolute/path/ECEN721_PAM4_SAR7_CML_RDEG_20261115.zip`，工具核對其完整 SHA。未提供時會明確標記 unavailable，expected SHA 不是遠端實測 receipt。原 ZIP 正確完整 SHA 為 `938e179f33863ddec49894ba0a44f27b5249cf4efad3dfbfe4ac1bd9248e43dc`；portable SHA 為 `362dc80f1ca8444f59c1f620d2fb5fdae2d8c8948ef2bb7aa3155b2533cbf006`，避免沿用 2042 回報中縮寫尾碼誤植。

最多一個 Python collector；1 CPU／6 GiB／10 分鐘，零 solver，raw 不新增。若需要排程資源，只能啟動這個 collector，不能啟動任何模擬；最遲 Chicago 2026-11-15 21:45:37 前開始，過時只回報狀態。

## 證據與輸出

工具先 bind 原 CML build／PLAN／MANIFEST／SCHEMA，核對 exact case、job 760348、完成狀態、原 summary SHA、measurements provenance 與 raw inventory，然後只 parse 原生 PSF 一次。結束時再次核對原證據、inventory、summary 和 measurements 未變。新輸出僅 `sar7_cml_rdeg_final_audit.json`，寫到分離的新 root。

回本機 outbox 報這個 JSON 的完整 SHA、CDAC fit、感測 fit／零交越的單位與定義、大小訊號符號一致數，以及原 summary／measurements／tran／staged bench／portable／manifest 的完整 SHA receipt。不得把模型路徑、deck、原始波形或 private 檔案內容貼入回報或 repo；JSON 本身只含相對識別、job IDs、指標與雜湊。raw 全部保留。原既有計分和「錯碼 10／12、max 5 LSB」結論不因本次回歸而改寫。

C1／C2、其他專案、參數調整及新模擬都不在本查核範圍。依原規則處理任何完整性失敗；不得以重新 collect、重跑或修改證據避過錯誤。
