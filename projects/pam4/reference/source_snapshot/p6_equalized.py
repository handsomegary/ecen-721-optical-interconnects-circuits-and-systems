#!/usr/bin/env python3
"""Clocked confirmation of the strongest-peaking screened two-stage CTLE."""
import json,math
import p6_bench as b
import p6_dynamic as d
import p6_extra as e
from psf_ascii import parse_file

def main():
    rows=json.loads((b.BASE/'double_eq_summary.json').read_text())['results']
    best=max([r for r in rows if r.get('static_headroom_ok')],key=lambda r:r['peaking_56_vs_1GHz_dB'])
    c=best['config'];folder=b.BASE/'equalized';folder.mkdir(exist_ok=True)
    acdir=folder/'low_reference';ll,ss=b.circuit(c,'X')
    lines=b.header()+ll+['saveOptions options save=selected currents=selected','save '+' '.join(ss),'dcOp dc',
        'acResponse ac start=1M stop=150G dec=60','noiseResponse (X_h0p X_h0m) noise start=1M stop=150G dec=60 iprobe=XVin']
    status=b.run(acdir,lines,120)
    if status['exit_code']!=0:raise ValueError(status)
    ac=b.analyze_ac(acdir,c,'X');a=parse_file(acdir/'raw/acResponse.ac');f=a.values['freq']
    h=[x-y for x,y in zip(a.values['X_o_p'],a.values['X_o_m'])]
    ac['gain_1MHz_VV']=abs(h[0]);ac['peaking_56_vs_1MHz_dB']=20*math.log10(ac['gain_56GHz_VV']/abs(h[0]))
    n=parse_file(acdir/'raw/noiseResponse.noise')
    if n.unit('out')!='V/sqrt(Hz)':raise ValueError('Unexpected output noise density unit')
    ac['track_noise_1MHz_to_56GHz_Vrms']=b.noise_band(n.values['freq'],n.values['out'],1e6,56e9)
    ac['sha256']['noise']=n.sha256;ac['run_status']=status
    records=[]
    summary=lambda:(b.BASE/'equalized_summary.json').write_text(json.dumps({'kind':'actual clocked two-stage CTLE confirmation,not ADC or PAM4 link proof','selected_config':c,'low_reference_ac':ac,'results':records},indent=2,allow_nan=False))
    summary()
    for i,(amp,seed) in enumerate([(.2,None),(.4,None),(.4,11)]):
        directory=folder/('q%02d'%i);ll,ss=b.circuit(c,'X',mode='tran',vinpp=amp,freq=112e9*127/256,clocked=True)
        ss=[s for s in ss if not s.startswith(('X_ck','X_kb','X_s1','X_s2','X_c_')) or s in ['X_ck0','X_kb0']]
        suffix='' if seed is None else ' noisefmax=150G noisefmin=500M noiseseed=%d'%seed
        lines=b.header()+ll+['saveOptions options save=selected currents=selected','save '+' '.join(ss),'dcOp dc',
            'tranResponse tran stop=8n outputstart=4.8n maxstep=.2p errpreset=conservative'+suffix]
        status=b.run(directory,lines,180)
        if status['exit_code']!=0:raise ValueError(status)
        r=d.analyze(directory,c,amp,112e9*127/256,True,8e-9)
        r['run_status']=status;r['transient_noise_enabled']=seed is not None
        r['noiseseed']=seed;r['noisefmax_Hz']=150e9 if seed else None;r['noisefmin_Hz']=5e8 if seed else None
        # A fitted residual from a noise-enabled run is total sampled SNDR.
        if seed:
            for key in ['continuous_output_fit','held_samples_fit']:
                r[key]['SNDR_with_simulated_noise_dB']=r[key].pop('deterministic_SNDR_dB')
        records.append(r);summary()
        print(json.dumps({k:r[k] for k in ['input_Vppd','transient_noise_enabled','held_gain_VV','held_samples_fit','AFE_and_sampler_VDD_power_W']}),flush=True)

if __name__=='__main__':main()
