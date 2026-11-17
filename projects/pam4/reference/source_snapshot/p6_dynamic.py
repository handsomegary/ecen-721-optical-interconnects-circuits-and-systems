#!/usr/bin/env python3
"""Clocked MOS sampling and large-signal screens, with no transient noise claim."""
import bisect,json,math,re,hashlib
from pathlib import Path
import p6_bench as b
from psf_ascii import parse_file

def parse_tran(path,window_start=4.8e-9):
    if path.stat().st_size<=64*1024*1024:return parse_file(path)
    # Retain full resolution in the steady window; do not decimate waveforms.
    compact=path.parent/'steady_window.psfascii';in_values=False;keep=True
    sha=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):sha.update(block)
    with path.open() as src,compact.open('w') as dst:
        for line in src:
            if line.strip()=='VALUE':in_values=True;dst.write(line);continue
            if not in_values:dst.write(line);continue
            match=re.match(r'^\s*"time"\s+([+\-0-9.eE]+)\s*$',line)
            if match:keep=float(match.group(1))>=window_start
            if keep or line.strip()=='END':dst.write(line)
    result=parse_file(compact);result.sha256=sha.hexdigest();return result

def interp(x,y,t):
    i=bisect.bisect_left(x,t)
    if i==0:return y[0]
    if i>=len(x):return y[-1]
    a=(t-x[i-1])/(x[i]-x[i-1]);return y[i-1]+a*(y[i]-y[i-1])

def mean_time(t,y,lo,hi):
    tt=[lo]+[x for x in t if lo<x<hi]+[hi]
    yy=[interp(t,y,x) for x in tt]
    return sum((tt[i+1]-tt[i])*(yy[i+1]+yy[i])/2 for i in range(len(tt)-1))/(hi-lo)

def sampling_times(psf,t):
    clock=psf.values['X_ck0'];half=(max(clock)+min(clock))/2
    falls=[];rises=[]
    for i in range(1,len(t)):
        if clock[i-1]>=half>clock[i]:falls.append(t[i-1]+(t[i]-t[i-1])*(clock[i-1]-half)/(clock[i-1]-clock[i]))
        if clock[i-1]<half<=clock[i]:rises.append(t[i-1]+(t[i]-t[i-1])*(half-clock[i-1])/(clock[i]-clock[i-1]))
    close=next(x for x in falls if x>=5e-9)
    first=close+.5e-12+1e-12
    times=[first+q*b.UI for q in range(256)]
    previous=max(x for x in rises if x<close)
    return times,{'lane0_close_50percent_s':close,'sample_after_gate_fall_end_s':1e-12,'measured_clock_track_duty':(close-previous)/(8*b.UI)}

def solve(a,v):
    m=[list(row)+[value] for row,value in zip(a,v)]
    for k in range(len(v)):
        pivot=max(range(k,len(v)),key=lambda i:abs(m[i][k]));m[k],m[pivot]=m[pivot],m[k]
        div=m[k][k]
        if abs(div)<1e-20:raise ValueError('Singular sine fit')
        m[k]=[x/div for x in m[k]]
        for i in range(len(v)):
            if i!=k:
                q=m[i][k];m[i]=[x-q*y for x,y in zip(m[i],m[k])]
    return [row[-1] for row in m]

def sine_fit(t,y,f):
    rows=[[1,math.sin(2*math.pi*f*x),math.cos(2*math.pi*f*x)] for x in t]
    a=[[sum(row[i]*row[j] for row in rows) for j in range(3)] for i in range(3)]
    v=[sum(row[i]*val for row,val in zip(rows,y)) for i in range(3)]
    c=solve(a,v);res=[val-sum(x*z for x,z in zip(row,c)) for row,val in zip(rows,y)]
    amp=math.hypot(c[1],c[2]);rms=math.sqrt(sum(x*x for x in res)/len(res))
    return {'dc_V':c[0],'fundamental_Vppd':2*amp,'residual_Vrms':rms,'deterministic_SNDR_dB':20*math.log10(amp/math.sqrt(2)/rms) if rms else None,
            'phase_rad':math.atan2(c[2],c[1])}

def clock_voltage(t,lane,vdd):
    delay=100e-12+lane*b.UI;period=8*b.UI;edge=1e-12;width=period/2-edge
    if t<delay:return 0
    p=(t-delay)%period
    if p<edge:return vdd*p/edge
    if p<edge+width:return vdd
    if p<2*edge+width:return vdd*(2*edge+width-p)/edge
    return 0

def analyze(directory,c,vinpp,f,clocked,stop):
    files=list((directory/'raw').glob('tranResponse.tran*'))
    if len(files)!=1:raise ValueError('Ambiguous transient file')
    d=parse_tran(files[0],4.8e-9 if clocked else 2.4e-9);t=d.values[d.sweep_names[0]]
    if t[0]>(5e-9 if clocked else 2.5e-9) or t[-1]<stop-1e-15:
        raise ValueError('Saved transient data does not cover the measurement window')
    vo=[x-y for x,y in zip(d.values['X_o_p'],d.values['X_o_m'])]
    start=5e-9 if clocked else 2.5e-9
    ts=[start+i*(stop-start)/4096 for i in range(4096)]
    yy=[interp(t,vo,x) for x in ts]
    fit=sine_fit(ts,yy,f)
    half=len(ts)//2
    drift=[sine_fit(ts[:half],yy[:half],f),sine_fit(ts[half:],yy[half:],f)]
    r={'config':c,'input_Vppd':vinpp,'tone_Hz':f,'clocked':clocked,'continuous_output_fit':fit,
       'continuous_gain_VV':fit['fundamental_Vppd']/vinpp,
       'output_min_max_V':[min(interp(t,d.values['X_o_'+side],x) for side in ['p','m'] for x in ts),max(interp(t,d.values['X_o_'+side],x) for side in ['p','m'] for x in ts)],
       'AFE_and_sampler_VDD_power_W':-c.get('vdd',.9)*mean_time(t,d.values['XVs:p'],start,stop),
       'sha256':d.sha256,'directory':str(directory),'transient_noise_enabled':False}
    r['steady_window_gain_drift_dB']=20*math.log10(drift[1]['fundamental_Vppd']/drift[0]['fundamental_Vppd'])
    r['steady_window_differential_offset_drift_V']=drift[1]['dc_V']-drift[0]['dc_V']
    cm=[(x+y)/2 for x,y in zip(d.values['X_o_p'],d.values['X_o_m'])]
    middle=(start+stop)/2
    r['steady_window_common_mode_drift_V']=mean_time(t,cm,middle,stop)-mean_time(t,cm,start,middle)
    if clocked:
        times,clockcheck=sampling_times(d,t);qs=list(range(256));r.update(clockcheck)
        samples=[interp(t,d.values['X_h%dp'%(q%8)],x)-interp(t,d.values['X_h%dm'%(q%8)],x) for q,x in zip(qs,times)]
        sf=sine_fit(times,samples,f);r['held_samples_fit']=sf;r['held_gain_VV']=sf['fundamental_Vppd']/vinpp
        # N=256, tone bin 127. Exclude DC/fundamental; all other bins are spurs.
        mags=[]
        for k in range(1,129):
            re=sum((samples[i]-sf['dc_V'])*math.cos(2*math.pi*k*i/256) for i in range(256))/256
            im=-sum((samples[i]-sf['dc_V'])*math.sin(2*math.pi*k*i/256) for i in range(256))/256
            mags.append(math.hypot(re,im))
        mags=[v*(1 if k==128 else 2) for k,v in enumerate(mags,1)]
        spur=max(v for k,v in enumerate(mags,1) if k!=127)
        r['held_samples_SFDR_dB']=20*math.log10(mags[126]/spur)
        r['held_sample_count']=256;r['sample_interval_s']=b.UI;r['lane_count']=8
        lo=times[0];hi=lo+256*b.UI
        r['AFE_and_sampler_VDD_power_W']=-c.get('vdd',.9)*mean_time(t,d.values['XVs:p'],lo,hi)
        r['power_average_interval_s']=[lo,hi]
        r['clock_power_voltage_source']='measured lane0 CK/KB traces shifted by each lane phase; no analytic pulse-width assumption'
        cp=[]
        for lane in range(8):
            for suffix,invert in [('CK',False),('KB',True)]:
                cur=d.values['X%s%d:p'%(suffix,lane)]
                pv=[]
                ref=d.values['X_kb0'] if invert else d.values['X_ck0']
                for x,i in zip(t,cur):
                    v=interp(t,ref,x-lane*b.UI)
                    pv.append(-v*i)
                cp.append(mean_time(t,pv,lo,hi))
        r['ideal_clock_sources_net_delivered_power_W']=sum(cp)
        r['total_ideal_supply_and_clock_power_W']=r['AFE_and_sampler_VDD_power_W']+sum(cp)
        r['clock_assumptions']='eight ideal complementary zero-jitter 14GHz clocks,1ps edges,approximately50%tracking (actual duty measured); physical clock buffers not modeled'
    return r

def main():
    rr=json.loads((b.BASE/'refine_summary.json').read_text())['results']
    valid=[r for r in rr if r.get('static_headroom_ok')]
    best=max(valid,key=lambda r:r['hold_gain_56GHz_VV'])
    configs=[dict(best['config'],ch=ch) for ch in [5e-15,10e-15,20e-15]]
    records=[];index=0
    tests=[]
    for c in configs:
        for amp in [.05,.1,.2,.4]:tests.append((c,amp,False,56e9,3e-9))
        for amp in [.1,.2,.4]:tests.append((c,amp,True,112e9*127/256,8e-9))
    for c,amp,clocked,f,stop in tests:
        directory=b.BASE/'dynamic'/('d%02d'%index);index+=1
        lines=b.header();ll,saves=b.circuit(c,'X',mode='tran',vinpp=amp,freq=f,clocked=clocked);lines+=ll
        if clocked:
            # Retain measured lane0 clock voltages and all clock currents for power.
            saves=[s for s in saves if not s.startswith(('X_ck','X_kb','X_s1','X_s2','X_c_')) or s in ['X_ck0','X_kb0']]
        lines+=['saveOptions options save=selected currents=selected','save '+' '.join(dict.fromkeys(saves)),'dcOp dc',
                'tranResponse tran stop=%g maxstep=%g outputstart=%g errpreset=conservative'%(stop,.2e-12 if clocked else .1e-12,4.8e-9 if clocked else 2.4e-9)]
        prior=directory/'run_status.json'
        status=json.loads(prior.read_text()) if prior.exists() else None
        if not status or status['exit_code']!=0:status=b.run(directory,lines,150)
        if status['exit_code']==0:
            r=analyze(directory,c,amp,f,clocked,stop);r['run_status']=status
        else:r={'config':c,'input_Vppd':amp,'clocked':clocked,'run_status':status}
        records.append(r)
        (b.BASE/'dynamic_summary.json').write_text(json.dumps({'selected_config':best['config'],'kind':'ordinary noiseless transient, actual TG sampling, not ADC or BER proof','results':records},indent=2,allow_nan=False))
        print(json.dumps({k:r[k] for k in ['input_Vppd','clocked','continuous_gain_VV','held_gain_VV','AFE_and_sampler_VDD_power_W','held_samples_fit'] if k in r}),flush=True)

if __name__=='__main__':main()
