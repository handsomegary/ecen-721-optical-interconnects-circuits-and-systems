Stage: SAR7 1.75 GS/s 首案的保留波形診斷
ZIP: this message
SHA256: n/a
Guide: this message；以 761321 及 761279 原量測與波形為輸入
Recommended: 只讀兩案既有執行與波形，在 Olympus 比對上位元事件先後，回傳 compact JSON 及表格到本機 outbox
Resources: 零新 Spectre／Slurm job；原 run root 和 raw 留原位
Commit allowed: handoff + results
Needs user decision: no

761321 的 1.75 GS/s 固定時序檢查沒有通過（b5 兩次、b4 一次未解析，registered 9/12 錯，max 32 LSB）。用保留證據定位再選下一案，本次不用新的 transient。761321 的 summary SHA 是 `a5432be72f2c293c8577bdb3c5d0f886e4765d7c61852ba93a0a69c164f9ae5a`、measurements `935150c70665c0effde4c63cf47fcac6ffafc2412706a096420d7143c75c9cb5`、tran `6d6ab5f3f5052bc30e227772310ff35423067a81dfd580ee0a232ada9bab35b7`。761279 的 summary／measurements／tran 分別是 `84b051d79c71979637416674aeb17b851104b199e544d9035870f8116f761a0a`、`b3a514de93049c737b9c1c7c18cafda99be78373e0638255f8127ea8e5af8394`、`d2e900facf2c569801cfb61e0794e0420f7b5cf62129f2ab98cdc1fe1131bc00`。沿用兩案 manifest、同一 sign convention、原波形 metadata 的 event times，核對後用既有 PSF parser 的 selected trace 功能。可另存 compact 診斷檔，保留原 summary、measurements 和 raw。

請對兩案的 12 碼 × 7 bit 列出原 read 分類、有證據的 read margin、前一個 bit 的 trial 解除／registered rail 成立時刻，及本 bit trial rise、compare rise、read 時刻。對 b6/b5/b4 全碼（另帶 b3 對照）取樣 `mp−mn`、`lp−ln`、CML sense 差動、comparator 內部 x/y 和 buffered q。窗內取 launch 後 5/10/15 ps，compare 前 6/3/1 ps，compare 後 1/3/6/12 ps、read；與下一級 trial 相鄰時只留該 trial 內的點。將 sample、compare、read、trial release 周圍的符號翻轉與其絕對時刻對齊。若需要取得某個決策接點所需訊號但 raw 未存，標示缺測，不可從波形以外推補值。以 100 mV/128 換算差動 LSB，並列出 V。失敗碼要附前一級 comparator/registered 是否已和慢案分歧。已解碼卻找不到第一個穩定取樣點時，把裕度列為未證實，勿省略該紀錄。

「比較前到讀取的總差動變化」包含比較器開啟和前一位元切換，單靠這值不能定位。若快速案開比較前仍有明顯斜率、未到慢案在同一決策歷史下的差動符號／值，支持 CDAC 建立窗不足或前一位元切換太晚；若比較前已穩定，只在內部 x/y 再生啟動時突然跳，支持 comparator kickback；若 held/sense 都已穩定，但 x/y 或 buffered q 到讀取仍未達 rail，比較器或邏輯窗是限制。每項以實際波形的匹配對照說明。Bheemisetti 在實測 1.75 GS/s 用 CDAC 開關事件產生非同步 ready，以免下一比較先於 DAC 切換；Ramkaj 的 28 nm 做法也把 DAC 建立與比較器／邏輯列為獨立的限制。本輪只用舊資料分辨這些機制。[Bheemisetti，IEEE JSSC](https://doi.org/10.1109/JSSC.2024.3449115) · [Ramkaj，IEEE JSSC](https://doi.org/10.1109/JSSC.2018.2822823)
