AFE PVT AC/DC/固定 track noise 共 27 點。可先提交 TT/25 °C/0.90 V 及歷史 SS/FF 兩端點，
確認 AC 與 DC output 名稱、模型讀入和資源實測，再選其餘點。
`pvt/cases/case_ids.txt` 是 0 起算的索引，AC 與 transient 是兩種 fixture。
執行前設定 PAM4_PVT_CASES、PAM4_PVT_CASE_LIST、PAM4_PDK_ROOT、PAM4_STUDY_ROOT 及 PAM4_RUN_ROOT。

時域沿用本輪 TT quiet_z000，另用 pvt_transient_classic.sbatch 索引 0–1，
SS/85 °C/0.81 V 與 FF/−40 °C/0.99 V，採同一 r5 admission 和原 validation pattern。
保持 frozen FFE／量化器／對齊／clock／STOP／save。實體 supply 變動限原 XVs rail，
原資料共模、偏壓、clock source 設定依原 fixture 固定。結果只代表這個固定偏壓／刺激條件。
`python3 -B stage_skew.py --pvt-transient --admission "$PAM4_SKEW_ADMISSION" --output <new-review-dir>`
可先產生 model admission 後的 corner deck 及 diff。時域模型 wrapper 也以同一私有樹核對。
執行後在 Olympus 彙整 `python3 -B summarize_pvt.py --run-root "$PAM4_RUN_ROOT" --admission "$PAM4_SKEW_ADMISSION" --output <new-pvt-summary.json>`。
三個 endpoint 報 FFE 錯誤及抽樣間隔，PVT 雜訊只報 AC fixture 頻帶積分，
多 seed transient noise 的量測屬於名義溫度、VDD 下的 skew 對照。
