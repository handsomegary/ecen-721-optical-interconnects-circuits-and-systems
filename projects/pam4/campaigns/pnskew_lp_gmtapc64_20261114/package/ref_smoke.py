"""Isolated LP14 long-channel Iref and native replica OTA smoke fixtures."""
import argparse
from pathlib import Path
import re

import gm_select as gm
import olympus_common as common
import physical_bias as phy
from recover_bias import validate_save_currents

ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'smoke_plan.json'
BASE = gm.original.base


def build_plan():
    base = phy.build_plan()['cases']
    cases = []
    for i in (42,43,50,51):
        cases.append(dict(base[i],case_id=f'lpref_{len(cases):02d}_ota_{base[i]["process"]}_{base[i]["drive"]}',
                          stage='ota',old_index=i))

    def add(process,mode,r=1600,length=120,stage='reference'):
        c = next(c for c in base if c['process']==process and c['hardware']=='native_ref'
                 and c['drive']=='p' and c['count_b']==0)
        cases.append(dict(c,case_id=f'lpref_{len(cases):02d}_{process}_{mode}',stage=stage,
                          kind='dc',match_mode=mode,ref_R_ohm=r,length_nm=length))

    for process in ('tt','ss','ff'):
        for mode in ('long','matched'):
            add(process,mode)
    for r in (1300,2200):
        add('tt','matched',r,stage='trim')
    add('tt','matched',length=240,stage='trim')
    return {'format':'pam4_lp_refsmoke_v1','status':'REVIEW_PENDING',
            'target_reference_A':phy.TARGET*1e-3/14,'cases':cases}


def render(case,model_root):
    if case['kind']=='ac':
        return phy.render(case,model_root)
    parent,r5 = BASE.load_inputs()
    seed = phy.render(case,model_root)[0]
    include = next(line for line in seed.splitlines() if line.startswith('include '))
    lines = ['simulator lang=spectre',include,
             next(line for line in seed.splitlines() if line.startswith('simulatorOptions ')),
             f'GFVDD (GF_VDD 0) vsource dc={case["vdd_V"]:.9g}',
             'GMSRRREF (GF_VDD GMSR_REF) resistor r=462']
    mirrored = r'^GMSQ(?:RPD|RPM|RND|RNS|RNM)\d+ '
    for line in phy.native_blocks(case,parent,r5):
        if re.match(mirrored,line):
            line,n = re.subn(r'\bl=(?:30|60)n\b',f'l={case["length_nm"]}n',line,count=1)
            common.need(n==1,'Expected one native schematic length field')
            if re.match(r'^GMSQRPM\d+ ',line):
                line = line.replace('(GMSQBN ','(GMSQPD_OUT ',1)
            if re.match(r'^GMSQRNM\d+ ',line):
                line = line.replace('(GMSR_REF ','(GMSQND_OUT ',1)
        lines.append(line)
    if case['match_mode']=='matched':
        # Floating ideal series sources equalize drains and pass branch current.
        # They are diagnostic constraints, with their headroom recorded.
        lines += ['GMSQPALIGN (GMSQPD_OUT GMSQBN GMSQBP GMSQBN) vcvs gain=1',
                  'GMSQNALIGN (GMSR_REF GMSQND_OUT GMSR_REF GMSQBN) vcvs gain=1']
    else:
        lines += ['GMSQPALIGN (GMSQPD_OUT GMSQBN) vsource dc=0',
                  'GMSQNALIGN (GMSR_REF GMSQND_OUT) vsource dc=0']
    nodes = ['GMSR_REF','GMSQBP','GMSQBN','GMSQRS','GMSQST','GMSQK','GMSQPD_OUT','GMSQND_OUT']
    currents = ['GMSQPALIGN:p','GMSQNALIGN:p']
    rails = {'GFVDD:p':case['vdd_V']}
    lines += ['saveOptions options save=selected currents=selected',
              'save '+' '.join(nodes+currents+list(rails)),
              'dcOp dc','dcOpInfo info what=oppoint where=rawfile']
    deck = '\n'.join(lines)+'\n'
    validate_save_currents(deck,dict(AC_traces=[],DC_nodes=nodes,DC_currents=currents,rail_voltages_V=rails))
    return deck,rails,[],nodes,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def stage(case,destination,model_root=None):
    return gm.stage(case,destination,model_root,renderer=render)


def measure_reference(root,case,status):
    dc = gm.comp_measure.safe_raw(root,status,'dcOp.dc')
    op = gm.comp_measure.safe_raw(root,status,'dcOpInfo.info')
    common.need(dc.header.get('analysis name')=='dcOp' and not dc.sweep_names,'Expected scalar DC')
    def trace(name,unit):
        value = gm.original.trace(dc,name,1)[0]
        common.need(dc.unit(name)==unit and value.imag==0,'DC trace unit differs: '+name)
        return value.real
    volts = {n:trace(n,'V') for n in case['DC_nodes']}
    amps = {n:trace(n,'A') for n in case['DC_currents']}
    iref = (case['vdd_V']-volts['GMSR_REF'])/462
    core = volts['GMSQRS']/case['ref_R_ohm']
    supply = -case['vdd_V']*trace('GFVDD:p','A')
    p_mirror = amps['GMSQPALIGN:p']
    n_mirror = amps['GMSQNALIGN:p']
    report = {
        'format':'pam4_lp_iref_measurement_v1','measurement_complete':True,'case_id':case['case_id'],
        'bench_sha256':common.sha(root/'bench.scs'),'run_status_sha256':common.sha(root/'run_status.json'),
        'reference_current_A':iref,'core_current_A':core,
        'PMOS_mirror_ratio':p_mirror/core if core>0 else None,
        'NMOS_mirror_ratio_over_10':n_mirror/(10*p_mirror) if p_mirror>0 else None,
        'reference_error_fraction':iref/(phy.TARGET*1e-3/14)-1,
        'supply_mW':1000*supply,'DC_voltage_V':volts,'DC_current_A':amps,
        'ideal_alignment_sources_absorbed_mW':1000*(
            (volts['GMSQPD_OUT']-volts['GMSQBN'])*p_mirror+
            (volts['GMSR_REF']-volts['GMSQND_OUT'])*n_mirror),
        'PMOS_drain_delta_V':volts['GMSQPD_OUT']-volts['GMSQBP'],
        'NMOS_drain_delta_V':volts['GMSQND_OUT']-volts['GMSQBN'],
        'P_series_headroom_V':volts['GMSQPD_OUT']-volts['GMSQBN'],
        'N_series_headroom_V':volts['GMSR_REF']-volts['GMSQND_OUT'],
        'startup_kick_uA':1e6*(volts['GMSQBP']-volts['GMSQK'])/50e3,
        'saved_mos_oppoint':{n:{k:v for k,v in xs[0].items()
                                   if k in ('ids','gm','gds','vds','vdsat','region','vgs')}
                             for n,xs in op.values.items() if n.startswith('GMSQ') and
                             xs and isinstance(xs[0],dict)},
    }
    common.need(common.sha(root/'spectre.log')==status['spectre_log_sha256'] and
                all(common.sha(root/n)==h for n,h in case['staged_source_sha256'].items()),
                'Input or log SHA differs')
    return report


def collect(root,case,status):
    log = (root/'spectre.log').read_text(encoding='utf-8',errors='replace')
    common.need(not re.search(r'SPECTRE-(8059|8282)\b',log),'Spectre skipped a required save')
    if case['kind']=='ac':
        return gm.collect(root,case,status)
    report = measure_reference(root,case,status)
    common.write_new(root/'measurements.json',report)
    common.write_new(root/'completion.json',{'measurement_complete':True,
        'measurement_sha256':common.sha(root/'measurements.json'),'completed_utc':common.utc()})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--model-root',type=Path)
    p.add_argument('--approval',type=Path)
    a = p.parse_args()
    gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan==build_plan(),'Smoke plan differs')
    if a.mode=='verify':
        for c in plan['cases']:
            render(c,BASE.MODEL_TOKEN)
        print('Smoke manifest, plan and all renderers verified')
        return
    cases = plan['cases']
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Use explicit distinct smoke indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.approval and a.model_root,'Provide one approved case and model root')
    phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,common.read(a.approval),
                      plan=PLAN,stage_case=stage,collect_case=collect)


if __name__=='__main__':
    main()
