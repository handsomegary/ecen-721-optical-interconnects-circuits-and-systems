"""Stage the native LP14 range, seam, and peaking-coil AC campaign."""
import argparse
from pathlib import Path
import re

import lp_integrate as integrated
import lp_next as coils
import olympus_common as common


ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'endpoint_plan.json'
BASE = integrated.BASE
ZERO = ((33,33),(33,33))
EDGE = coils.EDGE
SEGMENTS = coils.SEGMENTS
COILS = {
    'native': (15,150), 'ideal_coil': (None,None), 'q8': (8,110),
    'r15_only': (15,None), 'c150_only': (None,150),
    'r8_only': (8,None), 'c110_only': (None,110),
}
TOLERANCE = {'l90':(.9,.9),'l110':(1.1,1.1),'ldiff_pm':(.9,1.1),'ldiff_mp':(1.1,.9)}


def build_plan():
    cases = []
    prior = integrated.build_plan()['cases']
    corners = ('ss','tt','ff')

    def add(group,proc,variant,cb=0,direction=1,routes=ZERO,segment=None):
        kind = 'reference' if variant in ('r3','ideal_route') else 'native_direct'
        template_launch = 'bypass' if variant=='r3' else 'idealz50' if kind=='reference' else coils.SHARED
        template_cb = 0 if cb<2 else 2
        if direction==-1:
            routes = tuple(tuple(reversed(row)) for row in routes)
        q,srf = COILS.get(variant,(15,150) if variant in TOLERANCE else (None,None))
        fixture = f'{group}_{proc}_{variant}_cb{cb}_{"pos" if direction==1 else "neg"}'
        if segment is not None:
            fixture += f'_seg{segment}'
        for side in 'pn':
            parent, = [c for c in prior if c['process']==proc and c['launch']==template_launch and
                       c['integration']==kind and c['drive']==side and c['count_b']==template_cb]
            cases.append(dict(parent,case_id=f'lpend_{len(cases):03d}_{fixture}_{side}',
                              fixture_id=fixture,stage=group,group=group,variant_name=variant,
                              route_thirds=[list(r) for r in routes],
                              route_a=[v//3 for v in routes[0]],route_b=[v//3 for v in routes[1]],
                              count_b=cb,direction=direction,segment=segment,
                              coil_Q56=q,coil_SRF_GHz=srf))

    for proc in corners:
        add('baseline',proc,'r3')
        for cb in (0,2):
            for variant in ('native','ideal_route'):
                add('coverage',proc,variant,cb)
    for proc,cb in (('ss',2),('ff',0)):
        for variant in ('ideal_coil','native','q8','r15_only','c150_only','r8_only','c110_only'):
            add('coil_split',proc,variant,cb)
    for proc,cb in (('ss',2),('ff',0)):
        for variant in TOLERANCE:
            add('tolerance',proc,variant,cb)
    for proc in corners:
        for sign in (1,-1):
            for cb in (0,2):
                for variant in ('native','ideal_route'):
                    add('endpoint',proc,variant,cb,sign,EDGE)
    for proc in ('tt','ss','ff'):
        for sign in (1,-1):
            for segment in range(3):
                codes = range(9) if (proc,sign)==('tt',1) else (0,1,7,8)
                for cb in codes:
                    add('fine',proc,'native',cb,sign,SEGMENTS[segment:segment+2],segment)
    return {'format':'pam4_lp14_endpoint_fine_ac_v1','status':'REVIEW_PENDING',
            'cases':cases}


def render(case, model_root):
    deck,rails,ac,dc,currents,diff = integrated.render(case,model_root)
    if case['variant_name'] not in TOLERANCE:
        return deck,rails,ac,dc,currents,diff
    scales = dict(zip('PM',TOLERANCE[case['variant_name']]))
    # Hold series R and parallel C fixed while varying the physical inductance.
    deck,count = re.subn(r'(?m)^(GMSH([PM])LPK \([^\n]+\) inductor l=)120p$',
                        lambda m:f'{m[1]}{120*scales[m[2]]:.12g}p',deck)
    common.need(count==2,'Expected both native coil devices')
    parent,_ = BASE.load_inputs()
    return deck,rails,ac,dc,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def stage(case, dest, model_root=None):
    return integrated.mirror.prior.gm.stage(case,dest,model_root,renderer=render)


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
    common.need(plan==build_plan(),'Endpoint and fine plan differs')
    cases = plan['cases']
    if a.mode=='verify':
        for c in cases:
            render(c,BASE.MODEL_TOKEN)
        print(f'Endpoint/fine manifest and all {len(cases)} decks verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Supply distinct reviewed indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.model_root and a.approval,'Supply approved case and model root')
    approval = common.read(a.approval)
    common.need(approval.get('retire_new_raw') is not True,'Preserve endpoint raw')
    integrated.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,approval,
                                 plan=PLAN,stage_case=stage)


if __name__=='__main__':
    main()
