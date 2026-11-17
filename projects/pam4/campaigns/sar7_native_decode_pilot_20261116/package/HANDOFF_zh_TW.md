# SAR7 1.75 GS/s 實體參考解碼及重配時槽

本包只送 `sar7_14_tt_175gs_native_decode`。以原實體快案 761321 的 portable deck `903d79a5…` 重建。同程式的 761426 理想 gate 對照把最大 registered 誤差從 32 降至 1 LSB，但 b0 有 2 次未解析。理想 gate 下 b6 最慢仍需 37.0 ps，b5 最慢 40.6 ps；原控制在卸載對照中 50% 交越最晚約 18.6 ps，這個數字不能當實際帶載延遲。候選用實體 OAI21 直接生成 `cbO=¬(conv∧(trial∨qplus))`、實體 NOR3 直接生成 `cZ=¬(convb∨trial∨qplus)`，各接原生反相器生成互補控制。原 `XBitb`/`XBit` 保留，原 CDAC、參考、TG、比較器及取樣保持一致。新增 q− 的對稱 decoder 與接固定 RCM 的空載匹配 TG，讓幾何輸入與輸出 gate fanout 對稱；不把其動態 Miller 耦合視為跟切換 CDAC 完全相同。每個晶體管使用原 CDF 單位，不另加平行驅動。

| bit | launch | compare | read | trial release |
| --- | ---: | ---: | ---: | ---: |
| b6 | 78 | 120 | 159 | 161 |
| b5 | 162 | 202 | 244 | 246 |
| b4 | 247 | 271 | 309 | 311 |
| b3 | 312 | 329 | 368 | 370 |
| b2 | 371 | 384 | 426 | 428 |
| b1 | 429 | 439 | 483 | 485 |
| b0 | 486 | 494 | 548 | 550 |

單位 ps，週期 571.428571 ps。b5 的 40 ps 已接近理想 gate 對照的 40.6 ps 最差值，實體驅動的額外延遲仍有風險。b0 留 54 ps 比較窗。沿用 554 ps 原 readout，另在 conv 開始下降前的 557 ps 取一次，預先以 557 為主 gate；兩個結果都報。候選是單一短模擬，有 (1.75~\mathrm{GS/s}\) 的外加固定時序；不等同量測型非同步 ADC。Bheemisetti 的每位時序直接參考 CDAC 底板切換；Ramkaj 在開關選擇上明確安排先斷 VCM 再接 VREF。此案量底板、決策和參考短時間重疊來驗證兩個機制；純靜態真值表無法保證沒有類比短路瞬態。[Bheemisetti，IEEE JSSC](https://doi.org/10.1109/JSSC.2024.3449115) · [Ramkaj，IEEE JSSC](https://doi.org/10.1109/JSSC.2018.2822823)

## Olympus

沿用 761321 的原環境和私有模型 root。依 `Commit allowed` 可保留去識別摘要，不把 ZIP、deck、模型或原始波形放 GitHub。核對外層 ZIP SHA，解到新資料夾後用同一 761321 dependency 鏈。

```bash
export PAM4_SAR7_NATIVE_DECODE_PACKAGE='/absolute/path/PAM4_SAR7_NATIVE_DECODE_PILOT_20261116'
export PAM4_SAR7_NATIVE_DECODE_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_native_decode_pilot_20261116.XXXXXX")"
export PAM4_SAR7_NATIVE_DECODE_APPROVAL="$PAM4_SAR7_NATIVE_DECODE_ROOT/approval.json"
cd "$PAM4_SAR7_NATIVE_DECODE_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_native_decode.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_native_decode.py approval-template \
  --root "$PAM4_SAR7_NATIVE_DECODE_ROOT" --approval "$PAM4_SAR7_NATIVE_DECODE_APPROVAL"
```

依使用者授權核對 root、manifest 和唯一 portable deck SHA `ecd325622c426dfe2c1f5dd42cb00ca30c59f238ba77764d7757af15dd04720a` 後，只改 `approved=true`。對 761321 stage deck 差異為 14 個 clock/trial pulse 替換、28 條原 decoder 替換成 84 條 native decoder/對稱負載、2 個 subckt（16 行）、1 個 save 擴充。須確認 XRef、XBitb/XBit、analog、供應、stop 和 strobe 保持原樣。先 stage 再只提交一案。

```bash
/usr/bin/python3.11 -B sar7_native_decode.py stage --root "$PAM4_SAR7_NATIVE_DECODE_ROOT" \
  --approval "$PAM4_SAR7_NATIVE_DECODE_APPROVAL" --model-root "$PAM4_PDK_ROOT"
sbatch --export=ALL --output="$PAM4_SAR7_NATIVE_DECODE_ROOT/slurm-%j.out" sar7_native_decode.sbatch
```

1 CPU、6 GiB、Slurm 12 分鐘、solver 540 秒。估計 3–7 分鐘、raw 約 100–180 MB。solver 成功但收集中止才使用 `collect-only` 及原 root/approval；其餘失敗保存原始記錄並停止。

## 判讀

報 554／557 ps 的 registered code、比較器決策、兩套一致性和 |ΔCM|。每套 screen 需 84 bit 全解析、12 個直接比較器碼和 readout 相同、最大碼誤差 ≤1 LSB、最多 6 個錯碼且 |ΔCM|≤10 mV。另報 zero-error `logic_smoke_pass`。報每 bit 控制 50% 交越、底板及 held/CMP 取樣、到 read ±1 LSB 的時間、raw 與量測 SHA。`overlap_proxy_full_conversion` 把兩路 TG 同時各有至少一個門極跨 50% 判成疑似重疊，輸出 0.25 ps 快照樣點數、事件數和最長取樣跨度；它不表示實際導通寬度。`V_RHI:p/V_RLO:p` 報各轉換窗口內兩參考源的電流絕對峰值，包含切換充電，不能當作逐元件短路電流。配合底板、gate 和電流判定是否需要 break-before-make。保留 fail/PVT/多碼/DC、SNDR 及 112 GS/s 進一步驗證邊界。
