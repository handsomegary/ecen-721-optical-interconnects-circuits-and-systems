# ECEN 721 #6｜TG-free gm-select AC pilot

## 先前 GLOBAL SS 的停止點

中心點 1×→4× 的 tap→gate 損失從約 −8.24 dB 降到 −5.8～−5.9 dB，但整體 Hdd 相對理想從 −9.75 dB 變成 −10.75 dB。極限碼 G00 的 tap→gate 也改善了約 2–3 dB，整體無 skew 的 Hdd 卻額外下降 24.03 dB。G00 的絕對 Hdc 幾乎不變（約 −29 dB），56 GHz 的相位等效延遲由 −6.42 ps 拉到 −8.48 ps，接近半個 56 GHz 週期（8.93 ps）。這支持兩腿相位造成差模向量互抵，並疊加分散式寄生負載。相同激勵加入正確方向的 4.464 ps skew 後，1×、4× 的 Hdd 相對理想仍低 10.07、12.76 dB。兩個當前候選仍超過 2 dB。 [SS pilot 量測摘要，ed77dc2](https://github.com/<owner>/ecen-721-optical-interconnects-circuits-and-systems/blob/ed77dc2a5f58b0b484e22fbf327ecfe214b6ab15/projects/pam4/campaigns/pnskew_lp_global_20261114/results/lp_global_ss_pilot.json)

舊加權摘要的 branch-null 判定看各欄分支是否衰到低於門檻。兩欄仍可各自有限、合成差模接近零，所以 branch-null 空白不能解決 notch 問題。這包附 `inspect_old_tg.py`，只讀原 1×／4×、理想的既有 AC 緊湊量測，列 45–80 GHz 的 Hdd/Hdc、兩分支和相對相位，並在零 skew 和注入 skew 下找最低點及頻帶內局部低谷。

## 新主線

- 每腿一條 16 節的 50 Ω 延遲線，末端保留一個 50 Ω 終端。選定 taps 直接通到實體差動輸入對，RF 路徑沒有 TG。比較 3、5、7 組永久接線 bank 的負載影響。
- 3 組的 P 端 taps 是 6、11、16。5 組加 8、14，7 組再加 10、12。N 端使用 22−P，提供鏡像的兩種校正方向。
- 每組維持原器件幾何、源端退化及原生尾偏壓切換。固定控制先量中心、兩個極限，以及相鄰 bank 分配 5/3 或 7/1 的近端點狀態。任一狀態總共八個尾電流單元導通。只有電流權重會變，各 bank 與主延遲線接法固定。Q15／SRF150、原 LP14 偏壓、Vb2 = 0.580 V 沿用。
- 幾組附加 bank 的閘極及關斷 bank 的汲極寄生都在網表。最小負載對照使用同一條延遲線、同一組啟用 bank 與同一權重，省略其他關斷 bank。這讓附加 bank 的總負載能量化。舊固定路徑 Q15 另作實測重現與中心／端點絕對對照。選配 launch 50 Ω 並聯負載放在後批，確認是否反映舊兩路負載。

SS 首輪先驗 3/5/7 bank 的中心與兩個極限。選可在兩邊達到 4.464 ps 的最小可用 bank 數，並檢查 ±4.464 ps 注入時 Hdd 相較同硬體零校正有改善。額外 bank 相對最小負載對照，56 GHz 損失先以 2 dB 作篩選。中心同時比較舊固定路徑的 56 GHz Hdd，若中心比舊主線低逾 2 dB、CM→DM 異常，或端點只靠深陷 Hdd 得到相位範圍，就先查 gate loading、bank drain 電流與絕對 Hdd。單／雙 bank 預算仍為 r3 增量 +10／+14 mW。所有比較報增益、相位與絕對值，單靠增加等效延遲不足以通過。

若 3/5/7 bank 都有明顯額外損失，先判斷是沿線閘極電容還是 CTLE 汲極總負載。前者可再提合併寄生電容的線節設計，後者可考慮減少 RF bank 或改變電流合成節點。只有 SS 試跑通過才提三角落與相鄰碼驗證。這幾種固定接線的 pilot 可以直接辨別負載代價。真正全表仍需覆蓋 ±4.464 ps、跨角落相鄰步階 0–0.50 ps 的正增量、切碼穩定時間，以及之後的 C0/C1/C2。原 GLOBAL MAP 全碼批次保持停跑。
