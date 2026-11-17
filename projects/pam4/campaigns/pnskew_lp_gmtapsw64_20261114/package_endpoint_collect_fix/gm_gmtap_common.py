"""Stage common-hardware Split64 transition, endpoint, and PVT sweeps."""
import argparse
from pathlib import Path

import gm_center64 as prior
import gm_center64_rf as rf
import gm_taptrim as trim
import olympus_common as common
from weighted_delay import ENDPOINT_PS


ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'gm_gmtap_common_plan.json'
WORDS = ROOT/'split64_control_words.json'
BASE = prior.BASE
CORNERS = ('ss','tt','ff')


def symmetric(magnitudes):
    return tuple(code for q in magnitudes for code in (-q,q))


EDGE = symmetric(range(56,61))
ENDPOINT_GRID = (0,-1,1,-2,2,-32,32,*EDGE)
SS_IDEAL = (0,*symmetric(range(1,13)),-32,32,-52,52,*EDGE)
GRID = tuple(sorted({0,*symmetric(range(1,13)),*symmetric(range(16,53,4)),*EDGE}))
EXTRA_GRID = symmetric(range(14,55,4))


def control_word(code):
    weights = prior.distribution(code,64)
    names = [str(a) for a in trim.fine.ANCHORS]
    bits = {k:list(rf.active_cells(w)) for k,w in zip(names,weights)}
    return {'code':code,'weights_by_bank':dict(zip(names,weights)),'enabled_tail_indices_by_bank':bits,
            'enable_mask_by_bank':{k:sum(1<<i for i in cells) for k,cells in bits.items()}}


def word_table():
    return {'format':'split64_static_controls_v1','candidate_words':[control_word(q) for q in sorted({*GRID,*EXTRA_GRID})],
            'scope':'Nominal tail enable only, ordered calibration map is established separately from measured evidence'}


def build_plan():
    cases=[]
    parents=trim.fine.endpoint.build_plan()['cases']
    templates={(c['process'],c['drive'],c['variant_name']):c for c in parents if
               c['group'] in ('baseline','coverage') and c['count_b']==0}
    ideal_exists={(corner,q) for corner in CORNERS for q in (SS_IDEAL if corner=='ss' else ENDPOINT_GRID)}

    def add(corner,group,code,res,bias,fixture,*,oracle=None,ideal=None):
        banks=tuple(zip(trim.fine.ANCHORS,prior.distribution(code,res)))
        variant='r3' if group=='baseline' else 'native'
        if group=='baseline':
            banks=()
        elif group=='oracle':
            banks=tuple((a,w) for a,w in banks if w)
        for side in 'pn':
            c=templates[(corner,side,variant)]
            cases.append(dict(c,case_id=f'gmtg_{len(cases):04d}_{fixture}_{side}',
                              fixture_id=fixture,stage=group,group=group,
                              variant_name='r3' if group=='baseline' else 'gmtap',
                              point=trim.point(code),anchors=[a for a,w in banks],weights=[w for a,w in banks],
                              resolution=res,code=code,tail_variant='split64' if res==64 else 'old8',
                              vb1_V=.565 if res==64 else .580,bias_kind=bias,match_load=False,
                              anchor_set='minimal' if group=='oracle' else 'coarse3',
                              oracle_fixture_id=oracle,ideal_reference_fixture_id=ideal,fixed_fixture_id=None,
                              target_current_fixture_id=f'{corner}_legacy_center',
                              reference_current_fixture_id=f'{corner}_legacy_center',
                              injected_skew_ps=ENDPOINT_PS if code<0 else -ENDPOINT_PS if code else 0.))

    def controls(corner):
        add(corner,'baseline',0,8,'ideal',f'{corner}_r3')
        add(corner,'legacy',0,8,'ideal',f'{corner}_legacy_center')

    def pair(corner,group,code,bias):
        tag=trim.tag(code)
        mode='ideal' if bias=='ideal' else 'div'
        fixture=f'{corner}_{mode}_{tag}'
        oracle=f'{corner}_{mode}_min_{tag}'
        ideal=f'{corner}_ideal_{tag}' if bias!='ideal' and (corner,code) in ideal_exists else None
        add(corner,'oracle',code,64,bias,oracle)
        add(corner,group,code,64,bias,fixture,oracle=oracle,ideal=ideal)

    controls('ss')
    for q in SS_IDEAL:
        pair('ss','ideal',q,'ideal')
    common.need(len(cases)==160,'Unexpected SS ideal batch')
    for corner in CORNERS[1:]:
        controls(corner)
        for q in ENDPOINT_GRID:
            pair(corner,'ideal',q,'ideal')
    common.need(len(cases)==304,'Unexpected ideal PVT batch')
    for corner in CORNERS:
        for q in ENDPOINT_GRID:
            pair(corner,'divider',q,'divider_lowz')
    common.need(len(cases)==508,'Unexpected divider PVT pilot')
    for corner in CORNERS:
        for q in GRID:
            if q not in ENDPOINT_GRID:
                pair(corner,'codes',q,'divider_lowz')
    common.need(len(cases)==964,'Unexpected complete common grid')
    for corner in CORNERS:
        for q in EXTRA_GRID:
            pair(corner,'extra',q,'divider_lowz')
    return {'format':'pam4_lp14_gm_tap_common64_v1','status':'REVIEW_PENDING',
            'physical_bias':{'Vb2_V':.580,'Vb1_unloaded_V':.565,'r_top_ohm':375,
                             'r_bottom_ohm':14125,'bypass_pF':2},'cases':cases}


def stage(case,dest,model_root=None):
    return trim.fine.endpoint.integrated.mirror.prior.gm.stage(case,dest,model_root,renderer=prior.render)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--approval',type=Path)
    p.add_argument('--model-root',type=Path)
    a=p.parse_args()
    trim.fine.endpoint.integrated.mirror.prior.gm.original.verify_package()
    plan=common.read(PLAN)
    common.need(plan==build_plan() and common.read(WORDS)==word_table(),'Common64 plan or control words differ')
    cases=plan['cases']
    if a.mode=='verify':
        for case in cases:
            prior.render(case,BASE.MODEL_TOKEN)
        print(f'Common64 manifest, controls, and all {len(cases)} decks verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Supply distinct reviewed indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.model_root and a.approval,'Supply approved case and model root')
    approval=common.read(a.approval)
    common.need(approval.get('retire_new_raw') is not True,'Raw retirement follows the committed measurement review')
    trim.fine.endpoint.integrated.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,approval,
                                                   plan=PLAN,stage_case=stage)


if __name__=='__main__':
    main()
