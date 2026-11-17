"""Stage coarse3 midcodes, PVT endpoints, and Vb2-derived Vb1 pilot decks."""
import argparse
from pathlib import Path

import gm_taptrim as trim
import gm_tapmid_rf as rf
import olympus_common as common
from weighted_delay import ENDPOINT_PS


ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'gm_tapmid_plan.json'
BASE = trim.fine.endpoint.BASE
CORNERS = ('ss','tt','ff')
END_CODES = (0,-30,30,-29,29,-28,28)
MID_CODES = tuple(c for c in range(-30,31,2) if c not in END_CODES)
EXTRA_CODES = tuple(range(-27,28,2))
VBIAS = .570


def build_plan():
    cases = []
    parent = trim.fine.endpoint.build_plan()['cases']
    templates = {(c['process'],c['drive'],c['variant_name']):c for c in parent if
                 c['group'] in ('baseline','coverage') and c['count_b']==0}

    def add(proc,group,code,bias,variant,fixture,*,oracle=None,ideal=None):
        count = 32 if variant=='split32' else 8
        anchors = tuple(zip(trim.fine.ANCHORS,trim.distribution(code,count)))
        if group=='baseline':
            anchors = ()
        elif group=='oracle':
            anchors = tuple((a,w) for a,w in anchors if w)
        for side in 'pn':
            old = templates[(proc,side,'r3' if group=='baseline' else 'native')]
            cases.append(dict(old,case_id=f'gmtm_{len(cases):03d}_{fixture}_{side}',fixture_id=fixture,
                              stage=group,group=group,variant_name='r3' if group=='baseline' else 'gmtap',
                              point=trim.point(code),anchors=[a for a,w in anchors],
                              weights=[w for a,w in anchors],resolution=count,code=code,
                              tail_variant=variant,vb1_V=VBIAS if count==32 else .580,
                              anchor_set='minimal' if group=='oracle' else 'coarse3',
                              injected_skew_ps=ENDPOINT_PS if code<0 else -ENDPOINT_PS if code else 0.,
                              match_load=False,bias_kind=bias,oracle_fixture_id=oracle,
                              target_current_fixture_id=f'{proc}_legacy_center',
                              ideal_reference_fixture_id=ideal,fixed_fixture_id=None))

    def controls(proc):
        add(proc,'baseline',0,'ideal','old8',f'{proc}_r3')
        add(proc,'legacy',0,'ideal','old8',f'{proc}_legacy_center')

    def pair(proc,group,code,bias='ideal'):
        tag = trim.tag(code)
        name = f'{proc}_{bias}_{tag}'
        oracle = f'{proc}_{bias}_min_{tag}'
        ideal = f'{proc}_ideal_{tag}' if bias!='ideal' else None
        add(proc,'oracle',code,bias,'split32',oracle)
        add(proc,group,code,bias,'split32',name,oracle=oracle,ideal=ideal)

    controls('ss')
    for c in (*END_CODES,*MID_CODES):
        pair('ss','sweep',c)
    common.need(len(cases)==136,'Unexpected SS measured grid size')
    for proc in ('tt','ff'):
        controls(proc)
        for c in END_CODES:
            pair(proc,'pvt',c)
    common.need(len(cases)==200,'Unexpected ideal-bias comparator size')
    for proc in CORNERS:
        for c in END_CODES:
            pair(proc,'divider',c,'divider')
    for c in (0,-29,29):
        pair('ss','divider',c,'divider_lowz')
    common.need(len(cases)==296,'Unexpected physical Vb1 pilot size')
    for c in EXTRA_CODES:
        pair('ss','extra',c)
    return {'format':'pam4_lp14_gm_tap_midbias_v1','status':'REVIEW_PENDING',
            'nominal_vb1_V':VBIAS,'cases':cases}


def render(case,model_root):
    if case['group'] in ('baseline','legacy'):
        return trim.render(case,model_root)
    return rf.render(case,model_root)


def stage(case,dest,model_root=None):
    return trim.fine.endpoint.integrated.mirror.prior.gm.stage(case,dest,model_root,renderer=render)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--approval',type=Path)
    p.add_argument('--model-root',type=Path)
    a = p.parse_args()
    trim.fine.endpoint.integrated.mirror.prior.gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan==build_plan(),'Midbias plan differs')
    cases = plan['cases']
    if a.mode=='verify':
        for c in cases:
            render(c,BASE.MODEL_TOKEN)
        print(f'Midbias manifest and all {len(cases)} decks verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Supply distinct reviewed indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.root and a.model_root and a.approval,'Supply approved case and model root')
    approval = common.read(a.approval)
    common.need(approval.get('retire_new_raw') is not True,'Preserve Midbias raw')
    trim.fine.endpoint.integrated.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,approval,
                                                   plan=PLAN,stage_case=stage)


if __name__=='__main__':
    main()
