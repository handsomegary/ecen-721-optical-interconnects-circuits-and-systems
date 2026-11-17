Stage: SAR7 1.75 GS/s 實體參考解碼及重配時槽（回覆 20261116T1902_sar7_native_decode_pilot.md）
Status: done
Decision: STOP — 761433 跑完且 solver 正常，但 554 ps 和 557 ps 兩個讀出點都是 screen_pass=false、logic_smoke_pass=false。主要有兩個問題：
(1) b0 trial 在 550 ps 解除後，b0=0 的 register 正在由 1 翻到 0，554／557 ps 還沒到 rail，所以 12 碼中有 8 碼 registered 讀不到；560 ps 才到 rail。
(2) 實體解碼下，b4–b1 的 held 在 compare 時都還沒進入 read ±1 LSB（b4 要 32–41 ps，只配了 24 ps），comparator 有 2 個 bit 未解析、5 碼錯，max 6 LSB。
Summary: ZIP（R2）SHA 相符。Olympus sha256sum 5/5；verify 通過（portable ecd32562…）；unittest 3/3；manifest 12e5745c… 相符；approval 只把 approved 改成 true。stage 後與 761321 bench 比對：刪 43 行、增 115 行，正好是宣告的範圍——14 條 clock/trial pulse、28 條原 decoder 換成 84 條 native decoder 與對稱負載、2 個 subckt 共 16 行、1 條 save。XRef、XBit、供應、tran 都沒動。job 761433 COMPLETED 0:0，耗時 3:54。
Run paths: ~/ecen720_28nm/runs/pam4_sar7_native_decode_pilot_20261116.4FHdcw（package PAM4_SAR7_NATIVE_DECODE_PILOT_20261116/，case sar7_14_tt_175gs_native_decode/，summary sar7_native_decode_summary.json，deck diff logs/deck_diff_vs_761321.txt，register 唯讀抽樣 logs/native_regbits.py，env wrappers/env_native.sh）
Commit: 見下方「Commit」段
Needs user decision: no

## Job
- 761433，1 CPU／6G。Slurm 耗時 3:54，MaxRSS 113,972 KiB。
- solver 200.5 s。
- raw 93,321,874 B。原始資料保留。
- 不需要 collect-only。
- SHA：
  - summary `c2f46592839597c54d61ee843da089f86fcc9771aadc7cec0d01ed15f4bfbab6`
  - measurements `c293ff78ec827454d0d70910ee66f61f41e2e1d8a73e6fac57379b7814b0e830`
  - tran `06fe50b014d4505a70cc6c650ba2442208c3804b2f474e3425653ba2626c9830`
  - bench `0397d66e…6407`
- provenance：parent portable 903d79a5…、isolation summary fdcca523…，兩者都相符。

## 兩個讀出點
| 項目 | 554 ps | 557 ps |
|---|---|---|
| screen_pass／logic_smoke_pass | false／false | false／false |
| comparator 可讀／錯／總和／max | 10／5／10／6 | 同左 |
| registered 可讀／錯／總和／max | 4／2／7／6 | 同左 |
| 未解析 bit | 2 | 2 |
| comparator 與 registered 一致 | 否 | 否 |
| 末端 ΔCM（mV） | −4.03／−3.78 | −4.05／−3.77 |

其他：最大取樣誤差 1.64 LSB，最慢判決延遲 41.96 ps。

## 逐碼（expected → comparator / registered@554 / registered@557）
| # | exp | cmp | reg 554 | reg 557 | 761426（理想 gate）reg |
|---|---|---|---|---|---|
| 0 | 64 | 64 | 缺 | 缺 | 64 |
| 1 | 0 | 0 | 缺 | 缺 | 0 |
| 2 | 127 | 127 | 127 | 127 | 127 |
| 3 | 31 | 31 | 31 | 31 | 31 |
| 4 | 96 | 缺（b5 未解析） | 缺 | 缺 | 95 |
| 5 | 63 | 64 | 缺 | 缺 | 64 |
| 6 | 65 | 64 | 缺 | 缺 | 64 |
| 7 | 85 | 缺（b4 未解析） | 79 | 79 | 85 |
| 8 | 42 | 48 | 缺 | 缺 | 43 |
| 9 | 1 | 0 | 缺 | 缺 | 0 |
| 10 | 126 | 127 | 127 | 127 | 127 |
| 11 | 64 | 64 | 缺 | 缺 | 64 |

## registered 讀不到：b0 解除後才翻轉（唯讀抽樣，沒有修改 Codex 程式）
用既有 parser 讀 raw 中 bit6–0／bit6b–0b 和 conv，時間相對每次轉換起點：
- b6–b1 在 548 ps 時 12 碼全部已經在 rail。
- b0 在 548 ps 時 12 碼都是 0.90／0.00 V，也就是 trial 還在，值為 1。
- trial0 在 550 ps 解除後：
  - b0=1 的 4 碼（#2、#3、#7、#10）維持在 rail，所以可讀；
  - b0=0 的 8 碼開始翻轉：554 ps 為 0.91／0.47 V，557 ps 為 0.35／0.72 V，兩點都還在中間；560 ps 為 0.02／0.83 V，565 ps 為 0.00／0.89 V，此時已到 rail。
- conv 在 557 ps 仍是 0.9 V，560 ps 已降到 0。conv 降下後，b6–b0 到 565 ps 都還保持。
- 結論：b0 解除到 register 建立約需 8–10 ps，兩個讀出點都太早。這和 1928 審查中「b0=0 在 end+3.5 ps 才到 rail」是同一類問題，只是這次時槽更緊。

## 每 bit 時序（相對 launch；compare 窗是新配置）
| bit | launch→compare 配置 | native gate 50% 交越（帶載） | held 進入 read ±1 LSB | 窗內 | |compare 前−read| held（LSB） | 未解析 | margin ps | 761426 理想 gate 進入 ±1 LSB |
|---|---|---|---|---|---|---|---|---|
| 6 | 42 | 11.4–17.0 | 61.3–62.0 | 0/12 | 7.56–7.76 | 0 | 2.75–11.1 | 36.5–37.0 |
| 5 | 40 | 6.1–16.7 | 39.1–64.8 | 8/12 | 0.84–10.35 | 1（#4） | 0.18–12.4 | 11.9–40.6 |
| 4 | 24 | 6.1–16.6 | 32.0–41.0 | 0/12 | 9.16–11.84 | 1（#7） | 0.93–6.68 | 14.5–20.5 |
| 3 | 17 | 6.1–16.6 | 28.7–30.5 | 0/12 | 6.94–8.97 | 0 | 1.43–6.29 | 4.8–14.5 |
| 2 | 13 | 6.1–16.7 | 23.2–29.1 | 0/12 | 3.93–5.15 | 0 | 6.29–8.43 | 4.2–10.6 |
| 1 | 10 | 6.1–16.7 | 22.4–24.5 | 0/12 | 1.88–2.03 | 0 | 5.29–9.0 | 0.6–2.1 |
| 0 | 8 | 6.1–16.6 | 0.0–17.9 | 8/12 | 0.92–1.04 | 0 | 12.0–18.5 | 0.0–0.5 |

- 帶載的 native gate 50% 交越落在 launch 後 6–17 ps。和 761426 的理想 gate 相比，held 進入 ±1 LSB 的時間在 b4–b1 晚了約 13–22 ps，在 b6 晚了約 25 ps。
- 新配的 b4–b1 窗（24/17/13/10 ps）都比實測的建立時間短。b6 雖然配了 42 ps，compare 前到 read 仍差 7.6 LSB；但 b6 判決除了 #5 之外都正確。
- 錯誤的 comparator 決策都出現在 compare 前 held 還沒到最終值的 bit：
  - #8 的 b4：compare 前 +7.4 LSB，read 時 −4.5，判 1；
  - #7 的 b3：+5.7 → +12.7；
  - #5 的 b6：+6.5 → −1.1，判 1，之後各 bit 依序判 0，comparator 碼 64（差 1 LSB）。
- b0 的兩個近門檻點：#6（−1.38 LSB）和 #10（+1.23 LSB），compare 前輸入約 ±1 LSB，判決落在 1 LSB 誤差內。

## break-before-make 指標
- overlap proxy：84 個 bit 中有 44 個各有 1 個事件（b6 4 個，b5–b1 各 8 個，b0 沒有），每個 21–23 個 0.25 ps 快照，最長跨度 5.0–5.5 ps。這只代表兩路 TG 的 gate 同時跨過 50%，不是實際導通寬度。
- 參考源電流峰值（各轉換窗內，含充電）：V_RHI 99.5–113.6 µA，V_RLO 121.9–125.2 µA，12 碼之間沒有明顯的異常尖峰。本案沒有同一程式的 761321／761426 電流可以對照，所以無法判定 overlap 是否造成額外電流。

## 判讀（交 Codex）
- 這一案沒有通過。主因有兩個，可以分開處理：
  1. readout 和 b0 解除的時序：554／557 ps 都落在 b0=0 register 翻轉中間；
  2. native decoder 的帶載延遲加上新配置的時槽，使 b4–b1 在 compare 前都沒建立完成。
- 是否把 readout 移到 conv 降下後（560–565 ps 時 register 已到 rail 並保持）、b0 解除提前，或重新分配 b4–b1 的窗，由 Codex 決定。本輪沒有送其他 job。

## Commit
handoff + results：
- `projects/pam4/handoff/archive/`：收到的 inbox 訊息和本封回覆。
- `projects/pam4/campaigns/sar7_native_decode_pilot_20261116/`：`package/`（Codex 原始碼，不含 deck／ZIP）、`results/`（去識別 summary，以及 register 抽樣 JSON）、`prompts/`、`README.md`、`scripts/native_regbits.py`（Claude 的唯讀抽樣腳本）。
