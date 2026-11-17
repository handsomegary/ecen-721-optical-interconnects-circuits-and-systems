#!/usr/bin/env python3
"""Low-frequency-reference equalizer tuning and loaded AFE sensitivity checks."""
import itertools,json,math
import p6_bench as b
from psf_ascii import parse_file

def main():
    configs=[]
    for nc,rd in itertools.product([8,16],[1000,1500,2000,3000]):
        configs.append(dict(arch='cml',nc=nc,nv=nc,rc=50,rv=50,vb=.58,rdeg=rd,cdeg=80e-15,rdeg2=rd,cdeg2=80e-15,ch=5e-15,cm=.6,vdd=.9))
    results=[]
    for i,c in enumerate(configs):
        directory=b.BASE/'tune'/('t%02d'%i);ll,ss=b.circuit(c,'X')
        lines=b.header()+ll+['saveOptions options save=selected currents=selected','save '+' '.join(ss),'dcOp dc',
              'dcOpInfo info what=oppoint where=rawfile','acResponse ac start=1M stop=150G dec=60',
              'noiseResponse (X_h0p X_h0m) noise start=1M stop=150G dec=60 iprobe=XVin']
        status=b.run(directory,lines,120)
        if status['exit_code']==0:
            r=b.analyze_ac(directory,c,'X');a=parse_file(directory/'raw/acResponse.ac');f=a.values[a.sweep_names[0]]
            h=[x-y for x,y in zip(a.values['X_o_p'],a.values['X_o_m'])]
            r['gain_1MHz_VV']=abs(h[0]);r['peaking_56_vs_1MHz_dB']=20*math.log10(r['gain_56GHz_VV']/abs(h[0]))
            n=parse_file(directory/'raw/noiseResponse.noise');ff=n.values[n.sweep_names[0]]
            r['track_noise_1MHz_to_56GHz_Vrms']=b.noise_band(ff,n.values['out'],1e6,56e9)
            op=parse_file(directory/'raw/dcOpInfo.info');selected={}
            for key,val in op.values.items():
                if key in ['XM1p0','XT1p0','XM2p0','XT2p0'] and isinstance(val[0],dict):
                    selected[key]={k:val[0][k] for k in ['gm','gds','ids','vgs','vds','vdsat','region'] if k in val[0]}
            r['selected_primitive_op']=selected;r['run_status']=status
        else:r={'config':c,'run_status':status}
        results.append(r)
        (b.BASE/'tune_summary.json').write_text(json.dumps({'kind':'double CTLE adjustable peaking referenced to1MHz,actual static eight-way MOS sampler load','results':results},indent=2,allow_nan=False))
        print(json.dumps({k:r[k] for k in ['config','gain_56GHz_dB','hold_gain_56GHz_dB','peaking_56_vs_1MHz_dB','track_noise_1MHz_to_56GHz_Vrms','power_W'] if k in r}),flush=True)

if __name__=='__main__':main()
