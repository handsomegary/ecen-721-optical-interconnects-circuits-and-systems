【ECEN 721 Project #6（224 Gb/s PAM4 ADC-based RX）：PN skew 影響掃描 ＋ AFE PVT corner — 請設計，Claude 在 Olympus 執行】

一、課程規格（ECEN 721 Final Project #6 原文要點）
224 Gb/s PAM4 ADC-based receiver front-end；AFE 在 56 GHz Nyquist 最多 20 dB peaking；7b、112 GS/s time-interleaved ADC；需包含補償 ±0.5 UI 差動 PN skew 的技術（112 GBaud 下 ±4.464 ps）。題目未規定功耗、雜訊、full-scale、BER 門檻，請不要捏造合格門檻，判準須在模擬前預先寫定。

二、目前狀態（repo：github.com/<owner>/ecen-721-optical-interconnects-circuits-and-systems，projects/pam4；歷史全部已在 Olympus 重現）
- AFE：兩級 NMOS 電阻負載 CTLE（選定 focus55／Cadence r3）；r2 原生基準 56 GHz 相對 1 kHz 提升：TT/25°C/0.9 V 21.83 dB、SS/85°C/0.81 V 16.64 dB、FF/−40°C/0.99 V 24.78 dB（只有這三點，r3 版尚未做 corner）。響應峰值約 22 GHz，不在 56 GHz。
- 取樣：8 路 × 14 GHz 實體 MOS TG（相位差 8.928571 ps），主取樣端 → CML buffer → 次取樣端；量化與 FFE 為理想 7-bit 數值量化器 + 凍結 17-tap FFE。
- 測試條件：0.4 Vppd 發送、56 GHz 處 20 dB 的合成雙極點通道、理想時脈 1 ps 邊緣。已知問題：次取樣端加 transient noise 後錯誤偏高。
- PN skew：只做過早期 3 次「PN skew + 理想校正」診斷；沒有補償電路。之前另一份 prompt 已請你為補償電路做架構比較（AFE 前 P/N 可調延遲 vs P/N 分開取樣、時脈相位調整後數位相減等）；本 prompt 是其中「先量化影響」那一步，請和那份對齊，不要重複做兩次。

三、請設計（需要你判斷）
1. PN skew 影響掃描（model-first，先不加補償電路）
   - skew 的注入方式與位置（例如在通道後、AFE 輸入前對 P 或 N 單邊加理想延遲；或 P/N 各半），說明為什麼這代表題目的「差動 PN skew」。
   - 掃描點：至少 −0.5 … +0.5 UI 共 9 點（0、±0.125、±0.25、±0.375、±0.5 UI），若需要更密請說明。
   - 指標與預先宣告的判讀：差動增益與 CM→DM 轉換、56 GHz 頻響凹陷、取樣眼圖／margin、FFE 後 primary/secondary symbol error；有雜訊的結論用多 seed（建議沿用 20-seed 範圍法或你認為合適的 seed 數）。
   - 要回答的問題：在不補償時 skew 到多少開始明顯劣化、補償電路需要的範圍與解析度（殘餘 skew 要壓到多少 ps）、理想補償能恢復到什麼程度（可做一組「已知 skew＋理想反向延遲」對照）。
2. AFE PVT corner（以 r3 選定版本為準）
   - corner 組合（例如 TT/SS/FF/SF/FS × 溫度 × VDD ±10%），和要報的量：56 GHz 相對低頻提升、峰值頻率、DC 增益、功耗；再選少數 corner 做 transient＋FFE symbol error。
   - 模型：Olympus 上只有 VM 模型樹的私有複本（28nm 含 shrink wrapper），pdk_toplevel.scs 提供 tt 等 section；歷史 corner deck 使用 la5_foundry_corners.scs（ss/ff 等 section，內含 shrink 引用）。請確認你要的 corner section 在這套模型中存在，不要自行改模型或拿掉 shrink。
3. 交付給 Claude 的內容
   - 由現有 netlist／deck 產生器生成的 deck（只改 skew 注入、corner section/溫度/VDD 與 save；其餘電路、尺寸、刺激與分析設定不變，改動要能逐行 diff）。
   - runner／分析腳本（沿用原 analyzer 或說明新增部分），預先寫定的判讀規則，每個 case 的預估 Spectre 時間與記憶體。
   - SHA256 清單與離線測試。

四、Olympus 執行環境（Claude 負責提交）
- Spectre 23.1.0.722.isr15、SPECTRE_DEFAULTS=-E；QOS 每 job ≤ 6 CPU、≤ 12 h；使用者 home 剩約 36 GB。
- 已實測：23.1 classic Spectre 模式最多 1 thread（「limited to the maximum allowed number of 1 with Spectre mode」）；歷史 PAM4 雜訊 transient 每個約 70 分鐘。因此掃描以「多個 1-CPU job 平行」最有效率；若你認為需要 APS／Spectre X 加速，請明確提出並說明對結果的影響（歷史比對都是 classic）。
- 模型路徑：~/ecen720_28nm/tools/local_replay_migration_20261108/private_models/r7_vm_shrink（VM 原檔的逐位元複本；deck 只做可逆的 PDK 根目錄替換）。
- 規則：量測結果與輸入保留，原始波形分析完即刪，不下載；PDK／模型不上 GitHub；有雜訊結論用多 seed。

不自動調參、不放寬判準；本輪只做影響量化與 corner 補資料，不宣稱任何規格通過。

---
【Claude 2026-11-12 執行回饋（r1）】
- Olympus 前置全部通過：ZIP SHA 80b7fa1e…、verify_delivery（390 files／106 decks）、admission、skew 逐案 diff、TT/SS/FF model_preflight（tt/ss/ff macro sections 存在，四檔 SHA 相同，scale 0.9）。
- 首例與歷史一致：quiet_z000 ideal7bit+FFE primary 0/2032、secondary 2/2032；PVT TT CTLE +6.47994 dB、track +5.34158 dB、AFE 10.077 mW。其餘 104 案已送出（748418 PVT AC、748419 quiet+tone、748420 PVT transient、748421 noise）。
- 執行方式：原 *.sbatch 未改（SHA 核對），另加 wrapper 負責 source IC231、PATH 中 spectre 與 python3→/usr/bin/python3.11（計算節點預設 python3 是 3.6）、partition/qos/account。
- Bug：olympus_common.raw_in_use() 只攔 FileNotFoundError／ProcessLookupError。共用計算節點上，同 uid 但 /proc/<pid>/fd 不可讀的程序會丟 PermissionError，使 retire_case_raw 失敗、job 記為 FAILED（PVT AC 26 案中 5 案：tt_t85_v099、ss_tm40_v099、ss_t25_v090、ss_t85_v090、ss_t85_v099）。這 5 案的模擬與量測已完成（measurements.json／completion.json 都在），只有 raw 未刪（各約 2 MB）。建議下一版把 PermissionError 一併略過（或改以 lsof／fuser 判定）。本輪不改程式，campaign 結束後由 Claude 以同樣的量測核對條件手動刪除並留收據。
