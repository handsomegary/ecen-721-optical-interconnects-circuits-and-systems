"""Generate the native LP14 reference and OTA integration AC fixtures."""
import argparse
from pathlib import Path
import re

import ref_mirror as mirror
import physical_bias as phy
import olympus_common as common
from recover_bias import validate_save_currents

ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'integration_plan.json'
BASE = mirror.BASE


def build_plan():
    prior = phy.build_plan()['cases'][:66]
    cases = []
    for variant, selector in (
        ('reference',lambda c:c['hardware']=='reference'),
        ('native_direct',lambda c:c['hardware']=='native_both'),
        ('fixed_iref_ota',lambda c:c['hardware']=='native_ota' and c['process']=='tt'),
    ):
        for c in filter(selector,prior):
            cases.append(dict(c,case_id=f'lpint_{len(cases):02d}_{c["process"]}_{variant}_{c["drive"]}',
                              stage='integration',integration=variant,ref_R_ohm=1934,
                              p_output_units=4,n_output_units=1))
    return {'format':'pam4_lp14_native_integration_v1','status':'REVIEW_PENDING',
            'scope':'Three-corner zero-skew AC, OP and stationary output noise',
            'cases':cases}


def render(case,model_root):
    deck,rails,ac,dc,currents,diff = phy.render(case,model_root)
    if case['integration']=='reference':
        return deck,rails,ac,dc,currents,diff
    deck = mirror.mirror_ota(deck,case)
    if case['integration']=='native_direct':
        # Match the isolated 1934-ohm L120 core exactly. Keep the replica
        # itself at the original RF device length.
        pattern = r'(?m)^(GMSQ(?:RPD|RPM|RND|RNS|RNM)\d+ [^\n]+?\bl=)(?:30|60)n\b'
        deck,n = re.subn(pattern,r'\g<1>120n',deck)
        common.need(n==19,'Unexpected Iref device count')
    validate_save_currents(deck,dict(AC_traces=ac,DC_nodes=dc,DC_currents=currents,rail_voltages_V=rails))
    parent,_ = BASE.load_inputs()
    return deck,rails,ac,dc,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def diagnostic(case,model_root,kind):
    return phy.diagnostic(case,model_root,kind,renderer=render)


def stage(case,destination,model_root=None):
    return mirror.prior.gm.stage(case,destination,model_root,renderer=render)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--model-root',type=Path)
    p.add_argument('--approval',type=Path)
    a = p.parse_args()
    mirror.prior.gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan==build_plan(),'Integration plan differs')
    cases = plan['cases']
    if a.mode=='verify':
        for c in cases:
            render(c,BASE.MODEL_TOKEN)
        print('Integration manifest, plan and decks verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Use distinct explicit indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.approval and a.model_root,'Provide approved case and model root')
    phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,common.read(a.approval),
                      plan=PLAN,stage_case=stage)


if __name__=='__main__':
    main()
