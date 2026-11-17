"""Stage the SS shared-bias and centre-resolution AC repair."""
import argparse
from pathlib import Path
import re

import gm_center64_rf as rf
import gm_tapmid as mid
import gm_tapmid_rf
import gm_taptrim as trim
import olympus_common as common
from recover_bias import validate_save_currents
from weighted_delay import ENDPOINT_PS


ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'gm_center64_plan.json'
BASE = mid.BASE
MID_CODES = tuple(code for q in range(12,53,4) for code in (-q,q))
CENTER_CODES = (0,-1,1,-2,2)
WORST_CODES = (-12,12,-32,32,-52,52)


def distribution(code,resolution):
    common.need(type(code) is int and abs(code)<=64 and resolution in (8,32,64),
                'Invalid Center64 control')
    common.need(abs(code)*resolution%64==0,'Control is outside the requested grid')
    moved = abs(code)*resolution//64
    return moved if code<0 else 0,resolution-moved,moved if code>0 else 0


def build_plan():
    cases = []
    parent = trim.fine.endpoint.build_plan()['cases']
    refs = {(c['drive'],c['variant_name']):c for c in parent if c['process']=='ss'
            and c['group'] in ('baseline','coverage') and c['count_b']==0}
    matches = set(MID_CODES)|{0,-2,2}

    def add(group,code,res,bias,fixture,*,oracle=None,equal=None,ideal=None):
        banks = tuple(zip(trim.fine.ANCHORS,distribution(code,res)))
        if group=='baseline':
            banks=()
        elif group=='oracle':
            banks=tuple((a,w) for a,w in banks if w)
        for side in 'pn':
            template = refs[(side,'r3' if group=='baseline' else 'native')]
            cases.append(dict(template,
                              case_id=f'gmtc_{len(cases):03d}_{fixture}_{side}',fixture_id=fixture,
                              stage=group,group=group,variant_name='r3' if group=='baseline' else 'gmtap',
                              anchors=[a for a,w in banks],weights=[w for a,w in banks],
                              resolution=res,code=code,tail_variant={8:'old8',32:'split32',64:'split64'}[res],
                              point=trim.point(code),anchor_set='minimal' if group=='oracle' else 'coarse3',
                              vb1_V=.580 if res==8 else .570 if bias=='divider_legacy' else .565,
                              bias_kind=bias,match_load=False,oracle_fixture_id=oracle,fixed_fixture_id=None,
                              target_current_fixture_id='ss_legacy_center',
                              reference_current_fixture_id='ss_legacy_center',
                              same_weight_32_fixture_id=equal,ideal_reference_fixture_id=ideal,
                              injected_skew_ps=ENDPOINT_PS if code<0 else -ENDPOINT_PS if code else 0.))

    def pair(group,stem,code,res,bias='ideal'):
        tag = trim.tag(code)
        name=f'ss_{stem}_{tag}'
        oracle=f'ss_{stem}_min_{tag}'
        equal=f'ss_split32_{tag}' if res==64 and bias=='ideal' and code in matches else None
        ideal=f'ss_split64_{tag}' if bias=='divider_lowz' else None
        add('oracle',code,res,bias,oracle)
        add(group,code,res,bias,name,oracle=oracle,equal=equal,ideal=ideal)

    add('baseline',0,8,'ideal','ss_r3')
    add('legacy',0,8,'ideal','ss_legacy_center')
    for code in (0,-2,2,*MID_CODES):
        pair('control','split32',code,32)
    common.need(len(cases)==104,'Unexpected common Vb1 pilot size')
    for code in (*CENTER_CODES,*WORST_CODES):
        pair('pilot','split64',code,64)
    common.need(len(cases)==148,'Unexpected Center64 pilot size')
    for code in (*CENTER_CODES,-32,32):
        pair('divider','lowz64',code,64,'divider_lowz')
    for code in (0,-32,32):
        pair('divider','legacydiv32',code,32,'divider_legacy')
    return {'format':'pam4_lp14_gm_tap_center64_v1','status':'REVIEW_PENDING','cases':cases}


def add_lowz_divider(case,model_root):
    deck,rails,ac,dc,currents,_ = rf.render(case,model_root)
    common.need(rails.get('GMSKV1:p')==.565 and rails.get('XVb:p')==.580 and 'GMSKVBIAS' in dc,
                'Unexpected bias sources for the 565 mV divider')
    divider = '\n'.join((
        'GMSKVDIV (X_vb GMSKVDIVIN) vsource dc=0',
        'GMSKVRU (GMSKVDIVIN GMSKV1RAW) resistor r=375',
        'GMSKVRD (GMSKV1RAW 0) resistor r=14125',
        'GMSKV1 (GMSKV1RAW GMSKVBIAS) vsource dc=0',
        'GMSKVC1 (GMSKVBIAS 0) capacitor c=2p',
    ))
    deck = BASE.replace_once(deck,'GMSKV1 (GMSKVBIAS 0) vsource dc=0.565',divider)
    del rails['GMSKV1:p']
    currents.extend(('GMSKVDIV:p','GMSKV1:p'))
    save = re.search(r'(?m)^save PNC_PREP [^\n]+$',deck)
    common.need(save is not None,'Missing center64 save list')
    deck = BASE.replace_once(deck,save.group(),'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails))))
    validate_save_currents(deck,dict(AC_traces=ac,DC_nodes=dc,DC_currents=currents,rail_voltages_V=rails))
    parent,_=BASE.load_inputs()
    return deck,rails,ac,dc,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def render(case,model_root):
    if case['bias_kind']=='divider_lowz':
        return add_lowz_divider(case,model_root)
    if case['bias_kind']=='divider_legacy':
        return gm_tapmid_rf.render(dict(case,bias_kind='divider'),model_root)
    if case['resolution']==64:
        return rf.render(case,model_root)
    return trim.render(case,model_root)


def stage(case,dest,model_root=None):
    return trim.fine.endpoint.integrated.mirror.prior.gm.stage(case,dest,model_root,renderer=render)


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
    common.need(plan==build_plan(),'Center64 plan differs')
    cases=plan['cases']
    if a.mode=='verify':
        for case in cases:
            render(case,BASE.MODEL_TOKEN)
        print(f'Center64 manifest and all {len(cases)} decks verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Supply distinct reviewed indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.model_root and a.approval,'Supply approved case and model root')
    approval=common.read(a.approval)
    common.need(approval.get('retire_new_raw') is not True,'Preserve Center64 raw')
    trim.fine.endpoint.integrated.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,approval,
                                                   plan=PLAN,stage_case=stage)


if __name__=='__main__':
    main()
