"""Stage physical LP14 tapped-ladder pilot and a conditional global sweep."""
import argparse
from pathlib import Path

import global_codes
import global_rf
import lp_endpoint as prior
import olympus_common as common


ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'global_plan.json'
LUT = ROOT/'global_control_map.json'
BASE = prior.BASE
CORNERS = ('ss','tt','ff')
SMOKE_CODES = (0,4,8,39,40,41,72,76,80)


def build_plan():
    cases = []
    base = prior.build_plan()['cases']
    templates = {(c['process'],c['drive'],c['variant_name']):c for c in base if
                 c['group'] in ('baseline','coverage') and c['count_b']==0}

    def add(group, proc, code, switch, parallel, match):
        logical = code['logical_code']
        variant = 'r3' if switch=='r3' else 'native'
        hardware = f'{switch}{parallel}_{"match" if match else "line"}'
        alias = f'_left{code["left_tap"]}' if group=='alias' else ''
        fixture = f'{group}_{proc}_g{logical:02d}_{hardware}{alias}'
        for side in 'pn':
            parent = templates[(proc,side,variant)]
            cases.append(dict(parent,**code,case_id=f'lpg_{len(cases):03d}_{fixture}_{side}',
                              fixture_id=fixture,stage=group,group=group,variant_name=variant,
                              switch_mode=switch,tg_parallel=parallel,match_load=match))

    zero = global_codes.decode(40)
    for proc in CORNERS:
        add('reference',proc,zero,'r3',0,False)

    for proc in ('ss','tt'):
        for code in map(global_codes.decode,SMOKE_CODES):
            for parallel in (0,1,2,4):
                add('pilot',proc,code,'ideal' if parallel==0 else 'native',parallel,True)
        for logical in (0,40,80):
            for parallel in (0,4):
                add('pilot',proc,global_codes.decode(logical),
                    'ideal' if parallel==0 else 'native',parallel,False)
    for logical in (0,8,40,72,80):
        for parallel in (0,4):
            add('pilot','ff',global_codes.decode(logical),
                'ideal' if parallel==0 else 'native',parallel,True)

    for proc in CORNERS:
        for code in global_codes.codes():
            for parallel in (0,4):
                add('map',proc,code,'ideal' if parallel==0 else 'native',parallel,True)
        for alias in global_codes.seam_aliases():
            for parallel in (0,4):
                add('alias',proc,alias,'ideal' if parallel==0 else 'native',parallel,True)

    return {'format':'pam4_lp14_global_tap_v1','status':'REVIEW_PENDING',
            'candidate_match_load':True,'candidate_tg_parallel':4,'cases':cases}


def stage(case, dest, model_root=None):
    return prior.integrated.mirror.prior.gm.stage(case,dest,model_root,renderer=global_rf.render)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--approval',type=Path)
    p.add_argument('--model-root',type=Path)
    a = p.parse_args()
    prior.integrated.mirror.prior.gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan==build_plan(),'Global plan differs')
    common.need(common.read(LUT)=={'codes':global_codes.codes(),'seam_aliases':global_codes.seam_aliases()},
                'Global hardware control map differs')
    cases = plan['cases']
    if a.mode=='verify':
        for c in cases:
            global_rf.render(c,BASE.MODEL_TOKEN)
        print(f'Global map manifest, controls and {len(cases)} decks verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Supply distinct reviewed indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.model_root and a.approval,'Supply approved case and model root')
    approval = common.read(a.approval)
    common.need(approval.get('retire_new_raw') is not True,'Preserve global pilot raw')
    prior.integrated.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,approval,
                                       plan=PLAN,stage_case=stage)


if __name__=='__main__':
    main()
