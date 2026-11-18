# ECEN 721 C2 · TT 有雜訊配對驗證（P3：最多三案並行）

這是原 C2 凍結包的 P3 資源版本；只將提交並行上限從六案改為三案，95 個 portable deck、seed、科學計分、配對 gate、C0/C1 依賴及統計方法完全不變。原包保留，不修改。

使用者已於 2026-11-16 16:58 指示「PAM4 deskew 先跑 C1，通過再跑 C2」，並於 18:43 直接指示「C1 通過就直接跑 C2，有關鍵結果再跟我說」。C1 五案現已完成且通過預先凍結條件，因此這一批 1002–1020 的條件授權已成立，不重問相同批准。這是獨立的 C2 長批次授權，排隊和完成可以跨越先前 SAR7 短修正的 23:15 時窗；不代表授權新 seed、新 PVT 或改電路。

只有 C1 五案完整、無 clipping 或計分異常，而且兩個方向補償後 primary 錯誤減少、secondary 錯誤沒有增加，才進 C2。執行端必須拿到驗證過的 C1 summary SHA 和對應的計分審查收據 SHA。收據確認時鐘、窗口與計分的完整性。runner 會重核 C1 運行、量測與原核准檔，並獨立重算 C1 的配對門檻。C2 用獨立 run root 綁定所有 deck SHA，既有 C1 證據及 C0 選擇檔，透過既有 Olympus 核准流程執行。

## 設計與計分

沿用 C1 所用的 TT 模型、固定刺激、共同相位 −1/8 UI、取樣和歷史長窗。每案每讀出端計分 2,032 符號，採已凍結的理想 7-bit ADC 和 17-tap FFE。每個 Spectre noise seed 跑零偏斜、P 晚 0／−60、N 晚 0／+60。各配對內使用同 seed。P 晚 −60 是固定端點補償診斷，正式 C0 訓練選出的是 0。N 晚 +60 是正式 C0 選出的補償碼。

1001 沿用通過門檻的 C1 五案，1002–1020 各有五個新案。共 100 個個案、95 個新 Spectre 執行。除了 `noiseseed`，C2 的 portable deck 與對應的 C1 案一樣。全數回報錯誤分子／分母、SER、clipping 和每 seed 配對差。用全部 20 個 seed 做描述性表格，用新跑的 19 個 seed 做精確單尾配對符號檢定，分開報 P/N、primary/secondary，並列出改善、同分和退化的 seed 數。以 seed 為統計單位。C1 seed 因作為放行條件，排除於檢定。這批證據只對固定刺激、TT、兩個 skew 端點和已測的控制策略成立。Gray 位錯率與參考實測 BER 的測試條件要在報告中分開列出。

## 資源和執行

每案 Spectre Classic `+mt=1`、1 CPU、6 GiB、solver timeout 4.5 小時、Slurm 5 小時。runner 固定 `MAX_PARALLEL=3`，提交唯一陣列 `--array=0-94%3`；不使用原包的 `%6`。C2 最多三案，加一個 SAR7 短案後仍為其他帳號工作保留兩個 CPU 的額度；同帳號總 QOS 上限仍是 6 CPU，提交前唯讀核對現有占用，不修改或取消其他工作。

用實際 C1 五案重新估算：solver 平均 6,024.75 秒、最大 6,092.11 秒，95 案約 158.99–160.76 CPU 小時；三路理想排程約 53 小時，32 波使用最大 solver 時間約 54.15 小時，另加收集與排隊。實際 Slurm 最大約 102 分鐘／案；每案 child peak RSS 不超過 285,240 KiB，仍保留原 6 GiB 配置。新 raw 最大估值 13,846,098,950 bytes（12.895 GiB），加現有 C1 和 metadata／logs；提交前確認足夠配額。這份 runner 保留 raw，沒有自動刪除。遇到解析錯誤先從完成的原波形以 `collect-only` 量測；不要為收集重跑 solver。未收齊時不輸出完成摘要。

使用已核對的原 C1 套件，在同一個 C0/C1 歷史環境下執行。審查收據是獨立 JSON，由本機 handoff 提供 SHA。
C1 通過摘要的原檔 SHA256 為 `ec30d9d95c29e3dcfb3cede5f0b83e48ae3e2354011a8fd841f1b8d6f4549fc9`。獨立審查收據在本機 `work/ecen721_handoff_wake/messages/c1_scoring_review_20261116.json`，SHA256 `f3e983d07da7489348999ea2c4836f705dfd179477194ef0eb4a8d39882a59cf`；此收據不在 ZIP 裡，由本機 handoff 一併傳到 Olympus 並設定 review 路徑。收據嚴格只有下列五個欄位，不添加 authorization_basis；使用者授權原話留在 handoff／本機執行紀錄。原 summary／五案 evidence／C1 approval／C0 selection pins 都由 runner 再核對，不能以本機格式化副本替代來源 byte SHA。

C1 的 primary 配對錯誤分別減少 125／278，secondary 減少 173／224，clipping 全為 0。secondary 絕對 SER 34–45% 不是參考論文等級；其 confusion matrix 也含非相鄰錯誤，不重複「全部相鄰」的舊敘述。本批只驗證凍結 metric 的多 seed 配對方向，不重新訓練 FFE、不換窗口，不將單 seed 工程 gate 當作統計顯著性。

格式為：

```json
{
  "schema": "pam4_c1_scoring_review_v1",
  "c1_summary_sha256": "<full C1 summary SHA256>",
  "reviewer": "<reviewer>",
  "scoring_review": "pass",
  "notes": "<clock, frozen scoring window and anomaly review>"
}
```

確認新套件 ZIP sidecar 和 `SHA256SUMS.txt`，執行 `verify` 與 `unittest`。本機 `verify` 只生成 portable SHA 清單。請以現有 run root 和環境變數填入以下命令。`PAM4_C1_ROOT` 指向包含 C1 個案和 `c1_noise_smoke_summary.json` 的目錄，`PAM4_C1_APPROVAL` 指向原案的核准檔。`PAM4_C2_ROOT` 是 `~/ecen720_28nm/runs` 下的新目錄。核准步驟沿用執行端已授權的流程。核准前可在 Olympus 比對 `verify` 的完整 95 案 SHA。

```bash
export PAM4_C2_PACKAGE='/absolute/path/to/PAM4_C2_TT_PAIRED_P3_20261116'
export PAM4_C2_C1_SUMMARY_SHA='ec30d9d95c29e3dcfb3cede5f0b83e48ae3e2354011a8fd841f1b8d6f4549fc9'
export PAM4_C2_REVIEW='/absolute/path/to/c1_scoring_review_20261116.json'
export PAM4_C2_REVIEW_SHA='f3e983d07da7489348999ea2c4836f705dfd179477194ef0eb4a8d39882a59cf'
cd "$PAM4_C2_PACKAGE"
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B c2_run.py verify
/usr/bin/python3.11 -B -m unittest discover -v

c2=(/usr/bin/python3.11 -B "$PAM4_C2_PACKAGE/c2_run.py")
args=(--c0-root "$PAM4_C0_FORMAL_ROOT" --c1-root "$PAM4_C1_ROOT" --c1-approval "$PAM4_C1_APPROVAL"
      --root "$PAM4_C2_ROOT" --approval "$PAM4_C2_ROOT/approval_c2.json"
      --c1-summary-sha "$PAM4_C2_C1_SUMMARY_SHA" --review "$PAM4_C2_REVIEW"
      --review-sha "$PAM4_C2_REVIEW_SHA")
"${c2[@]}" approval-template "${args[@]}"
# Recheck the bound root, C1 evidence, review SHA and all95deck hashes.
# Use the quoted conditional user authorization via the normal execution-side process;
# change only approved=false to true, with no extra approval fields.
"${c2[@]}" submit "${args[@]}" --model-root "$PAM4_PDK_ROOT"
"${c2[@]}" summarize "${args[@]}"
```

提交會保留 `c2_submission_intent.json` 並在 Slurm 接受後記錄 `c2_submission.json`。若只留下 intent，先查 Slurm 與本機提交記錄，確認是否有 job，勿直接重送。需要補收時用同一組參數呼叫 `collect-only --index <index>`。C2 阻擋既有證據和 approval 不符的提交，每個 task 也會在展開網表前重核。結果回本機 outbox。套件、deck、私有模型和波形只留在批准的 OneDrive／Olympus 位置。
