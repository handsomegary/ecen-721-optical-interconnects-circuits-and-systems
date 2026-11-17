"""Build the SS coarse3 bias and local one-thirty-second-spaced endpoint pilot."""
import argparse
from pathlib import Path

import gm_tap16 as fine
import gm_taptrim_rf as rf
import olympus_common as common
from weighted_delay import ENDPOINT_PS


ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'gm_taptrim_plan.json'
BIAS_MV = (580,570,575,565,560)
CODES = (0,-30,30,-29,29,-28,28)
PILOT_COLUMNS = 82


def distribution(code,resolution):
    common.need(type(code) is int and -32<=code<=32 and resolution in (8,16,32),
                'Invalid trim code')
    common.need(abs(code)*resolution%32==0,'Code is outside the resolution grid')
    moved = abs(code)*resolution//32
    return moved if code<0 else 0,resolution-moved,moved if code>0 else 0


def tag(code):
    return f'{"m" if code<0 else "p"}{abs(code):02d}'


def point(code):
    if not code:
        return 'center'
    return f'edge_{"neg" if code<0 else "pos"}_{abs(code)}'


def build_plan():
    cases = []
    parent = fine.build_plan()['cases'][:48]
    base = {c['drive']:c for c in parent if c['group']=='baseline'}
    native = {c['drive']:c for c in parent if c['group']=='legacy' and c['code']==0}

    def add(group,variant,code,mv,*,ref=None,oracle=None,exact=False):
        res = {'old8':8,'half16':16,'split32':32}[variant]
        stem = {'baseline':'r3','legacy':'legacy','control':'control16',
                'oracle':'min32','pilot':'split32'}[group]
        suffix = '' if group=='baseline' else f'_{tag(code)}'
        bias_tag = '' if group in ('baseline','legacy') else f'_b{mv}'
        fixture = 'ss_'+stem+suffix+bias_tag
        banks = tuple(zip(fine.ANCHORS,distribution(code,res)))
        if group=='baseline':
            banks = ()
        elif group=='oracle':
            banks = tuple((a,w) for a,w in banks if w)
        name = 'r3' if group=='baseline' else 'gmtap'
        for side in 'pn':
            template = (base if group=='baseline' else native)[side]
            cases.append(dict(template,case_id=f'gmt32_{len(cases):03d}_{fixture}_{side}',
                              fixture_id=fixture,stage=group,group=group,variant_name=name,
                              point=point(code),anchors=[a for a,w in banks],weights=[w for a,w in banks],
                              resolution=res,code=code,tail_variant=variant,vb1_V=mv/1000,
                              anchor_set='minimal' if group=='oracle' else 'coarse3',
                              injected_skew_ps=ENDPOINT_PS if code<0 else -ENDPOINT_PS if code else 0.,
                              match_load=False,oracle_fixture_id=oracle,legacy_fixture_id=None,
                              fixed_fixture_id=None,reference_current_fixture_id=ref,
                              reference_current_exact=exact,target_current_fixture_id='ss_legacy_p00'))
        return fixture

    add('baseline','old8',0,580)
    for code in (0,-32,32,-28,28):
        add('legacy','old8',code,580)

    def anchor(code):
        if code:
            ref = (-1 if code<0 else 1)*(32 if abs(code) in (30,32) else 28)
        else:
            ref = 0
        return f'ss_legacy_{tag(ref)}',ref==code

    for code in (0,-30,30,-28,28,-26,26):
        ref,exact = anchor(code)
        add('control','half16',code,580,ref=ref,exact=exact)

    for mv in BIAS_MV:
        for code in CODES:
            ref,exact = anchor(code)
            oracle = add('oracle','split32',code,mv,ref=ref,exact=exact)
            add('pilot','split32',code,mv,ref=ref,oracle=oracle,exact=exact)
        if mv==570:
            common.need(len(cases)==PILOT_COLUMNS,'Unexpected primary trim column count')
    return {'format':'pam4_lp14_gm_tap_trim32_v1','status':'REVIEW_PENDING',
            'primary_columns':PILOT_COLUMNS,'bias_mV':list(BIAS_MV),'cases':cases}


def render(case,model_root):
    if case['group'] in ('baseline','legacy'):
        return fine.render(case,model_root)
    return rf.render(case,model_root)


def stage(case,dest,model_root=None):
    return fine.endpoint.integrated.mirror.prior.gm.stage(case,dest,model_root,renderer=render)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--approval',type=Path)
    p.add_argument('--model-root',type=Path)
    a = p.parse_args()
    fine.endpoint.integrated.mirror.prior.gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan==build_plan(),'Trim32 plan differs')
    cases = plan['cases']
    if a.mode=='verify':
        for case in cases:
            render(case,fine.endpoint.BASE.MODEL_TOKEN)
        print(f'Trim32 manifest and all {len(cases)} decks verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Supply distinct reviewed indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.model_root and a.approval,'Supply approved case and model root')
    approval = common.read(a.approval)
    common.need(approval.get('retire_new_raw') is not True,'Preserve Trim32 pilot raw')
    fine.endpoint.integrated.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,approval,
                                             plan=PLAN,stage_case=stage)


if __name__=='__main__':
    main()
