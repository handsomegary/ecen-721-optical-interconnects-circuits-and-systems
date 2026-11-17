# SAR7 q-buffer retained audit：兩個既有 raw，零 solver

本包只讀 job761549 qbuffer 與 job761524 strong 的既有完成根目錄。沒有 approval、stage、run、電路修改或 Spectre 呼叫。每個 physical source 的 PSF 只 parse 一次，最多兩個；讀取前後核對原 execution files、raw inventory、measurements 與 summary SHA，不重算或覆寫原量測。新輸出必須位於獨立的 `pam4_sar7_qbuffer_audit_` 根目錄。

2237 回報的原始 read 有兩筆 comparator 未判定，因此只能說 10 筆可讀 comparator code 與 register 相符，不能說 12/12 原 read 全相符。既有 raw 顯示 84 個 raw q 在各自 release（read+2ps）都可分類，其重建碼與 565ps register 12/12 相符（含 88/44）；這是 eventual decision 診斷，不能取代原 read gate，也不能單獨證明錯碼原因。conv0b6 的 compare120/read159 是 +39ps，並非 +61ps。22:37 Chicago 並未超過當晚 23:15 授權截止；本包仍只作 retained audit，今晚先不提出另一個 physical case。

既有 qbuffer collector 的 q/mid/decode crossing 視窗在 next launch 截止；沒有 crossing 是截尾觀察，不能解釋成永遠不到位。本包針對 conv0b6、conv7b4→b3→b2、conv8b3→b2→b1，從前一 bit release−5ps 一直讀到 max(下一 bit compare+30ps, 下一 bit read)，每個來源由自身 waveform metadata 取得時間。輸出同時給 conversion-relative 與 current-compare-relative 時間。每段保留前、當前、後一 bit 的 raw q、mid/decode（strong 明示 direct raw、沒有實體 mid）、四個 reference gate、bottom、held/sense、x/y、register、trial/clock；列出 compare+0/5/10/15/20/30ps、read/release 及 release 後固定點。使用原生 saved 時點（約0.25ps）與 crossing，沒有新 raw。

判讀時先對齊前一 bit release 後 reference command、bottom/held/sense 變化、下一 comparator x/y 初次 regeneration，再看 raw/mid/decode 與 register。O/Z rail command 與 half-VDD crossing 只是 gate proxy，不能當作直接量到開關導通或電流。held/sense 在 regeneration 中可變號，較晚負值不能單獨證明 comparator intrinsic offset。

Bheemisetti 等的 7-bit1.75GS/s prototype 使用 ready/completion 與非同步比較／CDAC 控制，提醒 digital ready 不等同類比完全 settling；其 comparator、製程與本測試不同，不能直接套用 delay 數值。DOI：[10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115)。Ramkaj 等 SectionIII-D 說明縮短 comparator→CDAC memory path、降低 comparator load 的理由；我們額外兩級 q-buffer 的 delay 是另外的取捨，並非複製該文拓撲。DOI：[10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823)。本 audit 的鑑別結果是：錯誤 reference 狀態是否在下一 compare 前／regeneration 中持續，或 reference 已穩而 comparator 先走向錯誤；沒有新設計假設或保證。

## 執行

沿用既有完整 dependency chain（包含已核對的 qbuffer、strong、native 及其既有父包）；本包 import 的 manifest/portable pins 在 PLAN 與 runner 中固定。不要重新打包父包。設定現有各父包環境變數，至少：

```bash
export PAM4_SAR7_QBUFFER_AUDIT_PACKAGE=/approved/PAM4_SAR7_QBUFFER_AUDIT_20261116
export PAM4_SAR7_QBUFFER_PACKAGE=/approved/PAM4_SAR7_QBUFFER_PILOT_20261116
export PAM4_SAR7_STRONG_DECODE_PACKAGE=/approved/PAM4_SAR7_STRONG_DECODE_PILOT_20261116
export PAM4_SAR7_QBUFFER_SOURCE_ROOT=/approved/pam4_sar7_qbuffer_pilot_20261116.GscWI6
export PAM4_SAR7_STRONG_SOURCE_ROOT=/approved/pam4_sar7_strong_decode_pilot_20261116.qUaOJ0
export PAM4_SAR7_QBUFFER_AUDIT_ROOT=/approved/pam4_sar7_qbuffer_audit_20261116.NEW
python3.11 -B "$PAM4_SAR7_QBUFFER_AUDIT_PACKAGE/sar7_qbuffer_audit.py" verify
python3.11 -B -m unittest discover -s "$PAM4_SAR7_QBUFFER_AUDIT_PACKAGE" -p 'test_sar7_qbuffer_audit.py' -v
sbatch "$PAM4_SAR7_QBUFFER_AUDIT_PACKAGE/sar7_qbuffer_audit.sbatch"
```

collector 限一個 Slurm job、1CPU、6GiB、10min，無 solver。直接執行時使用 `audit --qbuffer-root ... --strong-root ... --output-root ...`。既有根目錄 basename 和 summary/measurement/tran SHA 必須與 PLAN 完全一致；不嘗試搜尋替代 raw 或 fallback。先完成兩來源讀取與不變驗證才寫新輸出。

`sar7_qbuffer_audit_compact.json` 為可審查的 edges/狀態/compact metrics；`sar7_qbuffer_audit_local_evidence.json` 是密集電壓與 phase samples，只留 OneDrive/Olympus，不進 GitHub。compact 檔仍須經人工檢查才可放 repo，不可附 private models/deck 或 raw trace。相同新輸出可重讀驗證，但若內容不同會拒絕覆寫。不要重跑 source collect、不要 lock／寫入 source。回報兩個新輸出 SHA、collector jobID／耗時、原資料不變證明與上述關鍵時序，不啟動新的 physical case。
