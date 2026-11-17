"""Reviewable AC fixtures for the PAM4 TTD selector revision."""
import argparse
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys

import ac_next as previous
import comp_measure
import olympus_common as common

ROOT = Path(__file__).resolve().parent
TT, SS, FF = previous.CORNERS
TTD_POINTS = ((6,6), (6,16), (16,6), (9,13))


def build_plan():
    cases = []

    def add(corner, topology, bias, fingers, codes=(0,0), state='na'):
        process, temp, vdd = corner
        p, n = codes
        for drive in ('p', 'n'):
            name = 'sel_%s_%s%02d_v%03d_%s_%s_f%d_%02d_%02d_%s_%s' % (
                process, 'm' if temp < 0 else 'p', abs(temp), round(vdd*100), topology,
                bias, fingers, p, n, state, drive)
            cases.append(dict(case_id=name, process=process, temperature_C=temp, vdd_V=vdd,
                kind='ac', variant=topology, bias=bias, fingers=fingers, p_code=p, n_code=n,
                state=state, drive=drive, source_ohm=25, termination_ohm=25, load='r3',
                stage='device' if topology=='device' else
                      ('tt_loaded' if corner==TT else 'corner_loaded'),
                cpus=1, memory_GiB=4, wall_limit_min=30, estimated_solver_s=[1,12]))

    for corner in (TT,SS,FF):
        options = [('native',1),('mid',1),('mid',4)] if corner==TT else [('native',1),('mid',4)]
        for bias, fingers in options:
            for state in ('on','off'):
                add(corner,'device',bias,fingers,state=state)
    for variant,bias,fingers,codes in (
        ('bypass','native',0,(0,0)),
        ('ttd_selected','native',0,(6,6)), ('ttd_selected','native',0,(6,16)),
        ('ttd_selected','native',0,(16,6)), ('ttd_selected','native',0,(9,13)),
        ('ttd_switch','native',1,(6,6)), ('ttd_on_only','native',1,(6,6)),
        ('ttd_mid_direct','mid',0,(6,6)), ('ttd_mid_direct','mid',0,(6,16)),
        ('ttd_mid_direct','mid',0,(16,6)), ('ttd_mid_direct','mid',0,(9,13)),
        ('ttd_mid_mux','mid',1,(6,6)), ('ttd_mid_on_only','mid',4,(6,6)),
        *((('ttd_mid_mux','mid',4,c) for c in TTD_POINTS)),
    ):
        add(TT,variant,bias,fingers,codes)
    for corner in (SS,FF):
        add(corner,'bypass','native',0)
        for codes in TTD_POINTS[:3]:
            add(corner,'ttd_mid_direct','mid',0,codes)
            add(corner,'ttd_mid_mux','mid',4,codes)
    return {'format':'pam4_selector_sparse_v1', 'status':'REVIEW_PENDING',
            'solver':'Olympus Spectre 23.1 classic +mt=1 and Python 3.11',
            'scope':'Device Y-parameters and loaded AC only. No transient or full code table.',
            'cases':cases}


def tg(lines, name, a, b, n_gate, p_gate, cards, fingers):
    for k in range(fingers):
        for type_, gate, body in (('N',n_gate,'0'),('P',p_gate,'SEL_VDD')):
            lines.append('%s%s%d (%s %s %s %s) %s' % (
                name,type_,k,a,gate,b,body,cards[type_]))


def supply(lines, rails, name, node, voltage):
    lines.append('%s (%s 0) vsource dc=%.9g'%(name,node,voltage))
    rails[name+':p']=voltage


def loaded_lines(case, cards):
    variant=case['variant']
    if variant in ('bypass','ttd_selected','ttd_switch'):
        return previous.ttd_lines(case,cards)
    mid=case['bias']=='mid'
    switched=variant!='ttd_mid_direct'
    off_path=variant=='ttd_mid_mux'
    lines=['// BEGIN SELECTOR: explicit local common-mode and unchanged r3 gate plane']
    rails={}
    ports=[]
    vdd=case['vdd_V']
    if mid:
        supply(lines,rails,'SELVM','SEL_VM',vdd/2)
    if switched:
        supply(lines,rails,'SELVDD','SEL_VDD',vdd)
        supply(lines,rails,'SELHI','SEL_HI',vdd)
        supply(lines,rails,'SELLO','SEL_LO',0.)
    for leg,pre,out,code in zip('PN',('PNC_PREP','PNC_PREN'),('X_ip','X_im'),
                                (case['p_code'],case['n_code'])):
        tag='SEL'+leg
        pin=tag+'IN'
        output=tag+'OUT' if mid else out
        if mid:
            # 10 pF ideal DC-block capacitor per interface. This is an AC feasibility
            # control, not a claim about physical area, Q, startup or self resonance.
            lines.extend(('%sRS (%s %sEXT) resistor r=25'%(tag,pre,tag),
                          '%sCIN (%sEXT %s) capacitor c=10p'%(tag,tag,pin),
                          '%sRB (%s SEL_VM) resistor r=100K'%(tag,pin),
                          '%sRT (%s SEL_VM) resistor r=25'%(tag,output),
                          '%sCOUT (%s %s) capacitor c=10p'%(tag,output,out),
                          '%sREST (%s X_cm) resistor r=100K'%(tag,out)))
        else:
            lines.extend(('%sRS (%s %s) resistor r=25'%(tag,pre,pin),
                          '%sRT (%s X_cm) resistor r=25'%(tag,out)))
        ports.extend((pin,output))
        if not switched:
            previous.passive_path(lines,tag,pin,output,code)
            continue
        lengths=[('SEL',code,True)]
        if off_path:
            lengths.append(('OFF',16 if code<=11 else 6,False))
        for route,count,on in lengths:
            name=tag+route
            a,b=name+'I',name+'O'
            n_gate,p_gate=('SEL_HI','SEL_LO') if on else ('SEL_LO','SEL_HI')
            tg(lines,name+'A',a,pin,n_gate,p_gate,cards,case['fingers'])
            tg(lines,name+'B',b,output,n_gate,p_gate,cards,case['fingers'])
            lines.append('%sBIAS (%s %s) resistor r=100K'%(name,a,'SEL_VM' if mid else 'X_cm'))
            previous.passive_path(lines,name,a,b,count)
            ports.extend((a,b))
    return '\n'.join(lines+['// END SELECTOR','']),rails,ports


def model_parent(case, model_root):
    parent,_=previous.base.load_inputs()
    original='include "'+previous.base.MODEL_TOKEN+'/models/spectre/pdk_toplevel.scs" section=tt'
    section=original.replace(previous.base.MODEL_TOKEN,model_root) if case['process']=='tt' else (
        'include "la5_foundry_corners.scs" section=top_'+case['process'])
    text=previous.base.replace_once(parent,original,section)
    text=previous.base.replace_once(text,'options temp=25 tnom=25',
                                    'options temp=%d tnom=25'%case['temperature_C'])
    return parent,text


def device_deck(case, model_root):
    parent, model=model_parent(case,model_root)
    _,r5=previous.base.load_inputs()
    cards=previous.switch_cards(r5)
    lines=model.splitlines()[:3]
    lines.append('// Isolated TG with hard-driven ports. Complex Y from two AC excitations.')
    vdd=case['vdd_V']
    vcm=.7 if case['bias']=='native' else vdd/2
    supply_volts={}
    for name,node,v in (('SELVDD','SEL_VDD',vdd),('SELHI','SEL_HI',vdd),('SELLO','SEL_LO',0.)):
        supply(lines,supply_volts,name,node,v)
    amp=1 if case['drive']=='p' else 0
    lines.extend(('XVin (PNC_PREP 0) vsource dc=%.9g mag=%d'%(vcm,amp),
                  'PNCVN (PNC_PREN 0) vsource dc=%.9g mag=%d'%(vcm,1-amp)))
    supply_volts.update({'XVin:p':vcm,'PNCVN:p':vcm})
    ng,pg=('SEL_HI','SEL_LO') if case['state']=='on' else ('SEL_LO','SEL_HI')
    tg(lines,'SELDUT','PNC_PREP','PNC_PREN',ng,pg,cards,case['fingers'])
    ports=['PNC_PREP','PNC_PREN','XVin:p','PNCVN:p']
    lines.extend(('saveOptions options save=selected currents=selected',
                  'save '+' '.join(dict.fromkeys(ports+list(supply_volts))),
                  'dcOp dc','dcOpInfo info what=oppoint where=rawfile',
                  'acResponse ac start=1K stop=150G dec=100'))
    return parent,'\n'.join(lines)+'\n',supply_volts,ports


def render(case,model_root):
    if case['variant']=='device':
        parent,deck,rails,ports=device_deck(case,model_root)
        dc_nodes=['PNC_PREP','PNC_PREN']
    else:
        parent,deck=model_parent(case,model_root)
        _,r5=previous.base.load_inputs()
        cell,rails,extra=loaded_lines(case,previous.switch_cards(r5))
        amp=1 if case['drive']=='p' else 0
        source=('XVin (PNC_PREP X_cm) vsource dc=0 mag=%d\n'
                'PNCVN (PNC_PREN X_cm) vsource dc=0 mag=%d\n')%(amp,1-amp)
        deck=previous.base.replace_once(deck,'XVs (X_vdd 0) vsource dc=0.9',
                        'XVs (X_vdd 0) vsource dc=%.9g'%case['vdd_V'])
        deck=previous.base.replace_once(deck,'XVin (X_ip X_cm) vsource dc=0 mag=0.5\n'
             'XEin (X_im X_cm X_ip X_cm) vcvs gain=-1\n',source+cell)
        rails.update({'XVs:p':case['vdd_V'],'XVcm:p':.7})
        ports=list(dict.fromkeys(list(previous.PORTS)+extra))
        dc_nodes=list(dict.fromkeys(['X_ip','X_im']+extra))
        save=re.search(r'^save X_ip X_im [^\n]+$',deck,re.M).group()
        deck=previous.base.replace_once(deck,save,'save '+' '.join(dict.fromkeys(ports+list(rails))))
        old='noiseResponse (X_h0p X_h0m) noise start=1M stop=56G dec=40 iprobe=XVin'
        deck=previous.base.replace_once(deck,old,'noiseResponse (X_ip X_im) noise start=1M stop=56G dec=40 iprobe=XVin'
                                        if amp else '// N-side AC probe only')
        deck=previous.base.replace_once(deck,'acResponse ac start=1K stop=150G dec=50',
                                        'acResponse ac start=1K stop=150G dec=100')
    return deck,rails,ports,dc_nodes,previous.base.unified(parent.replace(previous.base.MODEL_TOKEN,model_root),deck)


def stage(case, destination, model_path=None):
    proof,wrapper=None,None
    model_root=previous.base.MODEL_TOKEN
    if model_path is not None:
        if case['process']=='tt':
            proof=previous.base.model_preflight.verify_private_kit(model_path,'tt')
        else:
            wrapper,proof=previous.base.model_preflight.stage_corner(case['process'],model_path)
        model_root=proof['model_root']
    elif case['process']!='tt':
        wrapper=(ROOT/'pvt/reference/la5_foundry_corners.scs').read_bytes()
    deck,rails,ports,dc_nodes,diff=render(case,model_root)
    destination.mkdir()
    (destination/'bench.scs').write_bytes(deck.encode('ascii'))
    (destination/'parent_diff.txt').write_bytes(diff.encode('ascii'))
    if wrapper is not None:
        (destination/'la5_foundry_corners.scs').write_bytes(wrapper)
    record=dict(case,rail_voltages_V=rails,AC_traces=ports,DC_nodes=dc_nodes,
                model_preflight=proof,
                staged_source_sha256={p.name:common.sha(p) for p in destination.iterdir()})
    common.write_new(destination/'case.json',record)
    return record


def collect(root,case,status):
    if case['variant']=='device':
        # Reuse the original parser and the same evidence and grid checks. Isolated
        # ports have no r3 nodes or output-noise analysis.
        ac,dc=[comp_measure.safe_raw(root,status,n) for n in ('acResponse.ac','dcOp.dc')]
        fs=[x.real for x in ac.values['freq']]
        common.need(ac.sweep_names==['freq'] and len(fs)>=700 and fs[0]<=1000.01 and fs[-1]>=145e9 and
                    all(0<x<y<=x*10**.010001 for x,y in zip(fs,fs[1:])), 'Incomplete AC grid')
        vals={n:previous.trace(ac,n,len(fs)) for n in case['AC_traces']}
        for n,a in zip(('PNC_PREP','PNC_PREN'),(1,0) if case['drive']=='p' else (0,1)):
            common.need(max(abs(x-a) for x in vals[n])<1e-7,'Terminal excitation differs')
        currents={n:previous.trace(dc,n,1)[0].real for n in case['rail_voltages_V']}
        dc_voltages={n:previous.trace(dc,n,1)[0].real for n in case['DC_nodes']}
        biases=(('PNC_PREP','XVin:p'),('PNC_PREN','PNCVN:p'))
        common.need(all(abs(dc_voltages[n]-case['rail_voltages_V'][source])<1e-6
                        for n,source in biases),'Device bias differs')
        report={'format':'pam4_selector_device_v1','measurement_complete':True,'case_id':case['case_id'],
                'bench_sha256':common.sha(root/'bench.scs'),'run_status_sha256':common.sha(root/'run_status.json'),
                'frequency_Hz':fs,'traces':{n:[[z.real,z.imag] for z in v] for n,v in vals.items()},
                'DC_terminal_V':dc_voltages,
                'DC_source_currents_A':currents}
    else:
        report=previous.collect(root,case,status,write_output=False)
    op=comp_measure.safe_raw(root,status,'dcOpInfo.info')
    report['saved_mos_oppoint'] = {
        k:{key:value for key,value in records[0].items()
           if key in ('region','gm','gds','ids','vgs','vds','vth','vdsat') and isinstance(value,(int,float,str))
           and (not isinstance(value,float) or math.isfinite(value))}
        for k,records in op.values.items() if k.startswith(('SEL','ACN')) and records and isinstance(records[0],dict)}
    common.need(common.sha(root/'spectre.log')==status['spectre_log_sha256'] and
                all(common.sha(root/n)==h for n,h in case['staged_source_sha256'].items()),'Deck or log changed')
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
    previous.verify_package()
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
                'New user approval must bind this plan, package, stage and case')
    common.need(datetime.now(timezone.utc)+timedelta(minutes=30)<=datetime(2027,1,1,6,tzinfo=timezone.utc),
                'Run exceeds Olympus authorization')
    spectre,env=common.environment()
    dest=common.checked_root(a.root)/c['case_id']
    record=stage(c,dest,a.model_root)
    (dest/'.study_owned').write_text(os.environ['SLURM_JOB_ID']+'\n',encoding='utf-8')
    status=common.run_classic(dest,common.sha(dest/'bench.scs'),dict(format='pam4_selector_run_v1',
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
