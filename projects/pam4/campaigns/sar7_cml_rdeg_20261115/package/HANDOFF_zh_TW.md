# ECEN 721 SAR7 · 補齊 r5 CML source 差動路徑單案

760254 的實體感測已將 CDAC 共模下降降至約 4 mV，但差動增益只有 0.0335，總絕對碼差 197。核對歷史 r5 後，前包遺漏了兩腿 source 間的 250 Ω 電阻，使兩個獨立 tail 無法提供原設計的差動電流路徑。這一包只恢復該電阻；不改 MOS、偏壓、500 Ω 負載、CDAC、未 trim 的參考電壓、輸入碼、比較器或時序。

只有 `sar7_07_tt_r5_cml_rdeg` 一案；沿用 12 碼、1,080 ps 週期、60／60 ps 以及 1030 ps final read。這是約 0.926 GS/s 的診斷，不能宣稱 1.75 GS/s。請勿重跑舊案、sweep、改 bias／tail、調 Vref，或自動開下一案。新舊 raw 全部保留。

## Olympus

傳 ZIP／sidecar 至核准 Olympus 位置，先核對 SHA，沿用原 SAR7／relaxed／CML 包與既有私有模型環境。舊 CML 包僅供 unittest 對照，不會執行舊案。

```bash
export PAM4_SAR7_CML_RDEG_PACKAGE='/absolute/path/PAM4_SAR7_CML_RDEG_20261115'
export PAM4_SAR7_CML_RDEG_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_cml_rdeg_20261115.XXXXXX")"
export PAM4_SAR7_CML_RDEG_APPROVAL="$PAM4_SAR7_CML_RDEG_ROOT/approval.json"
cd "$PAM4_SAR7_CML_RDEG_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_cml_rdeg.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_cml_rdeg.py approval-template --root "$PAM4_SAR7_CML_RDEG_ROOT" --approval "$PAM4_SAR7_CML_RDEG_APPROVAL"
```

核對範本綁定新 root、唯一 case、manifest SHA 與 portable deck SHA，只將 `approved` 改為 true，勿加欄位。stage 後對 760254 bench 的差異必須恰好只有一條 source 間電阻，不能夾帶任何其他改動；三項測試核對完整歷史元件與此單一差異。

```bash
/usr/bin/python3.11 -B sar7_cml_rdeg.py stage --root "$PAM4_SAR7_CML_RDEG_ROOT" --approval "$PAM4_SAR7_CML_RDEG_APPROVAL" --model-root "$PAM4_PDK_ROOT"
sbatch --export=ALL --output="$PAM4_SAR7_CML_RDEG_ROOT/slurm-%j.out" "$PAM4_SAR7_CML_RDEG_PACKAGE/sar7_cml_rdeg.sbatch"
```

完成後回報 `sar7_cml_rdeg_summary.json` 的 SHA256、job ID、solver／raw 大小、84 點增益／符號一致／輸出共模與電流、未解析 bit、12 碼 comparator／registered、Σ|Δcode|／max、CDAC 共模下降及末端殘差。以保留的 760254、760132、760234 摘要比較，不重跑。

若增益恢復且共模隔離保持，即便尚有約 1–2 LSB 誤差，也先停下總結，不為小差異繼續調參。若增益仍低或出現新失敗，提供現有 raw 的證據，不另送新案。資源 1 CPU／6 GiB／Slurm 30 分鐘，預估 solver 3–6 分鐘、raw 80–110 MB；最多並行一案。使用者委派截止 2026-11-15 21:45:37 Chicago，過時不送新 job。C1／C2 維持未授權狀態；任何超出範圍需求回報 `Needs user decision: yes`。

ZIP、deck、模型、raw 都留在核准 OneDrive／Olympus；repo 僅允許無 deck 的程式、去識別摘要和 handoff 存檔，由 Claude 操作。
