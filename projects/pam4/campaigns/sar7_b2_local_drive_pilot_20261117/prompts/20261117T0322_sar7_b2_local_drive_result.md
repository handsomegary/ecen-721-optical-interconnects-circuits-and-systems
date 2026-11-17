Stage: SAR7 case20 b2 局部平衡驅動單案 sar7_20_tt_175gs_b2_local_drive（case19 電路＋b2 局部 10 個 instance 換 3 個新 cell；MSB EVAL 39→37、b0 EVAL 46→48）
Status: done
Decision: STOP — 565 screen_pass=false：未解析 bit 2→1（conv7 b0 已解析；conv8 b1 仍 None），reg 仍 7 錯 Σ7 max1，cmp 11/12、cmp≠reg；b2 接受 Z 只提早 2.25 ps，仍比 b1 compare 晚 4.07 ps；CM 和讀窗通過
Summary: job 761688 COMPLETED 6:07（solver 324.1 s）；summary 83d41a50aeea4285dbecf922deb94f949c2a4265cc2a8ce3d6acda4d7b7682a3（3,397,472 B）；measurements 5e90957d…0161；tran 48dfbe1d…3872
Run paths: ~/ecen720_28nm/runs/pam4_sar7_b2_local_drive_pilot_20261117.PY0zx1
Commit: 見 state.json（handoff + results）
Needs user decision: no

本訊息取代 20261117T0252_sar7_b2_local_drive_needs_user.md（使用者在互動 session 中處理了 approval，之後已提交）。

## 執行
- inbox `20261117T0243_sar7_b2_local_drive_pilot.md`；ZIP SHA256 `9165595b88b36065ad35937a92802fca8aff1ecfd5ee39e2da0959cb2253cc01` 和 header 一致；manifest `2887bf07…84e1`；sha256sum -c OK，verify rc0（portable deck c587a30c…bfbf），unittest 14/14 OK。
- root 用 mktemp 新建，存在、canonical，basename 符合 `pam4_sar7_b2_local_drive_pilot_*`。approval 和 template 只差 approved false→true。
- stage rc0（09:09:41Z）。staged bench 6ddcc18d…9073 對 case19 bench diff：13 條 pulse card、10 個 b2 instance 換 cell、新增 3 個 subckt（SAR_B2_OAI21_X4、SAR_B2_NOR3_P6、SAR_B2_INV4），和 Guide 宣告一致。
- 送出前帳號 running 4 CPU（C2 3＋其他專案 1），SAR7 0。只送一次：**761688，SubmitTime 2026-11-17T09:10:09Z**（在 05:37–13:37Z 時窗內），Start 09:10:10Z，End 09:16:17Z。1 CPU，classic +mt=1，exit 0，solver_completion_errors 0，input deck before==after（6ddcc18d…），batch MaxRSS 123 MB（solver child peak 249 MB）。
- circuit_change：bit2、scale 2；oai 2、nor 2、decoder_inv 4、qbuffer_second 2；原 global cell 不變、TG 不變、14 路第一級 qbuffer INV1 不變。

## 正式 screen（原 gate 不變）
| read | screen | reg avail/wrong/Σ/max | cmp avail/wrong/max | unresolved | cmp=reg | final DAC CM (mV) | window |
|---|---|---|---|---|---|---|---|
| 565 | **FAIL** | 12/7/7/1 | 11/6/1 | **1** | no | −9.17 / +5.39 | valid |
| 563 | FAIL | 12/7/7/1 | 11/6/1 | 1 | no | −7.62 / +4.67 | valid |
| 554 | FAIL | 12/8/10/2 | 11/6/1 | 1 | no | −4.11 / −4.06 | valid |
| 557 | FAIL | 5/3/3/1 | 11/6/1 | 1 | no | −3.98 / −3.68 | valid |
- active CM（552）：trigger −4.23/−3.66 mV，read −4.05/−3.99 mV，pass。logic_smoke false。max_abs_sample_error 1.668 LSB。max observed resolve delay 46.25 ps（conv7 b0，case19 是 42.82）。
- 碼（expected→cmp/reg565）：0:64→64/64，1:0→0/0，2:127→127/127，3:31→31/31，4:96→95/95，5:63→64/64，6:65→64/64，**7:85→86/86**（case19 cmp 是 None），**8:42→None/41**，9:1→0/0，10:126→127/127，11:64→64/64。
- 失敗原因：84 bit 沒有全部解析（1 個）、cmp≠reg、wrong 7 > 6。max1、CM、讀窗通過。
- 逐 bit：和 case19 比，只有 conv7 b0 None→0 改變，其餘 83 個決策相同。

## 判別量 1：conv8 b2→b1（接受 Z）
| 項目 | case20 | case19 |
|---|---|---|
| b2 決策 / sampled margin | 0 / 4.93 ps | 0 / 4.18 ps |
| raw q2n 50% / raw stable（從 b2 compare） | 36.64 / 42.07 ps | 37.21 / 42.82 ps |
| qmid2n 50% | **45.90 ps（晚 1.91）** | 43.99 ps |
| qdecode2n 50% | **52.21 ps（晚 2.58）** | 49.63 ps |
| 四控制 rail 50%（從 release 算）c2z↑ / cb2z↓ / c2o↓ / cb2o↑ | +3.98 / +7.75 / +8.70 / +4.78 ps | +4.48 / +9.17 / +10.39 / +5.43 ps |
| post-release 命令 | O 5018.5–5020.25 → transition 5020.5–5028.75 → **Z 5029.0** | O 5020.5–5022.5 → transition → Z 5033.25 |
| Z 成立距 release | 10.57 ps | 12.82 ps |
| 下一個 b1 compare | 5024.93 ps | 5026.93 ps |
| **Z 晚於 b1 compare** | **4.07 ps** | 6.32 ps |
- release 到 b1 compare 是 6.5 ps（兩案相同）。四條 rail 提早 0.5–1.7 ps，最慢的 c2o↓ 仍在 release 後 8.70 ps，晚於 6.5 ps。Z 整體只提早 2.25 ps，低於 Guide 估的 RC 代理約 5.2 ps。
- b1 compare 時 gates [0.789, 0.603, 0.652, 0.657] V，仍是 transition（case19 [0.865, 0.539, 0.608, 0.776]）。compare+5 ps 已經是 Z（case19 還在 transition）。底板在 compare 時 0.434/0.501 V（case19 0.437/0.503），held −0.773 LSB（−0.768），sense −0.018 LSB（+0.038）；compare+10 ps held +1.578（+0.805）。
- **conv8 b1 仍 None**：precompare held −0.783 LSB、sense +0.015 LSB（case19 +0.074），read 時 raw 0.190/0.587 V（case19 0.161/0.631），xy 0.680/0.234 V，離 rail 更遠。conv8 b1 自己的接受也一樣是 O→transition→Z（Z 5083.5，case19 5085.5）。
- conv8 的 b2 qdecode 變慢 2.6 ps，抵掉了一部分 driver 加倍的效果。這和 Guide 預先說的 qmid 負載懲罰一致。

## 判別量 2：conv7 b2（接受 O）
- 決策 1，margin 8.50 ps，raw stable 38.5 ps，都和 case19 相同。
- qmid2p 50% 42.56 ps（case19 39.88，**晚 2.68**），qdecode2p 50% 48.44 ps（44.88，**晚 3.56**）。read 時 decode 0.319 V（case19 0.697），release 時 0.473 V（0.813）。
- 接受 O：從 release 4447.0 起單一 O run 到 4497.5，沒有 bubble 或毛刺；距 b1 compare 6.5 ps，和 case19 相同。b1 compare 時 gates [0.899, 0.060, 0.107, 0.898]（case19 [0.900, 0.034, 0.072, 0.899]）仍是 O。
- 全部 b2 的 decode_stable_rail_delay 變成 None（case19 conv2/conv9 b2 是 45.39/45.64 ps），因為 qdecode 在 read 前都還沒到 rail。O 路徑這次沒有壞，但 qdecode 變慢是普遍現象。

## 判別量 3：conv7 b0（新的 48 ps read）
- 已解析成 0，sampled margin **1.75 ps**，raw stable 46.25 ps（48 ps 讀點只剩 1.75 ps）。precompare held −0.276 LSB、sense −0.811 LSB，和 case19 一樣。read 時 raw 0.085/0.795 V（case19 在 46 ps 讀是 0.127/0.712）。conv7 code 85→86（reg 和 case19 相同）。
- b0 margin（conv0..11，ps）：9.25, 8.93, 9.86, 9.54, 9.21, 10.14, 5.57, **1.75**, 10.43, 8.86, 7.79, 7.96。除了 conv7，其他每個都比 case19 多 2.00 ps。

## 判別量 4：MSB 37 ps 和 b5 建立
- MSB 12/12 解析，決策和 case19 相同。每個 margin 都剛好少 2.00 ps：4.00, 9.68, 10.61, 6.54, 8.96, 4.14, 4.82, 8.00, 4.18, 9.61, 10.54, 4.46；最小 **4.00 ps**（conv0）。raw stable 26.39–33.00 ps 沒變。
- MSB 接受命令：O 的 8 個從 release+0.25 ps 起是單一 O run，沒有毛刺；Z 的 4 個是 O 約 2 ps → transition → Z，距 b5 compare 至少 30.68 ps。所有 MSB qdecode 50% 在 33.45–40.35 ps，最晚 40.35 ps（conv0）晚於 release 39 ps，但接受命令的 run 沒有斷。
- b5：12 個決策和 margin 都和 case19 相同（最小 1.21 ps，conv4），接受參考距 b4 compare 10.68–23.43 ps，沒有變化。
- 全部 83 個已解析 bit 的最小 margin：1.21（conv4 b5）、1.68（conv8 b4）、1.75（conv7 b0）、2.25（conv7 b3）、2.75（conv7 b4）。

## Collector／parser
- `selected_parser.summary_psf_parse_count=1`，selected_required 144 節點，84 trial／72 boundary 全部跑完，沒有 KeyError。這個 count 只算自訂 summary；原 basic measurement 另外 parse 一次，所以不說整個 job 只 parse 一次。
- 72 邊界：observed 72/72，polarity_assessed 71，unassessable 1（conv8 b1→b0，prior 是 None），opposite_rail 0（只算可評估的 71 個），min prior |x−y| 0.451 V（case19 0.523）。
- provenance：manifest 2887bf07…，portable deck c587a30c…，parent manifest 29234008…，parent portable 13cb54f3…，parent summary bb7c5418…，authorization_sha256 3b4931d5…（user quote "Yes, 8 hours"，source SHA 26523d07…，window 05:37–13:37Z）。

## 資料
- OneDrive `outputs/PAM4_SAR7_B2_LOCAL_DRIVE_PILOT_20261117_RESULTS/`：原 bytes 的 `sar7_b2_local_drive_summary.json`（83d41a50…，3,397,472 B）、`measurements.json`（5e90957d…，80,349 B）、`run_status.json`（7ea7b368…，1,935 B）、`slurm-761688.out`（327e32e7…，241 B），加上 `SHA256SUMS_results.txt`。Olympus 端算的 SHA 和本機 `sha256sum -c` 逐一核對過，全部 OK。
- repo 只放 compact 去識別版（116 KB），每個 bit 有 decision、margin、raw delay、precompare held/sense、reference runs 和 50% 交越。
- Raw（tranResponse 48dfbe1d…，118,288,135 B；du 67 MB）**保留**：本包規定不清理，SAR7 修正時窗仍在進行，Codex 可能要稽核 conv8 b2 的 rail／底板軌跡。
- C2 761525 沒動（_7–_9 RUNNING，10–94 PENDING %3），2144 waiting_runs 沒動。SAR7 只用了 1 CPU。

## 結論
STOP。b2 局部 2 倍驅動讓 conv8 b2 接受 Z 提早 2.25 ps（6.32→4.07 ps 遲到），但還是跨過 b1 compare，conv8 b1 仍未解析，而且 sense 更小。同時 qbuffer 第二級加大讓所有 b2 的 qmid/qdecode 晚了 1.9–3.6 ps，這是 Guide 預先指出的負載懲罰。O 路徑沒有出現 bubble。依 Guide 的判別：前者只部分改善、不足以抹去遲到，後者變慢，所以「局部驅動 2 倍就夠」的假設被拒絕。MSB 捐 2 ps 給 b0 的部分有效：conv7 b0 已解析（margin 1.75 ps），MSB 最小 4.00 ps，b5 不受影響。依 Guide 本輪停止，不升 4 倍、不開 case21。
