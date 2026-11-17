# SAR7 強解碼器 q 隔離單案

只執行 `sar7_16_tt_175gs_qbuffer`，從已完成 job 761524 的 **原 strong 包**重建，不回到舊 native、也不疊加其他參數。使用者要求繼續 Project #6 的 SAR7 1.75 GS/s 驗證；本輪截止仍為 **2026-11-16 23:15 Chicago＝2026-11-17 05:15 UTC**。最多此一個新 solver，回報後由 Codex 決策。

## 證據與假設

761524 的 reference gate/held 建立已改善，內部 x/y 在 read 時已再生，但原 buffered q 有 26/84 未達原 rail 門檻。此案減輕 q 對新強解碼器的直接負載，同時保留已得到的解碼驅動能力。

每個 q 正、負側各加兩級，第一級用既有 `SAR_INV`（1×），第二級用既有 `SAR_NDINV2`（2×）。總共 14 組非反相緩衝器、28 個新 instance；不新增或修改任何 subckt/MOS 卡。只把 28 個 XNDO/XNDZ 的 q 輸入改接非反相 decode 節點。原 raw q 仍接原 register、matched NOR 與原輸出電容，正負支路保持鏡像。

原強解碼器、TG、CDAC、CML、參考、全部 pulse、取樣、輸入碼、565/563/554/557 ps 讀點與 screen/CM 門檻均不改。只增加 28 個 mid/decode save。

原強解碼器每側 q 輸入為 3N＋5P 單位，第一級 inverter 為 1N＋1P。依原 CDF 寬度、同 L/nf 的一階代理，這部分負載寬度約降 4.35 倍；連同保留的原 NOR 後約降 2.68 倍。**這不是總電容量或延遲的實測比例**，原輸出電容、寄生及動態 Miller 仍在。兩級 buffer 也新增傳播延遲，可能把問題轉回 reference/held；不保證會通過。

[Ramkaj et al., JSSC, DOI 10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823) Section III-D 強調減小 comparator loading 與記憶／CDAC 關鍵路徑；其 pass-device/inverter/TG 實作及隱藏邏輯延遲不同於本案增加兩級 buffer。[Bheemisetti et al., JSSC, DOI 10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) 的底板 ready 機制同樣提醒須量實際建立。本案只借用負載／時間權衡，不宣稱複製論文拓樸或速度。

## 固定時序與判定

沿用 strong 包：wait `[42,45,25,19,15,8,6]` ps，compare window `[39,44,40,40,38,41,54]` ps，起點 78 ps、相鄰 read 到下個 launch 3 ps。b0 compare/read/release 為 498/552/554 ps。週期 571.428571 ps，comparator clocks 在 568 ps 下降，conv 558、reset 566、track 569，正式 registered read **565 ps**。565 ps 距 reset 起始僅 0.5 ps，須沿用實際 reset/track/clock 輸出窗查核。

原比較器計分仍用 raw q，**不以 decode 已到 rail 取代 raw q 未解析**。主 screen 仍需 raw q 84 bit 全解析、12 個 cmp/reg 可讀且一致、max≤1 LSB、錯碼≤6、active 最後比較 read 552 ps 與 post-conv 565 ps 的 |ΔCM| 都≤10 mV，且輸出窗有效。strict `logic_smoke_pass` 保持原數位零錯定義。

## Olympus

原 strong 包 manifest 必須為 `43b93d73f5f5e08fc350a6b9a12ae6c54ec3c5eac280190be93a38b3fe4b8bd8`，portable 為 `31d7e4e66c8f33a6432d640050285736454e63fa8cc171b04f13b39875180da8`。沿用原 strong/native R2/fast/offset 等完整依賴及私有模型環境。新 portable SHA 為 `509bbedfdc2be956eafade7021b968eeb60d29f0fcb654d2c0037a22b5da813a`。

```bash
export PAM4_SAR7_QBUFFER_PACKAGE='/absolute/path/PAM4_SAR7_QBUFFER_PILOT_20261116'
export PAM4_SAR7_QBUFFER_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_qbuffer_pilot_20261116.XXXXXX")"
export PAM4_SAR7_QBUFFER_APPROVAL="$PAM4_SAR7_QBUFFER_ROOT/approval.json"
cd "$PAM4_SAR7_QBUFFER_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_qbuffer.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_qbuffer.py approval-template \
  --root "$PAM4_SAR7_QBUFFER_ROOT" --approval "$PAM4_SAR7_QBUFFER_APPROVAL"
```

核對唯一 case、root、manifest/deck SHA，依使用者授權只改 `approved=true`。stage 與 761524 比對應為 **刪 29／加 57 行**：28 個 q port 替換、28 個新 buffer instance、1 個 save 擴充；subckt/MOS、其他 instance、全部 sources/時序均一致。

```bash
/usr/bin/python3.11 -B sar7_qbuffer.py stage \
  --root "$PAM4_SAR7_QBUFFER_ROOT" --approval "$PAM4_SAR7_QBUFFER_APPROVAL" \
  --model-root "$PAM4_PDK_ROOT"
SAR7_QBUF_CUTOFF=$(date -u -d '2026-11-17T05:15:00Z' +%s)
test "$(date -u +%s)" -lt "$SAR7_QBUF_CUTOFF" && \
sbatch --parsable --export=ALL --output="$PAM4_SAR7_QBUFFER_ROOT/slurm-%j.out" \
  "$PAM4_SAR7_QBUFFER_PACKAGE/sar7_qbuffer.sbatch"
```

必須拿到成功的 sbatch job ID 才算提交；截止後不新 stage/送件。截止前已送、延後排到的 job，run 只接受 byte-exact 既有 stage，並於截止後沿用一次唯讀 Slurm SubmitTime 查核；不能確認就停止，不輪詢重試。已完成 solver 只用同 root `collect-only` 恢復收集，不重送。

資源 1 CPU／6 GiB／Slurm 12 分鐘／solver 540 秒，預估 3–7 分鐘；只此一案。全部新舊 raw 保留，ZIP/deck 留核准 OneDrive/Olympus，PDK/模型/PSF 不進 repo，Claude 單獨操作 repo。

## 回報與可否證結果

沿用 strong 的 84 trial held/sense/底板/q/x/y 快照及時序、四個讀點、active/post-conv CM、取樣誤差、reference 電流與 overlap proxy。另報每 bit 的 raw/mid/decode 在 compare＋15、＋30 ps、read、release、next launch 的電位、原 rail 分類、非反相一致性、50% 交越及 read 前持續到 rail 的時間。最後一筆 b0 的下一周期 launch 超出原 stop，明示 unavailable，不能外插或延長本案。

- raw q 提早到 rail，decode 亦及時且 held/碼差改善，支持原 q 負載參與限制。
- raw q 恢復但 decode/reference 延後、held 仍不穩，表示兩級延遲抵銷了負載改善。
- raw q 仍慢，則這個特定負載解釋不完整；不得只換計分點宣稱通過。

回 outbox 報 job、wrong/Σ/max、raw q 未解析、raw/decode 到達時間、reg 一致性、CM/取樣、summary/measurements/tran 完整 SHA 與仍不確定的原因。不自行送第二案或改時序/TG。
