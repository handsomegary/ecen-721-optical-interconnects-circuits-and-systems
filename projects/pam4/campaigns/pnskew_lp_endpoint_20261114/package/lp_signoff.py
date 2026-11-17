"""Extend replica STB and characterize peaking coils on the native LP14."""
import argparse
from pathlib import Path
import re

import lp_diagnostics as diag
import lp_integrate as integrated
import olympus_common as common

ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'signoff_plan.json'
BASE = integrated.BASE
RISK = {('ss',0),('ss',2),('ff',0)}
NOMINAL = RISK | {('tt',2)}


def build_plan():
    cases = []
    def add(c,stage,variant,**updates):
        cases.append(dict(c,**updates) | dict(stage=stage,variant_name=variant,
            case_id=f'lpsign_{len(cases):02d}_{c["process"]}_{variant}_cb{c["count_b"]}_{c["drive"]}'))

    for i in (13,15,17,19):
        add(diag.build_plan()['cases'][i],'replica20','replica20',prior_diag_index=i)
    for c in integrated.build_plan()['cases']:
        if c['launch']=='bypass' or (c['integration'] in ('reference','native_direct')
                                     and (c['process'],c['count_b']) in NOMINAL):
            add(c,'passive','r3' if c['launch']=='bypass' else
                'ideal_route' if c['integration']=='reference' else 'ideal_coil')
    for q,srf,variant,conditions in ((15,150,'q15_srf150',NOMINAL),(8,110,'q8_srf110',RISK)):
        for c in integrated.build_plan()['cases']:
            if c['integration']=='native_direct' and (c['process'],c['count_b']) in conditions:
                add(c,'passive',variant,coil_Q56=q,coil_SRF_GHz=srf)
    return {'format':'lp14_signoff_ac_v1','status':'REVIEW_PENDING','cases':cases}


def render(case,model_root):
    if case['stage']=='replica20':
        deck,rails,ac,dc,currents,_ = diag.render(dict(case,stage='stb'),model_root)
        deck = BASE.replace_once(deck,'replicaSTB stb start=1 stop=1G dec=50',
                                 'replicaSTB stb start=1 stop=20G dec=100')
    else:
        return integrated.render(case,model_root)
    parent,_ = BASE.load_inputs()
    return deck,rails,ac,dc,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def stage(case,dest,model_root=None):
    return integrated.mirror.prior.gm.stage(case,dest,model_root,renderer=render)


def collect(root,case,status):
    if case['stage']=='passive':
        return integrated.mirror.prior.gm.collect(root,case,status)
    from diag_metrics import TARGET_IREF_UA, _vector
    from replica20_metrics import replica20_metrics
    trace = diag.raw_psf(root,status,r'raw/replicaSTB(?:[-.]stb)?\.stb')
    margins = diag.raw_psf(root,status,r'raw/replicaSTB[-.]margin\.stb',required=False)
    data = replica20_metrics(trace,margins)
    op = diag.raw_psf(root,status,r'raw/dcOp\.dc')
    v = {n:_vector(op,n,1)[0] for n in ('GF_VDD','GMSR_REF','GMSR_D','GMSQBP','GMSQK')}
    iref = 1e6*(v['GF_VDD']-v['GMSR_REF'])/462
    data['dc_iref_uA'] = iref
    data['dc_kick_uA'] = 1e6*(v['GMSQBP']-v['GMSQK'])/50e3
    data['dc_servo_error_fraction'] = ((v['GMSR_REF']-v['GMSR_D'])/
                                      (v['GF_VDD']-v['GMSR_REF']) if iref>0 else None)
    log = (root/'spectre.log').read_text(encoding='utf-8',errors='replace')
    common.need(not re.search(r'SPECTRE-(8059|8061|8282|8287)\b',log),'Spectre skipped a requested save')
    if (abs(iref/TARGET_IREF_UA[case['process']]-1)>.02 or abs(data['dc_kick_uA'])>=.01
            or data['dc_servo_error_fraction'] is None or abs(data['dc_servo_error_fraction'])>.02
            or re.search(r'SPECTRE-16922\b',log)):
        data.update(status='fail',passed=False,formal_margin_pass=False,sampled_screen_pass=False,
                    reason='Incorrect settled operating point or native instability')
    common.need(all(common.sha(root/n)==h for n,h in case['staged_source_sha256'].items()) and
                common.sha(root/'spectre.log')==status['spectre_log_sha256'],'Input or log SHA differs')
    report = dict(data,format='pam4_lp_replica20_measurement_v1',case_id=case['case_id'],
                  measurement_complete=True,bench_sha256=common.sha(root/'bench.scs'),
                  run_status_sha256=common.sha(root/'run_status.json'))
    common.write_new(root/'measurements.json',report)
    common.write_new(root/'completion.json',{'measurement_complete':True,
        'measurement_sha256':common.sha(root/'measurements.json'),'completed_utc':common.utc()})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--approval',type=Path)
    p.add_argument('--model-root',type=Path)
    a = p.parse_args()
    integrated.mirror.prior.gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan==build_plan(),'Signoff plan differs')
    cases = plan['cases']
    if a.mode=='verify':
        for c in cases:
            render(c,BASE.MODEL_TOKEN)
        print('Replica and passive manifest, plan and decks verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Supply distinct reviewed indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.model_root and a.approval,'Supply approved case and model root')
    approval = common.read(a.approval)
    common.need(approval.get('retire_new_raw') is not True,'Preserve diagnostic raw')
    integrated.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,approval,
                                 plan=PLAN,stage_case=stage,collect_case=collect)


if __name__=='__main__':
    main()
