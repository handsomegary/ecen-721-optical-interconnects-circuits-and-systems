# ECEN 721 SAR7 · 既有 PSF 的 CDAC 與輸出查核

本次用保留的 760091（直接感測）與 760132（理想隔離）兩案。讀 `pre_s` 的 hold 差動和已到 rail 的七個控制位元，估計每個 bit 的有效權重、滿刻度轉移、offset 與 held-input gain。以逐轉換留一交叉檢查看線性模型誤差。樣本不足以分開各權重時，將結果留作無法辨識。端點碼以外的實際 transfer 仍需要電路驗證。

另讀原 `end_s` 與 `end_s+3.5 ps` 的 b0 輸出，掃最後 trial release 到末端 conv 下降前的保存點。這一段區分讀取時刻過早與 valid hold window 內仍達不到 rail。使用原門檻 0.18／0.72 V，記錄每次轉換時刻與電位。模型驗證使用有記錄的 CDAC 狀態與電位；既有正式錯碼結果保留原樣。

## Olympus

從 OneDrive 傳 ZIP／sidecar，核對 SHA；沿用 760132 的原環境和套件位置。

```bash
export PAM4_SAR7_ISOLATE_PACKAGE='/absolute/path/PAM4_SAR7_SENSE_ISOLATION_20261115'
export PAM4_SAR7_RELAXED_PACKAGE='/absolute/path/PAM4_SAR7_RELAXED_PILOT_20261115'
export PAM4_SAR7_PACKAGE='/absolute/path/PAM4_R5_SAR7_SLICE_20261115'
export PAM4_SAR7_RELAXED_ROOT='/absolute/path/to/completed/job-760091-campaign'
export PAM4_SAR7_ISOLATE_ROOT='/absolute/path/to/completed/job-760132-campaign'
export PAM4_SAR7_AUDIT_ROOT="$(mktemp -d "$HOME/ecen720_28nm/runs/pam4_sar7_cdac_audit_20261115.XXXXXX")"
# 保留原案的 PAM4_C0_ORIGINAL_PACKAGE、PAM4_C0_SWITCH_PACKAGE、PAM4_C0_R5_ORIGINAL。
cd '/absolute/path/PAM4_SAR7_CDAC_AUDIT_20261115'
sha256sum -c SHA256SUMS.txt
/usr/bin/python3.11 -B sar7_cdac_audit.py verify
/usr/bin/python3.11 -B -m unittest discover -v
/usr/bin/python3.11 -B sar7_cdac_audit.py audit \
  --relaxed-root "$PAM4_SAR7_RELAXED_ROOT" --isolation-root "$PAM4_SAR7_ISOLATE_ROOT" \
  --output-root "$PAM4_SAR7_AUDIT_ROOT"
```

使用單一 Python 收集程序，預估數分鐘，零個新 solver。回本機 outbox 報兩案權重、held-out 誤差、b0 是否有可靠的晚讀點、JSON SHA。保留原始 PSF、網表與證據。新摘要 `sar7_cdac_weight_audit.json` 寫入指定的新根目錄。
