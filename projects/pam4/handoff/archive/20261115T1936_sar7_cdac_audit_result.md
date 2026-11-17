Stage: SAR7 retained-raw CDAC 權重及 b0 readout 查核
Status: done
Decision: STOP — 兩案 CDAC 有效權重都可辨識且線性模型留一誤差 <1 LSB，錯碼主因是靜態滿刻度不足（107.2／119.2 LSB 對 127）與 offset；b0=0 路徑在 end_s 後 3.5 ps 內（conv 下降前）可達門檻，屬讀取時刻過早。
Summary: 只讀 760091（直接感測）與 760132（理想隔離）保留 PSF；0 個新模擬。Audit job 760174 COMPLETED 0:33。sar7_cdac_weight_audit.json SHA256 e7d7e006c6d7b5455b501aae2afaf338df5891b47302946995d24410aa3c58b7。
Run paths: ~/ecen720_28nm/runs/pam4_sar7_cdac_audit_20261115.QDKGAI（package、wrappers/env_audit.sh、wrap_audit.sbatch、logs/audit_760174.out、sar7_cdac_weight_audit.json）
Commit: 見下方 commit（handoff + results）
Needs user decision: no

## 檢查
- ZIP SHA256 f41bba0b672f6b59fa5e99981927eabeeea2786d97f63cc1dd2726cdddc5a24f 相符；`sha256sum -c` 3/3 OK；`verify`：「Verified original runs and held CDAC analysis package」；unittest 2/2 OK。
- 環境沿用 760132 的 env（PAM4_SAR7_PACKAGE、C0_ORIGINAL、C0_SWITCH、C0_R5_ORIGINAL、PDK_ROOT、RELAXED_PACKAGE/ROOT、ISOLATE_PACKAGE/ROOT），新 root 為 PAM4_SAR7_AUDIT_ROOT。
- tran SHA：760091 1ce73eae…；760132 a3c3572c…。

## CDAC 權重（fit 只用實際 bit 狀態與電位，預期碼不參與）

| 項目 | 760091 直接感測 | 760132 理想隔離 | 理想 |
|---|---|---|---|
| status | identified | identified | — |
| usable / held-out points | 84 / 84 | 84 / 84 | — |
| omitted state points | 0 | 0 | — |
| offset (LSB) | 53.74 | 59.75 | — |
| held-input gain | 0.9887 | 0.9899 | 1 |
| w_b6..b0 (LSB) | 52.57, 27.65, 13.84, 6.85, 3.37, 1.87, 1.01 | 58.77, 30.77, 15.37, 7.32, 3.77, 2.04, 1.12 | 64,32,16,8,4,2,1 |
| w／理想 | 0.82, 0.86, 0.86, 0.86, 0.84, 0.94, 1.01 | 0.92, 0.96, 0.96, 0.92, 0.94, 1.02, 1.12 | 1 |
| full-code span (LSB) | 107.16（−15.6%） | 119.16（−6.2%） | 127 |
| leave-one-conversion-out RMSE (LSB) | 0.748 | 0.887 | — |

判讀（只讀）：
- 兩案權重都獨立可辨識，線性模型留一 RMSE <1 LSB，所以剩下的錯碼可用靜態權重／滿刻度與 offset 解釋，不像隨機或時序。
- 比較器負載移除後 span 由 107.2 → 119.2 LSB，MSB 群（b6–b2）比例由 ~0.82–0.86 → ~0.92–0.96；仍短 ~6%。LSB 端（b1、b0）比例 ≥1，相對 MSB 偏大，二進位比例不一致（例如 760091 b2/b1 = 1.80）。
- held-input gain 兩案 ~0.99，sampling 不是主因。

## b0 readout（原門檻 0.18／0.72 V，原 PSF；分數不變）
- 760091：b0=0 共 6 次（index 1,5,6,8,9,11），760132：b0=0 共 5 次（1,5,6,7,9）。
- b0=0：end_s 時 output ≈ 0.322／0.768 V（低側未過 0.18 V）；end_s+3.5 ps ≈ 0.077／0.837 V，兩側都過門檻。到 rail 時間 = 最後 trial release 後 12.5 ps；所有 24 次 `valid_before_conv_off=true`。
- b0=1：release 後 ~0.25 ps 內就到 0.900／0.008 V。
- 結論：b0=0 路徑在 valid window 內可讀；end_s 太早（慢約 12 ps 的 0→rail 轉換）。有可靠的晚讀點（end_s+3.5 ps，conv 下降前）。既有正式錯碼結果維持凍結，本次未改分數。

## 保留
- 兩來源 raw（760091 SvCNXK、760132 kbTlvs）與既有紀錄全保留；本次只新增 compact JSON 與 wrapper／log。
