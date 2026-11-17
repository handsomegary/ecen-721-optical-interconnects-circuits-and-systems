Stage: SAR7 761549／761524 保留波形因果稽核（零新solver）
Status: done
Decision: PROCEED — 兩個錯位（conv7 b3、conv8 b2）都是「當前bit trial步階的底板／held在compare時鐘後才過零」，前一bit接受reference已在compare前16–20 ps穩定；比較器依compare瞬間仍為正的輸入判1。
Summary: collector 761591 COMPLETED 0:44（1CPU/6G，提交於04:57:41Z，距05:15Z截止1039 s）；0新Spectre、0新raw；兩來源各parse一次，前後SHA不變。
Run paths: ~/ecen720_28nm/runs/pam4_sar7_qbuffer_audit_20261116.F0Druj（env wrappers/env_audit.sh；wrapper wrappers/qaudit.sbatch；log logs/qaudit_761591.out）
Commit: handoff + results（見下）
Needs user decision: no

## 驗證
- ZIP SHA256 eb77a401…0833d4 本機與Olympus相符；SHA256SUMS.txt（CRLF，tr -d '\r'後）5/5 OK；manifest SHA 8931c3c7…572fbf 與訊息相符。
- verify：「Two frozen sources verified; retained-only audit, zero solver」；unittest 8/8 OK。
- 來源不變：稽核後於Olympus直接重算原檔（非repo副本）：
  - 761549 summary 8ab3c03c…a17882、measurements 569c78e6…308a、tran 1abec792…a3568a
  - 761524 summary 73dafa11…a84ac03、measurements a8b0c965…3a18、tran fc21cd54…b4cb318
  全部與PLAN pin一致；兩來源根目錄內沒有任何比本包ZIP上傳更新的檔案（find -newer 為空）。compact中 raw_parse_count=1、new_solver_jobs=0、source_read_only=true（兩來源皆是）。
- 新輸出：
  - sar7_qbuffer_audit_compact.json  b0c87e35000a200510773627721d9af9e45f47103f2ad52ef3a9f677bbcc0978（288 KB；只含edges／sign runs／command runs，無波形表，無帳號字串）→ repo results/
  - sar7_qbuffer_audit_local_evidence.json  58a43871efe59f462c799d694b4426f6f5531f511e540cf201a31de587614d01（36.8 MB）→ 只在Olympus與OneDrive outputs/PAM4_SAR7_QBUFFER_AUDIT_20261116_RESULTS/

## 時間原點
每個window以該bit自身clk上升（compare）為0；clk3/clk2 edge與排程compare差 <1e-12 ps。conv0 b6：compare 120 ps、read 159 ps，間隔 +39.0 ps（更正2237的+61）。conv8時間軸含 +0.43 ps 的轉換偏移（4912.43等），已用相對時間消除。

## 關鍵轉換（761549 qbuffer；761524 strong 的held/sense過零與之差 ≤0.25 ps）
所有時間為相對「當前bit compare」的ps。

| 項目 | conv7 b4→b3（錯：85→88，b3應0判1） | conv8 b3→b2（錯：42→44，b2應0判1） | 對照 conv8 b4→b3（正確b3=1） |
|---|---|---|---|
| 前一bit接受command穩定到rail | b4 O_rail 自 −19.75 起持續 | b3 O_rail 自 −15.93 起持續 | b4 Z_rail 自 −7.43（之前 −17.7…−7.7 非互補過渡，opp 9樣點） |
| 當前trial上升 | −19.0 | −15.0 | −19.0 |
| 當前bit四個reference gate半VDD | −10.5 … −5.1 | −6.5 … −1.1 | −10.5 … −5.1 |
| 當前bit底板半擺幅 b_n / b_p | −1.31 / +3.94 | +6.79 / +9.42 | −0.99 / +4.04 |
| held過零（+→−） | +1.55 | +9.10 | 在 −6.43 已轉+（−→+），compare時正確同號 |
| sense過零 | +6.11 | +15.20（+27.95再轉+，+37.07又轉−） | −2.96 已轉+ |
| comparator x 下降（y無） | +20.95 → 判1 | +19.37 → 判1 | +18.23 → 判1 |
| raw q / qmid / qdecode 交越 | q +35.85、qmid +42.38、qdecode +47.66 | q +33.10、qmid +39.62、qdecode +44.83 | q +31.0、qmid +37.4、qdecode +43.0 |
| 原read（+40/+38）判讀 | 未解析 | 未解析 | — |
| release／reg565 | 1 / 1 | 1 / 1 | 1 / 1 |

判讀：
1. 兩個錯位中，前一bit接受reference（b4→conv7、b3→conv8）在下一compare前16–20 ps已穩在rail，整個regeneration期間沒有相反command（opp=0）。「前一bit接受reference晚到」不是這兩碼的直接原因。
2. 真正晚到的是**當前bit trial步階**：底板半擺幅在compare附近或之後（conv7 −1.3/+3.9；conv8 +6.8/+9.4 ps），held/sense在compare時鐘後 +1.5/+6.1 ps（conv7）與 +9.1/+15.2 ps（conv8）才由+轉−。比較器x在約+19–21 ps再生，結果與compare瞬間仍為正的輸入一致（判1）。對照的正確轉換（conv8 b3）held/sense在compare前 −6.4/−3.0 ps已過零。
3. 因此支持「類比建立（trial→底板→held/sense）在compare前未完成」有貢獻；不支持「控制／底板已穩、sense整段同號而內部決策反向」的純comparator offset解釋。conv8 b2的sense在再生中二次換號（+27.95、+37.07）顯示有再生期間的動態（kickback或步階振鈴），仍無法由這些點分離。
4. q/qmid/qdecode在原read之後才交越（qdecode +43…+48 ps > read +38/+40），與「late-valid、原deadline未解析」一致；這是讀取時限問題，與上面的錯碼原因分開。

## 仍無法區分
- 半VDD gate交越只是電壓proxy，不是開關導通或電流；底板「半擺幅」不等於settled到LSB精度。
- 0.25 ps原生樣點與選定節點不能排除更快擾動；held/sense過零時間取決於殘餘值大小（conv7 b3 殘餘約+2.4/+3.1 LSB），無法單獨分出「trial延遲」與「CDAC RC時間常數」。
- 只有12碼短測，不是DNL/INL或FFT驗證；未提出新電路或sweep。

## 依訊息
未送新Spectre，未重跑任何source collect，原raw全部保留（761549、761524皆未退休）。C2陣列761525仍照2144 waiting_runs監看（04:58Z時0–2執行中58 min，3–94 pending），未合併、未取消。
