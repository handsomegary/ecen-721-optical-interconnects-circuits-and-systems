Stage: SAR7 760348 保留資料最後收尾查核（零新模擬）（回覆 inbox/20261115T2050_sar7_cml_rdeg_final_audit.md）
Status: done
Decision: STOP。760348 既有 raw 的唯讀查核完成。感測級是乾淨的 affine：slope 0.588，零交越 −0.18 LSB，大訊號符號 82/82 一致。殘餘錯碼要歸到 CDAC 有效 span 壓縮：span 113.9 LSB，理想值 127 LSB，少約 10%；MSB 有效權重 56.1 LSB，理想值 64 LSB。依指示停止調參，不再送任何模擬。
Summary: collector job 760362 COMPLETED 0:20（1 CPU／6G／10 min，零 solver，raw 未新增）。sar7_cml_rdeg_final_audit.json SHA256 bc8c4e64c7d053b458adc5efe1c3c865202d1e02e52c7d48581f58c62898f9c4（4559 B），status measured_from_retained_evidence。
Run paths: ~/ecen720_28nm/runs/pam4_sar7_cml_rdeg_audit_20261115.rvHdNm（pkg.zip、PAM4_SAR7_CML_RDEG_AUDIT_20261115/、wrappers/env_rdeg_audit.sh、wrappers/wrap_rdeg_audit.sbatch、logs/audit_760362.out、sar7_cml_rdeg_final_audit.json）；來源 ~/ecen720_28nm/runs/pam4_sar7_cml_rdeg_20261115.ot1Vbg（未改動）
Commit: handoff + results（projects/pam4/campaigns/sar7_cml_rdeg_audit_20261115/、handoff/archive/）
Needs user decision: no

## 核對
- ZIP SHA256 83bf3ae0…7039 與 header、sidecar 都相符。上傳後 `sha256sum -c` 3/3 OK。`verify` 輸出 sar7_07_tt_r5_cml_rdeg 362dc80f1ca8444f59c1f620d2fb5fdae2d8c8948ef2bb7aa3155b2533cbf006 read-only analysis verified。unittest 3/3 OK。
- 環境：source 原 760348 的 env_rdeg.sh（PAM4_SAR7_CML_RDEG_PACKAGE 指向原 ot1Vbg 包）。PAM4_SAR7_AUDIT_PACKAGE 指向舊 CDAC_AUDIT 包（QDKGAI）。PAM4_SAR7_CML_RDEG_AUDIT_PACKAGE／ROOT 指向新的 rvHdNm。第一次 verify 失敗，原因是舊 CDAC_AUDIT 包 import 時需要 PAM4_SAR7_ISOLATE_PACKAGE。我從原 760174 audit wrapper 照抄同一個值（kbTlvs isolation 包），只加這一個 env，沒有改任何套件。之後 verify 和測試都通過。
- 執行 audit 時加了 `--source-zip`，指向 ot1Vbg 裡仍保留的原 ZIP。工具實測得到 original_zip status measured。

## 完整 SHA receipt（工具實測；更正 2042 回報）
- summary: ab2cdaaa6840bbb81841bc120d5d2cb69a47553c1e71e2c8ec22f0f2283dec95
- measurements: 0f311887f7e9803bf70afde08d36c40aab71b9d638196d7e5654f03987f07114
- tran: 1632e997754871f7c7957c5777285df18c6d5008576d505ba50a9e73ecb5a668
- staged bench: a6065cbd6820975f81026d3156214c330818ade9615e4bb5fa5bbc29fd674cd1
- portable bench: 362dc80f1ca8444f59c1f620d2fb5fdae2d8c8948ef2bb7aa3155b2533cbf006
- pilot manifest: bd6428e1f85aa5eaf1a8ee99c521b05ffef64c848eb0c53402ccb1be4f995ce3
- CDAC 分析 manifest: 91f528381bb0cc61b555f0ab673026faf61063803b1d19ed2c574b66143061c4
- 原 ZIP: 938e179f33863ddec49894ba0a44f27b5249cf4efad3dfbfe4ac1bd9248e43dc（measured）
- 更正：2042 回報把 ZIP 寫成「938e179f…3e9f」、portable 寫成「362dc80f…006f」，兩個縮寫尾碼都是我抄錯的。正確尾碼是 …3dc 和 …f006（完整值見上）。實際核對用的一直是完整雜湊，原 ZIP 在本機也重算到 938e179f…43dc。2042 原檔保留不改。

## CDAC 有效權重（84 個比較前狀態，9 參數線性擬合）
- status identified；usable 84 點，留一 84 點，留一 RMSE 0.861 LSB；omitted control-state 點 0。
- sample gain 0.9903；offset 57.12 LSB。
- 權重 b6→b0（LSB）：56.13、29.41、14.70、7.00、3.60、2.02、1.054（理想值 64、32、16、8、4、2、1）。
- 全碼 span 113.92 LSB，理想值 127 LSB（−10.3%）。對照 760174 retained-raw audit 的 107／119 LSB：這是不同電路條件下的描述性擬合，不合併宣稱，也不作 trim 預測。

## 感測級 affine（sense_diff = slope·held_diff + intercept）
- slope 0.5881 V/V；輸出端 intercept 82.2 µV；輸出端 affine RMSE 224.6 µV。
- SENSE STAGE ZERO CROSSING（不是 comparator offset）：輸入端 −139.8 µV＝−0.179 LSB（LSB 0.78125 mV）。
- 符號一致：全部 83/84；|held| ≥ 0.25 LSB 82/82；|held| < 0.25 LSB 1/2（唯一反號點落在這裡）；碼正確的 conversion 14/14；碼錯的 conversion 69/70。
- 判讀：感測級在大訊號下不會判錯號。錯碼的來源是 CDAC 收斂點（span 壓縮加 gain），不是感測級。

## 原計分（保留不改）
- 錯碼 10/12；Σ|Δcode| 23；max |Δcode| 5 LSB；max sample error 1.595 LSB；final CM −4.00／−3.91 mV。這只是 0.926 GS/s 診斷，不是 1.75 GS/s 驗證，不宣稱 SAR smoke 通過或達到參考論文。

## Raw
- 全部保留：760348 的 raw 和本次 root 都沒動，也沒有 retire。C1／C2 未碰，也沒碰其他專案。
