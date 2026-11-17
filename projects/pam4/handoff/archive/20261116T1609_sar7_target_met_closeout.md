Stage: SAR7 12碼max≤1 LSB目標達成：停止新修正並收尾
ZIP: this message
SHA256: n/a
Guide: this message；回覆20261116T1606_sar7_offset_load_pilot_result.md
Recommended: STOP_TARGET已核實；index1保持未stage／未送，不開新修正輪、不追加collector或solver；只保存既有結果與raw，不需獨立ack回覆
Resources: 零新job；已送出的工作可收完並保留；八小時時窗雖未到期，但已達既定停止目標
Commit allowed: handoff only
Needs user decision: no
authorization_basis: 使用者原話「八小時授權任何修正」，2026-11-16 15:15–23:15 Chicago，至max|Δcode|≤1 LSB或無合理方向即停止；現目標已達

## Codex核實與決定

已讀1606回報，並獨立重算本機聚合摘要中12個碼：job761279／sar7_10_tt_matched_q_load，wrong6／12、Σ6、max1，正負各3筆。84bit全解析、12筆comparator／registered可讀一致、CDAC CM約−4.04／−3.97mV，符合預先定義的STOP_TARGET。index1未執行正確；不要為了用滿八小時而繼續調參。

本機sar7_offset_pilot_index0_aggregate.json SHA256為be5bb6a8f6ed5e5b367eab3d64ac77d081e5209212f87c01e40391fdcabf4c5f；嵌入gate及來源summary／tran receipt與回報吻合。這是聚合副本核對，不冒稱已在本機重算遠端原PSF。完整summary原SHA仍84b051d79c71979637416674aeb17b851104b199e544d9035870f8116f761a0a。

## 保留限制與解讀

達成的是這12個固定碼中心、TT慢速約0.926GS/s的max≤1目標；仍有6碼±1，#6原本65正確現在65→64為新增−1，必須保留。沒有全碼零錯，不是完整ADC、DNL／INL、PVT、1.75GS/s或版圖驗證通過。

logic_smoke_pass=false不是無關legacy旗標：原sar7_score.measure定義為unresolved==wrong==0。此案wrong=6，所以false正確；不改旗標、門檻、原score或原結果。STOP_TARGET和strict zero-error smoke是不同判據。

在CDAC／Vref／CML／輸入／clock不變下，補互補第一級NOR負載後有效sense門檻移至包含零，支持該具體外部fanout參與原門檻偏移。不能據此斷言所有誤差已被因果分離；內部x/y與buffered q仍分開解讀。index1的負載微調只是未執行的預備對照，不把條件預估列為實測。

既有文獻對照保留：[Um DOI10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608)、[Bheemisetti DOI10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115)。本次是修正並驗證本平台特定負載機制，沒有宣稱移植論文全部性能。

## 保存與終止新工作

新舊raw、已執行case、未執行index1方案、所有訊息及完整SHA均保留。完整trial／內部節點資料留核准OneDrive／Olympus，repo只保留去識別聚合摘要、無deck程式與handoff，由Claude操作。C1／C2長測、全PVT、正式1.75GS/s、刪raw及其他專案均未啟動或授權。

八小時權限的來源與23:15截止記錄仍保留，但本目標已完成，不因時窗尚餘就新開工作。後續若收到這則不需再來一則ack，只作本機/允許的handoff存檔即可。archived steering command停用、無codex queue，transcript monitor唯讀。
