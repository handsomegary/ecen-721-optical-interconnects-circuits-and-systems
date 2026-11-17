#!/usr/bin/env python3
"""Build a user-facing derived-metrics report and a strictly enumerated archive."""
import hashlib,json,math,pathlib,zipfile

ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    source=OUT/'Project6_feasibility_results.json'
    s=json.loads(source.read_text(encoding='utf-8'))
    pr=s['CTLE_adjustable_peaking_range_confirmation'];noisy=next(r for r in pr['results'] if r['transient_noise_enabled'])
    quiet=next(r for r in pr['results'] if not r['transient_noise_enabled']);c=noisy['config']
    ac=next(r for r in pr['AC_results'] if r['config']==c)
    sample=noisy['held_samples_fit'];quietfit=quiet['held_samples_fit'];vga=s['best_absolute_gain_dynamic']['results']
    vganoise=s['sampled_transient_noise_and_step_checks']['results']
    dv=lambda amp:next(r for r in vga if r['clocked'] and r['config']['ch']==10e-15 and r['input_Vppd']==amp)
    nv=lambda amp:next(r for r in vganoise if r['config']['ch']==10e-15 and r['input_Vppd']==amp and r['noiseseed']==11)
    zero=[r['held_differential_rms_about_mean_V'] for r in vganoise if r['config']['ch']==10e-15 and not r['input_Vppd'] and r['noisefmax_Hz']==150e9]
    num=s['verification']['numerical_step_check']
    report=f'''28nm LVT — Project 6 背景實測結論（2026-10-10）

選題建議
值得沿用這組 28nm LVT，繼續做 Project 6 的 CTLE／VGA／取樣器。
這輪已有接近 56 GHz、約 20 dB 相對低頻增益提升、實際 MOS 取樣與含雜訊結果，
所以先前低功耗單級 TIA 的 16.6 GHz 並不是這組 MOS 的速度上限。
完整 Project 6 仍屬高風險、尚未證實：本輪沒有完成 7-bit 112 GS/s ADC、PN skew
補償與含通道 PAM4 驗證。不能把「MOS 可做 AFE」等同「完整接收器已可完成」。

課程規格的意思
Sam 的 Project 6 要求 224 Gb/s PAM4，AFE 在 56 GHz Nyquist 處提供最高 20 dB
peaking，後接 nominal 7-bit、112 GS/s time-interleaved ADC，並補償 ±0.5 UI
差動 PN skew（112 Gbaud 時約 ±4.464 ps）。7-bit resolution 不等同強制 7 ENOB。
原規格沒有明定本題的功耗、雜訊或 ADC full-scale，因此不能捏造合格門檻。
來源：https://people.engr.tamu.edu/spalermo/ecen689_oi/ecen721_project.pdf

本輪實際做了什麼
在你的 CentOS VM 上使用 Spectre 18.1.0.077 與現有 nmos_lvt／pmos_lvt。
TT、25°C、VDD 0.9 V；輸入 MOS drawn L=30 nm、tail L=60 nm；模型接觸、閘極
電阻及耦合寄生旗標開啟。未修改 PDK。R/C 是理想元件，未包含實作或佈局寄生。
掃描 832 組前端配置（單／雙 CTLE、互補反相器），另外做 8 組低頻基準調整、
8 組等化範圍確認、18 組 AC／雜訊細查、21 組擺幅／實際時脈取樣、9 組取樣
雜訊／數值精度檢查，以及 5 組等化 CTLE 的實際時脈確認。
不是只以電容代替開關：負載為 8 路真正 LVT MOS transmission-gate 取樣器，
每路 14 GHz，相位差 8.928571 ps，合成 112 GS/s。每路每邊保持電容掃
5／10／20 fF；凍結時脈 AC 有 4 路同時 tracking，並保留其餘開關的寄生。
時脈為理想互補 0–0.9 V、1 ps 邊緣、約 50% track duty、零 jitter。

目前最有用的等化候選：同一配置的完整配對結果
兩級 NMOS 電阻負載 CTLE；每級每邊 8 個 W=3 µm input MOS 與對應 tail。
兩級 Rload=50 Ω、tail gate bias=0.58 V、Rdeg=64 kΩ、Cdeg=100 fF；輸入 CM=0.6 V。
8 路差動取樣器，CH=5 fF／路／邊，TG 的 N/P W 均為 3 µm、L=30 nm。
56 GHz 相對 1 kHz 增益提升：{ac['peaking_56_vs_1kHz_dB']:.4f} dB
56 GHz 相對 1 MHz 增益提升：{ac['peaking_56_vs_1MHz_dB']:.4f} dB
56 GHz 取樣器 tracking 節點 AC 絕對增益：{ac['hold_gain_56GHz_dB']:.3f} dB
響應的最高增益頻率：約 {ac['peak_Hz']/1e9:.2f} GHz。
「56 GHz 相對低頻提升 20 dB」與「最高峰就在 56 GHz」是不同條件；本架構尚需
依實際通道修整完整增益／相位響應，不能直接宣稱等化通道已完成。

實際切換取樣採 55.5625 GHz（112 GHz × 127/256），避開恰好 Nyquist 的相位
歧義；合併 256 個交錯樣本，依實際時脈關閉時刻取 hold 值。
以下數值都屬於上述同一配置、AFE 接收端輸入 0.400 Vppd：
取樣後輸出 fundamental：{sample['fundamental_Vppd']*1000:.3f} mVppd
取樣後絕對增益：{noisy['held_gain_VV']:.5f} V/V（{20*math.log10(noisy['held_gain_VV']):.2f} dB）
無雜訊時 SNDR：{quietfit['deterministic_SNDR_dB']:.3f} dB
開啟取樣 transient noise 後 SNDR：{sample['SNDR_with_simulated_noise_dB']:.3f} dB
含雜訊／失真 residual：{sample['residual_Vrms']*1000:.4f} mVrms
AFE 與取樣開關的 VDD 功耗：{noisy['AFE_and_sampler_VDD_power_W']*1000:.4f} mW
理想時脈來源淨供能：約 {noisy['ideal_clock_sources_net_delivered_power_W']*1000:.4f} mW
合計：約 {noisy['total_ideal_supply_and_clock_power_W']*1000:.4f} mW。
這個功耗沒有包含實體時脈 buffer／分配、偏壓產生、ADC 與 PN-skew 電路。

上述 80.8 mVppd 不是自動判定不夠：需要跟 ADC full-scale、比較器雜訊和負載
一起設計。31.4 dB SNDR 是有用的初步取樣結果，不能因為低於理想 7-bit SNR
就判定違反課程規格。另一方面，輸入 0.4 Vppd 是直接加在 AFE 接收端，沒有
通道衰減；本輪不能證明經過有損通道後仍保有這個 SNR。

為什麼不能只挑最大絕對增益的 VGA
互補反相器兩級在 CH=5 fF 時，56 GHz 連續輸出 AC 增益約 +0.97 dB，
tracking 節點約 −1.53 dB，耗電約 15.8 mW；但沒有需要的高頻等化，
56 GHz 相對 1 GHz 反而下降約 28.4 dB。
CH=10 fF 的實際取樣、同條件比較：
輸入 0.2 Vppd：無雜訊輸出 {dv(.2)['held_samples_fit']['fundamental_Vppd']*1000:.2f} mVppd，
無雜訊 SNDR {dv(.2)['held_samples_fit']['deterministic_SNDR_dB']:.2f} dB；加入雜訊後
輸出 {nv(.2)['held_fit']['fundamental_Vppd']*1000:.2f} mVppd、SNDR {nv(.2)['held_fit']['SNDR_with_simulated_noise_dB']:.2f} dB。
輸入 0.4 Vppd：加入雜訊後輸出 {nv(.4)['held_fit']['fundamental_Vppd']*1000:.2f} mVppd、
SNDR {nv(.4)['held_fit']['SNDR_with_simulated_noise_dB']:.2f} dB。
CH=10 fF、零輸入的三個雜訊種子估計約 {min(zero)*1000:.2f}–{max(zero)*1000:.2f} mVrms。
這組 VGA 的 AC 耦合自偏壓仍有約 2.9 mV 共模漂移，因此其短時間結果屬探索
基準，不應當作已充分穩定或已最佳化的最終設計；等化 CTLE 沒有同一個慢速
自偏壓問題。較好的選擇是從上述低雜訊 CTLE 出發，配合 ADC 設計擺幅。

驗證與結果可信度
全部納入摘要的模擬成功；已獨立確認 35 組 transient 保存資料涵蓋分析窗口。
以 CH5 fF／0.2 Vppd 的無雜訊取樣檢查最大時間步長 0.2 ps→0.1 ps：
增益差 {num['relative_gain_change_percent']:.3f}%，SNDR 差 {num['SNDR_change_dB']:.3f} dB。
150 GHz 與 300 GHz 雜訊上限檢查是在 VGA 基準執行；有限樣本與種子使 RMS
存在變動，不能把它當成精確收斂或等化 CTLE 的全頻雜訊保證。
取樣 transient noise 可包含切換與有限頻帶的 folding；noisefmin=500 MHz，
模擬器將低於該頻率的 PSD 固定，因此不是完整低頻 1/f 雜訊驗證。
一般 noiseless transient SNDR 與開啟 noise 的 SNDR 已分開標示。

要把完整 Project 6 判定為可完成，還缺的實際測試
1. 把實際通道加進來，跑 112 Gbaud PAM4，調整完整 CTLE／VGA 增益與相位，
   在選定接收輸入範圍下確認眼圖、取樣裕度與 BER 或錯誤統計。
2. 接上選定 7-bit TIADC 的實際輸入負載／kickback，加入量化、比較器雜訊、
   ADC full-scale 與 interleaving mismatch；完成 112 GS/s 的 ADC 架構。
3. 加入 ±4.464 ps PN skew 與補償，檢查修正範圍、殘差與 PAM4 品質。
4. 加入真實時脈驅動／jitter／skew，並跑 PVT 與佈局寄生；核對這版模型在
   56 GHz 及更高雜訊頻率的適用性。這些尚未完成，不能給製程或矽後保證。

對「值不值得做」的直接回答
MOS 的部分：值得保留，不需要因為 16.6 GHz TIA 結果就放棄或換 PDK。
子題的部分：CTLE／VGA 加取樣器已有可研究、可交付的數據，值得繼續。
完整 Project 6 的部分：目前仍是高風險，還不能承諾能把 ADC 與 PN-skew
全部完成；下一個真正的 go/no-go 應是上述通道＋ADC 負載的 PAM4 測試。

資料保存與清理
已保存派生數值、條件及 SHA-256，不含 PDK 模型、係數、文件、私鑰或原始波形。
你先前指定的 /path/to/local/cadence-home/pdk_probe 已刪除，本輪確認它仍不存在。
新測試使用 /path/to/local/cadence-home/project6_feasibility/run_20261010，沒有重新建立 pdk_probe。
PDK 主模型 SHA-256 與測試前相同：
{s['verification']['main_model_sha256']}
'''
    textpath=OUT/'Project6_可行性結論.txt';textpath.write_text(report,encoding='utf-8')
    readme='''Project6 Feasibility Test Package

Contains only independently authored test code, derived numbers and hashes.
No PDK models, coefficients, foundry documents, raw waveforms or SSH keys.

Requires the user's existing Spectre/PDK installation on the VM. Paths and
conditions are explicit in p6_bench.py. No PDK modification is performed.
Copy the Python sources including psf_ascii.py into a dedicated test folder.
Use a fresh result folder by adjusting BASE in p6_bench.py when reproducing.

Run order on the VM:
python3 p6_bench.py grid
python3 p6_bench.py expanded
python3 p6_bench.py inverter
python3 p6_bench.py double_eq
python3 p6_bench.py refine
python3 p6_tune.py
python3 p6_dynamic.py
python3 p6_extra.py
python3 p6_equalized.py
python3 p6_peaking_range.py
python3 p6_collect.py

AC peaking references and sampled tone frequencies are explicit in the report.
Cached dynamic/extra runs require exit_code=0; use fresh folders for a new run.
Raw waveforms remain on the VM and are deliberately absent from this package.
The PDK baseline hash in p6_collect.py must match the existing tested revision.
'''
    readmepath=OUT/'Project6_重跑說明.txt';readmepath.write_text(readme,encoding='utf-8')
    files={source.name:source,textpath.name:textpath,readmepath.name:readmepath,'sources/psf_ascii.py':ROOT/'work/psf_ascii.py'}
    for name in ['p6_bench.py','p6_dynamic.py','p6_extra.py','p6_tune.py','p6_equalized.py','p6_peaking_range.py','p6_collect.py']:
        f=ROOT/'work/project6'/name
        assert sha(f)==s['verification']['script_sha256'][name],name
        files['sources/'+name]=f
    assert sha(files['sources/psf_ascii.py'])==s['verification']['parser_sha256']
    manifest={k:{'bytes':v.stat().st_size,'sha256':sha(v)} for k,v in files.items()}
    manifestpath=OUT/'Project6_manifest.json';manifestpath.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    files[manifestpath.name]=manifestpath
    package=OUT/'Project6_Feasibility_Test_Package.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
        for name,path in files.items():z.write(path,name)
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        assert set(z.namelist())==set(files)
        for name,path in files.items():assert z.read(name)==path.read_bytes(),name
    print(json.dumps({'report':str(textpath),'package_bytes':package.stat().st_size,'package_members':len(files),
        'summary_sha256':sha(source),'selected_peaking_dB':ac['peaking_56_vs_1kHz_dB'],'sampled_SNDR_dB':sample['SNDR_with_simulated_noise_dB']},ensure_ascii=False))

if __name__=='__main__':main()
