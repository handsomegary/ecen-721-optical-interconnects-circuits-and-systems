Stage: SAR7 1.75 GS/s 參考開關理想驅動隔離對照（回覆 20261116T1728_sar7_dac_drive_isolation.md）
Status: done
Decision: PROCEED（定位結論）— 換成理想 gate 驅動後，registered 錯碼從 9/12（max 32）降到 6/12、總和 6、max 1 LSB，12 碼和 761279 完全相同。所以 761321 的中段錯碼主要來自原控制路徑的延遲：原 c/cb 卸載後，最晚的 50% 交越仍在 launch 後約 18.6 ps。code_screen_under_ideal_drive=false，只因為 b0 有 2 個近零未解析（#8、#10），以及 comparator 和 registered 不一致；logic_smoke_pass=false。b6 的 held 在理想 gate 下仍需 36.5–37.0 ps 才進入 ±1 LSB，比 21 ps 晚。
Summary: ZIP SHA 相符。Olympus sha256sum 5/5；verify 通過（portable 49d09ab9…）；unittest 2/2；manifest ea184bc1… 相符；approval 只把 approved 改成 true。stage 後與 761321 的 bench 比對：28 條 XRef 的 c/cb 換成 ff_ net、新增 36 條 bsource、1 條 save 換成擴充版，共 29 行刪除、65 行新增，其他完全一致。Spectre 編譯並存出新的 bsource 組合（raw 內有 ff_c*/ff_cb* 交越）。job 761426 COMPLETED 0:0，耗時 3:21。
Run paths: ~/ecen720_28nm/runs/pam4_sar7_dac_drive_pilot_20261116.UawYd0（package PAM4_SAR7_DAC_DRIVE_PILOT_20261116/，case sar7_13_tt_175gs_dac_gate_bypass/，summary sar7_dac_drive_summary.json，deck diff logs/deck_diff_vs_761321.txt，env wrappers/env_drive.sh）
Commit: 見下方「Commit」段
Needs user decision: no

## Job
- 761426，1 CPU／6G。Slurm 耗時 3:21，MaxRSS 112,600 KiB。
- solver 161.0 s（761321 為 128.0 s）。
- raw 115,701,424 B。原始資料保留。
- 不需要 collect-only。
- SHA：
  - summary `fdcca5230efa8c6a8b534d54c4acd6ecdd2b290d2af4cfc0a55bd24a87625748`
  - measurements `cb6c4329329d24b158716c5e28eb6ac41fbd3482437880ecdafa7eb7b4f00092`
  - tran `cccc5ed1f074c72fb14ed80ed28095bd1991c8e7e0902bdc1be2b26d191cb807`
  - bench `d6d02431…e809`
- provenance：parent portable 903d79a5…，parent audit b4220fb8…，兩者都相符。

## 三案比較
| 項目 | 761279（0.926 GS/s） | 761321（1.75 GS/s，原驅動） | 761426（1.75 GS/s，理想 gate） |
|---|---|---|---|
| 未解析 bit | 0/84 | 3/84（b5×2、b4×1） | 2/84（b0×2） |
| comparator 可讀／錯／max | 12／6／1 | 9／9／32 | 10／4／1 |
| registered 錯碼／總和／max | 6／6／1 | 9／147／32 | 6／6／1 |
| comparator 與 registered 一致 | 是 | 否 | 否（只差 #8、#10 的 b0 未解析） |
| 末端 ΔCM（mV） | −4.04／−3.97 | −4.03／−3.93 | −4.01／−3.99 |
| 最大取樣誤差（LSB） | 1.63 | 1.24 | 1.63 |
| 最慢判決延遲 | 45.5 ps | 41.0 ps | 41.7 ps |

## 逐碼（expected → comparator / registered；761279 registered 對照）
| # | exp | 761426 cmp/reg | 761321 cmp/reg | 761279 reg |
|---|---|---|---|---|
| 0 | 64 | 64/64 | 缺/96 | 64 |
| 1 | 0 | 0/0 | 0/0 | 0 |
| 2 | 127 | 127/127 | 127/127 | 127 |
| 3 | 31 | 31/31 | 缺/31 | 31 |
| 4 | 96 | 95/95 | 112/112 | 95 |
| 5 | 63 | 64/64 | 缺/64 | 64 |
| 6 | 65 | 64/64 | 96/96 | 64 |
| 7 | 85 | 85/85 | 96/96 | 85 |
| 8 | 42 | 缺/43 | 64/64 | 43 |
| 9 | 1 | 0/0 | 0/0 | 0 |
| 10 | 126 | 缺/127 | 127/127 | 127 |
| 11 | 64 | 64/64 | 96/96 | 64 |

## 時差：控制 → 底板/held → 比較器（84 bit，依 bit 彙整，相對 launch）
原 c/cb 是卸載後的原控制輸出，只能作觀察，不代表帶負載延遲。ff_c/cb 是實際接到 TG 的理想 gate。

| bit | 原 c/cb 50% 交越（卸載）最早…最晚 ps | ff gate 交越 ps | held 進入 read ±1 LSB 並保持（ps） | 在 21 ps 內 | |compare 前→read| held 變化（LSB） | 未解析 | read margin ps |
|---|---|---|---|---|---|---|---|
| 6 | 1.45 … 18.09–18.33 | −0.14…+0.02 | 36.5–37.0 | 0/12 | 5.31–5.40 | 0 | 7.0–17.1 |
| 5 | 9.21 … 18.49–18.56 | 同上 | 11.9–40.6 | 8/12 | 0.90–6.72 | 0 | 1.71–15.2 |
| 4 | 9.21 … 18.52–18.56 | 同上 | 14.5–20.5 | 12/12 | 0.03–0.98 | 0 | 8.25–12.4 |
| 3 | 9.21 … 18.54–18.56 | 同上 | 4.8–14.5 | 12/12 | 0.34–0.54 | 0 | 6.68–10.4 |
| 2 | 9.21 … 18.55–18.57 | 同上 | 4.2–10.6 | 12/12 | 0.20–0.29 | 0 | 2.43–8.14 |
| 1 | 9.21 … 18.56–18.57 | 同上 | 0.6–2.1 | 12/12 | 0.05–0.15 | 0 | 2.04–6.64（#7 b1 已解碼但 margin 未證實） |
| 0 | 9.21 … 18.57 | 同上 | 0.0–0.5 | 12/12 | 0.04–0.08 | 2 | 0.32–5.64 |

說明：ff gate 另有一個交越在 +64.98 ps，那是下一次 trial 解除，不屬於本 trial。

對照 761321（1720 診斷）：
- b5/b4/b3 進入 ±1 LSB 最差為 59.9／49.4／37.2 ps，現在是 40.6／20.5／14.5 ps；
- compare 前完成的 trial 步進比例從約 0 變成 b4–b0 幾乎全部完成。

## 分支判讀（依 Guide）
1. b4–b0：gate 和 held 都及時（全部在 21 ps 內進入 ±1 LSB），中段錯碼消失，結果和 761279 一致。這支持優先重做 loaded TG gate driver。原控制即使卸載，最晚交越也要約 18.6 ps，幾乎吃掉整個 21 ps 窗。
2. b6，以及 b5 中的 4/12：理想 gate 已在 launch 時切換，held 仍晚到。b6 需要 36.5–37.0 ps，compare 前到 read 還差 5.3–5.4 LSB；b5 最差 40.6 ps，差 6.7 LSB。這部分不是驅動延遲，而是原生 TG 開關／CDAC 的建立，或 b6 轉換起始的暫態。本案中 b6 判決仍然正確（margin ≥7.0 ps），但沒有 1 LSB 以內的建立裕度。
3. 剩下的 2 個未解析都在 b0，compare 時 held 只有 +0.17／+0.14 LSB；#7 b1（−0.41 LSB）已解碼但 margin 未證實。這屬於比較器在門檻附近的情況，和 761279 的 1 LSB 誤差同一類，不是時序問題。
4. 尚未達成的量：
   - code_screen_under_ideal_drive 需要 84 bit 全解析，以及 comparator/registered 12 碼一致，現在未解析 2、可讀 10/12；
   - max≤1 LSB 已達成（registered 和 comparator 都是 1）；
   - 錯碼 ≤6 已達成；
   - |ΔCM|≤10 mV 已達成。

本案只是理想驅動的上限。真正的 1.75 GS/s 和完整 ADC 仍需實體 gate 驅動驗證。下一步由 Codex 判讀；本輪沒有送其他 job。

## Commit
handoff + results：
- `projects/pam4/handoff/archive/`：收到的 inbox 訊息和本封回覆。
- `projects/pam4/campaigns/sar7_dac_drive_pilot_20261116/`：`package/`（Codex 原始碼，不含 deck／ZIP）、`results/`（去識別 summary）、`prompts/`、`README.md`。
