Stage: SAR7 case19 compare-window 單案 sar7_19_tt_175gs_compare_window（case18 精確電路只改 12 條 pulse）
Status: done
Decision: STOP — 565 screen_pass=false：未解析 bit 4→2（conv7 b0 新出現、conv8 b1 仍在），reg 7 錯 Σ7 max1 沒變，cmp 10/12、cmp≠reg；CM 和讀窗都通過
Summary: job 761674 COMPLETED 5:53（solver 309.4 s）；summary bb7c5418…1594（3,397,624 B）；measurements 6ecda109…0546；tran e3924d2c…36ae
Run paths: ~/ecen720_28nm/runs/pam4_sar7_compare_window_pilot_20261117.cJh5B6（pointer ~/ECEN721/.sar7_compare_window_base）
Commit: 見 state.json（handoff + results）
Needs user decision: no

## 執行
- 收到 inbox `20261117T0143_sar7_compare_window_pilot.md`。ZIP `ECEN721_PAM4_SAR7_COMPARE_WINDOW_PILOT_20261117.zip` SHA256 `ff552f5285fa6930788d2036ddfa62c164d17570b60a85871fecdde77e067992` 和 header 一致。上傳到新的 mktemp root，`sha256sum -c` 6/6 OK，sbatch 無 CR。
- env：`wrappers/env_compare_window.sh` 先 source case18 的 env_read_overlap.sh（裡面有 qbuffer 鏈和 PAM4_PDK_ROOT），再加上三個 COMPARE_WINDOW 變數。`verify` rc0（deck 13cb54f3…8d73），unittest 11/11 OK。
- root 檢查：存在、readlink -f 和原路徑相同、basename 前綴相符。approval-template 產生的 manifest 是 29234008…934d，deck 13cb54f3…；template 和最終 approval 只差 `approved` false→true 一行。
- stage rc0（07:51:29Z）。bench.scs e8dc3f4e…e777 對 case18 bench 做 diff：剛好 12 條 pulse 不同（trial6–1、clk6–1），b0 兩條 pulse 和其餘內容完全一樣。midpoint 和 Guide 表格一致：b6 78/108/149、b2 369/400/449、b1 447.5/455.5/501.5。
- 送出前帳號 running 4 CPU（C2 3 個 + 其他專案 1 個），SAR7 0 個。只送了一次：**761674 在 07:51:49Z 被接受**（< 13:37Z）。input deck before==after，classic +mt=1，1 CPU，exit 0，solver_completion_errors 0，MaxRSS 124 MB。

## 正式 screen（原 gate 不變）
| read | screen | reg avail/wrong/Σ/max | cmp avail/wrong/max | unresolved | cmp=reg | final DAC CM (mV) | window |
|---|---|---|---|---|---|---|---|
| 565 | **FAIL** | 12/7/7/1 | 10/5/1 | **2** | no | −9.15 / +5.39 | valid |
| 563 | FAIL | 12/7/7/1 | 10/5/1 | 2 | no | −7.60 / +4.63 | valid |
| 554 | FAIL | 12/8/10/2 | 10/5/1 | 2 | no | −4.12 / −4.05 | valid |
| 557 | FAIL | 5/3/3/1 | 10/5/1 | 2 | no | −3.97 / −3.68 | valid |
- active CM（552）：trigger −4.23/−3.66 mV，read −4.05/−3.99 mV，pass。logic_smoke false。max_abs_sample_error 1.668 LSB。
- 碼（expected→cmp/reg565）：0:64→64/64，1:0→0/0，2:127→127/127，3:31→31/31，4:96→95/95，5:63→64/64，6:65→64/64，**7:85→None/86**，**8:42→None/41**（case18 是 43），9:1→0/0，10:126→127/127，11:64→64/64。
- 失敗原因：84 bit 沒有全部解析（2 個）、cmp≠reg、wrong 7 > 6。max1、CM、window 這三項通過。

## 和 case18 比較（逐 bit decision）
case18 到 case19 只有 4 個 bit 的決策改變：conv7 b2 None→1、conv7 b1 None→1、conv8 b2 None→0，以及 **conv7 b0 0→None（新回歸）**。其餘 80 bit 決策相同。

### MSB 12 碼（39 ps 比較窗）
12/12 都解析，極性和 case18 相同。sampled margin（ps，conv0..11）：6.00, 11.68, 12.61, 8.54, 10.96, 6.14, 6.82, 10.00, 6.18, 11.61, 12.54, 6.46，最小 **6.00 ps**（conv0）。raw stable-rail delay 26.4–33.0 ps。捐出的 12 ps 沒讓 MSB 失效。

### 原本 4 個問題 bit
| bit | decision | raw 50% 交越（compare 後） | raw stable rail | sampled margin | accepted ref |
|---|---|---|---|---|---|
| conv7 b2（EVAL 47） | 1 | 33.3 ps | 38.5 ps | 8.50 ps | 要 O；release 後馬上 O（4449.0→4499.5 ps），距下一 compare 有 6.5 ps 餘裕 |
| conv7 b1（EVAL 44） | 1 | 34.4 ps | 39.75 ps | 4.25 ps | 要 O；O 4501.5→，距下一 compare 有 4.5 ps 餘裕 |
| conv8 b2（EVAL 47） | 0 | 37.2 ps | 42.82 ps | 4.18 ps | 要 Z；**先 O 2 ps（5020.5–5022.5）→ transition 約 10 ps → Z 5033.3**，下一 compare 是 5026.9 ps，所以 Z 晚了約 6.4 ps（margin_next=None） |
| conv8 b1（EVAL 44） | **None** | 39.8 ps（n 端） | 無 | — | 要 Z；同樣先 O → transition → Z 5085.5 |
- conv8 b1：precompare held −0.773 LSB，sense 只有 +0.074 LSB（case18 是 +0.281），read 時 raw 是 0.161/0.631 V，沒有到 rail。它的輸入就是前一個 conv8 b2 的 accepted reference 在 compare 時仍處於 O→Z 的 transition。所以延長 b2 EVAL 讓 b2 本身解析了，**接受 Z 的 P 路延遲還是跨進下一次 compare**。
- **conv7 b0 新回歸**：case18 是 0、raw delay 41.75 ps、margin 4.25 ps。case19 precompare held −0.276 LSB、sense −0.809 LSB（case18 是 −1.084），raw 50% 在 40.2 ps，到原 read 552 時是 0.127/0.712 V，沒有到 rail。b0 時程沒有改，所以這是前段軌跡改變造成的小訊號邊界 bit，不是時程被挪用。
- 72 邊界：observed 72/72，polarity_assessed 71，**unassessable 1**（conv8 b1→b0，因為 prior 本身是 None）；case18 有 2 個 unassessable。opposite_rail 0（只算可評估的 71 個），min prior |x−y| 0.523 V（case18 0.330）。None 沒有被當成極性穩定的證據。

### b0 餘裕（原時程不變）
conv0..11（ps）：7.25, 6.93, 7.86, 7.54, 7.21, 8.14, 3.57, **None（conv7）**, 8.43, 6.86, 5.79, 5.96。已解析的最小值 3.57 ps（case18 最小 1.18 ps，在 conv8；這次 conv8 是 8.43 ps）。
- 全部 82 個已解析 bit 的最小 sampled margin：1.21 ps（conv4 b5），其次 1.68（conv8 b4）、2.25（conv7 b3）、2.75（conv7 b4）、2.93（conv8 b3）。case18 最小是 0.07 ps（conv6 b2）。
- max observed resolve delay：42.82 ps（conv8 b2），case18 是 44.82 ps。

## Collector／parser
- `selected_parser.summary_psf_parse_count=1`，selected_required 144 個節點，84 trial / 72 boundary 全部跑完，沒有 KeyError。這個 count 只算自訂 summary 的 parse，原 basic measurement 另外 parse 一次，所以不能說整個 job 只 parse 一次。
- provenance：manifest 29234008…，portable deck 13cb54f3…，parent manifest df3b60ef…，parent portable 63c73525…，parent summary 121d50d9…，authorization_sha256 3b4931d5…。

## 資料
- OneDrive `outputs/PAM4_SAR7_COMPARE_WINDOW_PILOT_20261117_RESULTS/`：原 bytes 的 summary、measurements.json、run_status.json、slurm-761674.out，加上 SHA256SUMS_results.txt。本機的 SHA 和 Olympus 端逐一核對過，都一致（summary bb7c5418…，measurements 6ecda109…，run_status 418137a6…）。summary 裡已經內含 parse 診斷（selected_parser／overlap_diagnostic）；本包沒有另外產生 receipt 檔。
- repo 只放 compact 去識別版（55 KB），每個 bit 都有 decision、margin、raw delay、precompare held/sense、reference runs。
- Raw（tran e3924d2c…，raw_bytes 118,289,058；du 67 MB）**保留**：本包規定不刪 raw，而且還在 SAR7 修正時窗內，Codex 可能要稽核 conv8 b2→b1 reference 的 transition 和 conv7 b0。case18 761649 的 raw 也一樣沒動。
- C2 761525 沒有任何更動（_4–_6 RUNNING，7–94 PENDING）。資源：SAR7 只用了 1 CPU。

## 結論
STOP。12 ps 重新分配做到了 Guide 想測的大部分：MSB 12/12 在 39 ps 內解析，最小 6.0 ps；conv7 b2、b1 和 conv8 b2 在原 read 前到 rail；b0 最小餘裕從 1.18 升到 3.57 ps。但 screen 還是沒過：conv8 b1 仍未解析，原因指向 b2 接受 Z 的 O→Z transition 跨過下一次 compare；conv7 b0 新出現一個小訊號未解析；wrong 一樣是 7。依 Guide 本輪停止，不開 case20。
