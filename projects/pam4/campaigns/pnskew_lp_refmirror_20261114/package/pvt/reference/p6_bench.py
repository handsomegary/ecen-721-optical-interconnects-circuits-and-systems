#!/usr/bin/env python3
"""Independent schematic feasibility benchmarks; never modifies PDK files."""
import argparse, bisect, itertools, json, math, os, re, subprocess, time
from pathlib import Path
from psf_ascii import parse_file, integrate_noise

BASE = Path('/path/to/local/cadence-home/project6_feasibility/run_20261010')
SPECTRE = '/opt/eda/cadence/SPECTRE181/bin/spectre'
MODEL = '/path/to/pdk_28nm/models/spectre/pdk_toplevel.scs'
UI = 1.0/112e9
FLAGS = 'l=30n nf=1 multi=1 _ccoflag=1 _rcoflag=1 _rgflag=1'

def at(x,y,f):
    r=bisect.bisect_left(x,f)
    if r==0: return y[0]
    if r>=len(x): return y[-1]
    q=math.log(f/x[r-1])/math.log(x[r]/x[r-1])
    return y[r-1]+q*(y[r]-y[r-1])

def noise_band(x,a,lo,hi):
    xx=[lo]+[f for f in x if lo<f<hi]+[hi]
    p=[abs(v)**2 for v in a]
    return integrate_noise(xx,[at(x,p,f) for f in xx],density_kind='psd')['rms']

def header(section='tt',temp=25,vdd=.9):
    return ['simulator lang=spectre','include "%s" section=%s'%(MODEL,section),
            'simulatorOptions options temp=%g tnom=25 reltol=1e-4 vabstol=1u iabstol=1p'%temp,
            '// Schematic models with gate/contact/coupling parasitics enabled.']

def mos(name,d,g,s,b,pmos=False,w=3e-6,l=30e-9):
    return '%s (%s %s %s %s) %s w=%g %s'%(name,d,g,s,b,'pmos_lvt' if pmos else 'nmos_lvt',w,FLAGS.replace('l=30n','l=%g'%l))

def circuit(c,tag,mode='ac',vinpp=.1,freq=56e9,cap=None,clocked=False):
    if c.get('arch')=='inverter': return invcircuit(c,tag,mode,vinpp,freq,cap,clocked)
    n=lambda s:tag+'_'+s
    name=lambda s:tag+s
    ch=c.get('ch',5e-15) if cap is None else cap
    vdd=c.get('vdd',.9)
    lines=['%s (%s 0) vsource dc=%g'%(name('Vs'),n('vdd'),vdd),
           '%s (%s 0) vsource dc=%g'%(name('Vcm'),n('cm'),c.get('cm',.6)),
           '%s (%s 0) vsource dc=%g'%(name('Vb'),n('vb'),c['vb'])]
    stim='dc=0 mag=0.5'
    if mode=='tran': stim='type=sine dc=0 ampl=%g freq=%g'%(vinpp/4,freq)
    lines+=['%s (%s %s) vsource %s'%(name('Vin'),n('ip'),n('cm'),stim),
            '%s (%s %s %s %s) vcvs gain=-1'%(name('Ein'),n('im'),n('cm'),n('ip'),n('cm'))]
    for stage,copies,rd,ins,outs in [(1,c['nc'],c['rc'],('ip','im'),('c_p','c_m')),(2,c['nv'],c['rv'],('c_p','c_m'),('o_p','o_m'))]:
        for side,gate,out in zip(['p','m'],ins,outs):
            src='s%d_%s'%(stage,side)
            lines.append('%s (%s %s) resistor r=%g'%(name('R%d%s'%(stage,side)),n('vdd'),n(out),rd))
            for j in range(copies):
                lines.append(mos(name('M%d%s%d'%(stage,side,j)),n(out),n(gate),n(src),'0'))
                lines.append(mos(name('T%d%s%d'%(stage,side,j)),n(src),n('vb'),'0','0',l=60e-9))
        rr=c['rdeg'] if stage==1 else c.get('rdeg2',0)
        cc=c['cdeg'] if stage==1 else c.get('cdeg2',0)
        if rr:
            lines+=['%s (%s %s) resistor r=%g'%(name('Rdeg%d'%stage),n('s%d_p'%stage),n('s%d_m'%stage),rr),
                    '%s (%s %s) capacitor c=%g'%(name('Cdeg%d'%stage),n('s%d_p'%stage),n('s%d_m'%stage),cc)]
        else:
            lines.append('%s (%s %s) vsource dc=0'%(name('Vtie%d'%stage),n('s%d_p'%stage),n('s%d_m'%stage)))
    ll,ss=sampler(c,tag,clocked,ch); lines+=ll
    saves=[n(s) for s in ['ip','im','c_p','c_m','o_p','o_m','s1_p','s1_m','s2_p','s2_m']]+[name('Vs')+':p']+ss
    return lines,saves

def sampler(c,tag,clocked=False,cap=None):
    n=lambda s:tag+'_'+s; name=lambda s:tag+s
    ch=c.get('ch',5e-15) if cap is None else cap
    vdd=c.get('vdd',.9); lines=[]
    # Eight lanes; frozen snapshot has four tracking, four holding.
    for lane in range(8):
        clk=n('ck%d'%lane); clkb=n('kb%d'%lane)
        if clocked:
            delay=100e-12+lane*UI
            period=8*UI; rise=1e-12
            width=period/2-rise
            lines+=['%s (%s 0) vsource type=pulse val0=0 val1=%g delay=%g rise=%g fall=%g width=%g period=%g'%(name('CK%d'%lane),clk,vdd,delay,rise,rise,width,period),
                    '%s (%s 0) vsource type=pulse val0=%g val1=0 delay=%g rise=%g fall=%g width=%g period=%g'%(name('KB%d'%lane),clkb,vdd,delay,rise,rise,width,period)]
        else:
            clk=n('vdd') if lane<4 else '0'
            clkb='0' if lane<4 else n('vdd')
        for side in ['p','m']:
            hold=n('h%d%s'%(lane,side)); out=n('o_'+side)
            lines+=[mos(name('SN%d%s'%(lane,side)),hold,clk,out,'0',w=c.get('wn_sw',3e-6)),
                    mos(name('SP%d%s'%(lane,side)),hold,clkb,out,n('vdd'),pmos=True,w=c.get('wp_sw',3e-6)),
                    '%s (%s 0) capacitor c=%g'%(name('CH%d%s'%(lane,side)),hold,ch),
                    '%s (%s %s) resistor r=1T'%(name('RH%d%s'%(lane,side)),hold,out)]
    saves=[n('h0p'),n('h0m')]
    if clocked:
        saves += [n('h%d%s'%(lane,side)) for lane in range(8) for side in ['p','m']]
        saves += [n('ck%d'%lane) for lane in range(8)]+[n('kb%d'%lane) for lane in range(8)]
        saves += [name('CK%d'%lane)+':p' for lane in range(8)]+[name('KB%d'%lane)+':p' for lane in range(8)]
    return lines,saves

def invcircuit(c,tag,mode='ac',vinpp=.1,freq=56e9,cap=None,clocked=False):
    n=lambda s:tag+'_'+s; name=lambda s:tag+s
    vdd=c.get('vdd',.9)
    lines=['%s (%s 0) vsource dc=%g'%(name('Vs'),n('vdd'),vdd),
           '%s (%s 0) vsource dc=%g'%(name('Vcm'),n('cm'),c.get('cm',.45))]
    stim='dc=0 mag=0.5'
    if mode=='tran': stim='type=sine dc=0 ampl=%g freq=%g'%(vinpp/4,freq)
    lines+=['%s (%s %s) vsource %s'%(name('Vin'),n('ip'),n('cm'),stim),
            '%s (%s %s %s %s) vcvs gain=-1'%(name('Ein'),n('im'),n('cm'),n('ip'),n('cm'))]
    for side,gate,out in [('p','ip','c_p'),('m','im','c_m')]:
        sn=n('s1_'+side); sp=n('p1_'+side)
        if c['rdeg']:
            lines+=['%s (%s 0) resistor r=%g'%(name('RN'+side),sn,c['rdeg']),
                    '%s (%s %s) resistor r=%g'%(name('RP'+side),n('vdd'),sp,c['rdeg']),
                    '%s (%s 0) capacitor c=%g'%(name('CN'+side),sn,c['cdeg']),
                    '%s (%s %s) capacitor c=%g'%(name('CP'+side),n('vdd'),sp,c['cdeg'])]
        else:
            lines+=['%s (%s 0) vsource dc=0'%(name('ZN'+side),sn),
                    '%s (%s %s) vsource dc=0'%(name('ZP'+side),sp,n('vdd'))]
        for j in range(c['nc']):
            lines+=[mos(name('N1%s%d'%(side,j)),n(out),n(gate),sn,'0',w=2e-6),
                    mos(name('P1%s%d'%(side,j)),n(out),n(gate),sp,n('vdd'),True,w=3e-6)]
        # Large but explicit coupling capacitor and resistive DC self bias.
        ig=n('g2_'+side); oo=n('o_'+side)
        lines+=['%s (%s %s) capacitor c=200f'%(name('CC'+side),n(out),ig),
                '%s (%s %s) resistor r=100k'%(name('RB'+side),oo,ig),
                '%s (%s 0) vsource dc=0'%(name('Z2'+side),n('s2_'+side))]
        for j in range(c['nv']):
            lines+=[mos(name('N2%s%d'%(side,j)),oo,ig,'0','0',w=2e-6),
                    mos(name('P2%s%d'%(side,j)),oo,ig,n('vdd'),n('vdd'),True,w=3e-6)]
    ll,ss=sampler(c,tag,clocked,cap); lines+=ll
    saves=[n(s) for s in ['ip','im','c_p','c_m','o_p','o_m','s1_p','s1_m','s2_p','s2_m']]+[name('Vs')+':p']+ss
    return lines,saves

def run(directory,lines,timeout=90):
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'bench.scs').write_text('\n'.join(lines)+'\n')
    command=[SPECTRE,'-64','bench.scs','-format','psfascii','-raw','raw','+log','spectre.log','+lqtimeout','30']
    started=time.time()
    try:
        with (directory/'console.log').open('w') as f:
            r=subprocess.run(command,cwd=str(directory),stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
        code=r.returncode
    except subprocess.TimeoutExpired: code='timeout'
    log=(directory/'spectre.log').read_text(errors='replace') if (directory/'spectre.log').exists() else ''
    result={'exit_code':code,'seconds':round(time.time()-started,3),'issue_codes':sorted(set(re.findall(r'\b(?:SFE|SPECTRE)-\d+\b',log))),
            'audit':re.findall(r'spectre completes with.*',log)[-1:]}
    (directory/'run_status.json').write_text(json.dumps(result,indent=2))
    if code!=0:
        result['error_lines']=[x for x in log.splitlines() if 'ERROR' in x or 'Error' in x][-12:]
        print(json.dumps(result),flush=True)
    return result

def analyze_ac(directory,c,tag):
    dc=parse_file(directory/'raw/dcOp.dc'); ac=parse_file(directory/'raw/acResponse.ac')
    n=lambda s:tag+'_'+s
    f=ac.values['freq']; diff=lambda p,m:[a-b for a,b in zip(ac.values[n(p)],ac.values[n(m)])]
    vin=diff('ip','im'); vo=diff('o_p','o_m'); vh=diff('h0p','h0m')
    if any(abs(v-1)>1e-7 for v in vin): raise ValueError('Differential AC input not 1V')
    h=[a/b for a,b in zip(vo,vin)]; hs=[a/b for a,b in zip(vh,vin)]
    ah=[abs(x) for x in h]; peak=max(range(len(ah)),key=lambda i:ah[i])
    point=lambda p:dc.values[n(p)][0]
    h1=abs(at(f,h,1e9)); h56=abs(at(f,h,56e9)); s56=abs(at(f,hs,56e9))
    power=-c.get('vdd',.9)*dc.values[tag+'Vs:p'][0]
    cm=(point('o_p')+point('o_m'))/2
    return {'config':c,'tag':tag,'power_W':power,'gain_1GHz_VV':h1,'gain_56GHz_VV':h56,'gain_56GHz_dB':20*math.log10(h56),
            'peaking_56_vs_1GHz_dB':20*math.log10(h56/h1),'peak_Hz':f[peak],'peak_relative_1GHz_dB':20*math.log10(ah[peak]/h1),
            'hold_gain_56GHz_VV':s56,'hold_gain_56GHz_dB':20*math.log10(s56),'track_switch_loss_56GHz_dB':20*math.log10(s56/h56),
            'output_common_mode_V':cm,'ctle_common_mode_V':(point('c_p')+point('c_m'))/2,
            'source1_V':point('s1_p'),'source2_V':point('s2_p'),
            'static_headroom_ok':all(.08<point(x)<c.get('vdd',.9)-.08 for x in (['c_p','c_m','o_p','o_m'] if c.get('arch')=='inverter' else ['c_p','c_m','o_p','o_m','s1_p','s2_p'])),
            'sha256':{'ac':ac.sha256,'dc':dc.sha256},'directory':str(directory)}

def grid(limit=None):
    # Initial grid trades widths, bias and resistive loads; no peaking inductors.
    records=[]; configs=[]
    for nc,nv,rc,rv,vb,eq in itertools.product([2,4,8,16],[2,4,8],[100,200],[75,150],[.48,.58],[(0,0),(2000,4e-15),(8000,1e-15)]):
        configs.append({'nc':nc,'nv':nv,'rc':rc,'rv':rv,'vb':vb,'rdeg':eq[0],'cdeg':eq[1],'ch':5e-15,'cm':.6,'vdd':.9})
    summary=BASE/'grid_v2_summary.json'
    if summary.exists(): records=json.loads(summary.read_text())['results']
    start=len(records)
    total=len(configs) if limit is None else min(limit,len(configs))
    for batch in range(start,total,12):
        subset=configs[batch:batch+12]; directory=BASE/'grid_v2'/('b%03d'%(batch//12))
        lines=header(); saves=[]
        for i,c in enumerate(subset):
            tag='X%d'%i; ll,ss=circuit(c,tag); lines+=ll; saves+=ss
        lines+=['saveOptions options save=selected currents=selected','save '+' '.join(saves),'dcOp dc','acResponse ac start=100M stop=150G dec=35']
        status=run(directory,lines,timeout=120)
        if status['exit_code']==0:
            for i,c in enumerate(subset):
                try: rec=analyze_ac(directory,c,'X%d'%i); rec['run_status']=status; records.append(rec)
                except Exception as e: records.append({'config':c,'analysis_error':repr(e),'directory':str(directory)})
        else: records.append({'batch':batch,'run_status':status})
        summary.write_text(json.dumps({'kind':'frozen 4-on/4-off eight-lane transmission-gate load','results':records},indent=2,allow_nan=False))
        valid=[x for x in records if x.get('static_headroom_ok')]
        best=max(valid,key=lambda x:x['hold_gain_56GHz_VV']) if valid else None
        print(json.dumps({'completed':batch+len(subset),'total':len(configs),'valid_count':len(valid),'best':{k:best[k] for k in ['config','gain_56GHz_dB','hold_gain_56GHz_dB','peaking_56_vs_1GHz_dB','power_W']} if best else None}),flush=True)

def refine():
    records=json.loads((BASE/'grid_v2_summary.json').read_text())['results']
    for source in ['expanded_summary.json','inverter_summary.json','double_eq_summary.json']:
        if (BASE/source).exists(): records+=json.loads((BASE/source).read_text())['results']
    valid=[r for r in records if r.get('static_headroom_ok')]
    selected=[]
    for score in [lambda r:r['hold_gain_56GHz_VV'],lambda r:r['hold_gain_56GHz_VV']/math.sqrt(r['power_W']),lambda r:r['peaking_56_vs_1GHz_dB'] if r['hold_gain_56GHz_dB']>-10 else -100]:
        for r in sorted(valid,key=score,reverse=True)[:2]:
            if r['config'] not in selected: selected.append(r['config'])
    results=[]
    for index,(c,ch) in enumerate(itertools.product(selected,[5e-15,10e-15,20e-15])):
        c=dict(c,ch=ch); directory=BASE/'refine'/('r%02d'%index)
        lines=header(); ll,saves=circuit(c,'X'); lines+=ll
        lines+=['saveOptions options save=selected currents=selected','save '+' '.join(saves),'dcOp dc',
                'acResponse ac start=100M stop=150G dec=60',
                'noiseResponse (X_o_p X_o_m) noise start=1M stop=150G dec=60 iprobe=XVin',
                'noiseHold (X_h0p X_h0m) noise start=1M stop=150G dec=60 iprobe=XVin']
        status=run(directory,lines,120)
        if status['exit_code']==0:
            r=analyze_ac(directory,c,'X'); r['run_status']=status
            noise=parse_file(directory/'raw/noiseResponse.noise'); held=parse_file(directory/'raw/noiseHold.noise')
            for label,d in [('output',noise),('track_hold',held)]:
                if d.unit('out')!='V/sqrt(Hz)': raise ValueError('Unverified noise units')
                ff=d.values[d.sweep_names[0]]; aa=d.values['out']
                r[label+'_noise_1MHz_to_56GHz_Vrms']=noise_band(ff,aa,1e6,56e9)
                r[label+'_noise_1MHz_to_150GHz_Vrms']=noise_band(ff,aa,1e6,150e9)
                r[label+'_noise_56GHz_V_sqrtHz']=at(ff,aa,56e9)
                r['sha256'][label+'_noise']=d.sha256
            results.append(r)
        else: results.append({'config':c,'run_status':status})
        (BASE/'refine_summary.json').write_text(json.dumps({'kind':'AC noise, frozen clock snapshot; excludes sampled-noise folding','results':results},indent=2,allow_nan=False))
        print(json.dumps(results[-1]),flush=True)

def additional_grid(arch):
    configs=[]
    if arch=='inverter':
        for nc,nv,rs,cs in itertools.product([2,4,8,16],[2,4,8,16],[0,25,100,200],[20e-15,80e-15,200e-15]):
            if rs==0 and cs!=20e-15: continue
            configs.append({'arch':'inverter','nc':nc,'nv':nv,'rdeg':rs/nc,'cdeg':cs*nc,'per_copy_rs':rs,'per_copy_cs':cs,'ch':5e-15,'cm':.45,'vdd':.9,'vb':0})
        filename='inverter_summary.json'
    elif arch=='double_eq':
        for nc,nv,rc,rv,rd,cd in itertools.product([8,16],[8,16],[50,100],[50,100],[1000,4000,8000],[20e-15,80e-15]):
            configs.append({'arch':'cml','nc':nc,'nv':nv,'rc':rc,'rv':rv,'vb':.58,'rdeg':rd,'cdeg':cd,'rdeg2':rd,'cdeg2':cd,'ch':5e-15,'cm':.6,'vdd':.9})
        filename='double_eq_summary.json'
    else:
        for nc,nv,rc,rv,vb,rd,cd in itertools.product([8,16],[8,16],[50,100],[50,100],[.48,.58],[500,2000,8000],[20e-15,80e-15,200e-15]):
            configs.append({'arch':'cml','nc':nc,'nv':nv,'rc':rc,'rv':rv,'vb':vb,'rdeg':rd,'cdeg':cd,'ch':5e-15,'cm':.6,'vdd':.9})
        filename='expanded_summary.json'
    records=[]
    for batch in range(0,len(configs),12):
        subset=configs[batch:batch+12]; directory=BASE/arch/('b%03d'%(batch//12))
        lines=header(); saves=[]
        for i,c in enumerate(subset):
            ll,ss=circuit(c,'X%d'%i); lines+=ll; saves+=ss
        lines+=['saveOptions options save=selected currents=selected','save '+' '.join(saves),'dcOp dc','acResponse ac start=100M stop=150G dec=35']
        status=run(directory,lines,120)
        if status['exit_code']==0:
            for i,c in enumerate(subset):
                r=analyze_ac(directory,c,'X%d'%i); r['run_status']=status; records.append(r)
        else: records.append({'run_status':status,'batch':batch})
        (BASE/filename).write_text(json.dumps({'kind':arch+' with frozen four-on/four-off MOS sampler','results':records},indent=2,allow_nan=False))
        valid=[r for r in records if r.get('static_headroom_ok')]
        best=max(valid,key=lambda r:r['hold_gain_56GHz_VV']) if valid else None
        print(json.dumps({'arch':arch,'completed':batch+len(subset),'total':len(configs),'best':{k:best[k] for k in ['config','hold_gain_56GHz_dB','peaking_56_vs_1GHz_dB','power_W']} if best else None}),flush=True)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('phase',choices=['grid','refine','expanded','inverter','double_eq']); ap.add_argument('--limit',type=int); args=ap.parse_args()
    BASE.mkdir(parents=True,exist_ok=True)
    if args.phase=='grid': grid(args.limit)
    elif args.phase=='refine': refine()
    else: additional_grid('cml' if args.phase=='expanded' else args.phase)

if __name__=='__main__': main()
