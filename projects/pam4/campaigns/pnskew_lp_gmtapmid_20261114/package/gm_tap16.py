"""Stage native half-width coarse3 controls and a conditional three-corner AC sweep."""
import argparse
from pathlib import Path

import gm_tap as prior
import gm_tap16_rf as rf
import lp_endpoint as endpoint
import olympus_common as common
from weighted_delay import ENDPOINT_PS


ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'gm_tap16_plan.json'
ANCHORS = (6,11,16)
CORNERS = ('ss','tt','ff')
CHECK_CODES = (0,-16,16,-14,14)
FIRST_CODES = (0,-16,16,-15,15,-14,14,-13,13)
PILOT_COUNT = 48


def distribution(code, resolution):
    common.need(type(code) is int and -16<=code<=16 and isinstance(resolution,int)
                and resolution in (8,16),'Invalid coarse3 code or resolution')
    common.need(resolution==16 or code%2==0,'Full-size tails implement even comparison codes only')
    moved = abs(code)*resolution//16
    return (moved if code<0 else 0,resolution-moved,moved if code>0 else 0)


def code_tag(code):
    return f'{"m" if code<0 else "p"}{abs(code):02d}'


def label(code):
    if not code:
        return 'center'
    sign = 'neg' if code<0 else 'pos'
    return {16:sign+'_end',14:'near_'+sign}.get(abs(code),f'fine_{sign}_{abs(code):02d}')


def build_plan():
    cases = []
    old = endpoint.build_plan()['cases']
    templates = {(c['process'],c['drive'],c['variant_name']):c for c in old if
                 c['group'] in ('baseline','coverage') and c['count_b']==0}

    def add(proc,group,code,resolution,fixture_id,*,oracle=None,legacy=None):
        weights = distribution(code,resolution)
        banks = tuple(zip(ANCHORS,weights))
        if group=='oracle':
            banks = tuple((a,w) for a,w in banks if w)
        elif group=='baseline':
            banks = ()
        variant = 'r3' if group=='baseline' else 'gmtap'
        anchor_set = 'minimal' if group=='oracle' else f'coarse3_{resolution}'
        skew = ENDPOINT_PS if code<0 else -ENDPOINT_PS if code else 0.
        for side in 'pn':
            parent = templates[(proc,side,'r3' if group=='baseline' else 'native')]
            cases.append(dict(parent,
                              case_id=f'gmt16_{len(cases):03d}_{fixture_id}_{side}',fixture_id=fixture_id,
                              stage=group,group=group,variant_name=variant,point=label(code),
                              anchors=[a for a,w in banks],weights=[w for a,w in banks],
                              anchor_set=anchor_set,resolution=resolution,code=code,
                              injected_skew_ps=skew,match_load=False,oracle_fixture_id=oracle,
                              fixed_fixture_id=None,legacy_fixture_id=legacy))

    def comparison(proc):
        add(proc,'baseline',0,8,f'{proc}_r3')
        for code in CHECK_CODES:
            add(proc,'legacy',code,8,f'{proc}_legacy_{code_tag(code)}')

    def candidate(proc,group,code):
        tag = code_tag(code)
        ctl = f'{proc}_min16_{tag}'
        legacy = f'{proc}_legacy_{tag}' if code in CHECK_CODES else None
        add(proc,'oracle',code,16,ctl)
        add(proc,group,code,16,f'{proc}_fine16_{tag}',oracle=ctl,legacy=legacy)

    comparison('ss')
    for code in FIRST_CODES:
        candidate('ss','pilot',code)
    common.need(len(cases)==PILOT_COUNT,'Fine16 pilot count differs')
    for proc in CORNERS:
        if proc!='ss':
            comparison(proc)
        for code in range(-16,17):
            if proc=='ss' and code in FIRST_CODES:
                continue
            candidate(proc,'map',code)
    return {'format':'pam4_lp14_gm_tap_fine16_v1','status':'REVIEW_PENDING','first_batch_columns':PILOT_COUNT,
            'cases':cases}


def render(case,model_root):
    if case['group']=='baseline':
        return endpoint.render(case,model_root)
    if case['resolution']==8:
        return prior.rf.render(case,model_root)
    return rf.render(case,model_root)


def stage(case,dest,model_root=None):
    return endpoint.integrated.mirror.prior.gm.stage(case,dest,model_root,renderer=render)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--approval',type=Path)
    p.add_argument('--model-root',type=Path)
    a = p.parse_args()
    endpoint.integrated.mirror.prior.gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan==build_plan(),'Fine16 plan differs')
    cases = plan['cases']
    if a.mode=='verify':
        for c in cases:
            render(c,endpoint.BASE.MODEL_TOKEN)
        print(f'Fine16 manifest and all {len(cases)} decks verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Supply distinct reviewed indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.model_root and a.approval,'Supply approved case and model root')
    approval = common.read(a.approval)
    common.need(approval.get('retire_new_raw') is not True,'Preserve Fine16 raw')
    endpoint.integrated.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,approval,
                                        plan=PLAN,stage_case=stage)


if __name__=='__main__':
    main()
