#!/usr/bin/env python3
"""Verify native OA netlist and a reconstructed fixture with the same cards."""
import hashlib,json,math,pathlib,re
import p6_bench as b
from psf_ascii import parse_file

PROJECT=pathlib.Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def native_cards(netlist):
    flat=netlist.replace('\\\n',' ')
    cards={}
    for key,name in [('n_l30','M1p0'),('n_l60','T1p0'),('p_l30','SP0p')]:
        m=re.search(r'^'+name+r'\s+\([^)]*\)\s+(\S+)\s+(.+)$',flat,re.M)
        if not m:raise ValueError('Native representative is missing: '+name)
        params=' '.join(m.group(2).split())
        for flag in ['_ccoflag','_rcoflag','_rgflag']:
            if not re.search(r'\b'+flag+r'=1(?:\s|$)',params):raise ValueError('Native parasitic override missing '+key+flag)
        cards[key]={'model':m.group(1),'parameters':params}
    allmos=re.findall(r'^\S+\s+\([^)]*\)\s+(?:nmos_lvt|pmos_lvt)\s+(.+)$',flat,re.M)
    if len(allmos)!=96:raise ValueError('Unexpected native MOS count')
    for params in allmos:
        for flag in ['_ccoflag','_rcoflag','_rgflag']:
            if not re.search(r'\b'+flag+r'=1(?:\s|$)',params):raise ValueError('Some native MOS lacks active parasitic override')
    return cards

def install_cards(cards):
    def mos(name,drain,gate,source,bulk,pmos=False,w=3e-6,l=30e-9):
        if abs(w-3e-6)>1e-15 or min(abs(l-30e-9),abs(l-60e-9))>1e-15:raise ValueError('Unsupported native geometry')
        key='p_l30' if pmos else ('n_l60' if l>45e-9 else 'n_l30')
        c=cards[key]
        return '%s (%s %s %s %s) %s %s'%(name,drain,gate,source,bulk,c['model'],c['parameters'])
    b.mos=mos

def metrics(directory,names,vdd):
    ac=parse_file(directory/'raw/acResponse.ac');dc=parse_file(directory/'raw/dcOp.dc')
    f=ac.values['freq'];ip,im,op,om,hp,hm,supply=names
    vi=[x-y for x,y in zip(ac.values[ip],ac.values[im])]
    if max(abs(x-1) for x in vi)>1e-8:raise ValueError('Differential AC normalization is incorrect')
    ho=[(x-y)/z for x,y,z in zip(ac.values[op],ac.values[om],vi)]
    hh=[(x-y)/z for x,y,z in zip(ac.values[hp],ac.values[hm],vi)]
    h56=abs(b.at(f,ho,56e9));held=abs(b.at(f,hh,56e9));peak=max(range(len(ho)),key=lambda i:abs(ho[i]))
    r={'output_gain_56GHz_VV':h56,'held_track_gain_56GHz_VV':held,'held_track_gain_56GHz_dB':20*math.log10(held),
       'output_peaking_56_vs_1kHz_dB':20*math.log10(h56/abs(ho[0])),'response_peak_Hz':f[peak],
       'VDD_power_W':-vdd*dc.values[supply][0],'output_common_mode_V':(dc.values[op][0]+dc.values[om][0])/2,
       'sha256':{'ac':ac.sha256,'dc':dc.sha256}}
    nf=directory/'raw/noiseResponse.noise'
    if nf.exists():
        n=parse_file(nf)
        if n.unit('out')!='V/sqrt(Hz)':raise ValueError('Unexpected noise density unit')
        r['track_noise_1MHz_to_56GHz_Vrms']=b.noise_band(n.values['freq'],n.values['out'],1e6,56e9)
        r['sha256']['noise']=n.sha256
    return r

def main():
    run=pathlib.Path((PROJECT/'notes/latest_oa_run.txt').read_text().strip())
    inputs=list(run.rglob('input.scs'))
    if len(inputs)!=1 or 'tb_p6_ctle_sampler_ac_r2' not in str(inputs[0]):raise ValueError('Expected completed native r2 netlist')
    source=inputs[0];text=source.read_text();cards=native_cards(text)
    cardfile=PROJECT/'configs/native_device_cards.json';cardfile.write_text(json.dumps(cards,indent=2)+'\n')
    install_cards(cards)
    circuit=text.split('simulatorOptions options')[0]
    target=PROJECT/'runs/native_baseline/oa_tt25'
    lines=circuit.splitlines()+['simulatorOptions options temp=25 tnom=25 reltol=1e-4 vabstol=1u iabstol=1p',
        'dcOp dc','acResponse ac start=1K stop=150G dec=60',
        'noiseResponse (h0p h0n) noise start=1M stop=150G dec=60 iprobe=VIN',
        'save inp inn outp outn h0p h0n VDD:p','saveOptions options save=selected currents=selected']
    status=b.run(target,lines,120)
    if status['exit_code']!=0:raise ValueError(status)
    native=metrics(target,('inp','inn','outp','outn','h0p','h0n','VDD:p'),.9);native['run_status']=status
    baseline=json.loads((PROJECT/'baseline/feasibility_results.json').read_text())
    config=baseline['CTLE_adjustable_peaking_range_confirmation']['results'][0]['config']
    cases=[]
    for name,section,temp,vdd in [('tt25', 'tt',25,.9),('ss85_v081','ss',85,.81),('ffm40_v099','ff',-40,.99)]:
        c=dict(config,vdd=vdd);directory=PROJECT/'runs/native_baseline'/name
        head=b.header(temp=temp)
        if section!='tt':head[1]='include "/path/to/local/cadence-home/Desktop/cadence_projects/la5_10g_20261004/scripts/la5_foundry_corners.scs" section='+section
        ll,ss=b.circuit(c,'X');lines=head+ll+['dcOp dc','acResponse ac start=1K stop=150G dec=60',
            'noiseResponse (X_h0p X_h0m) noise start=1M stop=150G dec=60 iprobe=XVin',
            'save '+' '.join(ss),'saveOptions options save=selected currents=selected']
        status=b.run(directory,lines,120)
        if status['exit_code']!=0:raise ValueError(status)
        r=metrics(directory,('X_ip','X_im','X_o_p','X_o_m','X_h0p','X_h0m','XVs:p'),vdd)
        r.update({'name':name,'model_section':section,'temperature_C':temp,'supply_V':vdd,'run_status':status});cases.append(r)
    errors={k:abs(cases[0][k]-native[k])/max(abs(native[k]),1e-12) for k in ['output_gain_56GHz_VV','held_track_gain_56GHz_VV','VDD_power_W']}
    if max(errors.values())>1e-5:raise ValueError('Native reconstruction differs: '+json.dumps(errors))
    result={'native_cell':'p6_224g_lib/tb_p6_ctle_sampler_ac_r2/schematic','native_source_netlist_sha256':sha(source),
        'native_device_cards_sha256':sha(cardfile),'all_96_native_MOS_parasitic_overrides_verified':True,
        'native_OA_TT25':native,'reconstructed_same_cards_and_topology_verified':True,'relative_reconstruction_errors':errors,
        'three_corner_smoke_results':cases,'full_PVT_or_layout_signoff':False,
        'previous_wrapper_only_TT_held_AC_gain_VV':next(r for r in baseline['CTLE_adjustable_peaking_range_confirmation']['AC_results'] if r['config']==config)['hold_gain_56GHz_VV']}
    (PROJECT/'results/native_baseline_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
