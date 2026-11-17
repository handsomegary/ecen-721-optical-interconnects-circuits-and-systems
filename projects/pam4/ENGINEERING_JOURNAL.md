# PAM4 工程觀察與設計決策紀錄

<!-- PHASE2_CURRENT_STATE -->
## 目前phase2狀態（2026-11-08）

740861已COMPLETED0:0／14:58；原source、5nodes/799edges模型與16,256列固定預測驗證通過，但secondary raw **225→228**（candidate多3），原VM218→190的優勢未重現；理想ADC253→250，primary皆0。**舊VM raw退役HOLD**，準備原solver異常診斷選項，沒有新fit/設計/大批次。兩邊effective scalefactor均0.9，沒有單一模型/scale/APS因果結論。以下pending/準備段落為歷史，以最新實測追加判讀；更早30pair結果仍保留其site-model內部比較範圍。
<!-- END_PHASE2_CURRENT_STATE -->

本檔按日期追加工程推理，保留成功、反例與失敗；不以最新數值覆寫先前結論。每筆紀錄固定寫明：假說、實際改動、理由、模擬/分析證據、觀察、推論、決策、下一個驗證，以及結果與限制。設計、規格或求解器的新變更，需先有模型證據與人類核准。

## 2026-11-07 — raw FFE 改善未穩健轉成 7-bit ADC+FFE 優勢

**假說與既有設計脈絡。** 已凍結的 baseline 次取樣支路每側為 **10 fF／TG 1 µm**，candidate 為 **25 fF／TG 2 µm**。這是本次 noise-seed 檢查之前已存在的改版，**不是本次新增的尺寸變更**。待檢驗問題是：candidate 的類比取樣/未量化 FFE 改善，是否能在固定理想 7-bit 量化後仍維持。

**本次實際改動與理由。** 只在既有固定資料序列上改 noise seed 251/252/253；不改電路、偏壓、時脈、fullscale、lag、門檻、訓練正規化、17 taps 或 bias。每案先讀取 2048 個 held inputs，再評分 2032 個完整 FFE outputs。noise repeats 是敏感度檢查，不能稱作新的 independent input-data holdout。

**模擬與分析證據。** 下表為 secondary branch 的 observed symbol errors，每格分母均為 2032。所有 primary raw/ADC+FFE 案例均為 0/2032；零錯誤不等於已證實任意低 BER。

| Noise seed | Baseline raw FFE | Candidate raw FFE | Baseline 7-bit ADC+FFE | Candidate 7-bit ADC+FFE |
| ---: | ---: | ---: | ---: | ---: |
| 251 | 212 | 191 | 216 | 210 |
| 252 | 214 | 170 | 216 | 200 |
| 253 | 222 | 208 | 226 | **237** |
| 合計／6096 | 648 | **569** | 658 | **647** |

**觀察。** secondary raw FFE 在三個 seeds 都較佳（primary 三 seed 均為零錯誤平手）；ADC+FFE 在 seed253 反而多 11 errors。raw 的總差距為 79 errors，經量化與原 ADC detector 後只剩 11。這支持「理想量化鏈中優勢大幅縮小且不一致」的敘述，不能只選 seed251/252 宣稱穩健改善。

**模型分解。** 原 raw 與 ADC detector 的凍結正規化、taps 和 bias 並不相同。定義 `r = F_raw(x)`、`c = F_raw(Q7(x))`、`a = F_ADC(Q7(x))`，則 `a-r = (c-r) + (a-c)`。第一項保持 raw filter 不變以隔離量化輸入影響，第二項為同一量化輸入下兩套固定 detector 的差異；不可把 `a-r` 全稱為純量化誤差。

| Secondary，三 seed 合計／6096 | 原 raw fit `r` | 量化輸入、同 raw fit `c` | 原 ADC fit `a` |
| --- | ---: | ---: | ---: |
| Baseline errors | 648 | 653 | 658 |
| Candidate errors | 569 | 635 | 647 |

這是事後、路徑相關的固定算術診斷，不是物理雜訊來源的因果比例。raw→ADC：baseline 有 87 個原先正確變錯、77 個原先錯誤變對（淨增10）；candidate 為150與72（淨增78）。各 branch 全部無 clipping。

**推論與可檢驗機制。** secondary fullscale 固定75 mVpp，理想7-bit LSB為585.9375 µV。ADC filter 的等效 tap L2 為 baseline 約649.742 V⁻¹、candidate約850.119 V⁻¹。白色、獨立、均勻誤差假設下，`LSB/sqrt(12) * tap_L2` 的輸出 RMS 參考約0.10990與0.14379（PAM4 target units，非 volts）。較大的固定濾波器誤差增益，與 candidate 對量化更敏感的觀察相符；這是模型提示，未證明所有差異只由量化造成，也不是實測 SNR、ENOB 或熱雜訊。

Python 與獨立 MATLAB R2026a fixed-arithmetic replay 已在相同六案、十二個 branches 核對648個數值 metrics，其中360個整數比較要求完全相同；最大數值絕對差為1.14×10⁻¹³。兩者重現保存的原預測與錯誤數，未 fitting、改電路或啟動模擬器。分析程式/報告使用 SHA256 綁定；實驗依賴與完整私人檔案不在此本工程紀錄。

**決策。** 保留候選版 raw FFE 的改善，也保留 seed253 ADC 反例；目前不宣稱穩健 ADC+FFE 優勢。先走「既有模擬→分析→保留 compact 證據/清理 bulk→MATLAB+Python 建模與模型驗證→人類核准實際改動→少量預宣告 transistor-level cases」的循環，不直接盲掃 Spectre 尺寸參數。

**下一個驗證。** 先在行為模型中提出可反駁的量化/濾波器敏感度假說，固定對照路徑、來源 hashes、模型預測與 acceptance criteria；評估是否能改善判決而不引入 clipping。模型結果不直接授權 circuit 改版。實際設計變更需列明 intended change 並由人核准，再用少量預定 transistor cases 驗證；新的 holdout 必須與已看過的三個 seeds/資料序列分開。

**可追溯來源。** 固定算術使用原始 [FFE prediction/metrics source at3ea5451](https://github.com/<owner>/ecen-721-optical-interconnects-circuits-and-systems/blob/3ea545189d2976bcd7e827f21c398a95504c3ec4/projects/pam4/reference/source_snapshot/pam4_ffe_diagnostic.py) 與 [quantizer/Gray-metric source at3ea5451](https://github.com/<owner>/ecen-721-optical-interconnects-circuits-and-systems/blob/3ea545189d2976bcd7e827f21c398a95504c3ec4/projects/pam4/reference/source_snapshot/pam4_metrics.py)。這些是本 repo 既有的歷史 source，並非宣稱完整私人實驗可只靠這兩檔重跑。2026-11-06 的[舊 checkpoint](../../PROJECT_CHECKPOINT_20261106.md)保持歷史原貌；其中較早一次比較的235→210與本次216→210條件不同，不可混用。

## 2026-11-07 — 最後一個新資料 holdout pair（執行中，結果待補）

**假說/理由。** 前一輪模型與三 seed 觀察後，預先固定三個方向：candidate secondary raw errors較少；candidate secondary ADC-minus-raw penalty較大；candidate primary ADC errors不大於baseline。它們是可被反例推翻的模型假說，不是電性 acceptance gates。

**實際改動/授權。** 使用者指定各專案只再完成一個任務便停止。此 PAM4 任務保持既有兩個硬體版本與原 frozen FFE，只把兩個理想 PWL 刺激區塊換成新資料 seed2026110701，noise seed254；其餘 deck bytes可反向還原為原來源。新序列包含2432symbols，仍評2048held inputs/2032FFE outputs，未重新訓練或更換滿幅、lag與門檻。

**證據與當前結果。** Job `739745`已送出並進入執行，4CPU/15GiB，兩案例依序。模擬、OCEAN匯出、held extraction、固定 FFE/模型分析、精確四個 bulk targets 清理與STOP在同一個有限job內。**目前沒有新 holdout 的錯誤數、假說結果或清理成功宣告。**

**觀察/推論/決策。** 新輸入與先前三 seed/訓練資料不同；在看到結果前已固定案例、假說與判讀。等實測後原樣記錄SUPPORTED或NOT_SUPPORTED，兩者都不觸發自動優化、重訓、重試或下一個job。單一新資料序列/單一noise seed仍不足以認證穩健BER或實體ADC。

**下一個動作。** 取得這個任務的實際結果，完成分析與必要 compact 證據核對，記錄成功與失敗、清理核對過的bulk，然後停止。本 entry 的後續結果會追加，先前反例保留。

### 結果追加 — 新資料驗證完成、分析/清理後STOP

Job `739745` 實際以 `COMPLETED 0:0` 結束，15分59秒。新資料2026110701/noise254的實測錯誤數如下；每格分母2032，所有輸入clipping為0。未換硬體、重新訓練或調整滿幅/lag/門檻。

| Branch | Baseline raw FFE | Candidate raw FFE | Baseline 7-bit ADC+FFE | Candidate 7-bit ADC+FFE |
| --- | ---: | ---: | ---: | ---: |
| Primary | 0 | 0 | 1 | 0 |
| Secondary | 220 | **205** | **241** | **241** |

**觀察。** secondary raw FFE少15errors，但ADC+FFE是平手，不能說candidate勝出。ADC MSE甚至由baseline0.473072變為candidate0.476967（PAM4 target-unit squared）；相同symbol-error count不代表相同誤差分布或更佳整體性能。Primary只觀察到1→0個ADC errors，不構成穩健BER聲明。

固定路徑 `raw → Q7(x)通過同一raw fit → 原ADC fit` 為baseline **220 → 244 → 241**、candidate **205 → 233 → 241**，candidate少錯的幅度 **15 → 11 → 0**。前一輪三seed的幅度則為79→18→11。分解依賴資料與指定的控制路徑；不可主張純量化始終是相同比例或單一主因，更不能把兩套固定detector差異忽略。raw→ADC時，baseline有42筆原先正確變錯/21筆恢復（淨增21），candidate為59/23（淨增36）。

**假說判讀。** 三個預宣告方向在這一個新sequence/noise實驗中均為SUPPORTED：secondary raw較少（220對205）、candidate ADC-minus-raw penalty較大（21對36）、primary ADC不較差（1對0）。它們是觀察支持，不是統計顯著性、完整電性規格或ADC勝出證明。尤其第二個方向描述的是candidate的額外損失。

**證據與保留。** 16,256筆預測在本機以原固定函式重現；33個compact檔案/2,906,877bytes傳輸SHA吻合，42個遠端retained指紋無差異。精確四個bulk targets已不存在，移除143,394,816allocated bytes（136.752MiB；logical158,236,553bytes），沒有完整波形下載或archive。保存必要樣本、原係數、分解數據、來源與刪除收據。

**可追溯宣告。** [本次假說與新序列的凍結程式來源](https://github.com/<owner>/olympus-cadence-ocean-analog-notes/blob/main/tools/workflows/20261107/pam4_final_holdout/protocol_core.py)，來源SHA256 `ecde3b7cfe39efd72334ff97c566bf8d273958c54e88567cbad462c27510057d`；提交前protocol artifact SHA256 `c57230c6cd1bc0f43f56eab08f8c419f9fe9cab1d2ea32eb35e6df912eb7dcc1`；final score SHA256 `3068458a6990e1dc6999ee22a3b100fd112388121f7f7d157e9747e564eecd95`。連結是有權存取的workflow repo中固定日期的own-code快照，不是公開私人執行artifact。

**決策/停止邊界。** 此次fresh-input結果再次顯示raw優勢未帶到既定理想7-bit ADC+FFE；平手不是winner。按使用者要求完成分析、保留compact證據與精確清理後停止，`further_sweeps_or_jobs_allowed=false`。沒有額外重訓、設計掃描或下一個job；未來若重開設計優化，需新的可檢驗假說、模型證據與實際改動核准。

## 2026-11-08 — 新授權的一個固定硬體驗證pair（準備中）

**假說/理由。** 前一新資料案例secondary raw220→205但理想7-bit ADC+FFE241→241平手，固定路徑分解也隨資料改變。本輪只再用一個預宣告的新sequence檢查既有模型方向，不把前輪平手當成勝出，也不宣稱量化永遠是單一主因。

**實際改動/授權。** 使用者今天重新授權各專案一個有限任務。PAM4保持原baseline10fF/TG1µm與candidate25fF/TG2µm、原凍結raw/ADC17-tap FFE、fullscale、lag及門檻，只換理想PWL輸入為data seed2026110801、noise255。兩案4CPU/15GiB依序執行；沒有新硬體修改、fitting或參數掃描。

**證據/觀察/推論。** PAM4 Job `740067`已提交（4CPU／15GiB），目前尚無本輪實測錯誤數、假說結果或清理成功收據。提交前固定來源SHA與假說；觀察後保留SUPPORTED、NOT_SUPPORTED、平手或反例，不能改定義挑結果。單一新sequence/noise仍不足以證實穩健BER或實體ADC性能。

**決策/下一個驗證。** 完成這一個pair的模擬、固定分析、必要compact保存與精確bulk清理後停止，追加實際結果。昨天STOP是已完成週期的歷史，本輪是今天明確授權的下一個有限週期；不自動開下一輪或設計掃描。

**提交前宣告追加。** 本輪三個方向維持：candidate secondary raw errors較少；candidate secondary ADC-minus-raw penalty較大；candidate primary ADC errors不大於baseline。跨data0701/0801比較僅是描述：前draw已被看過並影響本輪動機，且不同draw使用不同的單一noise seed，輸入與noise效應無法分離。

### 結果追加 — secondary改善，primary預宣告假說出現反例

Job `740067`以 `COMPLETED 0:0` 結束，15分45秒，4CPU／15GiB。data2026110801/noise255仍使用原硬體及固定FFE；每格2032個complete outputs，所有held inputs clipping為0，沒有fitting、改滿幅/lag/門檻或電路尺寸。

| Branch | Baseline raw FFE | Candidate raw FFE | Baseline 7-bit ADC+FFE | Candidate 7-bit ADC+FFE |
| --- | ---: | ---: | ---: | ---: |
| Primary | 0 | 0 | **0** | **1** |
| Secondary | 245 | **207** | 261 | **232** |

**假說/觀察。** secondary raw較少（245→207，少38errors）及candidate的secondary ADC-minus-raw penalty較大（+16→+25），兩個方向在此觀察為SUPPORTED。第三個「primary candidate ADC不較差」則為**NOT_SUPPORTED**，因baseline0而candidate1；這個反例完整保留，不改假說、不忽略primary，也不把1error差當成統計顯著性或穩健BER證據。

Primary另有一個需要保留的數值細節：candidate ADC MSE0.057622低於baseline0.064373，錯誤數卻由0變1；較低MSE不保證較少threshold decision errors。在同一raw fit的量化控制路徑兩者皆0錯，candidate切到其原ADC fit才有1錯。因兩套原凍結fit不同，這個單點不能全歸因於輸入量化本身，也不構成物理因果結論。

**模型分解與跨資料比較。** 同一固定路徑 `raw → Q7(x)通過同一raw fit → 原ADC fit` 為baseline **245→263→261**、candidate **207→230→232**，candidate少錯幅度**38→33→29**。上一個data0701/noise254則為15→11→0，secondary ADC241→241平手。現在這個secondary ADC改善不能覆寫前輪平手或更早noise253的反例；固定路徑分解依賴資料，原raw/ADC detector也不同，不能宣稱量化始終占同一比例或是唯一原因。

本次secondary raw→ADC中，baseline有44筆原先正確變錯/28筆恢復（淨增16），candidate為59/34（淨增25）。兩個draw都保持原係數；前draw已被看過並影響本輪假說，且資料seed與noise seed同時不同，各draw只有一個noise seed，無法分離輸入與noise效應。這是descriptive cross-data驗證，不是新的獨立bit BER或穩健硬體winner認證。

**證據/保留。** 獨立本機重算16,256筆固定預測，label、decision、數值及錯誤數均與保存結果一致；36個compact檔案、2,923,359bytes傳輸SHA一致，46個遠端retained指紋未變。精確四個bulk targets已清除，移除143,738,880allocated bytes（137.080MiB；logical158,234,382bytes）。保留必要樣本/係數/預測/固定模型分解與收據，未封存或下載完整波形。

**可追溯來源。** [本輪固定假說與資料生成程式](https://github.com/<owner>/olympus-cadence-ocean-analog-notes/blob/main/tools/workflows/20261108/pam4_next_20261108/protocol_core.py)為有權存取者可讀的own-code快照；source bundle manifest SHA256 `b5402520bf5ff82c979ddbd6fc8525b76942c6f33ca180401ceedff0207a3eb8`，final score SHA256 `37be59d06a8850a087d2dfefb821a0f9662ad26593f23a58f84d2722ef26ae6e`。實驗payload、帳號、主機/家目錄、PDK、netlist與大型波形不放入本工程紀錄。

**決策/停止。** 保留本輪secondary改善，也保留primary反例與前輪ADC平手；不提出普遍勝出或新設計優化聲明。本次有限cycle已完成模擬、分析、compact保存及精確bulk清理後STOP；沒有再訓練、設計掃描或額外job。任何後續工作須另行授權並延續model-first證據流程。

## 2026-11-08 — 另行授權的夜間 crossed-seed 驗證（準備中）

**假說/理由。** 已觀察 secondary raw 改善、ADC 平手/反例及 primary 0→1 反例，固定路徑分解依資料而變。先前每個新 draw 只有一個不同 noise seed，無法分離兩因子。本次先固定 data2026110802–2026110807 × noise256–260 的 6×5=30 pairs，描述現有固定硬體/模型對兩因子的敏感度，不改寫前輪反例。

**實際改動/授權。** 使用者明確指定夜間先排好工作、關閉本機、明天讀結果。每 pair 仍是原 baseline/candidate 依序、4CPU/15GiB；原 frozen raw/ADC FFE、fullscale、lag、threshold 與硬體都不變，只替換兩個理想 data PWL 區塊及指定 noise seed。每份來源/新 labels/deck 都先以 SHA 固定且可逆驗證。

**預宣告判讀。** 三方向維持 candidate secondary raw errors 較少、candidate secondary ADC-minus-raw penalty 較大、candidate primary ADC errors 不大於 baseline。每 pair 的 SUPPORTED/NOT_SUPPORTED 與平手都保留；第三方向前輪失敗不是這次重寫定義的理由。最終按 data/noise 給 descriptive means，同 seed 不等於兩硬體相同物理 noise，FFE windows 仍相關，因此不宣稱因果 ANOVA、顯著性、robust BER 或完整 ADC 認證。

**執行/保留/停止。** 30 jobs 以 server-side afterok 串接，每份自己完成模擬、OCEAN、固定分析、小證據與精確四個 bulk targets 清理；有效的假說反例不阻止後續預定觀察，工具/完整性/分析/清理異常則停止鏈且不 retry。開始前可用空間需大於2GiB，不清理無關檔案、不保存完整波形備份。第30份僅彙整 compact evidence 後 STOP，沒有新增設計掃描。

**目前證據/下一個動作。** 尚在準備，此 entry 尚無夜間實測結果或清理成功宣告；實際34份總工作中的30個PAM4 job IDs與來源 manifest 會在提交後追加。明天依完整收據與結果保留成功、反例及異常，再提出模型層解釋；此授權不包含自動調整設計。

### 提交追加 — 30 pairs已排入伺服器，科學結果待讀

30份PAM4 jobs全部提交且afterok前驅/4CPU/15GiB/時間限制已核對，當時第一份RUNNING、其餘PENDING。來源manifest SHA256 `3798d64cfc48355469bdb8529d05baab5104f2e8045d7c0f78c28ca660d782f7`，提交前完整private package13項測試通過。下表列實際收據IDs，columns對應noise256–260；它們不是模擬成功或分析/清理完成的證據。

| Data seed | Noise256 | Noise257 | Noise258 | Noise259 | Noise260 |
| --- | --- | --- | --- | --- | --- |
| 2026110802 | 740098 | 740099 | 740100 | 740101 | 740102 |
| 2026110803 | 740103 | 740104 | 740105 | 740106 | 740107 |
| 2026110804 | 740108 | 740109 | 740110 | 740111 | 740112 |
| 2026110805 | 740113 | 740114 | 740115 | 740116 | 740119 |
| 2026110806 | 740120 | 740121 | 740122 | 740123 | 740124 |
| 2026110807 | 740125 | 740126 | 740127 | 740128 | 740129 |

兩條有限工作鏈已由Slurm管理，本機不必保持開機。明天讀取所有預宣告pairs的compact結果與精確清理收據，再記錄支持、反例、平手與任何工具異常；目前沒有overnight錯誤數或清理成功宣告。前一primary反例及ADC平手保持原樣。

### 結果追加 — 30/30完成；secondary一致改善，primary仍有反例

30個jobs全部`COMPLETED0:0`，原定60次電晶體模擬完成，沒有額外job、fit或硬體/clock/FFE改動。Slurm job elapsed合計8小時10分40秒；整鏈起訖8小時10分46秒，差6秒為job間隔。每pair每branch仍2032個FFE中心符號；每硬體每branch合計60,960個**相關視窗**，不是60,960個獨立BER試驗。

| Branch /全部30pairs | Baseline raw FFE | Candidate raw FFE | Baseline理想7-bit ADC+FFE | Candidate理想7-bit ADC+FFE |
| --- | ---: | ---: | ---: | ---: |
| Primary | 0 | 0 | **3** | **4** |
| Secondary | 6838 | **5610** | 7035 | **6085** |

**觀察與反例。** 本次secondary raw及ADC兩路均30/30pairs candidate較少錯，分別少13–79及3–86errors；這是對本次預宣告6×5矩陣的觀察。Primary ADC則3pairs較好、23平手、4較差，總數3→4。四個較差案例均baseline0→candidate1：data/noise **2026110802/258、2026110804/259、2026110805/257、2026110806/259**。所有clipping為0。它們不能被secondary改善掩蓋，也不能把單一error差解釋為顯著性。

| 預宣告模型方向 | 本矩陣支持數 | 保留的非支持結果 |
| --- | ---: | --- |
| Candidate secondary raw errors較少 | 30/30 | 無 |
| Candidate secondary ADC-minus-raw penalty較大 | 25/30 | data/noise0802/258、0803/256、0804/260、0806/258、0807/260（data均前綴202611） |
| Candidate primary ADC不較差 | 26/30 | 上述4個0→1反例 |

**固定模型分解。** Secondary的`raw→Q7(x)通過同一raw fit→原ADC fit`為baseline **6838→7002→7035**、candidate **5610→6008→6085**，candidate少錯幅度 **1228→994→950**。原ADC-minus-raw淨增為baseline197、candidate475；raw優勢沿這條指定算術路徑縮小278（約22.6%），本矩陣中仍未消失。原raw與ADC的兩套凍結detectors不同，這不是物理雜訊來源的因果比例，也不支持「量化永遠是主要原因」。Primary同raw-fit量化路徑合計3→3，但原ADC-fit結果3→4，同樣要保留fit/threshold路徑差異。

**跨資料與決策。** 六個data draw各五個noise seeds的描述統計及每個pair均保留，不挑最佳seed。本輪secondary的一致改善，不覆寫較早noise253的ADC反例或data0701/noise254的平手；同noise seed也不保證兩個不同電路具有相同類比noise實現。重疊FFE windows相關，未評估統計顯著性，不宣稱通用winner、robust BER或實體ADC規格合格。下一個推理步驟限於利用保存held資料的Python/MATLAB模型，檢查primary decision margins與同raw/原ADC fit的差異；本次沒有自動改設計、重訓或新模擬。

**分析與保留證據。** 獨立collector在server以實際held樣本與原固定函式重算487,680列預測/門檻決策、錯誤數、混淆矩陣與MSE；1470個retained SHA無差異，30份STOP、來源deck逆向還原與120個exact bulk targets不存在均核對。取回304個compact檔案共3,509,135bytes，傳輸SHA全符；第二次獨立核對重算60列aggregate、30份score/cleanup byte closure及全部304個本機SHA。未下載held/prediction全集、raw或fullCSV。

原job內清理移除**4,303,859,712allocated bytes（4.008GiB）**，logical為4,747,161,691bytes，沒有完整波形archive。原fullCSV/deletion inventory hashes已驗證；保存held可重算FFE，但刪除raw後不能重新從原波形抽取held。這次check只讀取/分析，沒有新模擬或額外刪除；30份有限工作已STOP。

**可追溯結果。** [安全closeout checkpoint](https://github.com/<owner>/olympus-cadence-ocean-analog-notes/blob/main/expected/overnight_results_20261108.json)、[全部pair counts](https://github.com/<owner>/olympus-cadence-ocean-analog-notes/blob/main/expected/overnight_pam4_pairs_20261108.csv)及[描述factor means](https://github.com/<owner>/olympus-cadence-ocean-analog-notes/blob/main/expected/overnight_pam4_factor_means_20261108.csv)在有權存取的workflow repo中保存；source manifest仍為`3798d64cfc48355469bdb8529d05baab5104f2e8045d7c0f78c28ca660d782f7`。提交紀錄保持歷史，不用job完成狀態代替以上實測判讀。

## 2026-11-08 — 歷史R7參數脈絡與精確replay前置紀錄

**改動與原理由。** 原R7先比較10fF/TG1µm baseline、25fF/TG1µm及25fF/TG2µm三案，每案noiseless/noise各一次。data2026102202/noise223，256inputs訓練/240FFE windows，再用224完整outputs評估；只在該training pool建立原raw及理想7-bit的17tap detectors，沒有noise fitting。原delivery記錄bounded比較、禁止自動擴充與實體ADC未驗證；但未找到當時選C/TG的物理動機文字，因此保留**unknown**，不倒推成kT/C已被隔離或解決。參見[原training delivery](reference/historical_checkpoints/secondary_r7_delivery_20261022.json)。

**觀察→下一驗證。** 三案training的secondary noise-minus-noiseless held centered RMS約1.091635、0.813157、0.755320mV。原文限定這是包含非線性/動態的trajectory difference，並非獨立device noise。之後獨立data2026102301/noise251固定baseline與c25w2、保留原fit，2048held inputs/2032FFE outputs，不在validation再訓練。原VM的secondary raw errors **218→190**，理想7-bit ADC+FFE **235→210**，primary兩路皆0；held centered RMS9.769784→7.860070mV。ADC-minus-raw penalty17→20，較小held RMS不能直接證明量化後或全ADC穩健勝出。參見[原獨立validation](reference/historical_checkpoints/secondary_validation_r7_delivery_20261022.json)。

**原決策與未完成分支。** 當時交付固定比較後停止，明載不繼續simulation/candidates/fitting，亦不可調整後重用此validation。10-29後續TG-off計畫的直接理由是釐清buffer/load settling與held disturbance；保留TGs/caps與comparator loads、只關128secondary clock sources，改變load history而非純noise隔離。該計畫狀態為planned/not simulated，preflight為VM未執行，0次simulation；不能當成已得到機制證據。

**本次歷史重現/本地清理。** 使用者新授權把舊條件交給Olympus重現，同時暫停新設計探索。首批為原noise251兩個exact decks與原detectors，不換data、不重訓。原VM secondary218/190與235/210對照已有Olympus251的212/191與216/210差異保留；相同seed跨版本/模式不保證noise逐位相同。先核對fresh VM原deck與transitive模型閉包、版本和分析，再由controller按實測old/new差異及exact本地case審查root-only bulk清理；本entry未宣告新replay完成或本地刪除。原PSF/fullCSV等可退役，但source/scripts/結果/失敗flags保留；derived GDS/OA/PEX另需完整生成閉包、rebuild、DRC/LVS/extract與pre/post小證據。

**證據。** [已填lineage record](reference/historical_checkpoints/r7_replay_lineage_20261108.json)分開保存original artifact與sanitized repo-copy SHA；原training/validation artifact SHA為`b4a2f1c7b3a9124551b5696c787f41bab1e9e5fc7c479a7378a43e8c3b59dd57`及`ecf4a057658e233ed626bfc2d2595aca1c8a8ae52dd32472cc4298723984f5c3`。本次replay own-code manifest為`4854d2f4352338e1b77232fcf8a48348f7a7db04cab6444bd3c6db761da8dbb4`；提交ID/實際結果/清理收據待執行後追加，不以準備成功代替再現完成。

### 後續phase2 — exact historical replay揭露模型身分不一致

準備原R7/data2026102301/noise251的strict重現時，fresh原VM與先前Olympus的完整literal/include model graph實際為**5nodes/799edges對7nodes/1094edges**；頂層模型及原`shrink_embedded_usage`對先前unsuffixed variants不同。Mandatory model-equality gate在模擬提交前擋下，沒有放寬或略過多餘節點。先前Olympus251與30pair矩陣保留為其site model下的內部比較，**不能當成原VM模型精確重現**；原VM218/190、235/210對Olympus212/191、216/210的差異也不能只歸因APS或noise seed。

**決策。** 恢復舊模型閉包屬歷史條件重現，不是新設計探索。原授權VM模型direct stream至獨立private replay root，不覆寫共享PDK、不把licensed內容放Git；exact source及兩案完整normalized closure相符才可提交。尚無新PAM4 replay或本地清理完成宣告。此異常修正原先對重現範圍的理解，保留所有舊結果與限制；後續實測結果與精確本地retirement另加收據，new design探索仍hold。

### 模型解釋/原條件恢復提交追加 — scalefactor0.9不是單邊改動

新的exact log audit顯示原VM與先前Olympus `738952`兩案的**effective scalefactor都是0.9**。上段model graph/檔案身分差異不等於先前實際scale1，也不能從名稱推成30nm→27nm或宣稱已證明電性差異來源。另一份已提供CRN kit有geoshrink/scalefactor0.9 wrapper機制，但不證明exact CLN Spectre檔案的產生/轉換作者；這條來源鏈目前仍unknown。保留觀察及source-identity缺口，不用一個新因果敘事覆寫舊結果。

原VM的4份exact模型與2個exact decks已direct stream到獨立private replay root，未覆寫共享PDK、不把licensed body放Git。v4驗證3394/df05原deck SHA/size、恰一個PDK-root prefix可逆替換與兩案原5nodes/799edges完整normalized closure後，提交原data2026102301/noise251 pair **Job740861，4CPU/15GiB**。geometry、PWL/labels、原FFE coefficients/fullscale/lag/threshold未改。兩案依序模擬、固定分析、小保留及精確新bulk清理；本段仍是提交狀態，尚無新的錯誤數、VM本地清理或更廣reproduction完成宣告。v4 source manifest`bcdcdc049a878eea12427ba5a0e115d72ddd506bcc91d46674c27184b192dfb2`；來源與完整性門檻沒有為了清理而放寬。

### R7重現實測追加 — 原模型吻合，secondary raw優勢卻未重現；本地raw HOLD

`740861`已`COMPLETED0:0`、14分58秒。原deck可逆路徑替換、兩案5nodes/799edges與原VM模型SHA/closure、固定FFEs/labels均通過，獨立重算16,256列預測一致；這是source/condition與分析完整性證據，不能等同於原電性優勢已重現。每branch每案2032個相關FFE windows，primary raw/ADC皆0，所有clipping皆0。

| Secondary errors | 原VM | 先前Olympus site-model比較 | 本次原模型v4 |
| --- | ---: | ---: | ---: |
| Baseline raw FFE | 218 | 212 | 225 |
| Candidate raw FFE | 190 | 191 | **228** |
| Baseline理想7-bit ADC+FFE | 235 | 216 | 253 |
| Candidate理想7-bit ADC+FFE | 210 | 210 | 250 |

本次candidate raw **多3errors**，原VM少28的方向未重現；理想ADC路徑少3，也小於原先少25。本次candidate raw MSE較低（0.459915<0.463752）仍多decision errors，MSE與門檻決策不能互相代替。兩邊effective scale仍0.9；沒有把count變化因果歸給scale、model、APS或noise的證據，也不能以重疊視窗宣稱robust BER。

41個retained SHA與新server精確4個bulk targets不存在已核對；本job新server移除143,706,112allocated／158,228,306logical bytes，沒有下載完整waveform/model bodies。**控制器因實際觀察不一致而HOLD原VM這兩案raw的退役**：沒有用source identity pass覆蓋科學反例，也沒有宣告old-local清理eligibility。下一個可審查步驟是原solver條件診斷的異常節點選擇，不改硬體、fit、規格或為了回到較好結果而搜尋seed。

獨立report SHA`996b41e47fd17f28f7b187e93dbb65fef6fb0012b3799b041e63e071587749b6`及[安全結果](https://github.com/<owner>/olympus-cadence-ocean-analog-notes/blob/main/expected/historical_pam4_replay_740861_20261108.json)保留全部方向。前述提交/修復段落為當時快照；以本實測追加及最後current-state判讀目前狀態。

## 2026-11-09／11-10 — 歷史PAM4在Olympus的全面重現：無雜訊exact比對與有雜訊20-seed範圍法

**方法（全部家族共用）。** 每個case使用原VM deck（SHA與原紀錄相符），唯一改動是可逆的PDK-root前綴替換；PAM4家族另核對原VM的5nodes/799edges模型閉包。Spectre 23.1 classic、`SPECTRE_DEFAULTS=-E`與原log相同，分析使用原analyzer（有archived SHA者核對SHA；部分家族紀錄沒有analyzer SHA，改用VM現行版本，列為限制）。每個case分析完立即刪除新raw，不回傳波形。比對的是measurement，不是波形。

**無雜訊exact重現（共416 cases）。**

| 家族 | cases | 結果 |
| --- | ---: | --- |
| ADC R5/R6 | 13 | 12/13 discrete一致、max rel≤1.2e-5；cdac split僅worst_transition同分tie翻轉，DNL相同 |
| R4 isolation（archived analyzers） | 7 | 重現 |
| frontend_load_r5 | 3 | 重現 |
| ctle_ac_optimization | 349 | 0 shape/discrete差異，排名順序完全相同 |
| pam4_integration | 19 | max rel 7.8e-12，phase/lag重選相同，decks byte-exact重產 |
| R7 validation noiseless | 2 | MSE rel≤1.3e-12 |
| ffe_phase noiseless | 9 | 所有symbol errors相同，18份decision-point TSV 0判決翻轉，max rel 1.85e-9 |
| R7 secondary-cap training noiseless | 3 | 重新fit的detectors max rel 9.3e-10，errors全同 |
| backend r6/r6b（7 DC＋4 noiseless） | 11 | DC max rel 7.1e-6、eligibility相同；noiseless max rel 3.1e-10；硬體選擇（r6 baseline、r6b input2_r400_bias060）相同 |

**有雜訊：範圍法（使用者2026-11-09預先指定）。** 同一noise seed在不同Spectre版本／模式下的noise realization不同，無法逐位比較。因此每案跑20個seed（含原seed），判定原VM值是否落在新結果的[min,max]內；單次比較的偽失敗率約2/21。

| 家族 | 比較數 | 原值在範圍內 |
| --- | ---: | ---: |
| R7 validation pair（24 seeds） | 6 | 6 |
| opt_final（2 designs×2 data seeds） | 16 | 15（唯一超出：baseline d20261103 raw n11，56對34–55） |
| opt_train（56 runs） | 112 | 103（預期偽失敗約10.7） |
| noise_band_300G＋noise_synthetic_20dB | 9 | 9 |

**判讀。** 「optimized遠優於baseline」在opt_final、noise_band與三輪篩選的每個seed都成立（baseline勝出0/20）。不穩健的有兩項：(1) R7 candidate優勢——原VM的cand−base為−28 raw／−25 ADC，但24 seeds的平均為+3.6／+11.3（sd約26），candidate較好只有10/24、9/24；原VM candidate raw 190在24個新值中排第1，屬於有利的noise抽樣，不是穩健改善。(2) round2選中focus59只出現7/20（focus55 13/20）；但final篩選本來就選focus55，最終設計不受影響。round1 ac180 17/20、final focus55 16/20。這段取代前一段R7 HOLD的「單次counterexample」判讀：原值統計上落在範圍內，但改善不穩健。

**進行中。** 其餘只有單一seed的noisy runs（ffe_phase 9、R7 training 3、backend noise181 2、adc_backend_pam4_r5 training/validation_noise），以及r5 validation_noiseless exact replay，已用相同方法提交為chained jobs `743474–743477`（6 CPU）；結果另行追加。

**2026-11-11 追加：剩餘單seed noisy runs完成（jobs `743474–743477`，321 runs，0 failures，analysis後raw已刪）。** 每案原seed＋301–319，判定同上（原VM值是否在20個新值的[min,max]內）。r5 validation_noiseless為exact replay：136個數值max rel 3.9e-11，0 shape/discrete差異。

| 家族 | 比較數 | 原值在範圍內 |
| --- | ---: | ---: |
| ffe_phase noise（9 phases×8 metrics，原seed 197） | 72 | 67 |
| R7 secondary-cap training noise（3 cases，原seed 223） | 12 | 12 |
| backend r6/r6b noise（原seed 181） | 8 | 8 |
| adc_backend_pam4_r5 training（原seed 157） | 4 | 4 |
| adc_backend_pam4_r5 validation_noise（原seed 173） | 8 | 8 |
| 合計 | 104 | 99（預期偽失敗約9.9） |

五個超出範圍者都只差1–2個error count且位在邊界：phase00 secondary raw three-threshold 255對256–276、phase03 secondary ADC three-threshold 299對302–312、phase06 secondary ADC/raw three-threshold 329對330–340／325對329–341、phase07 primary raw-held FFE 236對224–234。

**判讀。** (1) ffe_phase：最佳取樣相位phase04在原值與20-seed中位數一致（primary 0對0、secondary ideal7bit 55對55），相位選擇穩健。(2) R7 training：原單seed secondary ADC_FFE為baseline 31、c25_w1 26、c25_w2 26，看似candidate較好；20-seed中位數為25.5／28.5／24.5，範圍15–36／14–40／12–39大幅重疊，candidate優勢不穩健，與前段R7 validation結論一致。(3) backend noise check：原單seed secondary ideal7bit為r6 baseline 14、r6b input2_r400_bias060 23（r6b看似較差）；20-seed中位數反轉為21對13.5。硬體選擇本來依noiseless compact scores，不受影響，但任何「r6b在noise下較差」的推論不成立。(4) r5 training：primary error皆0；但所選參數隨seed變動——secondary lag原為3，新值分布0–8，fullscale原0.075、新值0.05–0.2——training選出的lag/fullscale只對該次noise realization成立。

**本地清理。** 2026-11-09依使用者政策（只保留inputs與measurement）退役VM大型輸出：PAM4/LDO模擬目錄、壓縮OP與waveform dumps、可由`.il`重建的layout產物，共12.683GB，0 errors，由使用者本人執行；private receipts保存在VM與本機outputs。

**2026-11-11 追加：最後85個尚未重現的run（job `747697`，corner修正 `747775`；199 jobs，0 failures，analysis後raw已刪）。** 無雜訊79個：comparator_r5 19、reset_r4 16、comparator_r3（diag 6、tt 5）、comparator_burst_r5 6、doubletail_r5 5、equalizer_r4／frontend_load_r4／reset_clamp_r5／native_baseline各4、native_geometry_r5／native_verification_r3各2、native_capacitor_r5與optimization_op_probe各1。有雜訊6個（acquisition_r5、isolation_r4、isolation_r5各2）各跑原seed＋301–319。每個deck的模型include閉包都與新取得的VM閉包相同（5 nodes／799 edges；兩個corner deck經LA5 corner檔為811 edges）；分析使用原analyzer，紀錄有雜湊者逐一核對。

**無雜訊結果。** 最大相對差大多≤1e-6；列出的離散差異只有原始raw／PSF的SHA（檔頭含日期與版本，換版本必然不同）。需說明的三項：(1) comparator_r5 legacy3um_control的4.2e-4出在約1.3e-12 V的`prelaunch_X_minus_Y_V`，絕對差約5.5e-16 V，屬數值噪聲。(2) comparator_r3_diag一案有14個欄位結構不同：原紀錄沒有analyzer雜湊，只能用現行版本分析，屬分析程式版本限制。(3) native_geometry short_circuit_gain的4.2e-3來自重建的分析（原speed analyzer不在專案內）取最近頻點56.23 GHz；在VM以原Spectre 18.1重跑，drain current與紀錄完全相同，改為內插到56 GHz後只差7e-5，所以差異來自分析方式，不是模擬。

**有雜訊結果（範圍法）。** 可比較的268個summary leaf中248個原值落在20-seed範圍內（92.5%，範圍法預期約9.5%落在外）。幾個exploratory transfer-fit的`fit_error_rms`原值低於全部20個新值（acquisition noise181、isolation_r5 noise101），提示Spectre 23.1的雜訊實現可能略大；只有描述性觀察，沒有因果結論。

**儲存位置。** 本專案已移至ECEN 721課程repo（ECEN 721 Project #6）；歷史重現至此全部完成，VM上PAM4專案已沒有任何模擬輸出。
