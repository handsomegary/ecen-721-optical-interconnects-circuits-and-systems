Stage: 新8小時委派首案：SAR7 1.75GS/s reference path協同比例2×
ZIP: ECEN721_PAM4_SAR7_REFPATH2_PILOT_20261116.zip（OneDrive ECEN720/outputs）
SHA256: d9b981c774c3f86c26713c5dd9dc5147229b270cdfeb0b031a6501ab8e34138d
Guide: OneDrive ECEN720/outputs/PAM4_SAR7_REFPATH2_PILOT_20261116/HANDOFF_zh_TW.md
Recommended: 只送sar7_17_tt_175gs_refpath2；固定原時序，核對完整reference路徑2×之精確差異與新13:37UTC授權後跑單案
Resources: 本包最多1個新solver、1CPU／6GiB／Slurm12min／solver540s，估4–8min與120–180MB raw；本輪SAR7總同時CPU≤2，優先單案1CPU；C2保留3槽、account總QOS6CPU
Commit allowed: handoff + results
Needs user decision: no

## 新授權，取代上一輪停止狀態

已讀2337原訊息：使用者回覆「**Yes, 8 hours**」，確認與既有C2平行續作SAR7單通道1.75GS/s。原檔SHA `26523d076e396f82acc8844f3441c3517ebba4f05e2073e1629436586287da58`。這次是新的明確委派，2026-11-16 23:37至2026-11-17 07:37 Chicago，亦即 **2026-11-17 05:37至13:37 UTC**；不是延用已結束的05:15UTC時窗，不重問同一授權。舊closeout及原包保持完整；新授權紀錄是authorization_20261116_2337_8h.json。

時窗內可依證據做多輪短案，但每個固定包的case清單、gate、SHA與資源上限仍有效；本包只有一案。依本則授權按原執行流程只將template的approved改true，不往嚴格approval schema加臨時欄位。新授權透過AUTHORIZATION.json、PLAN、manifest與metadata綁定。達成84解析、12碼cmp/reg可讀一致、max≤1即停止修補；原wrong≤6、active552/post565 |ΔCM|≤10mV與565有效讀窗仍保留，strict零錯logic_smoke另列。

截止後不新stage/提交，新案必須在13:37UTC之前拿到sbatch接受ID；已於期限內提交的同一job可完成，collect-only可收尾。新程式必須使用自己綁定的新期限及SubmitTime驗證，不得呼叫舊fast.offset或parent的05:15截止helper。所有舊包只作renderer／證據依賴，不改檔、不改舊期限。

不含刪raw、修改／取消／重送C2、擴充C1/C2或其他長測、全PVT、112GS/s整合及其他專案。即使本案通過，112GS/s整合仍要使用者另外授權。

## 量測依據與唯一物理假設

761591保留波形證據顯示，兩個多LSB問題位元的前一接受reference已在compare前約16–20ps到rail；當前trial的gate交越後，底板中點仍落後約8–13ps，held／sense在compare後才過零。761549的rawq負載改善至82/84解析，但registered仍7錯、Σ10/max3，兩問題碼的原read仍缺失。這支持測reference路徑的動態建立，不能只靠後段負sense歸為intrinsic comparator offset。

新的單一協同尺度為2：

- 只把28個XRef及28個對稱dummy負載改用完整CDF複本的reference TG2；sampling/reset等全域SAR_TG不變。
- Strong OAI/NOR內全部元件複本數同比2×，decoder互補inverter2→4，qbuffer第二級2→4；原q第一級1與q→register／matchedNOR的直接負載幾何不變。
- 正負與real/dummy保持對稱；全域SAR_INV、register、CML、CDAC、參考、取樣、刺激、save及全部時序不變。固定原wait/eval、565正式讀點與563/554/557診斷，不同時搬時槽。

理由是一階上讓reference TG通道電阻降低，同時讓其前級drive/load比例在launch及接受O/Z兩種方向盡量維持。不能只強化N而放大P負載：正確對照conv8b4→b3的接受Z rail餘裕原僅7.43ps。TG diffusion／feedthrough也增加，q第一級現在驅動較大的第二級，mid／接受reference延遲可能增加；因此**不能把2×尺寸當作2×速度，也不保證直接修好conv8b2原+15.2ps的sense遲到**。

## 文獻對照與可否證結果

[Ramkaj等，JSSC DOI10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823) SectionIII-B把switch R及寄生R/C列入CDAC settling，III-D強調低comparator負載與短接受路徑。其28nm／1V／1.25GS/s triple-tail、USPC與rail references不同於本案窄reference／StrongARM+CML；本案不是複製其拓樸或已完成其晶片DNL/INL／頻譜驗證。[Bheemisetti，JSSC DOI10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) 的3nm DTFB和底板ready非同步控制則提醒要量底板／sense時序；其0.65V core、320mVppd與本案0.9V／100mVppd／固定時槽不同。Um的offset-first與split-CDAC隔離法仍保留作替代診斷，動態未釐清前不再次擬合權重：[DOI10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608)。

主要鑑別：gate edges若大致保持而bottom／held／sense提早，支持reference-switch路徑有貢獻；若gate或接受reference反而侵入下一compare，表示負載補償失敗。還須看qmid/qdecode增加的延遲、接受O/Z margin（特別conv8b4Z對照）、CM、取樣與實際逐碼，不只看gate50%或某個過零。Gate／底板中點是proxy，不能替代LSB精度settling；x/y半電源不是最初決策時點，offset／kickback仍可能共存。

## 執行與回報

Manifest SHA `a2d8b1d170c1619cf6dec21a6b2ead158ca32861ad236e7b0e5b94df5dfb31c0`。沿用761549既有完整依賴與模型環境，新run root／新approval，不改原root。先核對ZIP/manifest/verify/unittest與stage對父案的精確差異，再送唯一case。遇到已有jobID或submission意圖，先查原提交，禁止換root盲目重送。solver已完成而收集失敗只collect-only，所有raw保留。

提交前唯讀核對account占用；C2固定761525三路，其他既有工作不改動，SAR7同時最多2CPU。本包只用1CPU，通常合計3+1+1=5，保留餘量；若無餘額，讓Slurm排隊，不提高優先權、不取消或延遲C2、不操作其他專案。

回本機outbox先報接受的jobID／SubmitTime與新root；完成後回84trial、12碼、原全部讀點、參考gate／bottom／held／sense／x-y／q/mid/decode、當前及前一接受reference相對下一compare的時序、CM/取樣/峰值電流、summary/measurements/tran完整SHA與資源。Dense電壓只留批准OneDrive/Olympus，repo只compact去識別摘要及合規無deck程式。完成這一案就回Codex，不自行開下一倍率或搬clock。

C2仍按原授權95案、0-94%3、凍結計分執行；2144頂層inbox及waiting_runs/jobs=['761525']不變，不能因SAR7新委派而重新提交。新短案以自己的task及純數字jobID追蹤，優先回報，不與C2合併成53小時等待。若達新SAR7gate，回報後停下，後續整合另候授權。
