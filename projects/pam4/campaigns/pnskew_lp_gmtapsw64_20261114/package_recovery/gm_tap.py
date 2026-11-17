"""Generate the TG-free LP14 current-selected RF tap pilot."""
import argparse
from pathlib import Path

import gm_tap_rf as rf
import lp_endpoint as prior
import olympus_common as common


ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'gm_tap_plan.json'
ANCHORS = {'coarse3':(6,11,16), 'coarse5':(6,8,11,14,16),
           'coarse7':(6,8,10,11,12,14,16)}
PILOT_POINTS = ('center','neg_end','pos_end','near_neg','near_pos')


def states(anchors):
    enabled = {
        'center': {11:8}, 'neg_end': {6:8}, 'pos_end': {16:8},
        'near_neg': {6:5,8:3} if 8 in anchors else {6:7,11:1},
        'near_pos': {16:5,14:3} if 14 in anchors else {16:7,11:1},
    }
    return {label:tuple(enabled[label].get(a,0) for a in anchors) for label in PILOT_POINTS}


def build_plan():
    cases = []
    template = prior.build_plan()['cases']
    native_by_side = {c['drive']:c for c in template if c['group']=='coverage' and
                      c['process']=='ss' and c['variant_name']=='native' and c['count_b']==0}

    def add(fixture,group,variant,point,base,*,anchors=(),weights=(),anchor_set='',
            match_load=False,oracle_fixture_id=None,fixed_fixture_id=None):
        for side in 'pn':
            parent = base[side]
            cases.append(dict(parent,case_id=f'gmt_{len(cases):03d}_{fixture}_{side}',fixture_id=fixture,
                              stage=group,group=group,variant_name=variant,point=point,
                              anchors=list(anchors),weights=list(weights),anchor_set=anchor_set,
                              match_load=match_load,oracle_fixture_id=oracle_fixture_id,
                              fixed_fixture_id=fixed_fixture_id))

    def paired(predicate):
        return {c['drive']:c for c in template if c['process']=='ss' and predicate(c)}

    add('r3_ss','baseline','r3','center',paired(lambda c:c['group']=='baseline'))
    for label in PILOT_POINTS[:3]:
        direction = -1 if label=='pos_end' else 1
        control = paired(lambda c: c['group']==('coverage' if label=='center' else 'endpoint') and
                         c['variant_name']=='native' and c['count_b']==0 and c['direction']==direction)
        add('fixed_'+label,'fixed','fixed_route',label,control)

    def pair_fixture(anchor_set,anchors,weights,point,matched):
        label = 'match' if matched else 'line'
        active = tuple((a,w) for a,w in zip(anchors,weights) if w)
        state = '_'.join(f'{a}x{w}' for a,w in active)
        oracle_id = f'oracle_{label}_{state}'
        if not any(c['fixture_id']==oracle_id for c in cases):
            taps,counts = zip(*active)
            add(oracle_id,'oracle','gmtap',point,native_by_side,anchors=taps,weights=counts,
                anchor_set='minimal',match_load=matched)
        fixed = 'fixed_'+point if point in PILOT_POINTS[:3] else None
        add(f'{anchor_set}_{label}_{point}','pilot','gmtap',point,native_by_side,anchors=anchors,weights=weights,
            anchor_set=anchor_set,match_load=matched,oracle_fixture_id=oracle_id,fixed_fixture_id=fixed)

    # First use one-ended line and 3/5/7 populations at center and both extremes.
    for name,anchors in ANCHORS.items():
        by_point = states(anchors)
        for point in PILOT_POINTS[:3]:
            pair_fixture(name,anchors,by_point[point],point,False)
    for name,anchors in ANCHORS.items():
        by_point = states(anchors)
        for point in PILOT_POINTS[3:]:
            pair_fixture(name,anchors,by_point[point],point,False)
    for name,anchors in ANCHORS.items():
        by_point = states(anchors)
        for point in PILOT_POINTS:
            pair_fixture(name,anchors,by_point[point],point,True)
    return {'format':'pam4_lp14_gm_tap_pilot_v1','status':'REVIEW_PENDING','cases':cases}


def render(case,model_root):
    if case['group'] in ('baseline','fixed'):
        return prior.render(case,model_root)
    return rf.render(case,model_root)


def stage(case,dest,model_root=None):
    return prior.integrated.mirror.prior.gm.stage(case,dest,model_root,renderer=render)


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
    common.need(plan==build_plan(),'GM tap plan differs')
    cases = plan['cases']
    if a.mode=='verify':
        for c in cases:
            render(c,prior.BASE.MODEL_TOKEN)
        print(f'GM tap manifest and all {len(cases)} decks verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Supply distinct reviewed indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.model_root and a.approval,'Supply approved case and model root')
    approval = common.read(a.approval)
    common.need(approval.get('retire_new_raw') is not True,'Preserve pilot raw')
    prior.integrated.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,approval,
                                      plan=PLAN,stage_case=stage)


if __name__=='__main__':
    main()
