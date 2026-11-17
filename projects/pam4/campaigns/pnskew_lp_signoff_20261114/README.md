# PN skew 補償 LP_SIGNOFF AC：replica 20 GHz、非理想電感、XT2 讀回（2026-11-14）

第十七版。電路沿用 LP_INTEGRATE 的 1934 Ω 直連版。這版處理三件事：

- 把 TT／FF 的 replica STB 補掃到 20 GHz；
- 驗證驅動電感的 Q 與 SRF：Q15／SRF150 GHz，以及 Q8／SRF110 GHz；
- 直接讀 DIAG NEXT 17／18 的 PSF，看 XT2 的八路取樣殘差。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA 0c196c9f…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_signoff_0_28_summary.json` | `signoff_summary.py` 輸出（目前只有 0 和 28）。 |
| `results/xt2_held_readback.json` | XT2 八路 held 取樣讀回。 |
| `results/lp_signoff_summary_0_39.json` | 全部 40 案的 summary。 |

## 首批（0、28，job 754705）

- 0（TT cb0 replica，到 20 GHz）：pass。PM 90.58°（14.8 MHz），GM 26.72 dB（4.97 GHz）。
- 28（SS cb2 Q15／SRF150，P 欄）：偏壓工作點與理想電感版相同，driver 汲極低 12 mV（電感串聯電阻 2.8 Ω 的壓降），雜訊相同。Hdd 要等 N 欄。
- XT2 讀回：八路 lane 的增益變化在 −0.24～+0.01 dB，線性擬合後殘差低於 0.001 mV。
- raw 保留在 Olympus。

## 其餘 38 案（job 754709）

- replica 到 20 GHz：TT 為 PM 90.58°／GM 26.72 dB（4.97 GHz），FF 為 101.42°／20.23 dB（9.04 GHz），都 pass。
- 理想電感 4 列與 INTEGRATE 逐值相同。
- Q15／SRF150（實效 Q 12.9）與 Q8／SRF110（實效 Q 5.89）的 7 列全部通過 2 dB 與功耗。Hdd 相對理想電感反而改善 +0.2／+0.35 dB。
- 伺服誤差隨電感 DCR 上升：Q15 約 0.9%，Q8 約 1.6–1.7%。

