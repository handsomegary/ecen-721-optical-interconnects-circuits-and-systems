Stage: Project #6 SAR7 單通道 1.75 GS/s TT 固定時序首案（回覆 20261116T1704_sar7_175gs_timing_smoke.md）
Status: done
Decision: STOP — 761321 跑完且 solver 正常，但 screen_pass=false、logic_smoke_pass=false：3 個 bit 未解析（b5×2、b4×1），registered 碼 9/12 錯，最大誤差 32 LSB。依 Guide，不往 112 GS/s 推進。
Summary: ZIP SHA 相符；Olympus sha256sum 5/5，verify 通過（deck 903d79a5…），unittest 2/2；approval 只把 approved 改成 true（manifest e049fa8b…）。stage 後與 761279 同模型根目錄的 bench 逐行比對，只有 25 行不同：22 條脈波、srcp／srcn 兩條 PWL、tran stop。送出 1 案，job 761321 COMPLETED，耗時 2:21。
Run paths: ~/ecen720_28nm/runs/pam4_sar7_fast_pilot_20261116.bNXKcy（package PAM4_SAR7_FAST_PILOT_20261116/，case sar7_12_tt_175gs_matched_q/，summary sar7_fast_summary.json，deck diff logs/deck_diff_vs_761279.txt，env wrappers/env_fast.sh）
Commit: 見下方「Commit」段
Needs user decision: no

## Job
- task ID：761321，單一任務，n01-zeus，COMPLETED，exit 0。Spectre 23.1 classic，`+mt=1`，1 CPU。
- solver 128.04 s（761279 為 207.8 s）。child peak RSS 240 MB。
- raw 58,856,463 B（761279 為 110,961,727 B）。原始資料保留，未退役。
- 是否需要 collect-only：不需要。run_status=spectre_completed，solver_completion_errors 0，measurements.json 正常產生。
- SHA：
  - summary `a5432be72f2c293c8577bdb3c5d0f886e4765d7c61852ba93a0a69c164f9ae5a`
  - measurements `935150c70665c0effde4c63cf47fcac6ffafc2412706a096420d7143c75c9cb5`
  - tran `6d6ab5f3f5052bc30e227772310ff35423067a81dfd580ee0a232ada9bab35b7`
  - bench（staged）`ce82877e…6f5f`
  - spectre.log `b3b4a7ec…582c`

## 判讀
| 項目 | 761279（0.926 GS/s） | 761321（1.75 GS/s） | screen 門檻 |
|---|---|---|---|
| 未解析 bit | 0/84 | 3/84（b5×2、b4×1） | 0 |
| comparator 可讀 | 12/12 | 9/12 | 12 |
| registered 可讀 | 12/12 | 12/12 | 12 |
| comparator 與 registered 一致 | 是 | 否 | 是 |
| registered 錯碼 | 6/12 | 9/12 | ≤6/12 |
| registered 誤差總和 | 6 | 147 | — |
| registered 最大誤差 | 1 LSB | 32 LSB | ≤1 LSB |
| 末端 CDAC 共模變化 | −4.04／−3.97 mV | −4.03／−3.93 mV | 絕對值 ≤10 mV（通過） |
| 最大取樣誤差 | 1.63 LSB | 1.24 LSB | — |
| 最慢判決延遲 | 45.5 ps | 41.0 ps | — |

- screen_pass=false。
- logic_smoke_pass=false（原 scorer 的零錯、零未解析判準）。

## 逐 bit 判讀
| bit | 未解析 | 最小 buffered 讀取餘裕 (ps) | 比較前到讀取的最大 CDAC 差動變化 (LSB) |
|---|---|---|---|
| 6 | 0 | 3.93 | 19.56 |
| 5 | 2 | 1.96 | 32.56 |
| 4 | 1 | 0.96 | 16.55 |
| 3 | 0 | 11.96 | 8.83 |
| 2 | 0 | 9.29 | 4.73 |
| 1 | 0 | 6.29 | 1.97 |
| 0 | 0 | 2.79 | 1.01 |

## 逐碼結果（expected → comparator / registered）
| # | expected | comparator | registered |
|---|---|---|---|
| 0 | 64 | 缺 | 96 |
| 1 | 0 | 0 | 0 |
| 2 | 127 | 127 | 127 |
| 3 | 31 | 缺 | 31 |
| 4 | 96 | 112 | 112 |
| 5 | 63 | 缺 | 64 |
| 6 | 65 | 96 | 96 |
| 7 | 85 | 96 | 96 |
| 8 | 42 | 64 | 64 |
| 9 | 1 | 0 | 0 |
| 10 | 126 | 127 | 127 |
| 11 | 64 | 96 | 96 |

對照 761279 同順序的 registered 碼：64、0、127、31、95、64、64、85、43、0、127、64。末端碼（0、127、1、126）和 761279 相同；中段碼多數往上偏 16 或 32 LSB。

## 唯讀診斷（未修改 Codex 程式）
- 主因看起來是 CDAC 殘差在比較器開啟後還在移動，而不是 buffered rail 太慢。理由有四：
  1. 上三個 bit（b6／b5／b4）從比較前到讀取，CDAC 差動仍變化 19.6／32.6／16.6 LSB；b1／b0 只剩 2／1 LSB。
  2. 錯誤集中在 b5／b4 的權重（16、32 LSB），方向一致往上。
  3. 讀取餘裕雖小但為正（最小 0.96 ps，在 b4），最慢判決 41.0 ps，仍在 42 ps 的讀取窗內。
  4. 末端共模（−4 mV）和取樣誤差（1.24 LSB）與 761279 相當，所以取樣和共模不是主因。
- 結論：試碼到比較只有 21 ps，對上位 bit 的 CDAC 建立時間不夠；42 ps 的讀取窗在邊緣但尚可。
- 限制：761279 的 summary 沒有「比較前到讀取的 DAC 變化」這個欄位，這項無法直接和舊案比較；完整逐 trial 資料在 Olympus 的 measurements.json。
- 可能的下一步由 Codex 決定，例如：延長上位 bit 的 launch→compare（非均勻步距），或加快 CDAC 驅動和參考電壓。本輪沒有送任何後續案。

## Commit
handoff + results：
- `projects/pam4/handoff/archive/`：本封回覆和收到的 inbox 訊息。
- `projects/pam4/campaigns/sar7_fast_pilot_20261116/`：package 原始碼（不含 deck／ZIP）、results（去識別的 summary）、prompts、README。
