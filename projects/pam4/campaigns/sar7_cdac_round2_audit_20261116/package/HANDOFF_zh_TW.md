# SAR7 CDAC 第二輪：先查既有 760874 證據

依 20261116T1514_user_authorizes_sar7_cdac_round2.md 記載的新授權「授權再修一輪 SAR7 到 max ≤ 1」接續。本輪最多兩個新 solver、循序執行；本步僅讀既有資料，**新 solver 額度使用 0／2**。不含 C1／C2、全 PVT、1.75 GS/s 正式驗證、其他專案或刪除 raw。

上一輪較佳案 760874 的錯碼為 6／12、Σ7、max2；只有 conversion #8 的 42→44 超過 1 LSB。舊 planner 用推估的 sample 與最終碼前綴，實測比預估差。這次先取得實際 sample、比較前 CDAC 控制字及比較窗內的 hold／sense，不能直接沿用同一模型外推。

## IEEE 主文對照與判別問題

[Um et al., A-SSCC 2011, DOI 10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608) 的 Fig. 1–3／Eq. 1–10 使用差動 split-CDAC 的另一支路量測已隔離的電容切換殘差；DAC 校正前先校比較器 offset。其 130-nm、0.5-V、11-bit、10-kS/s 原型用量測 DNL／INL 與 FFT 驗證，不是本機高速度驗收條件。本文支持 bridge／LSB-bank 寄生可能改變有效權重，不能據此排除比較器誤差。

[Bheemisetti et al., JSSC, DOI 10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) 的 Fig. 3–9 使用 split-CDAC、bottom-plate 完成訊號觸發的非同步控制、DTFB 比較器與共模補償／offset 校正。原型是 3 nm、1.75 GS/s、320 mVppd、0.65-V core；以 offset 校正後的百萬點 histogram 與動態 FFT 驗證。我們的 28-nm StrongARM＋CML、0.9 V、100 mVppd、固定 60／60 ps 和 12 個 DC 中心碼，是不同條件。共同的七比較器數量不足以移植速度或誤差結論。

已讀兩篇原文文字與相關圖說；網路 PDF 影像存取失敗，沒有從未見的曲線／晶體管圖讀取數值。

**本資料的機制與可區分結果（Codex 推論）**：42＝`0101|010`，44＝`0101|100`，高四位一致而首個分歧在低位 b2，因此 bridge／LSB-bank 是合理候選。也可能是取樣偏移或比較時的動態／offset；max sample error 已約 1.64 LSB，不能忽略。

- 把實際 sample 納入後，若已穩定的 CDAC 狀態／步階仍有一致的低位權重誤差，支持 CDAC／bridge 原因。
- 若步階正常，但 #8 的實際 sample 已向正方向偏約 1.5 LSB，支持 acquisition 誤差。
- 若 trigger 周圍 hold／sense 支持 0，但 b2 最後接受 1，須檢查有效 offset、regeneration 時間與動態擾動；晚期 read 電壓不能反推最初決策電壓。
- 若 hold 已穩定而 sense 還在變化，支持感測支路動態；若 clock 邊緣出現跳動，支持 kickback／時序相關原因。

這些是既有波形的判別條件，不是新電路、timing sweep 或額外 solver。

## 核對來源與執行

保留 760874 原 root、原套件及既有環境。PAM4_SAR7_CDAC_FIX_PACKAGE 指向上一輪原包；PAM4_SAR7_AUDIT_PACKAGE 指向原 CDAC_AUDIT 包。後者仍需沿用原 audit wrapper 的 PAM4_SAR7_ISOLATE_PACKAGE 等依賴，避免重新找另一版套件。PAM4_SAR7_CML_RDEG_PACKAGE、RELAXED_PACKAGE、SAR7_PACKAGE 與既有私有模型環境沿用，不需要任何新模型。

```bash
export PAM4_SAR7_ROUND2_AUDIT_PACKAGE='/absolute/path/PAM4_SAR7_CDAC_ROUND2_AUDIT_20261116'
export PAM4_SAR7_ROUND2_AUDIT_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_cdac_round2_audit_20261116.XXXXXX")"
cd "$PAM4_SAR7_ROUND2_AUDIT_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_cdac_round2_audit.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_cdac_round2_audit.py audit \
  --source-root "$HOME/ecen720_28nm/runs/pam4_sar7_cdac_fix_20261116.zN5rXs" \
  --output-root "$PAM4_SAR7_ROUND2_AUDIT_ROOT" --copy-source-json
```

最多一個 Python collector，1 CPU／6 GiB／10 分鐘；若 Olympus 政策需 Slurm，可包成同樣資源的 collector job。不得啟動任何 solver、stage、run 或修改 approval。原始 measurements／summary 必須已存在且 hash 符合，不能重新 collect 或改寫原證據。這步不新增 raw，所有原 raw 保留。

程式綁定原 parent build／PLAN／manifest 與 case，核對完成狀態、job 760874、原 summary／measurements／tran／portable SHA 及 inventory。只 parse 原 PSF 一次，結束後再次核對原證據、inventory 與 JSON 未變。輸出到分離的新 root，不寫來源目錄。

## 輸出與後續界線

新 JSON 應包含實際 main／low／source sample、84 個 trial 的實際 pre_s 控制對電位與分類、hold／sense／共模、原 decision，以及 compare 後 0／0.25／0.5／1／2／5／15／30／50／60 ps 的有限內插觀察。這些時間只取自原 read window，不改 clock 或原 scoring。原儲存間距是 0.25 ps，仍可能漏掉更快擾動；未看見跳動不能當作排除 kickback 的證明。原計分所記整個 trial 的最大 excursion 也保留，但它不提供擾動的確切時刻。用實際控制字與實際 sampled hold 重估描述性權重／span，不能用最終碼推估控制狀態。

請將完整新分析 JSON 與 byte-exact 原 summary／measurements 複本傳回核准 OneDrive `ECEN 720/outputs/PAM4_SAR7_CDAC_ROUND2_EVIDENCE_20261116/`，保留原本完整 SHA。完整 trial／時間觀察資料留 OneDrive／Olympus；repo 可存不含 deck 的程式、聚合指標與 handoff，不存原 PSF、模型或完整波形資料。

本機 outbox 報：新分析檔／兩個複本完整 SHA、#8 sample error、b2 trigger 周圍 hold／sense 與原決策、實際控制狀態是否符合舊 prefix 假設、描述性 fit／留一誤差、哪些判別仍不確定。不要把「所有 bit 已解析」或 sense／hold 同號當作零 comparator offset 的證明。

此步完成後先回報，由 Codex 根據這些資料決定本輪固定 pilot；不要自行改 CDAC／bias／時序、選 trim 值或先送任何 case。兩個 solver 額度仍保留，後續不論達標與否最多使用兩案並收尾，不自動開第三輪。

通道維持本機 worker／inbox／outbox；不使用 codex queue，不啟用 archived steering command，transcript monitor 僅唯讀。Claude 單獨操作 repo，ZIP、deck、PDK／模型與 raw 留核准位置。
