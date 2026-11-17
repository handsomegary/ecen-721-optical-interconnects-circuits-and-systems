# SAR7 單通道 1.75 GS/s TT 固定時序首案（2026-11-16）

- 套件：ECEN721_PAM4_SAR7_FAST_PILOT_20261116（ZIP SHA-256 b01e56db…2ecb，manifest e049fa8b…98d0，portable deck 903d79a5…2032）。`package/` 為 Codex 原始碼，不含 deck／ZIP。
- 電路沿用 761279（`sar7_10_tt_matched_q_load`），只換 25 條時間卡片：週期 571.429 ps，試碼到比較 21 ps，比較到讀取 42 ps。
- 結果：job 761321 COMPLETED，solver 128 s。**screen_pass=false**，logic_smoke_pass=false。
  - 3/84 bit 未解析（b5×2、b4×1）。
  - registered 碼錯 9/12，誤差總和 147，最大 32 LSB（761279：6/12，總和 6，最大 1 LSB）。
  - 末端 CDAC 共模 −4.0 mV，最大取樣誤差 1.24 LSB。
  - 上三個 bit 從比較前到讀取的 CDAC 差動變化為 19.6／32.6／16.6 LSB，最小讀取餘裕 0.96 ps。這表示 21 ps 不夠讓 CDAC 建立。
- `results/sar7_fast_summary_761321.json`：去識別的 summary（原始 SHA a5432be7…ae5a；路徑已遮罩，故檔案 SHA 不同）。
- 原始波形與 measurements 保留在 Olympus run root。
