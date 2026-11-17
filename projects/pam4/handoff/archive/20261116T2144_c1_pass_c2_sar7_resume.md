Stage: C1 計分核對通過；C2 TT 配對批次及 SAR7 單案 driver 修正
ZIP: ECEN721_PAM4_C2_SAR7_RESUME_20261116.zip（OneDrive ECEN 720/outputs）
SHA256: c8441267e9dde906fd903916a4a00cb7804b8433905fd440acf5b4e8cd5cc7ee
Guide: OneDrive ECEN 720/outputs/PAM4_C2_SAR7_RESUME_20261116/HANDOFF_zh_TW.md
Recommended: 先送唯一 SAR7 strong-decode pilot，再核對及提交 C2 seeds1002–1020、95案、array0-94%3；提交後即回 job ID，由既有排程續看
Resources: SAR7 1CPU/6GiB/12min、solver540s、100–180MB raw；C2最多3並行、每案1CPU/6GiB/5h、solver4.5h，合計約159–161CPUh／53–54h加排隊、12.895GiB新raw；account總QOS6CPU
Commit allowed: handoff + results
Needs user decision: no

# C1 核對後的 C2 與 SAR7 單案續作

先跑一個 SAR7 實體短案並取得 job ID；同輪完成 C2 核對及提交，回報兩個 submission receipt。兩者根據已存在的使用者授權。SAR7 新案／提交截止為 2026-11-16 23:15 Chicago（2026-11-17 05:15 UTC）；截止前已提交的 job 可完成並收尾。C2 是獨立的條件長批次授權，不因 SAR7 截止而取消。

## 檔案與核對

先在外層解壓目錄執行 `python -B verify_bundle.py` 和 `sha256sum -c SHA256SUMS.txt`；再解開兩個子 ZIP，各自跑 manifest、verify 與 unittest。每個子包有自己的 `HANDOFF_zh_TW.md`、approval-template 和精確 deck 綁定；不共用 approval。審查收據 `c1_scoring_review_20261116.json` SHA256 `f3e983d07da7489348999ea2c4836f705dfd179477194ef0eb4a8d39882a59cf` 由此包一併上傳，C2 設定其實際 Olympus 路徑。

| 子包 | ZIP SHA256 | Manifest SHA256 |
| --- | --- | --- |
| `ECEN721_PAM4_C2_TT_PAIRED_P3_20261116.zip` | `8d8d429a4662fb9442ab056911f73171f365dd55565a3871c2f854155905e9b0` | `603f03f0b3041ab5b160cb7adc973c507aa0df4d640a278d09ca9c897e6825da` |
| `ECEN721_PAM4_SAR7_STRONG_DECODE_PILOT_20261116.zip` | `32603df47629cf0432218291e4c6802de1135013d142738ce1fb0db39b423617` | `43b93d73f5f5e08fc350a6b9a12ae6c54ec3c5eac280190be93a38b3fe4b8bd8` |

保留原 C1／native decode 包及所有 raw。新 ZIP、deck、模型與 PSF 留 OneDrive／Olympus；repo 只允許手工核對後的交接、無 deck 程式及去識別摘要。不得把此內含子 ZIP 的外層包或批次 ZIP 放入 repo。

## C1 工程 gate 已通過；C2 授權已成立

使用者 18:43 原話保存在 `20261116T1902_sar7_native_decode_pilot.md`，並記於當日本機 activity：「繼續跟 Claude 在背景跑，確認 SAR7 隔離案有送上 Olympus，拿到結果就接著修。C1 通過就直接跑 C2，有關鍵結果再跟我說。」16:58 另有「PAM4 deskew 先跑 C1，通過再跑 C2」。現在五案完整，primary 配對錯誤 −125／−278、secondary −173／−224、clipping 全零，滿足原凍結工程 gate。2118 redelivery 內的「C2 尚未授權」是過時判讀；以較早的使用者直接條件授權與現已滿足的 gate 接續，不需重新批准同一批。

C1 原 summary SHA 是 `ec30d9d95c29e3dcfb3cede5f0b83e48ae3e2354011a8fd841f1b8d6f4549fc9`。本機 checkout 的格式化副本 byte SHA 不同；按原 JSON 鍵序、indent=2 加結尾 LF 可精確重現原 SHA。C2 必須核對 Olympus 原檔 bytes、五案 evidence、原 approval 與 selection pins，不能拿重排副本取代來源。獨立收據核對計分契約及 summary，沒有聲稱本機重讀 Olympus raw。

更正 C1 的文字初判：secondary confusion matrix 包含非相鄰錯誤，五案各有 52／67／43／84／38；Gray 計數與 confusion 相符。不能再寫全部是相鄰錯誤。secondary 絕對 SER 34–45% 仍偏高，這批是凍結 metric 的配對方向驗證，並不代表接近參考論文的絕對性能。C2 不改 FFE／窗口／ADC／控制碼、不重訓。

C2 只跑 seed 1002–1020、每 seed 五案，共 95 個新 solver；seed 1001 只列描述，排除推論。使用 P3 子包，陣列必須是 `0-94%3`，每案 1 CPU／6 GiB／Slurm 5 h／solver 4.5 h。依 C1 實測估約 159–161 CPU h、三路約 53–54 h 加排隊與收集、新 raw 約 12.895 GiB。提交前讀取 account 現有占用及配額；所有專案合計不超過 QOS 6 CPU，不改動其他工作。至少保留新 raw 加現有 C1、logs 的空間；空間不足只回報技術阻礙，不刪任何 raw。

沿用 `wrappers/env_c1.sh` 的 C0／C1 根目錄與原 approval，新增獨立 C2 run root。按子包 Guide 傳原 C1 summary SHA、review 路徑／SHA，核對嚴格 approval-template 後只改 approved=false→true，依已存在的條件授權提交。不要往嚴格 approval／review schema 填額外欄位。若已有 `c2_submission_intent.json` 而無 receipt，先查 queue／accounting 再處理，禁止盲目重送。95 案未完成前保留 running 狀態，不產生假完成 summary。

提交後先回本機 outbox：實際 job/array ID、run root、submission receipt SHA、前三案狀態及配額。把後續監看狀態寫入現有本機 task state，交給既有排程續看；headless 輪次不應為等 53 小時而占住 inbox。每次輪次結束前照原規則重讀 inbox，SAR7 回報可以先處理。只有 solver 已完成但收集受阻才 collect-only；不以新 solver 補收集。

## SAR7：只測 driver 補強這一案

761433 的實體 native decode 仍有兩個未解析 bit、comparator max 6 LSB，且 b0 解除後 register 需約 8–10 ps；554／557 ps 讀得太早。理想 gate 對照 761426 已使 registered max 32→1，支持控制路徑有實質貢獻。新的單案補強 OAI21 串聯路徑及 NOR3 P stack、decoder 專用互補 inverter，正負鏡像；原 reference TG、CDAC、全域 register inverter 保持原樣。詳見子包精確 CDF 複本數和 stage diff。

非均勻 wait b6→b0 為 42／45／25／19／15／8／6 ps，比較窗 39／44／40／40／38／41／54 ps；b0 read 552、trial release 554、正式 registered read 565 ps。另列事先固定的 563 與舊 554／557 ps 診斷，不事後挑讀點。Comparator clocks 保持至 568、conv 558、reset 566、track 569、period 571.428571 ps。讀出 rail 在 reset 開始前的餘裕很小，必須從真實波形確認，不可由時序表直接宣稱成功。

文獻對照：Bheemisetti 等的 [IEEE JSSC，DOI10.1109/JSSC.2024.3449115](https://doi.org/10.1109/JSSC.2024.3449115) 採 3 nm DTFB 和由 CDAC 底板切換觸發的非同步 ready；我們是 28 nm、0.9 V、100 mVppd、固定時槽 StrongARM+CML，不能只因同為 1.75 GS/s 就套用其性能。Ramkaj 等的 [28 nm 1.25-GS/s JSSC，DOI10.1109/JSSC.2018.2822823](https://doi.org/10.1109/JSSC.2018.2822823) 以平行 SAR logic 和 USPC 減少臨界路徑負擔，並採 break-before-make；它使用 1 V 與 rail references，與我們的窄參考跨度不同，不是此 decoder 倍率可直接換算速度的證明。Um 的 [split-CDAC calibration，DOI10.1109/ASSCC.2011.6123608](https://doi.org/10.1109/ASSCC.2011.6123608) 支持隔離 bridge／LSB 權重與 offset 的方法；目前跨速度及理想 gate 對照較支持動態建立，故這一案不再調靜態權重。

要區分的結果是：loaded gate edge 加速後，底板／held 是否同步提早、再生期間差動符號是否仍翻轉、84 bit 是否解析，以及 register 是否於 565 ps 到 rail。若 gate 變快而 held 仍落後，才支持 reference-TG／類比 RC 成為下一限制；若 held 已穩而判決仍慢，則改查 comparator／q 負載與再生窗。以最晚 read plateau 推估的約 647 ps 是保守串行規劃，包含 kickback 且忽略 DAC／再生重疊，不是物理速度下限。Gate 50% overlap 仍只當 proxy，供電峰值包含充電，不能單靠它定導通或短路。

單案 1 CPU／6 GiB／Slurm 12 min／solver 540 s，估 3–7 min、100–180 MB raw；先驗 SHA／manifest／verify／unittest／stage diff，再於截止前提交唯一 case。正式 gate：84 bit 全解析、12 筆 comparator／registered 全可讀且一致、max≤1 LSB、wrong≤6/12、|ΔCM|≤10 mV（active 最後比較讀點 552 ps 與 post-conv 數位讀點 565 ps 皆須符合），避免關閉 conv 後的恢復掩蓋比較期間漂移；logic_smoke 零錯條件另報。回報 565 主讀點、全部診斷、84 trials、gate／bottom／held 與 sensep/sensen、x/y/q，含 compare+15／+30 ps 快照、reference current、summary／measurements／tran SHA 與資源。若已有 raw，解析問題只 collect-only。完成後回 Codex；不自行加第二案或 TG2x sweep。

此案即使 screen 通過，也只是一組固定 12 碼的 TT 短測；transfer／頻譜及 112 GS/s 實體整合仍需獨立證據，不宣稱已達論文驗證程度。
