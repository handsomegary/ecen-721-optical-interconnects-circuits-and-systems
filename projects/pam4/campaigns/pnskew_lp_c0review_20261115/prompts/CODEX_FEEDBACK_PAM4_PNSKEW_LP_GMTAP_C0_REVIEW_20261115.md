【ECEN 721 #6 C0 審查包 b0a86d6e：五份 deck 在 Olympus 上逐位元重現，deck 之間的差異也正確。但這包目前沒辦法跑：
(1) 實檔重播做不到，也沒有必要。83–86 的 raw 已在 SWITCH64 結案 commit 6c47a53 後依規則退役；而且 collect-only 已經用同一份實檔（完整 SHA 核對）算出現有量測，再算一次是同一套程式讀同一份檔案。
(2) 包裡沒有 runner、sbatch 與 approval 綁定，score_existing 要求的 run_status 無法產生。
所以沒有送任何模擬】

一、核對（Olympus，沒有啟動 Spectre）
- ZIP SHA b0a86d6e…，SHA256SUMS 通過。
- 父包 94aff417 的 SHA256SUMS 是 55d13973…，和 SWITCH_MANIFEST_SHA 相符。
- r5：用原 COMP 包 pnskew_comp_20261113_r0 的 r5_original（frozen.json 4cda4c9e…，相符）。94aff417 包裡的 r5_original 只有 quiet.scs，沒有 frozen.json。
- 在乾淨目錄執行 `c0_review.py --render` 重新產生，五份 deck 和包內的逐位元相同。c0_review_plan.json 的內容差異只在格式。
- deck 之間的差異：
  - 00→01、00→03：只有 PAM4Vp／PAM4Vm 的 PWL 時間平移（±4.464 ps 的一半各一邊）；
  - 01→02、03→04：只有 GMSK 致能電壓，也就是碼 0 換成 ∓60；
  - 其餘都相同。
- deck 設定：TT 25 °C／0.9 V；`tranResponse tran stop=14n maxstep=200f errpreset=conservative strobeperiod=UI/8 strobeoutput=strobeonly`；`__pdk_root__` 出現 1 次。

二、實檔重播
- replay_switch64_actual.py 需要補跑 root 的 84、86 PSF（live_raw）。這兩份已在 commit 6c47a53 後退役，收據是 RAW_RETIRED_83_86.txt。這也是 SWITCH64_COMPLETE 回饋第五節寫明的處置，沒有保留副本。
- 這一步的目的（用 Olympus 實檔驗證收集程式），在 94aff417 的 collect-only 時已經做過了：
  - recover_switch64_endpoint 核對了 task ID 757710／757730、757597／757729，以及完整 PSF SHA fea911b3…／10c96868…；
  - 它重讀 END、解析並寫出 measurements，合併 summary 判 ready_to_design_C0＝true。
  重播只是同一套程式對同一份檔案再算一次。照使用者「不要為小差異一直修」的原則，建議拿掉這個前置條件。
- C0 新增的 r5 次取樣與計分，本來就要用第一案的實際 PSF 核對，這個保留。

三、要能跑，請補
1. runner：`--mode stage`／`--mode run`，比照 gm_switch64：
   - stage 時替換 `__pdk_root__`；
   - 經 olympus_common.run_classic 寫出 run_status，含 spectre_log_sha256 與 raw_inventory。
2. sbatch：1 CPU、6 GiB，walltime 建議 60 分鐘，因為暫估 20–45 分鐘、上限要留空間。
3. approval_TEMPLATE 與綁定：plan SHA、新 SHA256SUMS、5 個 case_id、stage 名稱。
4. 收集：tranResponse PSF 估 65–115 MiB，在 512 MiB 內；串流讀取直接沿用。
5. 請用 SWITCH64 這次的實際 run_status 格式當 fixture，測一次 run→score→summary。SWITCH64 的四次來回都出在收集與核對程式對實檔的假設，不是電路。

四、範圍
- 這五案是固定端點碼加歷史相位的電路診斷，你已經寫明，不是正式 C0。
- 正式 C0 要用獨立訓練決定選碼與共同相位。如果那是必要的，請放進同一包（訓練案和 payload 案一起），不要再多一輪。
- 如果你判斷先跑五案診斷就足以決定下一步，也可以先只交五案的可執行版。
- 資源上沒問題：五案約 2–4 CPU-h，raw <600 MiB，家目錄約 25 GB 可用。C0 仍然不急。

五、Olympus 位置
- 審查目錄 pnskew_lp_c0review_20261115.*（只有解壓與重新產生的 deck，沒有模擬）。
