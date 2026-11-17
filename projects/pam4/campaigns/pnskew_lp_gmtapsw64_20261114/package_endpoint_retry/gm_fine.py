"""PAM4 adjacent-route interpolation and physical bias/launch AC fixtures."""
import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import sys

import gm_select as gm
import olympus_common as common

ROOT=Path(__file__).resolve().parent
TT,SS,FF=gm.TT,gm.SS,gm.FF
PAIR=((6,16),(8,14))
CENTER=((10,12),(11,11))


def build_plan():
    cases=[]
    def add(corner, mode, count=0, side=1, routes=PAIR, probe='full'):
        process,temp,vdd=corner
        if side<0:
            routes=tuple(tuple(reversed(row)) for row in routes)
        for drive in ('p','n'):
            family='short' if routes[0]==(1,1) else ('edge' if max(routes[0])==16 else 'center')
            cid='fine_%s_%s%02d_v%03d_%s_%s_%s_%d_%s_%s'%(
                process,'m' if temp<0 else 'p',abs(temp),round(vdd*100),mode,family,
                'p' if side>0 else 'n',count,probe,drive)
            cases.append(dict(case_id=cid, process=process,temperature_C=temp,vdd_V=vdd,
                kind='ac',variant='bypass' if mode=='bypass' else 'fine',
                route_a=list(routes[0]),route_b=list(routes[1]),active='a',
                mode=mode, count_b=count,probe=probe,drive=drive,off_probe=probe!='full',
                stage='tt' if corner==TT else 'corner',cpus=1,memory_GiB=4,
                estimated_solver_s=[1,15],wall_limit_min=30))
    add(TT,'bypass')
    add(TT,'plain')
    add(TT,'muted')
    add(TT,'plain',probe='dormant')
    add(TT,'bias')
    add(TT,'driver')
    add(TT,'driver',probe='dormant')
    for code in range(9):
        add(TT,'interpolation',code)
    for side in (1,-1):
        for k in (2,3,4,6):
            add(TT,'driver',k,side)
        if side<0:
            add(TT,'driver',0,side)
    for k in (0,4,8):
        add(TT,'interpolation',k,routes=CENTER)
        add(TT,'driver',k,routes=CENTER)
    add(TT,'driver_open')
    add(TT,'driver_open',probe='dormant')
    add(TT,'driver',routes=((1,1),(8,14)))
    for corner in (SS,FF):
        add(corner,'bypass')
        add(corner,'muted',2)
        for side in (1,-1):
            add(corner,'driver',2,side)
            add(corner,'driver',0,side)
    return {'format':'pam4_gmfine_review_v1','status':'REVIEW_PENDING',
            'scope':'Local adjacent-bank interpolation, dormant feedthrough, native bias gates and launch AC',
            'fixed_fixture':'25 ohm terminations; original r3 load, fixed track clocks',
            'cases':cases}


def device(lines,cards,name,key,nodes):
    lines.append('%s (%s) %s'%(name,' '.join(nodes),cards[key]))


def circuit(case, signal, tail, cards):
    mode=case['mode']
    lines=['// BEGIN GMFINE']
    rails={'XVs:p':case['vdd_V'],'XVcm:p':.7,'XVb:p':.58}
    ac=['PNC_PREP','PNC_PREN','X_c_p','X_c_m','X_o_p','X_o_m','X_h0p','X_h0m','XVin:p','PNCVN:p']
    dc=['X_c_p','X_c_m','X_o_p','X_o_m','X_cm','X_vdd','X_vb']
    currents=[]
    driver=mode in ('driver','driver_open')
    physical=mode=='bias' or driver
    if physical:
        lines.extend(('GFVDD (GF_VDD 0) vsource dc=%.9g'%case['vdd_V'],
                      'GFVCTL (GF_CTL 0) vsource dc=%.9g'%case['vdd_V']))
        rails.update({'GFVDD:p':case['vdd_V'],'GFVCTL:p':case['vdd_V']})
    for bank, route, count in (('A',case['route_a'],8-case['count_b']),
                               ('B',case['route_b'],case['count_b'])):
        tag='GMS'+bank
        bias_nodes=[]
        for k in range(8):
            enabled=k<count
            node=tag+'VB%d'%k if physical else ('X_vb' if enabled else '0')
            bias_nodes.append(node)
            if physical:
                n,p=tag+'EN%d'%k,tag+'EB%d'%k
                en=tag+'VE%d'%k
                voltage=case['vdd_V'] if enabled else 0.
                lines.append('%s (%s 0) vsource dc=%.9g'%(en,n,voltage))
                rails[en+':p']=voltage
                device(lines,cards,tag+'IN%d'%k,'N',(p,n,'0','0'))
                device(lines,cards,tag+'IP%d'%k,'P',(p,n,'GF_VDD','GF_VDD'))
                device(lines,cards,tag+'BN%d'%k,'N',(node,n,'X_vb','0'))
                device(lines,cards,tag+'BP%d'%k,'P',(node,p,'X_vb','GF_VDD'))
                device(lines,cards,tag+'BD%d'%k,'N',(node,p,'0','0'))
                lines.append('%sBR%d (%s 0) resistor r=100Meg'%(tag,k,node))
        dc.extend(n for n in bias_nodes if n!='0')
        active_ac=case['probe']!='dormant' or count==0
        mute=mode in ('muted','interpolation') and count==0
        sources=[]
        for leg,pre,length in zip(('p','m'),('PNC_PREP','PNC_PREN'),route):
            prefix=tag+leg.upper()
            launch,pin,gate,src,dr,zero=(prefix+x for x in ('L','I','G','S','D','Z'))
            sources.append(src)
            launch_in=prefix+'VIN'
            if driver:
                if active_ac:
                    lines.append('%sDRV (%s %s) vsource dc=0'%(prefix,pre,launch_in))
                else:
                    lines.append('%sDRV (%s X_cm) vsource dc=0'%(prefix,launch_in))
            else:
                lines.append('%sDRV (%s X_cm %s X_cm) vcvs gain=%d'%(
                    prefix,launch,pre,int(active_ac and not mute)))
            if driver:
                fg,fo=prefix+'FG',prefix+'FO'
                vgate=.10 if count==0 else .65
                lines.extend(('%sVFG (%sVGB 0) vsource dc=%.9g'%(prefix,prefix,vgate),
                              '%sCIN (%s %s) capacitor c=10p'%(prefix,launch_in,fg),
                              '%sGB (%s %sVGB) resistor r=10K'%(prefix,fg,prefix),
                              '%sLOAD (%s 0) resistor r=120'%(prefix,fo),
                              '%sCOUT (%s %s) capacitor c=10p'%(prefix,fo,launch),
                              '%sLB (%s X_cm) resistor r=100K'%(prefix,launch)))
                for k in range(8):
                    lines.append(gm.geometry(signal['XM1p%d'%k],prefix+'F%d'%k,
                                              ('GF_VDD',fg,fo,'0')))
                rails[prefix+'VFG:p']=vgate
                # Quiet the idle follower source before the DC block. The line
                # termination and its 0.7 V gate bias stay connected.
                for k in range(4):
                    clamp='GF_CTL' if count==0 and mode=='driver' else '0'
                    device(lines,cards,prefix+'CL%d'%k,'N',(fo,clamp,'0','0'))
                dc.extend((fg,fo))
                ac.extend((launch_in,fg,fo))
            lines.extend(('%sRS (%s %s) resistor r=%d'%(prefix,launch,pin,10 if driver else 25),
                          '%sRT (%s X_cm) resistor r=25'%(prefix,gate),
                          '%sVD (X_c_%s %s) vsource dc=0'%(prefix,leg,dr),
                          '%sVT (%s 0) vsource dc=0'%(prefix,zero)))
            gm.original.passive_path(lines,prefix,pin,gate,length)
            for k in range(8):
                lines.append(gm.geometry(signal['XM1%s%d'%(leg,k)],prefix+'M%d'%k,(dr,gate,src,'0')))
                lines.append(gm.geometry(tail['XT1%s%d'%(leg,k)],prefix+'T%d'%k,(src,bias_nodes[k],zero,'0')))
            if count==0:
                lines.append('%sBLEED (%s %s) resistor r=100G'%(prefix,src,dr))
            ac.extend((gate,src,launch,pin,prefix+'DRV:p'))
            dc.extend((gate,src,launch))
            currents.extend((prefix+'VD:p',prefix+'VT:p'))
        lines.extend(('%sRD (%s %s) resistor r=250'%(tag,*sources),
                      '%sCD (%s %s) capacitor c=100f'%(tag,*sources)))
    return '\n'.join(lines+['// END GMFINE','']),rails,ac,list(dict.fromkeys(dc)),currents


def render(case, model_root):
    if case['mode']=='bypass':
        return gm.render(case,model_root)
    parent,r5=gm.original.base.load_inputs()
    old='include "'+gm.original.base.MODEL_TOKEN+'/models/spectre/pdk_toplevel.scs" section=tt'
    text=gm.original.base.replace_once(parent,old,old.replace(gm.original.base.MODEL_TOKEN,model_root)
        if case['process']=='tt' else 'include "la5_foundry_corners.scs" section=top_'+case['process'])
    text=gm.original.base.replace_once(text,'options temp=25 tnom=25','options temp=%d tnom=25'%case['temperature_C'])
    text=gm.original.base.replace_once(text,'XVs (X_vdd 0) vsource dc=0.9',
                                      'XVs (X_vdd 0) vsource dc=%.9g'%case['vdd_V'])
    text,signal,tail,bridge=gm.frontend_parts(text)
    common.need(bridge=={'XRdeg1':'XRdeg1 (X_s1_p X_s1_m) resistor r=250',
                         'XCdeg1':'XCdeg1 (X_s1_p X_s1_m) capacitor c=1e-13'},
                'Unexpected original degeneration bridge')
    cell,rails,ac,dc,currents=circuit(case,signal,tail,gm.original.base.device_cards(r5))
    p=int(case['drive']=='p')
    sources=('XVin (PNC_PREP X_cm) vsource dc=0 mag=%d\n'
             'PNCVN (PNC_PREN X_cm) vsource dc=0 mag=%d\n')%(p,1-p)
    text=gm.original.base.replace_once(text,'XVin (X_ip X_cm) vsource dc=0 mag=0.5\n'
        'XEin (X_im X_cm X_ip X_cm) vcvs gain=-1\n',sources+cell)
    save=re.search(r'^save X_ip X_im [^\n]+$',text,re.M).group()
    text=gm.original.base.replace_once(text,save,'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails))))
    text=gm.original.base.replace_once(text,'acResponse ac start=1K stop=150G dec=50',
                                       'acResponse ac start=1K stop=150G dec=100')
    if not p or case['off_probe']:
        text=gm.original.base.replace_once(text,
            'noiseResponse (X_h0p X_h0m) noise start=1M stop=56G dec=40 iprobe=XVin','// AC-only column')
    return text,rails,ac,dc,currents,gm.original.base.unified(
        parent.replace(gm.original.base.MODEL_TOKEN,model_root),text)


def stage(case,path,model_root=None):
    return gm.stage(case,path,model_root,renderer=render)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--model-root',type=Path)
    p.add_argument('--approval',type=Path)
    a=p.parse_args()
    gm.original.verify_package()
    plan=ROOT/'case_plan.json'
    data=common.read(plan)
    common.need(data==build_plan(),'Case plan differs')
    if a.mode=='verify':
        print('SHA and case plan verified')
        return
    common.need(a.root and a.index and all(0<=i<len(data['cases']) for i in a.index),'Select explicit case indices')
    if a.mode=='stage':
        for i in a.index:
            case=data['cases'][i]
            stage(case,a.root.resolve()/case['case_id'],a.model_root)
        return
    common.need(a.model_root and a.approval and len(a.index)==1,'One approved Olympus case required')
    case=data['cases'][a.index[0]]
    approval=common.read(a.approval)
    common.need(approval.get('approved') is True and approval.get('platform')=='Olympus' and
        approval.get('plan_sha256')==common.sha(plan) and
        approval.get('design_source_sha256')==common.sha(ROOT/'SHA256SUMS.txt') and
        case['case_id'] in approval.get('case_ids',[]) and case['stage'] in approval.get('stages',[]),
        'Approval does not bind the exact package and case')
    common.need(datetime.now(timezone.utc)+timedelta(minutes=30)<=datetime(2027,1,1,6,tzinfo=timezone.utc),
                'Run exceeds Olympus authorization')
    spectre,env=common.environment()
    dest=common.checked_root(a.root)/case['case_id']
    record=stage(case,dest,a.model_root)
    (dest/'.study_owned').write_text(os.environ['SLURM_JOB_ID']+'\n',encoding='utf-8')
    status=common.run_classic(dest,common.sha(dest/'bench.scs'),dict(format='pam4_gmfine_run_v1',
        case_id=case['case_id'],case_sha256=common.sha(dest/'case.json'),plan_sha256=common.sha(plan)),
        1200,spectre,env)
    sys.path.insert(0,str(ROOT/'pvt'))
    from pvt.collect_ac import require_effective_scale
    require_effective_scale((dest/'spectre.log').read_bytes())
    gm.collect(dest,record,status)
    import resource
    common.write_new(dest/'resource_observation.json',dict(spectre_wall_s=status['spectre_wall_seconds'],
        peak_child_RSS_KiB=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        raw_bytes=sum(r['bytes'] for r in status['raw_inventory'])))
    if approval.get('retire_new_raw') is True:
        receipt=common.retire_case_raw(dest,[p.name for p in dest.iterdir() if p.is_file()])
        print('Raw retirement:',receipt['status'])
    print(case['case_id'])


if __name__=='__main__':
    main()
