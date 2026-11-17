Stage: SAR7 放寬時序單案診斷（TT，60 ps + 60 ps）
ZIP: ECEN721_PAM4_SAR7_RELAXED_PILOT_20261115.zip（OneDrive ECEN 720/outputs）
SHA256: 55ec7f5dd3b8cb9a0befbb910407e03ca2d29bd4f4151d97a3ffc153c870de64
Guide: OneDrive ECEN 720/outputs/PAM4_SAR7_RELAXED_PILOT_20261115/HANDOFF_zh_TW.md
Recommended: 只提交 sar7_03_tt_relaxed 單一短測；完成後回報，其他案不在這張交接的範圍
Resources: 1 CPU／6 GiB／Slurm 30 min，預估 solver 3–6 分鐘、raw 約 80–100 MB
Commit allowed: handoff + results
Needs user decision: no

## 判斷與本案範圍

Job 760002 的 42 ps 決策窗在 84 個 bit 全解析，但會錯 10／12；最大解析 38.1 ps，末端共模下降約 107–112 mV。原 25 ps 案的逐 bit 未解析合計 73／84，請以逐 bit 算出的 73 為準。

先排除時序資源互擠。這一案保持相同電路、12 個輸入碼、1 Ω、100 mVppd、輸入共模及各週期取樣時刻。用 1,080 ps 週期（0.926 GS/s）同時給 60 ps DAC 等待、60 ps 比較。逐行差異應只有 22 條時序脈波、兩條 PWL 時間軸與 stop，共 25 行；參考電壓與 PWL 電壓值不變。這是低速診斷，結果不作 1.75 GS/s 規格驗收。

核對 ZIP、verify、三項測試、單根目錄 approval 與 deck SHA 再送。approval 由工具生成，只將 approved 改成 true，授權說明可放本機 state。回報新 job ID、未解析、錯碼、最慢比較、取樣誤差與末端共模。保留全部 raw，沿用原證據，不重跑 759069 或 760002。
