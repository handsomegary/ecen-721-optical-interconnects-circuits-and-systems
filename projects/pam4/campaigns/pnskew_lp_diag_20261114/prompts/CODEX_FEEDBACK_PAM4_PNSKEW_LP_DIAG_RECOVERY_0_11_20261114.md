【ECEN 721 #6 P/N deskew LP_DIAG recovery（collect-only 0／11）：兩案正式判定都通過。SS 快速上電收斂到 338.335 µA；replica STB 為 PM 84.03°、GM 19.63 dB】

一、執行
- recovery 套件（ZIP SHA b57df58f…）：SHA256SUMS 全部通過，`lp_diagnostics.py --mode verify` 通過，86 項離線測試通過。diagnostic_plan.json 的 SHA 仍是 b74093eb…，與原 campaign 相同。
- 依 CLAUDE_START 在原 754102 campaign 產生 snapshot（diag_snapshot_0_11.json，SHA c79cfce4…）。兩案都記錄了原 job 754103、n01-zeus 與 4 個 raw。
- 使用者批准 collect-only 0／11。approval 放在套件外：mode collect-only，綁定 snapshot c79cfce4… 與 recovery manifest 0f709eb9…。
- `recover_diag.py --mode collect-only`：兩案都是 pass。三個新檔都有寫出（diagnostic_recovered.json、diagnostic_recovery_receipt.json、diagnostic_recovered_completion.json），completion 同時綁定量測與收據的 SHA。原 deck、run_status、measurements／completion 與 raw 都沒有動。沒有重跑 Spectre。

二、結果
1. 案 0（SS 快速上電，cb0）：status pass。
   - 檢查項全部 true：supply_within_2_percent、iref_within_2_percent、servo_within_2_percent、kick_below_0p01_uA、initial_supply_off。
   - 判定窗 475–500 µs（1251 點）：
     - Iref 338.335 µA（目標 338.3），最大與最小相差小於 0.001 µA；
     - replica 337.812 µA，伺服誤差 −0.155%；
     - 啟動 kick 0.00465 µA。
   - 初始 kick 峰值 0.052 µA，發生在 0.27 µs；當時 GF_VDD 0.217 V，GMSQST 0.170 V。
   - restart_rail_cycle_observed 是 null，符合預期（這案不是重啟）。
2. 案 11（SS cb2 replica STB）：status pass。
   - PM 84.034°（在 10.336 MHz），GM 19.625 dB（在 513.16 MHz），與原生 margin.stb 一致。
   - 由取樣的複數迴路增益算出 PM 84.033°、GM 19.625 dB；單位增益交越 10.3356 MHz，零相位交越 513.18 MHz，與原生值吻合。
   - DC Iref 338.335 µA（與整合版一致），啟動已釋放（kick 0.00465 µA）。

三、判讀
- SS 下的偏壓可以從零電源啟動，並收斂到與 DC 相同的工作點；replica 迴路的穩定度裕度充足（PM 遠高於 60°，GM 高於 10 dB 約 9.6 dB）。
- 收集器修正有效。之後新案件可以直接用新版收集。

四、下一步
- 依你的安排，1（SS 慢速上電）、2（SS 掉電重啟）、12（SS cb2 beta STB）要用新的 run approval 另外批准。beta 依 BETA_CRITERIA 判讀：無交越時看 max |T| 與 min |1−T|，若 max |T| ≤ 0.31623 就記為通過保守篩選。
- 這三案通過後，再提 TT／FF 的啟動（3–8）、其餘 STB（9–10、13–20），以及 XT2 有限擺幅（21–22）。
