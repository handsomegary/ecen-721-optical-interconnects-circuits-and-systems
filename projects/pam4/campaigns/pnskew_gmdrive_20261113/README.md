# PN skew 補償 GMDRIVE：以共源級取代 source follower（2026-11-13）

第六版。拆解 GMFINE 的 −8.75 dB 後確認：follower 的 gate→source 掉 11.25 dB，10 Ω 串阻掉 3.09 dB，延遲線只掉 0.02 dB。新版改用電阻負載共源級。全包 296 案；使用者批准首批 0–17（SS/85 °C/0.81 V 短路徑）。

| 路徑 | 內容 |
| --- | --- |
| `package/` | Codex 交付的原始碼、設計說明、follower 證據與 GMFINE OP 稽核；生成的 deck 未收錄，SHA 記在 `SHA256SUMS.txt`。 |
| `prompts/` | 首批結果回饋。 |
| `results/gmdrive_0_17_summary.json` | `drive_summary.py` 的輸出。 |

## 首批結果（18/18 完成）

| 驅動 | 相對理想驅動的額外損失 | SS 總功耗 |
| --- | ---: | ---: |
| cs12 | −2.71 dB | 18.94 mW |
| cs12lo | −3.41 dB | 16.21 mW |
| cs12r27 | −3.22 dB | 19.16 mW |
| cs16 | −0.92 dB（唯一低於 2 dB） | 22.11 mW |
| cs12l20 | −2.48 dB | 18.94 mW |

- 理想驅動的 SS 總功耗為 7.79 mW。
- CS 版的 56/7 GHz 滾降約 −3.3～−3.8 dB，理想驅動為 −0.34 dB。
- 漏訊（cs12）：相對 bypass −46.4 dB。

raw 190 MB 已退休，每案留有收據。其餘 278 案待使用者另外批准。
