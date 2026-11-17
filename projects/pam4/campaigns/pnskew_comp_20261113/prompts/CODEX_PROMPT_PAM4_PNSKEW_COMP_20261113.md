【ECEN 721 Project #6（224 Gb/s PAM4 ADC-based RX）：差動 PN skew 補償電路設計。請設計，Claude 在 Olympus 執行】

一、題目要求
題目要求「補償 ±0.5 UI 差動 PN skew 的技術」，112 GBaud 下為 ±4.464 ps。題目沒有規定補償後的殘餘量、BER、功耗或雜訊門檻。凡是新的數值判準，都請標成「自訂、待使用者批准」，並在模擬前寫定，不要當成課程規格。

二、已完成的影響量化（2026-11-12～13，Olympus Spectre 23.1 classic，106/106 案）
repo：github.com/<owner>/ecen-721-optical-interconnects-circuits-and-systems
完整結果：projects/pam4/campaigns/pnskew_pvt_20261112/results/RESULTS.md（含 skew_summary.json、pvt_summary.json）。這輪用的是你的 r1 套件；r2 只修了 raw_in_use。

1. 無雜訊 9 點掃描：r3 focus55 CTLE，r5 實體 8 路取樣，理想 7-bit 量化，凍結 17-tap FFE，每點 2,032 symbol。
   - 劣化對稱，都由 secondary 觸發。最後一個連續未觸發的點是 ±0.25 UI（±2.23 ps），第一個觸發點是 ±0.375 UI（±3.35 ps）。
   - secondary 錯誤數依序為：0 → 2；±0.125 → 4；±0.25 → 4/5；±0.375 → 25/26；±0.5 → 126。primary 只在 ±0.5 UI 出現 5/6 個錯誤。
   - 零 skew 時 held sample 相鄰電平的 p05−p95 間距已經是負值（primary 約 −51 mV，secondary 約 −24 mV），FFE 前眼圖沒張開，所以「間距縮小 %」無法評估，判定實際只用 SER。
2. 20 組配對雜訊種子（只測 0 與 ±0.5 UI）：
   - 零 skew：primary 0 錯；secondary 161–236 錯。這是先前就有的次取樣端雜訊問題，與 skew 無關，請分開處理，不要算進 skew 效應。
   - ±0.5 UI：primary 21–46 錯，配對 ΔSER +1.6 pp；secondary 326–419 錯，ΔSER +8.5 pp。20/20 seed 都標為劣化。
3. 56 GHz 模態傳遞（含合成 channel 與原生負載）：
   - ±0.5 UI 時 Hdd 下降 3.006 dB，匹配延遲模型為 −3.010 dB。
   - 新增 CM→DM 轉換為 1.391 × |Hdd(0)|，模型為 1.414。
   - DM 的半振幅線性度在 5% 內；AFE 輸出 CM 差 17%，超出診斷門檻，原量測保留。
4. 由以上推得的補償需求：
   - 差動範圍 ±4.464 ps；兩腿互補時每腿 ±2.232 ps。
   - 殘餘 skew 草案 0.25 ps。以 10% CM→DM 預算計，模型值為 0.284 ps。這兩個都是自訂值，仍待批准。
   - 理想均勻碼的 LSB ≤ 0.5 ps 只是必要條件。
   - 1.116 ps 的格點量不出 0.25 ps 等級的容差。
   - 理想反向延遲在代數上就是零 skew 的結果，即上限。
5. r3 AFE PVT（27 個 AC corner，TT/SS/FF × −40/25/85 °C × 0.81/0.9/0.99 V）：
   - 56 GHz 相對 1 kHz 只有 2.46–8.15 dB（TT 6.48 dB）；峰值在 22.9–25.1 GHz。
   - 功耗 5.85–15.35 mW；最小 rail 餘裕 90 mV（SS/−40 °C）。
   - 凍結 TT 權重的 FFE 在 SS/85 °C/0.81 V 下 primary SER 11%；FF/−40 °C/0.99 V 下 primary 7 錯、secondary 191 錯。
   - 這些代表補償電路本身也必須跨 PVT 保持範圍與解析度。FFE 的 per-corner 適應不屬於本 prompt，但補償電路不得依賴 TT 才成立的條件。

三、請設計（需要你判斷）
1. 架構定案
   延續 PN_SKEW_ARCHITECTURE_RESEARCH_20261111 的兩個方向，用上面的實測數據做取捨，不要重做那份研究：
   - (A) 第一個 P/N 混合點之前放兩條獨立可調的 analog delay；
   - (B) P/N 分開 track/sample，調相對取樣相位，量化後在數位域對齊相減。
   請說明：
   - 56 GHz 下增加的負載、頻寬與 Hdd 損失，以及功耗。
   - CM→DM 與殘餘 skew 的關係（以實測的 1.39 為基準）。
   - 要放在現有電路的哪一個節點，對 r3 CTLE 和 r5 取樣鏈各要改什麼。
   - 範圍 ±4.464 ps 與 LSB 如何同時跨 27 個 PVT corner 達成。
   - 是否需要範圍與步階兩級（粗調加細調）。
   若選 B，請說明它與目前「理想 7-bit 量化加 FFE」模型的接口，以及實體 ADC 尚未完成的限制。
2. skew 偵測與校正
   補償碼要怎麼決定：前景校正還是背景校正、用什麼可觀測量（例如 56 GHz CM 成分、FFE 誤差相關、P/N 交叉相關）、可辨識性與收斂、需要的訓練長度。
   - 不可使用模擬器內部才知道的真實 skew 值來設碼（理想對照組除外，並要明確標示）。
   - 和次取樣端既有的雜訊問題要能分開判讀。
3. 電晶體級設計（28nm，沿用 VM 模型樹的私有複本，含 shrink wrapper）
   - delay cell 或相位調整電路的拓撲、尺寸、碼表與控制方式。
   - 先做 standalone characterization：每個碼的 delay 與 PVT 變化（DNL/INL）、56 GHz 插入損失、加入的雜訊、功耗。
   - 再整合進 r3 AFE 和 r5 取樣鏈。電路改動要能從現有 netlist／deck 產生器逐行 diff。
4. Olympus 驗證計畫（判讀規則須在模擬前寫定）
   a. standalone：每碼 delay × 27 PVT corner，以及頻響、雜訊、功耗。
   b. 整合後無雜訊：
      - 對 9 個 skew 點各施加「校正後的碼」，與第二節的未補償結果、理想反向延遲上限並列。
      - 在 ±0.25～±0.375 UI 間加局部細掃。
      - 加一組「刻意殘餘 skew」掃描（例如 0、±0.25、±0.5、±1 ps）來量測殘餘容差。
   c. 雜訊：0 與 ±0.5 UI，各 20 組配對 seed（1001–1020，與上輪相同），補償前後同 seed 配對比較。
   d. PVT：至少 SS/85/0.81 與 FF/−40/0.99，各在 ±0.5 UI 下驗證補償範圍與殘餘量。FFE 是否重新適應請明確標示；若用凍結 TT 權重，結果不能解讀為補償失效。
   e. 每個案例的預估時間與記憶體。23.1 classic 只能用 1 thread；上輪實測 quiet 約 45–90 分鐘、noise 約 55–110 分鐘，每案 1 CPU / 6 GiB / 3 h 足夠。若要 APS 或 Spectre X，請明確提出並說明對比較的影響（上輪全部是 classic）。
5. 交付給 Claude
   - 產生器、runner、摘要工具、預先寫定的判讀規則（新門檻標成「待批准」）、SHA256 清單與離線測試。
   - 沿用 r2 套件的 admission、retire 與 wrapper 架構，含 python3→python3.11、source IC231、partition/qos/account 由 wrapper 提供。

四、請一併修正（上輪執行發現）
- summarize_skew.py：`--run-root` 給相對路徑時，native/readback_guard.owned_file() 會把 path.absolute() 和相對的 root 比較，一路走到 `/`，69 案全被判為 "Keeper escaped case root"。請在入口把 root 轉成絕對路徑（resolve），並加一個用相對路徑呼叫的測試。summarize_pvt.py 不受影響。
- r1 有 5 個 PVT AC 案的 raw 因 PermissionError 未刪，已由 Claude 手動核對後刪除並留收據。r2 的修正請保留在新套件。

五、Olympus 環境與規則
- Spectre 23.1.0.722.isr15，SPECTRE_DEFAULTS=-E；QOS 每 job ≤ 6 CPU、≤ 12 h；home 尚有約 36 GB。
- 模型：~/ecen720_28nm/tools/local_replay_migration_20261108/private_models/r7_vm_shrink。deck 只做可逆的 PDK 根目錄替換，不改模型，不拿掉 shrink。
- 量測與輸入保留；原始波形分析完即刪，不下載。PDK／模型不上 GitHub。有雜訊的結論用多 seed。

不自動調參、不放寬判準。本輪交付設計與驗證計畫，不宣稱課程規格通過；補償的最終殘餘門檻由使用者批准。
