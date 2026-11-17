# SAR7：互補輸出負載與有效門檻的獨立對照

authorization_basis：使用者原話「八小時授權任何修正」，2026-11-16 15:15–23:15 Chicago。適用 SAR7／相關 PAM4 的有假設短修正；本包最多兩個順序 solver，每案 1 CPU。達到 12 碼 max≤1 LSB 且原有效性 gate 通過即收尾。C1／C2 長測、全 PVT、1.75 GS/s 正式驗證、其他專案與刪 raw 均不在範圍。

## 證據、文獻與更正

以已核對完整 SHA 的 760874 為共同基準：wrong6／12、Σ7、max2、84 bit 解析、comparator＝registered、共模下降約4mV。保留原 CDAC／參考電壓、CML 幾何與偏壓、12碼、1,080ps／60–60ps／1030ps read。

保留波形新查核排除了兩個具體猜測：#8 的 sample 誤差是 −0.191 LSB，非 +1.5；84／84 實際控制字符合舊 prefix 假設。共同 pre_s sense 門檻區間約 −0.6734…−0.5538 LSB 能解釋全部84個決策，留一轉換檢查亦符合；這是此條件下的有效門檻，不能叫七顆 comparator 各自已量測的靜態 offset。

**更正1545文字判讀，原檔保留不改**：15ps 全84個輸出差範圍是 −70.94…+39.30mV，已有明顯輸入依賴，並非全部約 −15mV。只有近門檻子集接近該值。原保存 q/qb 是緩衝後輸出，不是內部再生 x/y，故不能據此宣稱 reset 故障或核心初始不平衡。

原生 comparator 核心的鏡像 CDF／reset 映射未找到不對稱；明確存在的外部差異是正 buffered output 驅動控制 NOR，而負輸出沒有同等邏輯負載。本包測試這個第一級 fanout 差異，並另設獨立門檻補償對照。

[Um, A-SSCC 2011, DOI 10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608) 在 split-CDAC 電容殘差校正前先校 comparator offset；其低速 0.5V／11bit／10kS/s 校正與量測驗證不能直接當本平台的精度證明。[Bheemisetti, JSSC, DOI 10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) 使用實際共模下的 offset 校正與不同的 DTFB／非同步時序。兩篇支持先隔離比較／門檻機制，而非再依舊 CDAC 擬合盲改電容；沒有把本次負載假設冒稱為論文已證明的原因。

## 兩案從原760874各自獨立開始

| index | case | 唯一電氣差異 |
| --- | --- | --- |
| 0 | sar7_10_tt_matched_q_load | 每個負 buffered output 加一個原生 SAR_NOR，同樣使用第二輸入腳位與原 trial 訊號，共7個dummy邏輯負載 |
| 1（有條件） | sar7_11_tt_cml_load_trim | 回到原760874，只把 RSENSE_P 改498.5Ω、RSENSE_N改501.5Ω，不含index0的NOR |

兩案共同增加內部 x/y 的14個 save probes，用於區分再生節點與 buffered q 輸出；不改元件或 scoring。

Case0 的比較窗內 trial 為1，原／dummy NOR 的同一直接 pull-down 會把輸出拉低，q 與 qb 使用相同輸入角色。這是匹配第一級 comparator fanout 的因果探針，不是完整複製後級 INV／NAND 的所有寄生。若沒有改善，不能排除所有 Miller／歷史／負載機制。Case0 的精度效果無法由現有資料數值預測。

Case1 的兩阻值和保持1000Ω；負輸出感測腿與正腿做相反方向微調，使 sense 差動向負移動。由既有平均總電流260.6907µA估算，1.5Ω差動平衡調整約產生 −391.036µV＝−0.5005 sense-LSB，位於條件模型在 pre／trigger／2ps 及門檻區間內的穩健區域。這是固定工作條件的部分有效門檻補償，不是內在 MOS offset 的量測或實體 mismatch 修復。

`PREDICTION.json` 以實際 sample／控制狀態與每 trial 殘差重現原12個碼，並對門檻做留一檢查；case1 條件預估 Σ6／max1。這是來源一致性及假設新路徑仍保留原殘差的推估，不是獨立新電路驗證。先前正確的某些 trial 可能改變；必須量測整個12碼，不能把舊prefix直接改分數當實測。

## Olympus 準備與時間限制

沿用760874原環境。PAM4_SAR7_CDAC_FIX_PACKAGE指向上一輪原包；PAM4_SAR7_CML_RDEG_PACKAGE／RELAXED_PACKAGE／SAR7_PACKAGE及私有模型環境原樣保留。傳新ZIP／sidecar到核准位置。

```bash
export PAM4_SAR7_OFFSET_PACKAGE='/absolute/path/PAM4_SAR7_OFFSET_PILOT_20261116'
export PAM4_SAR7_OFFSET_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_offset_pilot_20261116.XXXXXX")"
export PAM4_SAR7_OFFSET_APPROVAL="$PAM4_SAR7_OFFSET_ROOT/approval.json"
cd "$PAM4_SAR7_OFFSET_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_offset_pilot.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B planning.py --check PREDICTION.json
/usr/bin/python3.11 -B sar7_offset_pilot.py approval-template \
  --root "$PAM4_SAR7_OFFSET_ROOT" --approval "$PAM4_SAR7_OFFSET_APPROVAL"
```

預估數值使用具名浮點容差，字串／整數／結構仍一致；不再以跨平台重算JSON的byte equality作預估通過條件。來源檔、凍結PLAN與核准deck的SHA仍精確核對，不可放寬完整性。

核對approval的新root、固定case清單、manifest與每案deck SHA，只將approved改true，不增加欄位。來源是本次已授權原話；不可借此送未列case。

截止為 **2026-11-16 23:15 Chicago＝2026-11-17 05:15 UTC**。stage會寫入截止前的不可變證明；截止後啟動的job另外只讀查一次Slurm實際SubmitTime，核對job ID及送件時間嚴格早於截止，並驗證原stage電路未變。stage時間本身不能證明已送件。查不到有效送件證據就拒絕run；collect-only仍可收既有結果。此檢查使用[官方scontrol的SubmitTime與時間格式欄位](https://slurm.schedmd.com/scontrol.html)，不修改排程或重送。每次sbatch前仍執行下面的實際時間檢查，23:15後不得新stage／新送job或開新輪：

```bash
SAR7_OFFSET_CUTOFF_EPOCH=$(date -u -d '2026-11-17T05:15:00Z' +%s)
test "$(date -u +%s)" -lt "$SAR7_OFFSET_CUTOFF_EPOCH"
```

必須檢查退出碼；檢查不通過就只收集既有job，不能繼續下一條sbatch。資源每案1 CPU／6GiB／Slurm10min、solver540s，預估3–6分鐘、raw約100–140MB，最多並行一案。遵守共用QOS6CPU，不占滿、不碰其他job。

## 先跑index0

```bash
/usr/bin/python3.11 -B sar7_offset_pilot.py stage --index 0 \
  --root "$PAM4_SAR7_OFFSET_ROOT" --approval "$PAM4_SAR7_OFFSET_APPROVAL" \
  --model-root "$PAM4_PDK_ROOT"
# 確認stage差異為7個dummy NOR＋共同save instrumentation，沒有其他電氣變動。
test "$(date -u +%s)" -lt "$SAR7_OFFSET_CUTOFF_EPOCH" && \
sbatch --export=ALL --output="$PAM4_SAR7_OFFSET_ROOT/case0-%j.out" \
  "$PAM4_SAR7_OFFSET_PACKAGE/sar7_offset_pilot.sbatch" 0
```

等完成後跑gate。若solver完成但收集被中斷，用同案collect-only，不能重新送solver。

```bash
/usr/bin/python3.11 -B sar7_offset_pilot.py gate --root "$PAM4_SAR7_OFFSET_ROOT"
```

Gate必須由case0原始evidence／measurements／summary SHA重新驗證：84bit全解析、12筆comparator與registered可讀且一致、末端CDAC共模變化絕對值≤10mV。

- `STOP_TARGET`：有效且max≤1，停止，不跑index1。
- `ALLOW_INDEX1`：有效、未達標，且max≤2、Σ≤7，不劣於760874；才准唯一獨立補償對照。
- `STOP_REVIEW`：其餘任何新失敗／惡化／隔離失效／未解析，停止回報，不自行救火。

## 唯一條件式補償對照

僅ALLOW_INDEX1且仍在授權時窗內才執行。程式stage與run均再核對gate，不接受手寫通過。Case1必須從原760874重建，不帶dummy NOR。

```bash
/usr/bin/python3.11 -B sar7_offset_pilot.py stage --index 1 \
  --root "$PAM4_SAR7_OFFSET_ROOT" --approval "$PAM4_SAR7_OFFSET_APPROVAL" \
  --model-root "$PAM4_PDK_ROOT"
# 電氣差異只允許兩個感測負載阻值；另有共同內部save。
test "$(date -u +%s)" -lt "$SAR7_OFFSET_CUTOFF_EPOCH" && \
sbatch --export=ALL --output="$PAM4_SAR7_OFFSET_ROOT/case1-%j.out" \
  "$PAM4_SAR7_OFFSET_PACKAGE/sar7_offset_pilot.sbatch" 1
```

## 判別結果與保存

回本機outbox報實際job、逐碼wrong／Σ／max、84bit解析、registered一致性、原正確碼是否退化、sample／CM／resolve、sense slope／intercept與有效門檻，以及#8 b2的內部x/y與buffered q分開的觀察、完整summary／measurements／tran SHA。原q不是內部latch的更正也須沿用。

Case0若門檻與錯碼一起改善，支持第一級外部負載參與；未改善只能限制此具體探針。Case1若sense intercept如預期移負、held-domain判決門檻移近零且max≤1，支持固定條件的有效補償可行，不證明靜態／動態來源已分離。若改變不足或新路徑失敗，照實回報，不改CDAC或bias追數字。

本包兩案後一律先回Codex；八小時授權容許依證據另設合理短輪，但此包不得新增第三case。達標即停止小差異調整，不宣稱全碼完全正確、1.75GS/s或完整ADC／PVT／版圖驗證。

完整trial／內部節點資料放核准OneDrive／Olympus；repo只存聚合摘要、無deck程式與handoff。新舊raw全保留。通道仍是本機worker，Codex不git、不用codex queue，archived steering command停用、transcript monitor唯讀。
