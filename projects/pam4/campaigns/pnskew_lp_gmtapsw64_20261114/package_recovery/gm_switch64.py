"""Stage FF numerical AC checks and native COMMON64 code-switching transients."""
import argparse
from pathlib import Path

import gm_center64 as hardware
import gm_gmtap_common as prior
import gm_select
import gm_summary
import gm_switch64_dense as dense
import gm_switch64_metrics as metrics
import gm_switch64_rf as dynamic
import olympus_common as common
from weighted_delay import ENDPOINT_PS


ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'gm_switch64_plan.json'
BASE = prior.BASE
TIMING = {'switch_time_s':3e-9,'stop_s':14e-9,'slew_s':1e-12,'max_step_s':.5e-12,
          'amplitude_Vppd':.4}
CORE = ((0,60),(60,-60),(-60,0))
DYNAMIC_LINKS = {
    'ss':(*CORE,(0,1),(0,-1),(1,2),(2,1),(52,56),(0,32)),
    'tt':CORE,
    'ff':(*CORE,(0,1),(1,2)),
}


def build_plan():
    old=prior.build_plan()['cases']
    cases=[]
    original={(c['process'],c['drive'],c['code']):c for c in old if
              c['group'] in ('divider','codes')}
    bypass={c['drive']:c for c in old if c['group']=='baseline' and c['process']=='ff'}
    for profile in dense.PROFILES:
        for code in (None,0,-1,1,-2,2):
            tag='r3' if code is None else hardware.trim.tag(code)
            fixture=f'ff_dense_{profile}_{tag}'
            for side in 'pn':
                c=bypass[side] if code is None else original['ff',side,code]
                cases.append(dict(c,stage='dense',dense_profile=profile,fixture_id=fixture,
                                  case_id=f'gmsw_{len(cases):03d}_{fixture}_{side}'))
    common.need(len(cases)==48,'Dense FF case count differs')
    refs={}

    def add(corner,start,finish,skew,offset,group,ref=None):
        src=original[corner,'p',start]
        label='zero' if not skew else 'latep' if skew>0 else 'laten'
        fixture=f'{corner}_{group}_{hardware.trim.tag(start)}_{hardware.trim.tag(finish)}_{label}'
        if offset:
            fixture+=f'_offset{offset*1e12:g}ps'
        case=dict(src,**TIMING,kind='transient',group=group,stage=group,fixture_id=fixture,
                  initial_code=start,final_code=finish,skew_ps=skew,offset_s=offset,
                  reference_case_id=ref,case_id=f'gmsw_{len(cases):03d}_{fixture}')
        cases.append(case)
        return case['case_id']

    def pair(corner,start,finish,skew=0.,offset=0.):
        key=(corner,finish,skew)
        if key not in refs:
            refs[key]=add(corner,finish,finish,skew,0.,'hold')
        add(corner,start,finish,skew,offset,'switch',refs[key])

    # Start with primary SS smoke. The rest share exact stimulus per
    # corner and destination where possible.
    pair('ss',0,1)
    pair('ss',1,2)
    pair('ss',0,60)
    for corner,links in DYNAMIC_LINKS.items():
        for start,finish in links:
            if corner=='ss' and (start,finish) in ((0,1),(1,2),(0,60)):
                continue
            pair(corner,start,finish)
    pair('ss',60,-60,offset=2e-12)
    pair('ff',1,2,offset=2e-12)
    pair('ss',0,-60,skew=ENDPOINT_PS)
    pair('ff',0,60,skew=-ENDPOINT_PS)
    return {'format':'pam4_lp14_split64_switch_and_dense_v1','status':'REVIEW_PENDING',
            'common64_nominal_grid_codes':list(prior.GRID),'cases':cases}


def render(case,model_root):
    if case['stage']=='dense':
        return dense.render(case,model_root)
    return dynamic.render(case,model_root)


def stage(case,dest,model_root=None):
    return hardware.trim.fine.endpoint.integrated.mirror.prior.gm.stage(case,dest,model_root,renderer=render)


def collect(root,case,status):
    if case['stage']=='dense':
        return gm_select.collect(root,case,status)
    return metrics.collect(root,case,status)


def summarize(root):
    cases=common.read(PLAN)['cases']
    ac=[c for c in cases if c['stage']=='dense']
    dynamic_cases=[c for c in cases if c['stage']!='dense']
    results,missing,invalid={},{},{}
    for case in dynamic_cases:
        try:
            results[case['case_id']]=gm_summary.read_case(root,case,PLAN)
        except FileNotFoundError:
            missing[case['case_id']]='missing case, run status, measurements or receipt'
        except (ValueError,KeyError,TypeError,OSError) as error:
            invalid[case['case_id']]=str(error)
    transitions=[]
    for case in dynamic_cases:
        if case['group']!='switch':
            continue
        sid,rid=case['case_id'],case['reference_case_id']
        entry={'case_id':sid,'reference_case_id':rid,'case':case}
        if sid in results and rid in results:
            try:
                entry['comparison']=metrics.compare(results[sid],results[rid])
            except (ValueError,KeyError,TypeError,OSError) as error:
                invalid[sid]=str(error)
        transitions.append(entry)
    ff=dense.summarize(root,ac,PLAN)
    observed=[r.get('comparison',{}).get('settled') for r in transitions]
    recovery=[r['comparison']['recovery_s_after_event'] for r in transitions
              if r.get('comparison',{}).get('settled') is True]
    dynamic_pass=(all(observed) if observed and None not in observed else None)
    return {'format':'pam4_lp14_switch64_summary_v1','FF_dense':ff,
            'transitions':transitions,'dynamic_measured_case_count':len(results),
            'missing_dynamic_cases':missing,'invalid_dynamic_cases':invalid,
            'all_planned_transitions_recovered_in_window':dynamic_pass,
            'largest_observed_recovery_after_last_edge_s':max(recovery,default=None),
            'ready_to_design_C0':ff['verified_nominal_dense_steps'] and dynamic_pass is True
            and not invalid,'mismatch_or_PEX_verified':False,'FFE_SER':None}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run','summarize'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--approval',type=Path)
    p.add_argument('--model-root',type=Path)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    hardware.trim.fine.endpoint.integrated.mirror.prior.gm.original.verify_package()
    plan=common.read(PLAN)
    common.need(plan==build_plan(),'Switch64 plan differs')
    cases=plan['cases']
    if a.mode=='verify':
        for case in cases:
            render(case,BASE.MODEL_TOKEN)
        print(f'Switch64 manifest and all {len(cases)} decks verified')
        return
    if a.mode=='summarize':
        common.need(a.root and a.output,'Supply run root and a fresh summary path')
        common.write_new(a.output,summarize(a.root.resolve()))
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Supply distinct reviewed indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.model_root and a.approval,'Supply approved case and model root')
    approval=common.read(a.approval)
    common.need(approval.get('retire_new_raw') is not True,'Finish paired transition reviews before raw retirement')
    hardware.trim.fine.endpoint.integrated.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,approval,
                                                          plan=PLAN,stage_case=stage,collect_case=collect)


if __name__=='__main__':
    main()
