Stage: SAR7 補齊原生 r5 CML source 差動路徑單案（TT）（回覆 inbox/20261115T2032_sar7_cml_rdeg_pilot.md）
Status: done
Decision: STOP。補上 250 Ω source bridge 後，差動增益從 0.033 回到 0.588，符號一致 83/84，CDAC 共模隔離維持在約 −4 mV，未解析 bit 歸零。Σ|Δcode| 從 197 降到 23。不過 max |Δ| 是 5 LSB，大於「約 1–2 LSB」的目標，所以依指示停下總結，不調參、不續案。
Summary: job 760348 COMPLETED 3:39（n02-hera，solver 188.8 s，raw 87.8 MB／du 39M）。sar7_cml_rdeg_summary.json SHA256 ab2cdaaa6840bbb81841bc120d5d2cb69a47553c1e71e2c8ec22f0f2283dec95；measurements.json SHA256 0f311887…7114；tran SHA256 1632e997…a668；staged bench a6065cbd…cd1（執行前後相同）。
Run paths: ~/ecen720_28nm/runs/pam4_sar7_cml_rdeg_20261115.ot1Vbg（package、approval.json、wrappers/env_rdeg.sh、wrappers/wrap_rdeg.sbatch、logs/rdeg-760348.log、sar7_07_tt_r5_cml_rdeg/、sar7_cml_rdeg_summary.json）；pointer ~/ECEN721/.sar7_cml_rdeg_base
Commit: handoff + results（projects/pam4/campaigns/sar7_cml_rdeg_20261115/、handoff/archive/）
Needs user decision: no

## 核對
- ZIP SHA256 938e179f…3e9f 與 header、sidecar 都相符。`sha256sum -c` 5/5 OK。`verify` 顯示 sar7_07_tt_r5_cml_rdeg，portable deck 362dc80f…006f，與訊息相同。unittest 3/3 OK（含 test_only_source_bridge_differs_from_760254_portable_bench）。
- 環境沿用 760254 的 env。PAM4_SAR7_CML_PACKAGE 仍指向舊 CML 包（SJl3lN），沒有指向新包。另外設定 PAM4_SAR7_CML_RDEG_PACKAGE／ROOT／APPROVAL；root 前綴是 pam4_sar7_cml_rdeg_。
- Approval：template 綁定新 root、單案、manifest SHA bd6428e1…5ce3（= SHA256SUMS.txt）和 deck 362dc80f…。我只把 approved 改成 true，沒有加欄位。
- staged bench 對 760254 bench 的 diff 只有 1 行：`RSENSE_DEG (sem sep) resistor r=250`。case.json 的差異只有 case_id、portable/bench SHA，以及 comparator_sense 描述多了「source bridge 250 ohm」。
- 只送一案（20:36 送出，在 21:45:37 截止前）。沒有重跑舊案，也沒有 sweep。新舊 raw 全部保留。

## Gate 數字（760132 理想隔離 → 760254 CML 無 bridge → 760348 CML + 250 Ω bridge；760234 ref-trim 直接負載作參考）
- 感測臂 84 點：projected gain 1（理想）→ 0.0335 → **0.588**；符號一致 —／80/84 → **83/84**。唯一不一致的點是 #6 b1，held diff 只有 +15.5 µV（約 0.02 LSB），感測端輸出 −3.1 µV。
- 感測輸出共模 0.8348–0.8349 V（760254 為 0.8348–0.8350 V）。比較前平均供應電流 260.7 µA，和 760254 的 260.7 µA 相同，bridge 沒有改變 DC 電流。
- 未解析 bit：0 → 3 → **0**。comparator 和 registered 12/12 全部可讀且一致。最大解析時間 46 → 60 → **50.3 ps**，在 60 ps 視窗內。
- 錯碼：10/12 → 11/12 → **10/12**（760234 為 7/12）。
- Σ|Δcode|：15 → 197 → **23**（760234：8）；max |Δ|：3 → 24 → **5**（760234：2）。
- 逐碼（expected→registered，Δ）：64→65 (+1)、0→0、127→127、31→28 (−3)、96→101 (+5)、63→65 (+2)、65→67 (+2)、85→90 (+5)、42→41 (−1)、1→0 (−1)、126→127 (+1)、64→66 (+2)。760132 理想隔離的 comparator 碼是 +1, 0, 0, −2, +3, +1, +1, +3, −1, −1, +1, +1。兩者的誤差符號一模一樣，760348 的幅度大約是 760132 的 1.5–1.7 倍。
- 末端 CDAC 共模變化：−4.30／−4.26 → −4.01／−3.91 → **−4.00／−3.91 mV**。隔離維持（760234 直接負載為 −112.4／−109.0 mV）。
- 最大取樣誤差：1.687 → 1.655 → **1.595 LSB**。

## 判讀（唯讀，未改程式）
- bridge 恢復了差動路徑，所以增益回升，760254 的 −18.6 LSB 大偏移消失，主要失敗已經解除。
- 剩下的誤差和 760132 理想隔離的誤差同號、同型，760132 也用未 trim 的 Vref。由此推斷，主要來源仍是未 trim 參考和取樣誤差（最大約 1.6 LSB）。增益 0.588 < 1，使 comparator 的輸入等效誤差放大，因此幅度比 760132 大。760234 trim 過 Vref 之後只剩 Σ8／max 2，但那一案沒有感測隔離。這個推論沒有用模擬驗證。
- 未換 tail、未改 bias、未掃 Vref，也沒有送下一案。下一步（例如在 CML 感測下 trim Vref，或提高感測增益）由 Codex 決定。C1／C2 仍未授權。

## Raw
- 保留：sar7_07_tt_r5_cml_rdeg/raw（87.8 MB，du 39M），以及 760254、760132、760234 的既有 raw。summary commit 後也不退役，等 Codex 指示。
