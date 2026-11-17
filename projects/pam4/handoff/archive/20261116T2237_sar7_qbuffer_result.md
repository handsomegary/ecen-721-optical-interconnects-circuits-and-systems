Stage: SAR7 1.75 GS/s q-buffer 單案（sar7_16_tt_175gs_qbuffer），回覆 20261116T2217_sar7_qbuffer_pilot.md
Status: done
Decision: STOP — screen 未過：registered 7/12 錯、Σ10、max 3 LSB，與 761524 逐碼完全相同；raw q 已大幅恢復，但 decode 節點反而趕不上
Summary: raw q 未解析 26/84 → 2/84，comparator 10/12 可讀、5 錯、max 1 LSB，並與 register 逐碼一致；decode 在 552 ps read 只有 28/84 到 rail，release 時 40/84。錯碼來自比較決策本身，不是 q 讀出。
Run paths: ~/ecen720_28nm/runs/pam4_sar7_qbuffer_pilot_20261116.GscWI6（env: wrappers/env_qbuffer.sh；summary: sar7_qbuffer_summary.json）
Commit: pending
Needs user decision: no

## 執行
- ZIP SHA256 51973c01c8c6943b9d8e6166dfd6efc1763737a79009ec8313031ab0fa417882 相符；sha256sum -c 5/5 OK；verify OK（portable 509bbedf…da813a）；unittest 7/7；manifest 928590bc…0188ca 相符。
- 依授權，approval 只把 approved 由 false 改為 true。staged deck 0b3976968a459622b198d90939d77980d11f7dd5b3a5d3ea9a64e081b9c62f53，對 761524 deck（5aaa4b22…399be1）的 diff 是刪 29／加 57：28 個 XNDO/XNDZ 的 q port 改接，14 個 XQIN SAR_INV 與 14 個 XQOUT SAR_NDINV2，外加 1 行 save。沒有 subckt、MOS、source 或時序變更。
- job 761549 於 04:28:04Z（截止 05:15Z 之前）提交，COMPLETED 0:0，耗時 5:44，solver 301.3 s，batch MaxRSS 120 MiB，在 n02-hera 以 classic +mt=1 跑 1 CPU。只送這一案，未收集重試，也未送第二案。
- 送件時 account 用量：C2 761525_0..2 共 3 CPU，另有 1 CPU 不屬本專案，加上本案共 5 CPU，不超過 QOS 上限 6 CPU。
- SHA256：summary 8ab3c03c13658704b2c4a20be6bd453e864f74c4e7e1a6169434a275bbe2eb93；measurements 569c78e621d19bd6a9ab066b8fd87e0b1382c13fb872abd928f55964d1e4308a；tran 1abec792de375805df2b212a6ef8681855acc619d3202d09384180e067a3568a（118,290,642 B）。raw 全部保留。

## 結果（各讀點；括號為 761524）
| read | cmp 可讀/錯/Σ/max | reg 可讀/錯/Σ/max | 未解析 bit |
|---|---|---|---|
| 565 | 10/5/5/1（0/–） | 12/7/10/3（12/7/10/3） | 2（26） |
| 563 | 10/5/5/1 | 12/7/10/3 | 2 |
| 554 | 10/5/5/1 | 12/8/14/4 | 2 |
| 557 | 10/5/5/1 | 4/2/2/1（8 缺） | 2 |

- 逐碼比較（expected→cmp/reg565）：64→64/64、0→0/0、127→127/127、31→31/31、96→95/95、63→64/64、65→64/64、85→缺/88、42→缺/44、1→0/0、126→127/127、64→64/64。四個讀點的 registered 碼都與 761524 **逐碼完全相同**。
- 未解析的 2 bit 是 conv7 b3 與 conv8 b2，正好落在兩個多 LSB 錯碼（85→88、42→44）。conv7 b3 在 compare+30 時 held 為 −3.0 LSB、sense 為 −1.47 LSB；conv8 b2 的 held 為 −0.84 LSB、sense 為 +0.29 LSB，兩者符號相反。
- CM：active 552 ps 為 −4.04／−3.99 mV；post 565 ps 為 −9.15／+5.40 mV，物理讀出窗有效，兩者都在 ±10 mV 內。最大取樣誤差 1.68 LSB；最大 resolve delay 43.2 ps；reference 峰值電流約 0.19／0.20 mA。
- q 時序（84 trial）：raw q 在 read 時已解析 82/84，stable-rail delay 中位 34.95 ps、最大 43.18 ps。mid 在 read 時有原 rail 分類的 50/84。decode 在 read 時到 rail 28/84，release 時 40/84；有到達的 28 筆 decode stable delay 中位 40.4 ps、最大 51.7 ps。以 conv0 b6 為例：raw 50% 交越在 compare 後 32.7 ps，mid 39.2 ps，decode 在 read（+61 ps）時只有約 6 mV。最後一個 b0 的 next launch 依設計為 unavailable，未外插。

## 判讀（屬於上面三種預設結果中的第二種）
1. 減輕負載確實讓 raw q 到 rail：未解析 bit 由 26 降到 2，comparator 碼可讀、max 1 LSB，並與 register 一致。這支持原 q 負載限制了 comparator 的讀出。
2. 兩級 buffer 的延遲讓 decode 節點來不及：在 read 時只有 1/3 到 rail，約一半到 release 才到。不過 registered 碼與 761524 完全相同，表示 strong decoder 的 q 輸入時序並沒有改變任何決策結果；在 trial 為高的期間，決策由 trial 路徑主導。
3. 7 個錯碼（5 個 ±1 LSB、85→88、42→44）都是比較器本身的決策；comparator 與 register 結果一致。限制來源在 q 讀出之前：held、sense、reference 或 CDAC 在比較時的類比建立，尤其是 conv7 b3 與 conv8 b2 的 held 和 sense 符號不一致。q 負載不是錯碼的根因。
4. 尚不確定：(a) decode 晚到對下一個 bit 的 held 是否有影響，目前沒有逐 bit 歸因；(b) 兩個多 LSB 錯碼是 held 未建立還是 offset，需要看 held 對 compare 的時間序列。

依指示不自行加第二案，也不改時序或 TG；SAR7 截止已過，回 Codex 決策。C2 761525 仍在執行，前三案 RUNNING、其餘 PENDING，由既有 2144 entry 續看。
