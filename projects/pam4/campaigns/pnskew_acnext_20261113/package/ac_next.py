"""Stage and run the reviewed sparse AC bench for the next PAM4 deskew revision."""
import argparse
import math
import os
from pathlib import Path
import re
import sys

import comp_cell as base
import comp_measure as measure
import olympus_common as common

ROOT = Path(__file__).resolve().parent
NOMINAL = ('tt', 25, .90)
CORNERS = (NOMINAL, ('ss', 85, .81), ('ff', -40, .99))
PORTS = ('PNC_PREP','PNC_PREN','X_ip','X_im','X_o_p','X_o_m','X_h0p','X_h0m','XVin:p','PNCVN:p')


def build_plan():
    rows = []
    def add(corner, variant, p, n, rs=25, rt=25, load='r3'):
        process,t,v = corner
        for drive in ('p','n'):
            case_id = 'acnext_%s_%s%02d_v%03d_%s_%02d_%02d_r%d_t%d_%s_%s' % (
                process,'m' if t<0 else 'p',abs(t),round(v*100),variant,p,n,rs,rt,load,drive)
            rows.append(dict(case_id=case_id,process=process,temperature_C=t,vdd_V=v,kind='ac',
                variant=variant,p_code=p,n_code=n,source_ohm=rs,termination_ohm=rt,load=load,drive=drive,
                cpus=1,memory_GiB=4,wall_limit_min=30,
                estimated_solver_s=[1,8] if variant.startswith('lc') else [1,15]))
    for corner in CORNERS:
        add(corner,'bypass',0,0)
        for variant in ('ttd_selected','ttd_switch'):
            for p,n in ((6,16),(16,6),(6,6)):
                add(corner,variant,p,n)
    # The missing mirror at the carry, both equal-code controls, and both
    # internal mirrors of 16/47 and 48/15, under the original r0 25-ohm fixture.
    for p,n in ((15,48),(30,33),(31,32),(31,31),(32,31),(32,32),(33,30),(47,16)):
        add(NOMINAL,'lc_native',p,n,25,0)
    # Same circuit and load with an ideal connected capacitance, then add only
    # a declared series switch resistance, then replace the coupled load.
    for variant,load in (('lc_ideal','r3'),('lc_ron','r3'),('lc_ideal','cap')):
        for p,n in ((0,63),(31,32),(32,31)):
            add(NOMINAL,variant,p,n,25,0,load)
    add(NOMINAL,'bypass',0,0,25,0,'cap')
    for rs,rt in ((0,25),(25,0),(0,0)):
        add(NOMINAL,'ttd_switch',6,16,rs,rt)
        add(NOMINAL,'bypass',0,0,rs,rt)
    add(NOMINAL,'ttd_switch',6,15)
    add(NOMINAL,'ttd_switch',7,16)
    return {'format':'pam4_acnext_sparse_v1','status':'REVIEW_PENDING','cases':rows,
            'reference_fixture':'25 ohm per-leg Thevenin series and 25 ohm per-leg output termination to X_cm',
            'case_scope':'AC/DC/track noise only. No pilot, transient, payload, full codebook or device sweep.',
            'solver':'Olympus Spectre 23.1 classic +mt=1, Python 3.11, existing private shrink tree'}


def passive_path(lines, name, start, end, count):
    """25-ohm short-section T ladder. The ideal passives are explicitly provisional."""
    for k in range(count):
        s = name+'%02d'%k
        out = end if k==count-1 else s+'O'
        lines.extend(('%sLA (%s %sA) inductor l=6.5p'%(s,start,s),
                      '%sRA (%sA %sM) resistor r=0.1525'%(s,s,s),
                      '%sC (%sM 0) capacitor c=20.8f'%(s,s),
                      '%sLB (%sM %sB) inductor l=6.5p'%(s,s,s),
                      '%sRB (%sB %s) resistor r=0.1525'%(s,s,out)))
        start=out


def switch_cards(parent):
    cards = {}
    for key,name,model in (('N','XSN0p','nmos_lvt'),('P','XSP0p','pmos_lvt')):
        pattern = r'^'+name+r' \([^\n]*\) ('+model+r' l=30n w=3u multi=1 nf=1 [^\n]+)$'
        hit = re.search(pattern,parent,re.M)
        common.need(hit is not None,'Missing original 3 um gate card '+name)
        cards[key]=hit.group(1)
    return cards


def ttd_lines(case,cards):
    lines=['// BEGIN ACNEXT: 25-ohm fixed unit delay sections']
    vdd=case['vdd_V']
    native=case['variant']=='ttd_switch'
    extra_nodes=[]
    rails={}
    if native:
        rails['ACNVDD:p']=vdd
        lines.append('ACNVDD (ACN_VDD 0) vsource dc=%.9g'%vdd)
    for leg,pre,out,code in zip('PN',('PNC_PREP','PNC_PREN'),('X_ip','X_im'),
                                (case['p_code'],case['n_code'])):
        tag='ACN'+leg
        pin=pre
        rs=case['source_ohm']
        if rs:
            pin=out if case['variant']=='bypass' else tag+'I'
            lines.append('%sRS (%s %s) resistor r=%d'%(tag,pre,pin,rs))
        if case['termination_ohm']:
            lines.append('%sRT (%s X_cm) resistor r=%d'%(tag,out,case['termination_ohm']))
        if case['variant']=='bypass':
            if not rs:
                lines.append('%sBYP (%s %s) vsource dc=0'%(tag,pre,out))
            continue
        if not native:
            passive_path(lines,tag,pin,out,code)
            continue
        # Fast 6 sections and a selected slow route. Native TGs at both ends
        # isolate the unused path. A 6/6 case uses 6+16 on each side, fast selected.
        for route,sections,on in (('F',6,code==6),('S',16 if code==6 else code,code!=6)):
            name=tag+route
            for gate,voltage in (('N',vdd if on else 0.),('P',0. if on else vdd)):
                source=name+'V'+gate
                rails[source+':p']=voltage
                lines.append('%s (%sG%s 0) vsource dc=%.9g'%(source,name,gate,voltage))
            i,o=name+'I',name+'O'
            for edge,x,y in (('A',i,pin),('B',o,out)):
                lines.extend(('%s%sN (%s %sGN %s 0) %s'%(name,edge,x,name,y,cards['N']),
                              '%s%sP (%s %sGP %s ACN_VDD) %s'%(name,edge,x,name,y,cards['P'])))
            lines.append('%sBIAS (%s X_cm) resistor r=1T'%(name,i))
            passive_path(lines,name,i,o,sections)
            extra_nodes.extend((i,o))
        extra_nodes.append(pin)
    return '\n'.join(lines+['// END ACNEXT','']),rails,extra_nodes


def lc_lines(case,r5):
    circuit=base.trim_lines(case['p_code'],case['n_code'],base.device_cards(r5),
                            case['vdd_V'],case['source_ohm'])
    if case['variant']!='lc_native':
        result=[]
        for line in circuit.splitlines():
            if re.match(r'PNC[PN]\d(?:TN|TP|CB|RB\d)',line):
                continue
            result.append(line)
        for leg,code in zip('PN',(case['p_code'],case['n_code'])):
            for section in range(4):
                stem='PNC%s%d'%(leg,section)
                for bit,value in enumerate(base.CAP_WEIGHTS_FF):
                    if not code & (1<<bit):
                        continue
                    pin=stem+'M'
                    if case['variant']=='lc_ron':
                        pin=stem+'C%d'%bit
                        result.append('%sRD%d (%sM %s) resistor r=50'%(stem,bit,stem,pin))
                    result.append('%sCI%d (%s 0) capacitor c=%gf'%(stem,bit,pin,value))
        circuit='\n'.join(result)+'\n'
    rails={'PNCVTRIM:p':case['vdd_V']}
    for leg,code in zip('PN',(case['p_code'],case['n_code'])):
        for bit in range(6):
            for g in 'NP':
                rails['PNC%sV%s%d:p'%(leg,g,bit)]=case['vdd_V'] if (g=='N')==bool(code&(1<<bit)) else 0.
    extra=['PNCPS','PNCNS','PNCP0M','PNCN0M']
    if case['variant']=='lc_native':
        extra.extend('PNC%s0C%d'%(leg,b) for leg in 'PN' for b in range(6))
    return circuit,rails,extra


def render(case,model_root):
    parent,r5=base.load_inputs()
    process=case['process']
    original='include "'+base.MODEL_TOKEN+'/models/spectre/pdk_toplevel.scs" section=tt'
    inc=original.replace(base.MODEL_TOKEN,model_root) if process=='tt' else (
        'include "la5_foundry_corners.scs" section=top_'+process)
    text=base.replace_once(parent,original,inc)
    text=base.replace_once(text,'options temp=25 tnom=25','options temp=%d tnom=25'%case['temperature_C'])
    text=base.replace_once(text,'XVs (X_vdd 0) vsource dc=0.9',
                           'XVs (X_vdd 0) vsource dc=%.9g'%case['vdd_V'])
    a,b=(1,0) if case['drive']=='p' else (0,1)
    sources='XVin (PNC_PREP X_cm) vsource dc=0 mag=%d\nPNCVN (PNC_PREN X_cm) vsource dc=0 mag=%d\n'%(a,b)
    if case['variant'].startswith('lc'):
        cell,rails,extra=lc_lines(case,r5)
    else:
        cell,rails,extra=ttd_lines(case,switch_cards(r5))
    text=base.replace_once(text,'XVin (X_ip X_cm) vsource dc=0 mag=0.5\nXEin (X_im X_cm X_ip X_cm) vcvs gain=-1\n',sources+cell)
    rails=dict(rails, **{'XVs:p':case['vdd_V'],'XVcm:p':.7})
    ports=list(PORTS)
    if case['load']=='cap':
        # Standalone uncoupled capacitive control. r3 voltages/tracks do not exist.
        left=text.index('XR1p (')
        right=text.index('saveOptions options')
        text=text[:left]+('ACNCLP (X_ip 0) capacitor c=8.4f\n'
                          'ACNCLN (X_im 0) capacitor c=8.4f\n')+text[right:]
        ports=[n for n in ports if n not in ('X_o_p','X_o_m','X_h0p','X_h0m')]
    save=re.search(r'^save X_ip X_im [^\n]+$',text,re.M).group()
    text=base.replace_once(text,save,'save '+' '.join(dict.fromkeys(ports+extra+list(rails))))
    noise='noiseResponse (X_h0p X_h0m) noise start=1M stop=56G dec=40 iprobe=XVin'
    text=base.replace_once(text,noise,'noiseResponse (X_ip X_im) noise start=1M stop=56G dec=40 iprobe=XVin' if a else '// N-side AC probe only')
    text=base.replace_once(text,'acResponse ac start=1K stop=150G dec=50','acResponse ac start=1K stop=150G dec=100')
    return text,rails,list(dict.fromkeys(ports+extra)),base.unified(parent.replace(base.MODEL_TOKEN,model_root),text)


def stage(case, destination, model_path=None):
    proof, wrapper = None, None
    model_root=base.MODEL_TOKEN
    if model_path is not None:
        if case['process']=='tt':
            proof=base.model_preflight.verify_private_kit(model_path,'tt')
        else:
            wrapper,proof=base.model_preflight.stage_corner(case['process'],model_path)
        model_root=proof['model_root']
    elif case['process']!='tt':
        wrapper=(ROOT/'pvt/reference/la5_foundry_corners.scs').read_bytes()
    bench,rails,ports,diff=render(case,model_root)
    destination.mkdir()
    (destination/'bench.scs').write_bytes(bench.encode('ascii'))
    (destination/'parent_diff.txt').write_bytes(diff.encode('ascii'))
    if wrapper is not None:
        (destination/'la5_foundry_corners.scs').write_bytes(wrapper)
    case=dict(case,rail_voltages_V=rails,AC_traces=ports,model_preflight=proof,
              staged_source_sha256={p.name:common.sha(p) for p in destination.iterdir()})
    common.write_new(destination/'case.json',case)
    return case


def trace(data,name,n):
    values=data.values[name]
    common.need(len(values)==n and all(math.isfinite(z.real) and math.isfinite(z.imag) for z in values),
                'Missing or nonfinite trace '+name)
    return values


def collect(root,case,status):
    ac,dc=[measure.safe_raw(root,status,n) for n in ('acResponse.ac','dcOp.dc')]
    measure.safe_raw(root,status,'dcOpInfo.info')
    common.need(common.sha(root/'spectre.log')==status['spectre_log_sha256'] and
                all(common.sha(root/n)==h for n,h in case['staged_source_sha256'].items()), 'Input or log changed')
    fs=[x.real for x in ac.values['freq']]
    common.need(ac.sweep_names==['freq'] and len(fs)>=700 and fs[0]<=1000.01 and fs[-1]>=145e9 and
                all(0<x<y<=x*10**.010001 for x,y in zip(fs,fs[1:])), 'Incomplete AC grid')
    values={n:trace(ac,n,len(fs)) for n in case['AC_traces']}
    for n,v in zip(('PNC_PREP','PNC_PREN'),(1,0) if case['drive']=='p' else (0,1)):
        common.need(max(abs(x-v) for x in values[n])<1e-7, 'Single-leg excitation differs')
    currents={n:trace(dc,n,1)[0].real for n in case['rail_voltages_V']}
    dc_voltage={n:trace(dc,n,1)[0].real for n in ('X_ip','X_im')}
    noise=None
    if case['drive']=='p':
        raw=measure.safe_raw(root,status,'noiseResponse.noise')
        fn=[v.real for v in raw.values['freq']]
        ns=trace(raw,'out',len(fn))
        common.need(raw.unit('out')=='V/sqrt(Hz)' and fn[0]<=1.00001e6 and fn[-1]>=56e9/1.06 and
                    all(a<b for a,b in zip(fn,fn[1:])) and all(x.imag==0 and x.real>=0 for x in ns),
                    'Noise units or span differ')
        d=[x.real**2 for x in ns]
        variance=sum((a+b)*(y-x)/2 for x,y,a,b in zip(fn,fn[1:],d,d[1:]))+max(0.,56e9-fn[-1])*d[-1]
        noise={'Vrms_1MHz_to_56GHz':math.sqrt(variance),'scope':'Stationary differential X_ip-X_im'}
    report={'format':'pam4_acnext_measurement_v1','measurement_complete':True,'case_id':case['case_id'],
            'bench_sha256':common.sha(root/'bench.scs'),'run_status_sha256':common.sha(root/'run_status.json'),
            'frequency_Hz':fs,'traces':{n:[[z.real,z.imag] for z in v] for n,v in values.items()},
            'noise':noise,'DC_voltage_V':dc_voltage,'DC_supply_power_W':{
                n:-case['rail_voltages_V'][n]*i for n,i in currents.items()}}
    common.write_new(root/'measurements.json',report)
    common.write_new(root/'completion.json',{'measurement_complete':True,
                     'measurement_sha256':common.sha(root/'measurements.json'),'completed_utc':common.utc()})
    return report


def verify_package():
    for line in (ROOT/'SHA256SUMS.txt').read_text(encoding='ascii').splitlines():
        digest,n=line.split('  ',1)
        p=ROOT/n
        common.need(p.resolve().is_relative_to(ROOT) and common.sha(p)==digest, 'Unverified package file '+n)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('stage','run','verify'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--model-root',type=Path)
    p.add_argument('--approval',type=Path)
    a=p.parse_args()
    verify_package()
    if a.mode=='verify':
        print('Package SHA verified')
        return
    plan=ROOT/'case_plan.json'
    saved=common.read(plan)
    common.need(saved==build_plan() and a.root and a.index and all(0<=k<len(saved['cases']) for k in a.index),
                'Review the unchanged case plan and pass explicit indices')
    if a.mode=='stage':
        for k in a.index:
            c=saved['cases'][k]
            stage(c,a.root.resolve()/c['case_id'],a.model_root)
        return
    common.need(a.model_root and a.approval and len(a.index)==1,'Run only one approved Olympus case')
    c=saved['cases'][a.index[0]]
    approval=common.read(a.approval)
    common.need(approval['approved'] is True and approval['platform']=='Olympus' and
                approval['plan_sha256']==common.sha(plan) and
                approval['design_source_sha256']==common.sha(ROOT/'SHA256SUMS.txt') and
                c['case_id'] in approval['case_ids'],'User approval must bind the reviewed plan and case')
    from datetime import datetime,timezone,timedelta
    common.need(datetime.now(timezone.utc)+timedelta(minutes=30)<=datetime(2027,1,1,6,tzinfo=timezone.utc),
                'Run would exceed Olympus authorization through 2026-12-31')
    spectre,env=common.environment()
    dest=common.checked_root(a.root)/c['case_id']
    record=stage(c,dest,a.model_root)
    (dest/'.study_owned').write_text(os.environ['SLURM_JOB_ID']+'\n',encoding='utf-8')
    sys.path.insert(0,str(ROOT/'pvt'))
    from pvt.collect_ac import require_effective_scale
    status=common.run_classic(dest,common.sha(dest/'bench.scs'),dict(format='pam4_acnext_run_v1',
        case_id=c['case_id'],case_sha256=common.sha(dest/'case.json'),plan_sha256=common.sha(plan)),1200,spectre,env)
    require_effective_scale((dest/'spectre.log').read_bytes())
    collect(dest,record,status)
    import resource
    common.write_new(dest/'resource_observation.json',dict(spectre_wall_s=status['spectre_wall_seconds'],
        peak_child_RSS_KiB=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        raw_bytes=sum(row['bytes'] for row in status['raw_inventory'])))
    if approval.get('retire_new_raw') is True:
        receipt=common.retire_case_raw(dest,[f.name for f in dest.iterdir() if f.is_file()])
        print('Raw retirement:',receipt['status'])
    print(c['case_id'])


if __name__=='__main__':
    main()
