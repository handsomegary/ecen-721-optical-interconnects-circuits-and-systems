Stage: SAR7 case21 接受參考時序對照單案 sar7_21_tt_175gs_accept_gap（凍結 case20 全部電路，只改 10 條 pulse：MSB EVAL 37→35、b2 EVAL 47→44，b1 WAIT 8→13）
Status: done
Decision: STOP — 565 screen_pass=false：7 個 b2 接受 Z 全部在 b1 compare 前成立（名義餘裕 0.86–1.07 ps），conv8 b1 仍未解析，所以 late-Z-only 解釋被否定；另外 conv4/7/10 的 b2 接受 O 出現新的 bubble。reg 仍 7 錯 Σ7 max1，cmp 11/12
Summary: job 761700 COMPLETED 6:06（solver 323.1 s）；summary 7b93590f85c18b85b1cca6dae343d5e550d7b582d3922ee01a3fdb57a1eea851（3,408,873 B）；measurements 1a00d6d9…0aa2（80,357 B）；tran 11449a39…33e7
Run paths: ~/ecen720_28nm/runs/pam4_sar7_accept_gap_pilot_20261117.WRY0m7
Commit: 見 state.json（handoff + results）
Needs user decision: no

## 執行
- inbox `20261117T0335_sar7_accept_gap_pilot.md`。ZIP SHA256 `4e319b89c3e98ac8d27e2ad6a5bb7aeaf0480b24b2b2bec2a4711dfefc6827f0` 和 header 一致。manifest（SHA256SUMS.txt）`40a490ab…d650b`，sha256sum -c 6/6 OK，verify rc0（portable deck 532f9e8f…70ec），unittest 14/14 OK。
- root 用 mktemp 新建（`pam4_sar7_accept_gap_pilot_20261117.WRY0m7`），存在、canonical，basename 符合 `pam4_sar7_accept_gap_pilot_*`。env：沿用 case20 env，再加 `PAM4_SAR7_ACCEPT_GAP_{PACKAGE,ROOT,APPROVAL}`；`PAM4_SAR7_B2_LOCAL_DRIVE_PACKAGE` 指向原 case20。
- approval 和 template 只差 approved false→true（依既有 "Yes, 8 hours"，source SHA 26523d07…）。這次 headless 改寫沒有被平台擋。template 原檔存於 `logs/approval_template.json`。
- stage rc0（09:37:26Z）。staged bench 55c5c977…db2e 對 case20 bench 6ddcc18d…9073 的 diff：剛好 10 行，V_trial1–6 和 V_clk2–5；其他行逐 byte 相同（沒有 MOS/subckt/instance/save 變動）。
- 送出前帳號 running 4 CPU（C2 761525_7–9 三槽，其他專案一槽），SAR7 0。只送一次：**761700，SubmitTime 2026-11-17T09:37:41Z**（在 05:37–13:37Z 時窗內），Start 09:37:41Z，End 09:43:47Z。1 CPU，classic +mt=1，exit 0，solver_completion_errors 0，input deck before==after（55c5c977…），batch MaxRSS 110 MB（solver child peak 235 MB），raw 118,289,174 B（du 67 MB）。

## 正式 screen（原 gate 不變）
| read | screen | reg avail/wrong/Σ/max | cmp avail/wrong/max | unresolved | cmp=reg | final DAC CM (mV) | window |
|---|---|---|---|---|---|---|---|
| 565 | **FAIL** | 12/7/7/1 | 11/6/1 | **1** | no | −9.17 / +5.39 | valid |
| 563 | FAIL | 12/7/7/1 | 11/6/1 | 1 | no | −7.62 / +4.67 | valid |
| 554 | FAIL | 12/8/10/2 | 11/6/1 | 1 | no | −4.11 / −4.06 | valid |
| 557 | FAIL | 5/3/3/1 | 11/6/1 | 1 | no | −3.98 / −3.68 | valid |
- active CM（552）：trigger −4.23/−3.66 mV，read −4.05/−3.99 mV，pass。logic_smoke false。max_abs_sample_error 1.673 LSB。max observed resolve delay 45.0 ps。
- 碼（expected→cmp/reg565）：0:64→64/64，1:0→0/0，2:127→127/127，3:31→31/31，4:96→95/95，5:63→64/64，6:65→64/64，7:85→86/86，**8:42→None/43**（case20 reg 41），9:1→0/0，10:126→127/127，11:64→64/64。
- 失敗原因：84 bit 沒有全部解析（conv8 b1）、cmp≠reg、wrong 7 > 6。max1、CM、讀窗通過。
- 84 個比較器決策和 case20 完全相同（沒有任何決策改變），只有 margin 變了。conv8 registered 由 41 變 43：b1 的 registered 值變成 1（對），b0 仍是 1（錯）。

## 判別量 1：7 個 b2 接受 Z（Guide 主假設）
release 到 b1 compare：case20 6.5 ps → case21 11.5 ps。
| conv | Z 成立距 release (ps) | 距 b1 compare 餘裕 (ps) | case20 遲到 (ps) |
|---|---|---|---|
| 0 | 10.50 | +1.00 | −4.00 |
| 1 | 10.57 | +0.93 | −4.07 |
| 5 | 10.61 | +0.89 | −4.11 |
| 6 | 10.43 | +1.07 | −3.93 |
| 8 | 10.57 | +0.93 | −4.07 |
| 9 | 10.64 | **+0.86** | −4.14 |
| 11 | 10.54 | +0.96 | −4.04 |
- 7/7 trailing confirmed，Z_unconfirmed 0。Z 相對 release 的時間和 case20 完全一樣（O 約 1.8 ps → transition → Z），只因為 release 提早 5 ps 而落在 compare 前。這只是命令 rail 的名義餘裕，不代表 CDAC／sense 已建立。
- conv8 b1 compare 當下：gates [0.086, 0.803, 0.805, 0.057] V（接近 Z，還沒全 rail），held **+0.086 LSB**，sense **−0.060 LSB**（case20：held −0.773，sense −0.018）。+5 ps held +1.578／sense +0.377，+10 ps +1.309／+0.751，+15 ps +1.130／+0.728。
- **conv8 b1 仍 None**：precompare held −0.111、sense −0.062 LSB；raw p 在 compare 後 38.61 ps 才過半電源，原 read（44 ps）raw 0.702/0.120 V、xy 0.159/0.779 V，沒到 rail（case20 read 時 raw 0.190/0.587，方向相反）。這次 latch 往 1（正確方向）走，但 44 ps 內沒有解析。
- 結論：Z 已經及時，但 compare 當下差分仍只有約 ±0.1 LSB，conv8 b1 還是不解析。**late-Z-only 不足以解釋這個故障**（Guide 預先定義的否定條件成立）。

## 判別量 2：b2 接受 O（新 bubble）
| conv | case21 post-release runs（ps，相對 release） | case20 |
|---|---|---|
| 2 | O 0.14–55.39（單一 run） | 單一 O |
| 3 | O 0.21–55.46（單一 run） | 單一 O |
| 4 | O 0.04–3.54 → transition 3.79–4.54 → O 4.79– | 單一 O |
| **7** | O 0.0–2.0 → **transition 2.25–10.75** → O 11.0–（距 b1 compare 只剩 0.50 ps） | 單一 O |
| 10 | O 0.21–2.21 → transition 2.46–7.46 → O 7.71–（餘裕 3.79 ps） | 單一 O |
- 原因：release 提早 3 ps，但 b2 qmid/qdecode 時程沒變（qmid 50% 40.4–42.6 ps；所有 b2 qdecode 在新 read 44 ps 前都沒過半電源，case20 是 45.8–47.3 ps）。conv7 b2 read 時 decode 0.095 V、release 時 0.206 V，正確 O 還沒傳到 decoder 就 release，這就是 Guide 預先指出的 O bubble 風險，而且多了 conv4、conv10 兩個。
- 這次 O 的 b1 決策沒有被翻轉：conv7 b1 仍是 1，margin 4.25→3.25 ps；conv4 b1 6.96，conv10 b1 6.29。但 conv7 b1 compare 當下 gates 是 transition [0.903, 0.102, 0.184, 0.903]，O 只靠 0.5 ps 名義餘裕。

## 判別量 3：MSB 35 ps 與 b2 44 ps 捐時
- MSB 12/12 解析，決策同 case20，每個 margin 剛好少 2.00 ps：2.00, 7.68, 8.61, 4.54, 6.96, 2.14, 2.82, 6.00, 2.18, 7.61, 8.54, 2.46；最小 **2.00 ps**（conv0，Guide 預估 2.000）。raw stable 26.39–33.00 ps 沒變。
- MSB O 的 qdecode 50%：33.45–40.14 ps（相對 compare），最晚 conv0 在 release（37 ps）後 3.14 ps；conv0/5/6/11 的 qdecode 晚於 release，接受 O 的 margin 降到 31.75/32.39/34.07/33.71 ps（其他 O 是 43.25–43.46 ps），表示這四個也有短暫 bubble 後回到 O，但離 b5 compare 還有 30 ps 以上。MSB Z 4 個 30.68–30.86 ps。
- b2 12/12 解析，決策同 case20，每個 margin 少 3.00 ps：7.75, 7.68, 7.61, 7.54, 7.21, 8.14, 6.32, 5.50, **1.93**（conv8，Guide 預估 1.929）, 7.61, 6.54, 7.21。
- b1 margin（conv0..11）：7.25, 7.18, 7.36, 7.29, 6.96, 7.89, 5.57, 3.25, None, 7.11, 6.29, 6.46（比 case20 少 0.25–1.0 ps）。
- b0 margin：9.25, 8.93, 9.86, 9.54, 9.21, 10.14, 5.07, **3.00**（conv7，case20 1.75）, **4.18**（conv8，case20 10.43）, 8.86, 7.54, 7.71。conv8 b0 仍判 1（錯，期望 0），precompare sense 從 +1.29 變成 −0.22 LSB，held +1.106。
- b3、b4、b5 每個 margin 和 case20 完全相同。全部 83 個已解析 bit 的最小 margin：1.21（conv4 b5）、1.68（conv8 b4）、1.93（conv8 b2）、2.00（conv0 b6）、2.14（conv5 b6）。

## Collector／parser
- `selected_parser.summary_psf_parse_count=1`，selected_required 144 節點，84 trial／72 boundary 全部跑完，沒有 KeyError。這個 count 只算自訂 summary；原 basic measurement 另外 parse 一次。
- 72 邊界：observed 72/72，polarity_assessed **72**（case20 71），unassessable 0，opposite_rail 0，min prior |x−y| 0.624 V（case20 0.451）。
- provenance：manifest 40a490ab…，portable deck 532f9e8f…，parent manifest 2887bf07…，parent portable c587a30c…，parent summary 83d41a50…，authorization_sha256 3b4931d5…；relative_to_parent physical_changes=false、changed_pulse_rows=10、parent_job 761688。

## 資料
- OneDrive `outputs/PAM4_SAR7_ACCEPT_GAP_PILOT_20261117_RESULTS/`：原 bytes 的 `sar7_accept_gap_summary.json`（7b93590f…，3,408,873 B）、`measurements.json`（1a00d6d9…，80,357 B）、`run_status.json`（065e6d0b…，1,927 B）、`slurm-761700.out`（37874c4d…，233 B）、`package_SHA256SUMS.txt`（40a490ab…），加上 `SHA256SUMS_results.txt`。Olympus 端算的 SHA 和本機 `sha256sum -c` 逐一核對，全部 OK。
- repo 只放 compact 去識別版（146 KB）：每個 bit 的 decision、margin、raw delay、precompare held/sense、post-release 命令 runs、next compare、q 半電源交越，以及 acceptance_gap_diagnostic 全文。
- Raw（tranResponse 11449a39…，118,289,174 B；du 67 MB）**保留**：本包規定不清理，Codex 可能要稽核 conv8 b1 和 conv7 b2 的軌跡。
- C2 761525 沒動（_7–_9 RUNNING，10–94 PENDING %3），2144 waiting_runs 沒動。SAR7 只用 1 CPU。

## 結論
STOP。把 b2 release 提早 5 ps 之後，7 個 b2 接受 Z 全部在 b1 compare 前 0.86–1.07 ps 成立，但 conv8 b1 仍未解析：compare 當下的差分只有 held +0.09／sense −0.06 LSB，latch 在 44 ps 內到不了 rail。依 Guide 的判別，late-Z-only 被否定。同時提早 release 讓 conv4/7/10 的 b2 接受 O 出現新的 bubble（conv7 transition 8.5 ps，O 只在 b1 compare 前 0.5 ps 回來）。84 個決策和 case20 相同，screen 結果相同（reg 7 錯 max1）。依 Guide，這條時序分支到此停止：不開 case22、不掃參數、不改 gate。
