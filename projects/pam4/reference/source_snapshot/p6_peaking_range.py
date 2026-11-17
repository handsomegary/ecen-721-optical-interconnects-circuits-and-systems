#!/usr/bin/env python3
"""Confirm adjustable low-frequency-to56GHz peaking range and selected held SNDR."""
import json,math
import p6_bench as b
import p6_dynamic as d
from psf_ascii import parse_file

def main():
    seed=json.loads((b.BASE/'equalized_summary.json').read_text())['selected_config']
    records=[];dynamic=[]
    write=lambda:(b.BASE/'peaking_range_summary.json').write_text(json.dumps({'kind':'double CTLE peaking range referenced to1kHz and1MHz; real eight-lane sampler load','AC_results':records,'results':dynamic},indent=2,allow_nan=False))
    settings=[(rd,80e-15) for rd in [0,8000,16000,32000,64000]]+[(64000,cs) for cs in [100e-15,120e-15,160e-15]]
    for i,(rd,cs) in enumerate(settings):
        c=dict(seed,rdeg=rd,rdeg2=rd,cdeg=cs,cdeg2=cs);directory=b.BASE/'peaking_range'/('p%02d'%i)
        ll,ss=b.circuit(c,'X');lines=b.header()+ll+['saveOptions options save=selected currents=selected','save '+' '.join(ss),'dcOp dc',
            'acResponse ac start=1K stop=150G dec=60','noiseResponse (X_h0p X_h0m) noise start=1M stop=150G dec=60 iprobe=XVin']
        status=b.run(directory,lines,120)
        if status['exit_code']!=0:raise ValueError(status)
        r=b.analyze_ac(directory,c,'X');a=parse_file(directory/'raw/acResponse.ac');f=a.values['freq']
        h=[x-y for x,y in zip(a.values['X_o_p'],a.values['X_o_m'])]
        for freq,label in [(1e3,'1kHz'),(1e6,'1MHz')]:
            low=abs(b.at(f,h,freq));r['gain_'+label+'_VV']=low;r['peaking_56_vs_'+label+'_dB']=20*math.log10(r['gain_56GHz_VV']/low)
        n=parse_file(directory/'raw/noiseResponse.noise')
        if n.unit('out')!='V/sqrt(Hz)':raise ValueError('Unexpected noise density unit')
        r['track_noise_1MHz_to_56GHz_Vrms']=b.noise_band(n.values['freq'],n.values['out'],1e6,56e9)
        r['sha256']['noise']=n.sha256;r['run_status']=status;records.append(r);write()
        print(json.dumps({k:r[k] for k in ['config','peaking_56_vs_1kHz_dB','peaking_56_vs_1MHz_dB','hold_gain_56GHz_dB']}),flush=True)
    meet=[r for r in records if r['peaking_56_vs_1kHz_dB']>=20]
    chosen=min(meet,key=lambda r:(r['config']['rdeg'],r['config']['cdeg'])) if meet else max(records,key=lambda r:r['peaking_56_vs_1kHz_dB'])
    c=chosen['config']
    for i,noise in enumerate([False,True]):
        directory=b.BASE/'peaking_range'/('clocked%d'%i);ll,ss=b.circuit(c,'X',mode='tran',vinpp=.4,freq=112e9*127/256,clocked=True)
        ss=[s for s in ss if not s.startswith(('X_ck','X_kb','X_s1','X_s2','X_c_')) or s in ['X_ck0','X_kb0']]
        lines=b.header()+ll+['saveOptions options save=selected currents=selected','save '+' '.join(ss),'dcOp dc',
            'tranResponse tran stop=8n outputstart=4.8n maxstep=.2p errpreset=conservative'+(' noisefmax=150G noisefmin=500M noiseseed=11' if noise else '')]
        status=b.run(directory,lines,180)
        if status['exit_code']!=0:raise ValueError(status)
        r=d.analyze(directory,c,.4,112e9*127/256,True,8e-9);r['run_status']=status;r['transient_noise_enabled']=noise
        if noise:
            for key in ['continuous_output_fit','held_samples_fit']:r[key]['SNDR_with_simulated_noise_dB']=r[key].pop('deterministic_SNDR_dB')
            r.update({'noiseseed':11,'noisefmax_Hz':150e9,'noisefmin_Hz':5e8})
        dynamic.append(r);write()
        print(json.dumps({k:r[k] for k in ['config','held_gain_VV','held_samples_fit','transient_noise_enabled']}),flush=True)

if __name__=='__main__':main()
