"""Prepare and run a static tail-bias selection AC experiment on Olympus."""
import argparse
from datetime import datetime, timedelta, timezone
import math
import os
from pathlib import Path
import re
import sys

import ac_next as original
import comp_measure
import olympus_common as common

ROOT = Path(__file__).resolve().parent
TT, SS, FF = original.CORNERS
KEY = ('process','temperature_C','vdd_V','variant','route_a','route_b','active')


def build_plan():
    cases = []

    def add(corner, name, a=(0,0), b=(0,0), active='a', off_probe=False):
        process,temp,vdd=corner
        for drive in ('p','n'):
            prefix = 'gm_%s_%s%02d_v%03d' % (process,'m' if temp<0 else 'p',abs(temp),round(vdd*100))
            state=active+'_off' if off_probe else active
            cases.append(dict(case_id='%s_%s_%s_%s'%(prefix,name,state,drive),
                process=process,temperature_C=temp,vdd_V=vdd,kind='ac',variant=name,
                route_a=list(a),route_b=list(b),active=active,drive=drive,off_probe=off_probe,
                stage='tt' if corner==TT else 'corner',cpus=1,memory_GiB=4,wall_limit_min=30,
                estimated_solver_s=[1,12]))

    for corner in (TT,SS,FF):
        add(corner,'bypass')
        add(corner,'single_equal',(6,6))
        add(corner,'dual_equal',(6,6),(16,16))
        add(corner,'dual_end',(6,16),(16,6),'a')
        add(corner,'dual_end',(6,16),(16,6),'b')
        if corner==TT:
            add(corner,'bypass_original')
            add(corner,'single_end',(6,16))
            add(corner,'single_mid',(9,13))
            add(corner,'dual_equal',(6,6),(16,16),'b')
            add(corner,'dual_mid',(9,13),(13,9),'a')
            add(corner,'dual_mid',(9,13),(13,9),'b')
            for label, a,b,active in (
                    ('dual_equal',(6,6),(16,16),'a'),
                    ('dual_end',(6,16),(16,6),'a'),
                    ('dual_end',(6,16),(16,6),'b')):
                add(corner,label,a,b,active,True)
    return {'format':'pam4_gm_select_sparse_v1','status':'REVIEW_PENDING',
            'scope':'Static AC/DC/stationary noise, TT and two conditional corners only',
            'resources':'Olympus Spectre 23.1 classic +mt=1, Python 3.11, 1 CPU per case',
            'selectors':'Separate 0.58 V and 0 V bias buses, one whole input bank enabled. No RF switches.',
            'cases':cases}


def frontend_parts(text):
    signal, tail, bridge = {},{},{}
    other=[]
    for line in text.splitlines(keepends=True):
        name=line.split(maxsplit=1)[0] if line.strip() else ''
        if re.fullmatch(r'XM1[pm][0-7]',name):
            signal[name]=line.rstrip('\n')
        elif re.fullmatch(r'XT1[pm][0-7]',name):
            tail[name]=line.rstrip('\n')
        elif name in ('XRdeg1','XCdeg1'):
            bridge[name]=line.rstrip('\n')
        else:
            other.append(line)
    common.need(len(signal)==len(tail)==16 and len(bridge)==2,'Unexpected r3 stage-1 inventory')
    return ''.join(other),signal,tail,bridge


def geometry(line, name, nodes):
    match=re.fullmatch(r'\w+ \(([^()]*)\) (.+)',line)
    common.need(match is not None,'Unexpected native device line')
    return '%s (%s) %s'%(name,' '.join(nodes),match[2])


def banks(case, signal, tail):
    lines=['// BEGIN GMSELECT: fixed-length paths, switch only tail gate bias']
    voltage={'XVs:p':case['vdd_V'],'XVcm:p':.7,'XVb:p':.58}
    ac_ports=['PNC_PREP','PNC_PREN','X_c_p','X_c_m','X_o_p','X_o_m','X_h0p','X_h0m']
    dc_nodes=['X_c_p','X_c_m','X_o_p','X_o_m','X_cm','X_vdd','X_vb']
    dc_currents=[]
    for bank, route in (('a',case['route_a']),('b',case['route_b'])):
        if not any(route):
            continue
        enabled = bank==case['active']
        launch_on = not case['off_probe'] or not enabled
        tag='GMS'+bank.upper()
        bias='X_vb' if enabled else '0'
        sources=[]
        for leg,pre,sections in zip(('p','m'),('PNC_PREP','PNC_PREN'),route):
            prefix=tag+leg.upper()
            launch=prefix+'L'
            pin=prefix+'I'
            gate=prefix+'G'
            source=prefix+'S'
            internal_drain=prefix+'D'
            tail_ref=prefix+'Z'
            drain='X_c_'+leg
            sources.append(source)
            # Separate ideal launch buffers retain independent, explicit line
            # terminations. Their rail power and physical input load are unknown.
            lines.extend(('%sDRV (%s X_cm %s X_cm) vcvs gain=%d'%(prefix,launch,pre,int(launch_on)),
                          '%sRS (%s %s) resistor r=25'%(prefix,launch,pin),
                          '%sRT (%s X_cm) resistor r=25'%(prefix,gate),
                          '%sVD (%s %s) vsource dc=0'%(prefix,drain,internal_drain),
                          '%sVT (%s 0) vsource dc=0'%(prefix,tail_ref)))
            original.passive_path(lines,prefix,pin,gate,sections)
            for k in range(8):
                lines.append(geometry(signal['XM1%s%d'%(leg,k)],prefix+'M'+str(k),
                                      (internal_drain,gate,source,'0')))
                lines.append(geometry(tail['XT1%s%d'%(leg,k)],prefix+'T'+str(k),
                                      (source,bias,tail_ref,'0')))
            # Bleed only the idle source. In AC this stabilizes the floating node
            # without forcing its signal voltage or grounding the dormant input.
            if not enabled:
                lines.append('%sBLEED (%s %s) resistor r=100G'%(prefix,source,internal_drain))
            ac_ports.extend((gate,source,launch,pin,prefix+'DRV:p'))
            dc_nodes.extend((gate,source))
            dc_currents.extend((prefix+'VD:p',prefix+'VT:p'))
        p,n=sources
        lines.extend(('%sRD (%s %s) resistor r=250'%(tag,p,n),
                      '%sCD (%s %s) capacitor c=100f'%(tag,p,n)))
    return '\n'.join(lines+['// END GMSELECT','']),voltage,ac_ports,dc_nodes,dc_currents


def render(case, model_root):
    parent,_=original.base.load_inputs()
    if case['variant'].startswith('bypass'):
        bypass=dict(case,variant='bypass',p_code=0,n_code=0,load='r3',
                    source_ohm=0 if case['variant']=='bypass_original' else 25,
                    termination_ohm=0 if case['variant']=='bypass_original' else 25)
        deck,rails,ports,diff=original.render(bypass,model_root)
        if case['drive']=='p':
            deck=original.base.replace_once(deck,'noiseResponse (X_ip X_im) noise',
                                            'noiseResponse (X_h0p X_h0m) noise')
        return deck,rails,ports,['X_ip','X_im'],[],original.base.unified(
            parent.replace(original.base.MODEL_TOKEN,model_root),deck)
    token='include "'+original.base.MODEL_TOKEN+'/models/spectre/pdk_toplevel.scs" section=tt'
    process=case['process']
    include=token.replace(original.base.MODEL_TOKEN,model_root) if process=='tt' else (
        'include "la5_foundry_corners.scs" section=top_'+process)
    text=original.base.replace_once(parent,token,include)
    text=original.base.replace_once(text,'options temp=25 tnom=25',
                                    'options temp=%d tnom=25'%case['temperature_C'])
    text=original.base.replace_once(text,'XVs (X_vdd 0) vsource dc=0.9',
                                    'XVs (X_vdd 0) vsource dc=%.9g'%case['vdd_V'])
    text,signal,tail,bridge=frontend_parts(text)
    common.need(bridge=={'XRdeg1':'XRdeg1 (X_s1_p X_s1_m) resistor r=250',
                         'XCdeg1':'XCdeg1 (X_s1_p X_s1_m) capacitor c=1e-13'},
                'Unexpected original degeneration bridge')
    cell,rails,ports,dc_nodes,dc_currents=banks(case,signal,tail)
    p=1 if case['drive']=='p' else 0
    sources=('XVin (PNC_PREP X_cm) vsource dc=0 mag=%d\n'
             'PNCVN (PNC_PREN X_cm) vsource dc=0 mag=%d\n')%(p,1-p)
    text=original.base.replace_once(text,
        'XVin (X_ip X_cm) vsource dc=0 mag=0.5\nXEin (X_im X_cm X_ip X_cm) vcvs gain=-1\n',sources+cell)
    save=re.search(r'^save X_ip X_im [^\n]+$',text,re.M).group()
    text=original.base.replace_once(text,save,'save '+' '.join(dict.fromkeys(
        ports+dc_nodes+dc_currents+list(rails))))
    text=original.base.replace_once(text,'acResponse ac start=1K stop=150G dec=50',
                                    'acResponse ac start=1K stop=150G dec=100')
    noise='noiseResponse (X_h0p X_h0m) noise start=1M stop=56G dec=40 iprobe=XVin'
    if not p or case['off_probe']:
        text=original.base.replace_once(text,noise,'// AC-only column')
    diff=original.base.unified(parent.replace(original.base.MODEL_TOKEN,model_root),text)
    return text,rails,ports,dc_nodes,dc_currents,diff


def stage(case, destination, model_path=None, renderer=None):
    proof,wrapper=None,None
    model_root=original.base.MODEL_TOKEN
    if model_path is not None:
        if case['process']=='tt':
            proof=original.base.model_preflight.verify_private_kit(model_path,'tt')
        else:
            wrapper,proof=original.base.model_preflight.stage_corner(case['process'],model_path)
        model_root=proof['model_root']
    elif case['process']!='tt':
        wrapper=(ROOT/'pvt/reference/la5_foundry_corners.scs').read_bytes()
    deck,rails,ports,dc_nodes,dc_currents,diff=(renderer or render)(case,model_root)
    destination.mkdir()
    (destination/'bench.scs').write_bytes(deck.encode('ascii'))
    (destination/'parent_diff.txt').write_bytes(diff.encode('ascii'))
    if wrapper is not None:
        (destination/'la5_foundry_corners.scs').write_bytes(wrapper)
    record=dict(case,rail_voltages_V=rails,AC_traces=ports,DC_nodes=dc_nodes,
                DC_currents=dc_currents,model_preflight=proof,
                staged_source_sha256={p.name:common.sha(p) for p in destination.iterdir()})
    common.write_new(destination/'case.json',record)
    return record


def integrate_noise(root,status):
    noise=comp_measure.safe_raw(root,status,'noiseResponse.noise')
    fs=[x.real for x in noise.values['freq']]
    ys=original.trace(noise,'out',len(fs))
    common.need(noise.unit('out')=='V/sqrt(Hz)' and fs[0]<=1.00001e6 and fs[-1]>=56e9/1.06 and
                all(a<b for a,b in zip(fs,fs[1:])) and all(y.imag==0 and y.real>=0 for y in ys),
                'Noise units or bandwidth differ')
    psd=[x.real**2 for x in ys]
    power=sum((a+b)*(y-x)/2 for x,y,a,b in zip(fs,fs[1:],psd,psd[1:]))
    power+=max(0.,56e9-fs[-1])*psd[-1]
    return math.sqrt(power)


def collect(root,case,status):
    ac,dc,op=[comp_measure.safe_raw(root,status,n) for n in
              ('acResponse.ac','dcOp.dc','dcOpInfo.info')]
    fs=[v.real for v in ac.values['freq']]
    common.need(ac.sweep_names==['freq'] and len(fs)>=700 and fs[0]<=1000.01 and fs[-1]>=145e9 and
                all(0<x<y<=x*10**.010001 for x,y in zip(fs,fs[1:])), 'Incomplete AC grid')
    values={n:original.trace(ac,n,len(fs)) for n in case['AC_traces']}
    for node,amp in zip(('PNC_PREP','PNC_PREN'),(1,0) if case['drive']=='p' else (0,1)):
        common.need(max(abs(x-amp) for x in values[node])<1e-7,'Source AC amplitude differs')
    rail={n:original.trace(dc,n,1)[0].real for n in case['rail_voltages_V']}
    op_fields=('region','gm','gds','ids','vgs','vds','vth','vdsat','vgd','vbs','vbd')
    device_op={n:{k:v for k,v in rows[0].items() if k in op_fields and
                  isinstance(v,(float,int,str)) and (not isinstance(v,float) or math.isfinite(v))}
               for n,rows in op.values.items() if rows and isinstance(rows[0],dict) and
               n.startswith(('GMS','XT1','XT2','XM1','XM2'))}
    report={'format':'pam4_gmselect_measurement_v1','measurement_complete':True,'case_id':case['case_id'],
            'bench_sha256':common.sha(root/'bench.scs'),'run_status_sha256':common.sha(root/'run_status.json'),
            'frequency_Hz':fs,'traces':{n:[[z.real,z.imag] for z in vs] for n,vs in values.items()},
            'DC_voltage_V':{n:original.trace(dc,n,1)[0].real for n in case['DC_nodes']},
            'DC_current_A':{n:original.trace(dc,n,1)[0].real for n in case['DC_currents']},
            'DC_supply_power_W':{n:-case['rail_voltages_V'][n]*i for n,i in rail.items()},
            'saved_mos_oppoint':device_op,'noise':None}
    if case['drive']=='p' and not case['off_probe']:
        report['noise']={'Vrms_1MHz_to_56GHz':integrate_noise(root,status),
            'plane':'X_h0p-X_h0m'}
    common.need(common.sha(root/'spectre.log')==status['spectre_log_sha256'] and
                all(common.sha(root/n)==h for n,h in case['staged_source_sha256'].items()),'Input or log SHA differs')
    common.write_new(root/'measurements.json',report)
    common.write_new(root/'completion.json',{'measurement_complete':True,
                    'measurement_sha256':common.sha(root/'measurements.json'),'completed_utc':common.utc()})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--model-root',type=Path)
    p.add_argument('--approval',type=Path)
    a=p.parse_args()
    original.verify_package()
    plan_path=ROOT/'case_plan.json'
    plan=common.read(plan_path)
    common.need(plan==build_plan(),'Case plan differs')
    if a.mode=='verify':
        print('Package SHA and case plan verified')
        return
    common.need(a.root and a.index and all(0<=k<len(plan['cases']) for k in a.index),
                'Provide reviewed case indices and root')
    if a.mode=='stage':
        for k in a.index:
            c=plan['cases'][k]
            stage(c,a.root.resolve()/c['case_id'],a.model_root)
        return
    common.need(a.model_root and a.approval and len(a.index)==1,'One approved Olympus case required')
    c=plan['cases'][a.index[0]]
    approval=common.read(a.approval)
    common.need(approval.get('approved') is True and approval.get('platform')=='Olympus' and
                approval.get('plan_sha256')==common.sha(plan_path) and
                approval.get('design_source_sha256')==common.sha(ROOT/'SHA256SUMS.txt') and
                c['case_id'] in approval.get('case_ids',[]) and c['stage'] in approval.get('stages',[]),
                'New approval must bind this package, plan, stage and case')
    common.need(datetime.now(timezone.utc)+timedelta(minutes=30)<=datetime(2027,1,1,6,tzinfo=timezone.utc),
                'Run exceeds Olympus authorization')
    spectre,env=common.environment()
    dest=common.checked_root(a.root)/c['case_id']
    record=stage(c,dest,a.model_root)
    (dest/'.study_owned').write_text(os.environ['SLURM_JOB_ID']+'\n',encoding='utf-8')
    status=common.run_classic(dest,common.sha(dest/'bench.scs'),dict(format='pam4_gmselect_run_v1',
        case_id=c['case_id'],case_sha256=common.sha(dest/'case.json'),plan_sha256=common.sha(plan_path)),
        1200,spectre,env)
    sys.path.insert(0,str(ROOT/'pvt'))
    from pvt.collect_ac import require_effective_scale
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
