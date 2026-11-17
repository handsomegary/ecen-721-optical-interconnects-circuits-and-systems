Stage: SAR7 1.75GS/s refpath2 單案 sar7_17_tt_175gs_refpath2（新8小時委派首案）
Status: done
Decision: STOP — 參考路徑協同2×明顯變差：565ps registered 8/12錯、Σ58、max32 LSB；7/84 bit未解析（含4個MSB），未達任何gate
Summary:
- 處理 inbox 20261116T2355_sar7_refpath2_new8h_pilot.md；ZIP SHA d9b981c774c3f86c26713c5dd9dc5147229b270cdfeb0b031a6501ab8e34138d 相符；manifest a2d8b1d1…31c0 6/6 OK（SHA256SUMS為CRLF，以去CR串流核對，未改檔）；verify rc0；unittest 10/10；approval只改approved=true；stage 05:58:05Z rc0（staged deck 8174400b14618fc5469f9c66ed08d2a32bfa55d77f390c9ec848e4bc75151eb3，portable e113b079ce0b9a29eaeeeb5676232478c58a3a316205526bc48ca993cd352dbd）；對761549 deck diff：126個instance換cell＋4個local subckt（SAR_REFTG2/SAR_OAI21_RP2/SAR_NOR3_RP2/SAR_NDINV4），與宣告一致。
- Job 761632：sbatch accepted，SubmitTime epoch 1794895102 = 2026-11-17T05:58:22Z（窗內）；COMPLETED 0:0，elapsed 8:52（Slurm上限12min），solver 488.99 s（上限540 s，餘裕僅51 s），raw 118.3 MB（估120–180）。並行：C2 761525 三路未動，SAR7只1CPU。
- 逐碼（expected | 新 cmp / reg565 | 761549 cmp / reg565）：64|—/96|64/64；0|0/0|0/0；127|127/127|127/127；31|—/48|31/31；96|95/95|95/95；63|—/63|64/64；65|—/64|64/64；85|—/88|—/88；42|—/44|—/44；1|0/0|0/0；126|127/127|127/127；64|—/64|64/64。
- 讀點：565 cmp 5/12可讀（3錯Σ3 max1），reg 12/12可讀、8錯、Σ58、max32（761549：cmp 10/12、5錯；reg 7錯Σ10 max3）。563與565相同；554 reg 8錯Σ62 max33；557 reg 4/12可讀、2錯max1、comparator與registered不一致。physical window 565有效；CM：active552 −3.32/−3.19 mV（trigger −3.45/−3.09）、post565 −9.50/+7.81 mV，|ΔCM|≤10 mV仍過（565正向由+5.40升到+7.81 mV）。
- 未解析（decision None）7/84：(0,6)(3,5)(5,6)(6,6)(7,3)(8,1)(11,6)；761549為2/84。conv0、conv3的MSB或b5未解析，造成+32/+17 LSB大錯（64→96、31→48）。原先兩個問題碼85→88、42→44完全沒變。
- 時序 proxy（新 vs 761549，84 trial）：raw q 穩定到rail延遲中位數32.98 ps（34.95）、範圍26.82–42.46 ps；decode穩定中位數46.98 ps（40.37），且只有18/84在原讀點到rail（28/84）→ 一級qbuffer 1→4負載如預期增加延遲約+6.6 ps。sampled margin中位數8.64 ps（7.32），最小0.18 ps（不變）。例：conv0 b6 在761549時q6p 32.7 ps rise、qmid 39.2 ps；新案在原短視窗內沒有任何crossing，延伸視窗q6p 50.1 ps rise、qmid 60.9 ps、qdecode 66.7 ps，比原解析晚約17 ps，原讀點仍未解析。
- 接受reference command margin（下一compare前的連續穩定）：45/84有數值，最小2.18 ps（conv8 b3），無負值；39/84為None（沒有可量的穩定區段或在視窗邊界外）。conv8b4→b3 accepted Z margin 7.43 ps，跟原本7.43 ps相同。conv8b2 wanted O 的margin為None（reg bit=1）。
- Reference源峰值電流：最大454.5 µA（761549：217.1 µA），約2.1×，與TG加倍相符。max sample error 1.647 LSB（1.677），max resolve delay 42.46 ps（43.18）。
- 判讀（唯讀，未改Codex程式）：TG2降低channel R的效果，沒有轉成較早的bottom/held/sense。更明顯的是第一次比較（MSB）與部分中段bit的比較器決策延遲／未解析增加，加上峰值電流加倍、TG feedthrough／kickback增大，正符合Guide列出的失敗模式（「負載補償失敗」）。兩個原問題碼沒有改善，因此不支持「reference路徑動態建立是主因」這個假設。依指示不自動開下一個倍率或搬clock。
- SHA：summary 06de75d36d492b3e7d166e124094e73aa8a94a8be2e497d33f01b354b334b611；measurements 0616ba355310ac6d4b4d8e41fc4835fc4d768f15c6eaffd93bc90d4e53f1fb6b；tranResponse.tran.tran 754f1351502ce417db2217cea740340c7ef21fd6fecc46bb31c075f8750de5e5；authorization ec86523474c7fb6a20bb5e2d806f31b12bed6d177060672e67ff0b08371a9fd8。
- Raw 全部保留（67 MB case dir），依 sar7_raw_retire_after_window_20261117 等 07:37 窗結束後再處理。
Run paths: ~/ecen720_28nm/runs/pam4_sar7_refpath2_pilot_20261116.X5DzpR/sar7_refpath2_summary.json；case sar7_17_tt_175gs_refpath2/；slurm-761632.out；repo projects/pam4/campaigns/sar7_refpath2_pilot_20261116/results/
Commit: 見本機state（handoff + results）
Needs user decision: no
