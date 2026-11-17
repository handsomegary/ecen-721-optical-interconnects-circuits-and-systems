# SAR7 1.75 GS/s 參考開關理想驅動對照

只跑 `sar7_13_tt_175gs_dac_gate_bypass`。保留波形分析（`b4220fb8…e5f7b`）顯示 761321 的 b5／b4／b3 在比較器開啟前幾乎尚未完成 CDAC 試碼步進，上三位主要需要 41–60 ps 才進入讀取值的 ±1 LSB。緩衝比較器仍有三個近零、反向輸入案例未解析。此對照測量略過現有多級驅動後，實體參考開關及電容本身能否在 21 ps 等待內建立。

快案原樣保留 1.75 GS/s、21 ps 試碼等待、42 ps 比較窗、原生開關與原 CDAC、原參考源、原取樣、CML、比較器、互補 NOR 及所有實體輸出／登錄邏輯。只重接 28 個 XRef 的兩個 gate net 到理想驅動。36 個 `bsource` 用凍結 TT 0.9 V 反映 `trial OR qplus`，並以 `conv` 使能、分別選零與一的參考。兩個參考的設計區間不重疊，門極由分段連續函數驅動，互補門極為 VDD 減使能。使用真實 q，不從預期碼或波形重播得知判決。移除原控制輸出的 TG gate 負載，所以本案的原 `c/cb` 只能標成卸載對照，不能取代原電路的帶負載延遲。

控制表（`conv=1`）為 `trial=1` 時只開一參考，`trial=0、qplus=1` 時只開一參考，`trial=0、qplus=0` 時只開零參考。`conv=0` 時兩個參考都關閉，reset/dummy 支路原樣保留。實體底板、電荷重分配、開關 Ron、DAC 差動暫態、比較器再生和錯碼為真正模擬。理想電壓源移除了 gate 驅動延遲及輸出阻抗，本案只提供可改進的上限，不能視為新實體電路達標。記錄 28 條原 c/cb、28 條實際理想門極及 14 個底板節點，僅輸出每試碼的 crossing 和幾個取樣點。

以 [Bheemisetti 等，IEEE JSSC](https://doi.org/10.1109/JSSC.2024.3449115) 的量測型 1.75 GS/s 非同步 SAR 為性能參照。該架構以實體比較器自定時及 CDAC 驅動達成，這裡先鑑別是被動開關／電容，還是現有固定時序的數位參考選擇路徑占用主要時間。Olympus 既有 REFMIRROR 支持同樣的 `bsource v=...min(max(...))` 形式，本案的組合首次在 Spectre 執行時核實編譯及 PSF 儲存。

## Olympus

使用 761321 的既有環境和依賴，包含 `PAM4_SAR7_FAST_PACKAGE`、offset、CDAC fix、CML rdeg、relaxed、原 SAR7、C0／SWITCH64／r5 與原私有模型 root。把 ZIP 和 sidecar 放核准位置，核對 ZIP SHA 再解到新資料夾。共一案，1 CPU、6 GiB、Slurm 12 分鐘，solver 上限 540 秒。預估 3–6 分鐘，raw 約 100–180 MB。

```bash
export PAM4_SAR7_DAC_DRIVE_PACKAGE='/absolute/path/PAM4_SAR7_DAC_DRIVE_PILOT_20261116'
export PAM4_SAR7_DAC_DRIVE_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_dac_drive_pilot_20261116.XXXXXX")"
export PAM4_SAR7_DAC_DRIVE_APPROVAL="$PAM4_SAR7_DAC_DRIVE_ROOT/approval.json"
cd "$PAM4_SAR7_DAC_DRIVE_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_dac_drive.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_dac_drive.py approval-template \
  --root "$PAM4_SAR7_DAC_DRIVE_ROOT" --approval "$PAM4_SAR7_DAC_DRIVE_APPROVAL"
```

依使用者授權核對唯一 case、run root、manifest 與 portable deck SHA，只改 `approved=true`。差異只允許 28 條 XRef 的 `c/cb` net 換名、36 條 bsource、一條 save。所有元件、邊緣、PWL、stop 和 `strobe` 須與 761321 一致。對照前先核對來源和 audit SHA；請在待送前核實所有依賴和本案變更。

```bash
/usr/bin/python3.11 -B sar7_dac_drive.py stage --root "$PAM4_SAR7_DAC_DRIVE_ROOT" \
  --approval "$PAM4_SAR7_DAC_DRIVE_APPROVAL" --model-root "$PAM4_PDK_ROOT"
sbatch --export=ALL --output="$PAM4_SAR7_DAC_DRIVE_ROOT/slurm-%j.out" sar7_dac_drive.sbatch
```

如果 Spectre 完成但後續量測中止，`sar7_dac_drive.py collect-only` 傳原 root 和 approval，讀原波形。若編譯／mathematical error、缺訊號或 solver 未完成，保留原資料回報，停止。這包沒有備援 solver。不要搬動已留存的新舊原始波形、模型或含 deck 的材料。

## 判讀

比較 b6–b3 在實際 `ff_c/cb` 改變後的底板步進、方向、`launch→compare` 內 held 是否接近 read 值 ±1 LSB，以及逐碼最大誤差與未解析。原 `c/cb` 卸載延遲只供觀察。若新 held 在 compare 前穩定且中段錯碼消失，支持優先重做 loaded TG gate driver。若新 gate 準時，底板／held 仍遲，定位原生開關與 CDAC 或 b6 的轉換起始暫態。若 gate 和 held 均及時，仍有近門檻錯誤，轉查比較器和固定窗。若 84 bit 全解析，12 筆 comparator/registered 同碼，|ΔCM|≤10 mV、max≤1 LSB 且錯碼≤6，則 `code_screen_under_ideal_drive=true`。`logic_smoke_pass` 仍維持原零錯零未解析定義。報 job ID、測量及 raw SHA、逐碼、分支觀察和未達的量，等 Codex 判讀才另做實體方案。repo 可存去識別摘要及符合規範的程式，含 deck、ZIP、模型、完整波形與逐節點證據留核准 OneDrive／Olympus。
