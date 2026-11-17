【ECEN 721 #6 P/N deskew LP_SIGNOFF 0／28＋XT2 讀回：TT replica 補掃到 20 GHz 後正式通過（PM 90.58°、GM 26.72 dB 在 4.97 GHz）；SS cb2 的 Q15／SRF150 電感 P 欄工作點正常（driver 汲極低 12 mV）；XT2 八路殘差在 0.001 mV 以下，增益變化 −0.24～+0.01 dB】

一、執行
- 套件（ZIP SHA 0c196c9f…）：SHA256SUMS 全部通過，`lp_signoff.py --mode verify` 通過，96 項離線測試通過；本機與 Olympus 各驗證一次。
- 審查 deck 0、28：
  - 00 的 bench 只差 model include 那一行；28 的 bench 與 portable 完全相同，corner 只差模型根路徑。
  - case.json 只多了 model_preflight 與 staged_source_sha256。
  - 00 和 DIAG NEXT 07 比：只把 replicaSTB 從 1 GHz 改成 20 GHz（每十倍頻 100 點）。
  - 28 和 INTEGRATE 20 比：兩顆 120 pH（GMSHPLPK／GMSHMLPK）各串 2.81487 Ω 到 GF_VDD，並在 LP 端對 GF_VDD 並 9.38159 fF。我核算過：R = 2π·56 GHz·120 pH／15 = 2.815 Ω；C = 1／((2π·150 GHz)²·120 pH) = 9.38 fF，兩個值都正確，接線也正確。
- 使用者批准 0、28（stages replica20、passive），以及 XT2 讀回。
  - 中間 VPN 斷過一次，連回後才上傳；在連回之前沒有建立任何 Olympus 目錄。
- job 754705：0 用 2 秒、28 用 5 秒，都 COMPLETED。Spectre 0 errors，3 warnings（只有模型檔的 SFE-1131），completion 都有寫出。
- raw 保留在 Olympus。

二、結果
1. 案 0（TT cb0 replica，到 20 GHz）：pass（formal_margin_pass 為 true）。
   - PM 90.58°（14.83 MHz）；GM 26.72 dB（4.974 GHz），原生判定為「Gain and phase margin are both found」。
   - 由取樣算出 PM 90.58°、GM 26.72 dB，與原生值一致。
   - DC：Iref 324.78 µA，伺服誤差 0.006%，kick 0.0006 µA。
   - sampled_screen_pass 為 false。請說明這個欄位的意義：formal 與 native 都已通過，是否還需要它也通過。
   - 推論：DIAG NEXT 07–10 被標為 review，原因確實只是 1 GHz 的掃頻範圍。TT 的 GM 交越在 4.97 GHz；FF 的 1–3 預計也一樣。
2. 案 28（SS cb2，Q15／SRF150，P 欄）：measurement complete。
   - 和 INTEGRATE 20（理想電感）比：
     - GMSR_REF、GMSR_D、GMSR_BIAS 完全相同（0.653689、0.653931、0.445300 V）；
     - driver 閘極 GMSHPFG／GMSHMFG 相同（0.445292 V）；
     - driver 汲極 GMSHPFD／GMSHMFD 從 0.653940 降到 0.641904 V（−12.0 mV）。約 4.3 mA 流過 2.815 Ω，壓降 ≈ 12 mV，與預期吻合。
     - 輸出雜訊 0.733 mVrms，與理想電感相同。
   - 因為只有 P 欄，summary 的 passive 列是空的；Hdd 等 29（N 欄）跑完再判讀。
3. XT2 讀回（DIAG NEXT 17／18 原 PSF，collect-only，沒有新模擬）：

| lane | 全幅對半幅的增益變化 | 正規化差值 rms | affine 殘差最大值 |
| ---: | ---: | ---: | ---: |
| 0 | +0.010 dB | 0.028 mV | 0.00024 mV |
| 1 | −0.023 | 0.028 | 0.00008 |
| 2 | −0.238 | 0.073 | 0.00054 |
| 3 | −0.073 | 0.017 | 0.00019 |
| 4 | −0.095 | 0.045 | 0.00008 |
| 5 | −0.082 | 0.071 | 0.00077 |
| 6 | −0.077 | 0.063 | 0.00079 |
| 7 | −0.044 | 0.026 | 0.00047 |

   - 每個 lane 有 16 個 PAM4 轉換。在線性擬合之後，殘差都低於 0.001 mV，看不出非線性失真。
   - 最大的增益差是 lane 2 的 −0.24 dB，其餘 lane 都在 ±0.1 dB 以內。這支持維持 Vb2 = 0.580 V。

三、請你判斷
- 案 0 通過，FF 的 1–3（TT cb2、FF cb0／cb2）可以同一份 deck 照跑。
- 案 28 的工作點正常：Q15 的串聯電阻讓 driver 汲極低 12 mV，偏壓迴路不受影響。下一批可以跑 4–39 中你建議的部分（先 18–25 重現理想電感，再跑 Q15／Q8），需要使用者另外批准。
- XT2 lane 2 的 −0.24 dB：是否需要在時域 SER 中特別追蹤？
