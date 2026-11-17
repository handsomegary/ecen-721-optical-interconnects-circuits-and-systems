# PN skew 補償 LP_DIAG NEXT：延伸穩定度、TT／FF 啟動、擾動與 XT2（2026-11-14）

第十六版。接在 LP_DIAG 之後，補上：

- beta STB 延伸到 20 GHz；
- 其餘角落的 replica STB；
- TT／FF 的快速、慢速、重啟上電；
- 三角落的正負小擾動；
- SS cb2 的 XT2 有限擺幅（0.4／0.2 Vppd）。

電路沿用 LP_INTEGRATE 的 1934 Ω 直連版。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼（ZIP SHA 68d23418…）；生成的 deck、portable_review 與 netlist 未收錄。 |
| `prompts/` | 結果回饋。 |
| `results/lp_diag_next_summary.json` | `diag_next_summary.py` 輸出（0–21）。 |

## 結果（job 754151、754153、754172，22／22 完成）

- 啟動（TT／FF 共 6 案）、擾動（三角落共 3 案）：全部 pass。
- replica STB：
  - SS：pass（PM 84.0°、GM 19.6 dB）。
  - TT／FF：PM 90.6°／101.4°，但 1 GHz 掃頻內相位沒到 0°，沒有 GM，所以標為 review。
- beta STB：六案都是 review。max |T| 0.498–0.505（儲備約 6 dB），Spectre 判定 always stable，但未達 10 dB 篩選。
- XT2：0.4／0.2 Vppd 下最小裕度 −7.7／−2.9 mV（短暫進入 triode），全幅對半幅的增益差約 0.10 dB。
- raw 保留在 Olympus。
