#!/usr/bin/env python3
"""Sampled transient-noise and numerical accuracy checks on the selected AFE."""
import json, math
import p6_bench as b
import p6_dynamic as d
from psf_ascii import parse_file

def held_samples(directory):
    raw=list((directory/'raw').glob('tranResponse.tran*'))[0]
    psf=d.parse_tran(raw); t=psf.values[psf.sweep_names[0]]
    times,clockcheck=d.sampling_times(psf,t);qs=range(256)
    values=[d.interp(t,psf.values['X_h%dp'%(q%8)],x)-d.interp(t,psf.values['X_h%dm'%(q%8)],x) for q,x in zip(qs,times)]
    return times,values,psf.sha256

def main():
    rr=json.loads((b.BASE/'refine_summary.json').read_text())['results']
    best=max([r for r in rr if r.get('static_headroom_ok')],key=lambda r:r['hold_gain_56GHz_VV'])['config']
    tests=[]
    # Zero-input transient noise establishes actual held variance, not kT/C addition.
    for cap in [5e-15,10e-15,20e-15]: tests.append((cap,0,11,150e9,.2e-12))
    for seed in [17,23]:tests.append((10e-15,0,seed,150e9,.2e-12))
    tests.append((10e-15,.2,11,150e9,.2e-12))
    tests.append((10e-15,0,11,300e9,.2e-12))
    tests.append((5e-15,.2,None,None,.1e-12))
    tests.append((10e-15,.4,11,150e9,.2e-12))
    records=[]
    for i,(cap,amp,seed,fmax,step) in enumerate(tests):
        c=dict(best,ch=cap);directory=b.BASE/'extra'/('e%02d'%i)
        lines=b.header();ll,saves=b.circuit(c,'X',mode='tran',vinpp=amp,freq=112e9*127/256,clocked=True);lines+=ll
        saves=[s for s in saves if not s.startswith(('X_ck','X_kb','X_s1','X_s2','X_c_')) or s in ['X_ck0','X_kb0']]
        suffix='' if seed is None else ' noisefmax=%g noisefmin=500M noiseseed=%d'%(fmax,seed)
        lines+=['saveOptions options save=selected currents=selected','save '+' '.join(dict.fromkeys(saves)),'dcOp dc',
                'tranResponse tran stop=8n outputstart=4.8n maxstep=%g errpreset=conservative%s'%(step,suffix)]
        prior=directory/'run_status.json'
        status=json.loads(prior.read_text()) if prior.exists() else None
        if not status or status['exit_code']!=0:status=b.run(directory,lines,180)
        r={'config':c,'input_Vppd':amp,'noiseseed':seed,'noisefmax_Hz':fmax,'noisefmin_Hz':5e8 if seed else None,'maxstep_s':step,'run_status':status,'directory':str(directory)}
        if status['exit_code']==0:
            times,y,h=held_samples(directory);avg=sum(y)/len(y);std=math.sqrt(sum((v-avg)**2 for v in y)/len(y))
            r.update({'held_sample_count':256,'held_differential_mean_V':avg,'held_differential_rms_about_mean_V':std,'sha256':h})
            if amp:
                r['held_fit']=d.sine_fit(times,y,112e9*127/256)
                r['held_gain_VV']=r['held_fit']['fundamental_Vppd']/amp
                r['SNDR_includes_simulated_noise']=seed is not None
        records.append(r)
        (b.BASE/'extra_summary.json').write_text(json.dumps({'kind':'actual MOS sampler transient noise,finite noise bandwidth,zero-jitter ideal clocks; low frequency noise flattened below500MHz','results':records},indent=2,allow_nan=False))
        print(json.dumps({k:r[k] for k in ['input_Vppd','noiseseed','noisefmax_Hz','held_differential_rms_about_mean_V','held_fit','held_gain_VV','run_status'] if k in r}),flush=True)

if __name__=='__main__':main()
