"""Render and run the shared LP14 current-replica feasibility AC campaign."""
import argparse
from pathlib import Path
import re

import lp_next as prior
import olympus_common as common

ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'case_plan.json'
SHARED = prior.SHARED
DRIVE = prior.prior.parent
N = 14
R_LOAD = 33
OVERHEAD_MW = .4
MAIN_TARGETS = (4.2,4.5,4.7,5.0)
UPPER_TARGETS = (5.5,6.0)


def build_plan():
    cases = []
    for original in prior.build_plan()['cases'][:54]:
        launch = original['launch']
        if launch not in ('bypass','idealz50',SHARED):
            continue
        mode = 'fixed_v' if launch==SHARED else 'reference'
        cases.append(dict(original,case_id=f'lpbias_{len(cases):03d}_{original["process"]}_{mode}_{original["drive"]}',
                          stage='bias',bias_mode=mode,target_mA_per_leg=None))
    controls = [c for c in cases if c['bias_mode']=='fixed_v']
    for stage, targets in (('bias',MAIN_TARGETS),('upper',UPPER_TARGETS)):
        for target in targets:
            for c in controls:
                if stage=='upper' and c['process']=='ss':
                    continue
                cases.append(dict(c,case_id=f'lpbias_{len(cases):03d}_{c["process"]}_i{round(100*target):03d}_{c["drive"]}',
                                  stage=stage,bias_mode='replica',target_mA_per_leg=target))
    return {'format':'pam4_lp_bias_review_v1','status':'REVIEW_PENDING',
            'scope':'Shared LP14 zero-skew AC, DC OP, and output noise feasibility',
            'physical_bias_extra_reserve_mW':OVERHEAD_MW,'cases':cases}


def render(case, model_root):
    deck, rails, ac, dc, currents, diff = prior.render(case,model_root)
    if case['bias_mode']!='replica':
        return deck,rails,ac,dc,currents,diff
    original,_ = DRIVE.gm.original.base.load_inputs()
    template = DRIVE.gm.frontend_parts(original)[1]['XM1p0']
    replace = DRIVE.gm.original.base.replace_once
    rows = [
        '// LP14 replica bias feasibility: native replica, ideal reference and servo',
        f'GMSRRD (GF_VDD GMSR_D) resistor r={N*R_LOAD}',
        f'GMSRRREF (GF_VDD GMSR_REF) resistor r={N*R_LOAD}',
        f'GMSRIREF (GMSR_REF 0) isource dc={case["target_mA_per_leg"]*1e-3/N:.12g}',
        'GMSRAMP (GMSR_E 0 GMSR_D GMSR_REF) vcvs gain=1000',
        'GMSRRF (GMSR_E GMSR_BIAS) resistor r=100K',
        'GMSRCF (GMSR_BIAS 0) capacitor c=10p',
        DRIVE.gm.geometry(template,'GMSRCS0',('GMSR_D','GMSR_BIAS','0','0')),
    ]
    deck = replace(deck,'// END GMFINE','\n'.join(rows)+'\n// END GMFINE')
    for leg in 'PM':
        stem = 'GMSH'+leg
        old = f'{stem}VFG ({stem}VGB 0) vsource dc=0.48'
        deck = replace(deck,old+'\n','')
        deck = replace(deck,f'{stem}GB ({stem}FG {stem}VGB) resistor r=10K',
                       f'{stem}GB ({stem}FG GMSR_BIAS) resistor r=10K')
        del rails[stem+'VFG:p']
    dc = list(dict.fromkeys([*dc,'GMSR_D','GMSR_REF','GMSR_BIAS']))
    currents = list(dict.fromkeys([*currents,'GMSRIREF:p']))
    save = re.search(r'^save PNC_PREP [^\n]+$',deck,re.M).group()
    deck = replace(deck,save,'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails))))
    diff = DRIVE.gm.original.base.unified(
        original.replace(DRIVE.gm.original.base.MODEL_TOKEN,model_root),deck)
    return deck,rails,ac,dc,currents,diff


def stage(case, destination, model_root=None):
    return DRIVE.gm.stage(case,destination,model_root,renderer=render)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('verify','stage','run'),required=True)
    parser.add_argument('--index',type=int,action='append')
    parser.add_argument('--root',type=Path)
    parser.add_argument('--model-root',type=Path)
    parser.add_argument('--approval',type=Path)
    args = parser.parse_args()
    DRIVE.gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan==build_plan(),'Plan differs')
    if args.mode=='verify':
        print('LP BIAS manifest and plan verified')
        return
    cases = plan['cases']
    common.need(args.root and args.index and all(0<=i<len(cases) for i in args.index),
                'Supply root and explicit reviewed indices')
    if args.mode=='stage':
        for i in args.index:
            stage(cases[i],args.root.resolve()/cases[i]['case_id'],args.model_root)
        return
    common.need(len(args.index)==1 and args.model_root and args.approval,
                'Provide one approved case, private model root and approval')
    DRIVE.run(cases[args.index[0]],args.root,args.model_root,common.read(args.approval),
              plan=PLAN,stage_case=stage)


if __name__=='__main__':
    main()
