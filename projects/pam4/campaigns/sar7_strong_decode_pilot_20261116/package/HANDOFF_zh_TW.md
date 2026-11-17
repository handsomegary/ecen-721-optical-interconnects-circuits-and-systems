# SAR7 原生解碼堆疊補強單案

只執行 `sar7_15_tt_175gs_strong_decode`，從已完成 761433 的原生 R2 包重建。使用者 16:58 要求繼續完成 Project #6、先驗 SAR7 1.75 GS/s；八小時委派截止仍為 **2026-11-16 23:15 Chicago＝2026-11-17 05:15 UTC**。本包不發動 C1/C2、全 PVT、112 GS/s 整合或其他專案。

## 測試假設與唯一電路差異

761433 的實體 reference gate 帶載交越為 6–17 ps，b4–b1 在比較前仍未建立；b0 在 trial 550 ps 解除後還需要約 8–10 ps 才建立輸出。若把各 bit 的 read-plateau 建立與已量到的有限解析時間作保守串列估算，只搬時槽沒有足夠餘裕；此估算忽略 DAC 建立與再生重疊，不是 1.75 GS/s 物理不可能的證明。這一案用原生 CDF 單位並聯補償解碼堆疊，不假定一定加速到達標。

- OAI21 的三顆 N 與兩顆串聯 P 各用兩份完整原 CDF；單顆 enable P 保持一份。
- NOR3 的三顆串聯 P 各用三份完整原 CDF，N 保持一份。
- 只將 decoder 專用的互補 inverter 改成兩份並聯。正、負 q 的原生解碼與匹配負載保持鏡像。
- **所有 reference TG、全域 SAR_TG/SAR_INV、XBitb/XBit、比較器、CML、CDAC、參考電壓、輸入與取樣控制均保留。** 不使用新模型或只改 W 卻沿用錯誤寄生的元件卡。

OAI/NOR 輸入電容會增加，可能拖慢 comparator 或改變動態門檻；並聯元件也增加電容與能耗。必須量測 gate、held 及 x/y/q，不能把邏輯真值表或副本倍數當作建立時間保證。

[Bheemisetti et al., IEEE JSSC, DOI 10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) 用 CDAC 底板後的 ready 訊號安排下一次比較，機制上提醒要量實際類比建立；目前固定時序、28-nm StrongARM 與其 3-nm DTFB/非同步實作不同。[Ramkaj et al., IEEE JSSC, DOI 10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823) 的 USPC 與關鍵路徑優化也相關，但不能當作本案速度驗證。紙本／圖像未在本次重新讀取，沿用已記錄的原文對照；不新增未核實圖號或曲線主張。

## 固定時序與判讀

| bit | launch | compare | read | trial release |
| --- | ---: | ---: | ---: | ---: |
| 6 | 78 | 120 | 159 | 161 |
| 5 | 162 | 207 | 251 | 253 |
| 4 | 254 | 279 | 319 | 321 |
| 3 | 322 | 341 | 381 | 383 |
| 2 | 384 | 399 | 437 | 439 |
| 1 | 440 | 448 | 489 | 491 |
| 0 | 492 | 498 | 552 | 554 |

單位 ps，週期仍為 571.428571 ps（1.75 GS/s），同樣 12 個碼。b0 保留 54 ps 比較窗。所有 comparator clock 改在 568 ps 下降，conv 仍 558 ps、reset 566 ps、track 569 ps。**正式 registered read 固定 565 ps**，距 b0 release 11 ps；另報預先指定的 563、554、557 ps，不能事後挑點。原 stop/strobe 保持，最後一筆也包含 565 ps。

565 ps 在 conv 關閉後、reset/track 開始前；程式核對 reset/track 低且所有 comparator clock 高，才承認輸出窗有效。post-conv 的 CM 必須與最後 comparator trigger/read 的 CM 分開標示，不能把輸出讀點當作比較期間 CM。q 是 buffered 輸出，x/y 才是內部再生節點，兩者分開報。

主 screen 條件保持：84 bit 全解析、12 個 comparator/registered 可讀且一致、max≤1 LSB、錯碼≤6/12、565 ps 的 |末端 CM 變化|≤10 mV，加上輸出窗有效。**同一 CM 限制也必須在最後比較 read（552 ps、conv 尚高）通過**，以 `active_last_read_cm_pass` 明示，避免 post-conv 恢復掩蓋工作期間異常；498 ps trigger 瞬間只報數值、不另設 gate。另報原數位 strict zero-error `logic_smoke_pass`，不把類比 gate 改寫成數位錯碼。無論結果如何只跑此一案，回報後由 Codex 決策；不自行加強驅動、改 TG 或掃時序。

## Olympus 核對與執行

沿用 761433 原環境。`PAM4_SAR7_NATIVE_DECODE_PACKAGE` 必須指向 **R2**，manifest SHA `12e5745c9a28f26a5a1bbb8cc11030e1f41da59176d7fdca9b1b187c9763ae24`；其 fast/offset/CDAC/RDEG/relaxed/SAR7 與原私有模型依賴全部保留。新 portable deck SHA 為 `31d7e4e66c8f33a6432d640050285736454e63fa8cc171b04f13b39875180da8`。

```bash
export PAM4_SAR7_STRONG_DECODE_PACKAGE='/absolute/path/PAM4_SAR7_STRONG_DECODE_PILOT_20261116'
export PAM4_SAR7_STRONG_DECODE_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_strong_decode_pilot_20261116.XXXXXX")"
export PAM4_SAR7_STRONG_DECODE_APPROVAL="$PAM4_SAR7_STRONG_DECODE_ROOT/approval.json"
cd "$PAM4_SAR7_STRONG_DECODE_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_strong_decode.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_strong_decode.py approval-template \
  --root "$PAM4_SAR7_STRONG_DECODE_ROOT" --approval "$PAM4_SAR7_STRONG_DECODE_APPROVAL"
```

核對唯一 case、root、manifest/deck SHA 後，依現有使用者授權只改 `approved=true`。新 stage 與送件均須在截止前。stage 對原 R2 deck 的差異應為 16 行原 decoder 定義換成 33 行新定義、56 個 decoder instance 型別替換、13 條 pulse 時序變動；沒有 save、TG、register、analog 或其他控制變動。b6 trial 的時間本來相同，所以 14 個時序欄位中只有 13 條文字改變。

```bash
/usr/bin/python3.11 -B sar7_strong_decode.py stage \
  --root "$PAM4_SAR7_STRONG_DECODE_ROOT" --approval "$PAM4_SAR7_STRONG_DECODE_APPROVAL" \
  --model-root "$PAM4_PDK_ROOT"
SAR7_STRONG_CUTOFF=$(date -u -d '2026-11-17T05:15:00Z' +%s)
test "$(date -u +%s)" -lt "$SAR7_STRONG_CUTOFF" && \
sbatch --parsable --export=ALL --output="$PAM4_SAR7_STRONG_DECODE_ROOT/slurm-%j.out" \
  "$PAM4_SAR7_STRONG_DECODE_PACKAGE/sar7_strong_decode.sbatch"
```

取得成功的 sbatch job ID 才算已送件；截止後不新 stage、不新送件。截止前已提交但排隊較久的 job 可完成：run 只接受 byte-exact 的既有 stage，截止後另以一次唯讀 scontrol 查本 job 的 SubmitTime，必須嚴格早於截止；驗證失敗就停止。沒有輪詢或自動送件。collector 可於截止後完成；solver 已完成而收集失敗時，用同 root 的 `collect-only`，不重送 solver。

資源：一案、1 CPU／6 GiB、Slurm 12 分鐘、solver 上限 540 秒，預估 3–7 分鐘；全部 raw 保留。ZIP/deck 留核准 OneDrive/Olympus，PDK/模型/PSF 不進 repo。Claude 單獨操作 repo。

## 回報

回本機 outbox 報 job ID、solver/raw 大小、正式 565 與三個診斷讀點的分數、逐碼 cmp/reg、84 bit 解析、取樣誤差、active comparison 與 post-conv CM、讀出窗電位證據及完整 summary/measurements/tran SHA。報每 bit gate 50% 交越、held 保持於 read±1 LSB 的時間、overlap proxy 與參考電流限制。

84 trial 均輸出 precompare、compare＋15 ps、compare＋30 ps、read 的 held/sense/底板/q/x/y 快照，另有 launch 前及 release 後 1 ps；15/30 ps 都位於已凍結的比較窗內。sensep/sensen 原本已保存，不改 deck 或 save。用來判斷加強後是否仍有控制延遲、未建立就決策或再生期符號偏移。這些是既有 PSF 觀察，不能單憑稀疏快照排除更快的擾動。
