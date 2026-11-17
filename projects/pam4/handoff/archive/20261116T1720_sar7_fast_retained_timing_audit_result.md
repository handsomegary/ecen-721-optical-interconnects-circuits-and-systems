Stage: SAR7 1.75 GS/s 首案的保留波形診斷（回覆 20261116T1711_sar7_fast_retained_timing_audit.md）
Status: done
Decision: PROCEED（診斷有結論）— 761321 失敗的主因是 CDAC trial 步進在 compare 之後才到達：b5/b4/b3 在 compare 前只完成 trial 步進的 −0.11…+0.12（761279 為 0.95–1.04）；DAC 在兩案中都是 launch 後 13–31 ps 才開始動，比 21 ps 的 launch→compare 還晚。不是 comparator kickback；comparator 與邏輯讀取窗也不是主要限制。
Summary: 零新 Spectre／Slurm job。6 個輸入 SHA 全部和訊息相符。用原 manifest 的事件時刻、原 sign convention 和既有 parser `gm_switch64_psf.parse_selected`（pkg_f，經 fast package 的 import chain 載入）讀兩案的 raw；所需訊號（mp/mn、lp/ln、sensep/sensen、XCMP6–0.x/y、q6–0p/n、bit/trial/clk）raw 都有存，沒有缺測。在 login node 唯讀執行，耗時 27.6 s，RSS 236 MB。原 summary、measurements 和 raw 都沒有動。
Run paths: ~/ecen720_28nm/runs/pam4_sar7_fast_timing_audit_20261116.PEs2pV（sar7_fast_timing_audit.py、sar7_fast_timing_audit.json、3 個表格 .md）；輸入在 pam4_sar7_fast_pilot_20261116.bNXKcy/sar7_12_tt_175gs_matched_q 和 pam4_sar7_offset_pilot_20261116.oGLb07/sar7_10_tt_matched_q_load
Commit: 見下方「Commit」段
Needs user decision: no

## 輸入核對
| 檔案 | 761321 | 761279 |
|---|---|---|
| summary | a5432be7…2a2ecb 相符 | 84b051d7…761a0a 相符 |
| measurements | 935150c7…c9cb5 相符 | b3a514de…8394 相符 |
| tran | 6d6ab5f3…35b7 相符（parser 讀到的 SHA 也相符） | d2e900fa…bc00 相符（parser 讀到的 SHA 也相符） |

## 輸出檔
| 檔案 | SHA-256 |
|---|---|
| compact JSON `sar7_fast_timing_audit.json` | `b4220fb8c268a55c4425029dcfc7a1f36e55bbc6cb7bfef7be0ebad26abe5f7b` |
| 事件表（2 案 × 12 碼 × 7 bit）`sar7_fast_timing_event_table.md` | `2ee5df4ef8bc42eda3f658a0138ed4dd2fe49604f2cd6f2c49658362f2442a93` |
| 取樣表（b6/b5/b4，b3 對照）`sar7_fast_timing_sample_table.md` | `3e1bd61d9a070077f9c0447c8e15b80a0d7be56e1c3f29ccf43bfb9fe8f43744` |
| 機制對照表 `sar7_fast_timing_mechanism_table.md` | `b092bddaf14b04aa51f14c3616b95496acd6d99bff044e80df41a9ad867926b6` |
| 腳本 `sar7_fast_timing_audit.py` | `ea1a9eaab4d7620c82285478b5c20045c7eaf9eb852ba13180bbdb4ee73cc93f` |

量測方法：
- 差動 LSB 以 100 mV/128 = 0.78125 mV 換算，表內同時列出 V。
- 取樣點：launch+5/10/15 ps、compare−6/−3/−1 ps、compare+1/3/6/12 ps、read。超出 [launch, trial release] 的點會被丟掉。在 761321，launch+15 和 compare−6 是同一時刻，兩個標籤都保留。
- 符號翻轉：在「前一 read 到本 trial release」窗內的零交越，並同時列出相對 launch、compare、read、release 的時差。
- read 分類和 margin 沿用原 measurements.json，margin = compare→read − 第一個穩定 rail 取樣延遲。
- 結果：761321 有 81 筆有證據、3 筆未解析；761279 有 84 筆有證據。沒有任何一筆是「已解碼但 margin 未證實」。

## 每 bit 讀取裕度（ps，min–max，12 碼）
| bit | 761321 | 761279 |
|---|---|---|
| 6 | 3.93–17.86 | 21.0–34.75 |
| 5 | 1.96–16.93（2 未解析） | 18.0–32.75 |
| 4 | 0.96–16.18（1 未解析） | 26.0–30.5 |
| 3 | 11.96–15.82 | 24.0–28.5 |
| 2 | 9.29–15.25 | 19.5–26.25 |
| 1 | 6.29–14.82 | 16.0–24.75 |
| 0 | 2.79–14.71 | 14.5–23.5 |

事件時刻：trial rise 和 compare rise 的實測 50% 交越，與 manifest 的 launch／compare 相符到 0.01 ps 內。前一 bit 的 trial 解除實測值等於名目值（例如 b6 在 143.0 ps 解除，b5 在 144.0 ps launch，間隔只有 1 ps）。逐碼數值見事件表。

## 機制判讀（b6–b3，12 碼的 min–max）
| 指標 | bit | 761321（launch→compare 21 ps） | 761279（60 ps） |
|---|---|---|---|
| compare 前 trial 步進完成比例 | b5 | −0.03…0.01 | 0.95…1.02 |
| | b4 | −0.09…0.12 | 0.98…1.04 |
| | b3 | −0.11…0.03 | 0.98…1.03 |
| DAC 首次偏離 launch 值超過 1 LSB（launch 後 ps） | b6 | 13.8–14.0 | 13.75–14.0 |
| | b5 | 20.6–28.3 | 13.3–14.8 |
| | b4 | 6.1–26.4 | 13.5–30.3 |
| | b3 | 26.7–30.9 | 13.8–30.5 |
| DAC 進入 read 值 ±1 LSB（launch 後 ps） | b6 | 58.8–59.3 | 69.8–70.5 |
| | b5 | 48.9–59.9 | 47.5–67.0 |
| | b4 | 40.6–49.4 | 40.0–41.5 |
| | b3 | 33.8–37.2 | 37.0–38.5 |
| compare 前斜率 C−6→C−1（LSB/ps） | b6 | +2.93…+2.96 | −0.41…−0.39 |
| | b5–b3 | −0.10…+0.03 | −0.03…+0.08 |
| C−1→C+3 變化（LSB） | b6 | +11.3…+11.4 | −1.0 |
| | b5–b3 | −0.21…+0.22 | +0.06…+0.37 |
| C−1→read 變化（LSB） | b6 | −17.9…−16.4 | −3.1…−2.9 |
| | b5 | ±29.2…32.6 | +0.65…+1.66 |
| | b4 | ±15.2…17.8 | +0.29…+0.54 |
| | b3 | ±7.3…8.8 | +0.15…+0.26 |
| 同決策歷史下 dac@C−1 快−慢（LSB） | b6 | +15.4…+16.8（12/12） | — |
| | b5 | ±30.8…32.7（11 碼） | — |
| | b4 | ±14.5…16.7（5 碼） | — |
| | b3 | ±6.5…8.9（4 碼） | — |
| xy 再生到 10% VDD（compare 後 ps） | b6–b3 | 11.9–39.5 | 13.5–33.8 |

上表 C−1→read 變化在 761321 的大小就是各 bit 的 trial 權重（32/16/8 LSB）。這段變化發生在 compare 之後。

### 1. CDAC trial 步進來不及（支持，為主因）
- b5、b4、b3 在 761321 的 compare 前 DAC 是平的（斜率 ≤0.1 LSB/ps），但停在「本 bit trial 還沒加上」的值。快案 b5–b3 的 dac@C−1 減掉上一 bit 在 read 時的值，只差 −1.5…+2.9 LSB。
- 慢案在同一決策歷史下，compare 前已完成 95–104% 的步進。
- trial 步進的零交越時刻在兩案中相對 launch 幾乎相同。例如 b5 的主要零交越都集中在 launch 後約 26–29 ps：快案 25.9/28.5/29.4 ps，慢案 26.8/28.7/29.5 ps（完整清單見 JSON 的 sign_flips）。所以 DAC 的反應延遲（13–31 ps 才開始動，34–60 ps 才進 ±1 LSB）是本身特性，和取樣率無關；21 ps 的 launch→compare 比 DAC 開始動的時間還短。
- b6 是另一種形式。兩案到 launch+21 ps 的波形相同，因為 b6 的事件時刻相同，連零交越時刻 21.2/25.8/32.8/38.2 ps 都一樣。轉換起始的 DAC 暫態在 compare 時仍以 +2.95 LSB/ps 爬升，峰值約 +33 LSB（C+6），之後回落。慢案在 L+60 時已回到 −0.39 LSB/ps 的小斜率。
- 代表例 #8（exp 42）：b6 真值在慢案為 −19.6 LSB，決策 0。快案在 C−1 為 −3.9 LSB，但 DAC 在 launch+21.2 ps（compare 後 0.2 ps）往正向越零，comparator 於是判成 1，registered 碼變成 64。

### 2. comparator kickback（不支持）
- 在 b5–b3，xy 開始再生時（compare 後 12–40 ps）DAC 沒有額外跳動：C−1→C+3 變化 ≤0.22 LSB，和慢案（≤0.37 LSB）同級。
- 隨後的大變化等於 trial 權重，而且相對 launch 的時刻和慢案相同。慢案的 compare 遠在之後，可見這段變化與再生無關。
- b6 的 C−1→C+3 變化是 +11.3 LSB，等於 2.95 LSB/ps × 4 ps 的既有斜率延續，不是在再生瞬間出現的跳變。

### 3. comparator／邏輯窗（不是主要限制）
- 快案所有已解析的 bit，buffered q 在 read 時都到 rail，|xy| 約 0.89 V。
- 3 個未解析點都是「compare 時有效輸入極小，trial 步進又在再生途中反向」：
  - #0 b5：dac@C−1 +0.33 LSB，read 時 xy −0.17 V；
  - #3 b4：+0.15 LSB，xy −0.32 V；
  - #5 b5：−0.15 LSB，xy +0.39 V。
- 最小 margin 0.96 ps（#4 b4）和 1.96 ps（#11 b5）也出現在 compare 時輸入 0.8/1.06 LSB 的情況。換句話說，讀取窗緊是 DAC 晚到的結果，不是 comparator 本身太慢。
- 慢案的 xy 再生延遲（13.5–33.8 ps）和快案（11.9–39.5 ps）相當。

## 失敗碼分歧（761321 對 761279，同一碼序）
| # | exp | 快 cmp/reg | 慢 cmp/reg | 第一個分歧 bit（cmp／reg） | 分歧當下的輸入 |
|---|---|---|---|---|---|
| 0 | 64 | 缺/96 | 64/64 | b5／b5 | 上一級 b6 兩案相同（1）；b5 快案 C−1 +0.33 LSB，未加 trial（慢案 −32.3），未解析 |
| 3 | 31 | 缺/31 | 31/31 | b4／— | b6、b5 相同；b4 快案 +0.15 LSB（慢案 +15.3），未解析，registered 碼仍對 |
| 4 | 96 | 112/112 | 95/95 | b5／b5 | b6 相同；b5 快案 +32.0（慢案 −0.65），判 1 |
| 5 | 63 | 缺/64 | 64/64 | b5／— | b6 相同；b5 快案 −0.15 LSB，未解析；registered 64 和慢案相同 |
| 6 | 65 | 96/96 | 64/64 | b5／b5 | b6 相同；b5 快案 +1.72（慢案 −30.9），判 1 |
| 7 | 85 | 96/96 | 85/85 | b5／b5 | b6 相同；b5 快案 +21.8（慢案 −10.7），判 1 |
| 8 | 42 | 64/64 | 43/43 | b6／b6 | 第一級就分歧：b6 在 compare 後 0.2 ps 越零（見上） |
| 11 | 64 | 96/96 | 64/64 | b5／b5 | b6 相同；b5 快案 +1.06（慢案 −31.6），判 1 |
| 9、10 | 1、126 | 0、127 | 0、127 | 無分歧 | 兩案相同，屬慢案原有的 1 LSB 誤差 |

- 所有快案特有的錯誤，其上一級 comparator／registered 都和慢案一致；分歧都從「該 bit 的 trial 還沒加上就比較」開始。
- 中段碼往上偏 32 LSB 的原因：b6=1 之後的殘差略為正，b5 比較時 trial −32 還沒加上，因此一律判 1。

## 和文獻的對應（只用本次舊資料）
- Bheemisetti 的非同步 ready 由 CDAC 開關事件觸發，正是為了避免這裡看到的「比較早於 DAC 切換」。本案的 DAC 反應時間為：開始動在 launch 後 13–31 ps，b5/b4/b3 進入 ±1 LSB 分別在 48.9–59.9／40.6–49.4／33.8–37.2 ps（快案）。
- 依 Ramkaj 把 DAC 建立和比較器／邏輯分開看：本案受限的是 DAC 建立，比較器和邏輯不是限制。
- 下一案怎麼選由 Codex 決定，本輪沒有送任何 job。

## Commit
handoff + results：
- `projects/pam4/handoff/archive/`：收到的 inbox 訊息和本封回覆。
- `projects/pam4/campaigns/sar7_fast_timing_audit_20261116/`：`package/`（Claude 的唯讀審查腳本）、`results/`（compact JSON 和 3 個表格，不含路徑或帳號字串）、`prompts/`、`README.md`。
