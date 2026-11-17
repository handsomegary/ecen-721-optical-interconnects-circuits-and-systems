"""Prepare the LP14 1934-ohm reference and mirror-loaded OTA smoke."""
import argparse
from pathlib import Path
import re

import ref_smoke as prior
from recover_bias import validate_save_currents

ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'mirror_plan.json'
BASE = prior.BASE
common = prior.common
R_CORE = 1934


def build_plan():
    old = prior.build_plan()['cases']
    direct = [old[i] for i in (6,4,8)]
    cases = []

    def add(c, revision, stage='smoke', **overrides):
        cases.append(dict(dict(c, **overrides), revision=revision, stage=stage,
                          case_id=f'lpmirror_{len(cases):02d}_{c["process"]}_{revision}_{c["drive"]}'))

    for c in direct:
        add(c,'direct',ref_R_ohm=R_CORE)
    for c in direct:
        add(c,'pmos_pass',ref_R_ohm=R_CORE,pass_units=20)
    for c in old[:4]:
        add(c,'mirror_ota',p_output_units=4,n_output_units=1)
    for c in direct:
        add(c,'pmos_pass','followup',ref_R_ohm=R_CORE,pass_units=10)
    for c in old[:4]:
        add(c,'mirror_ota','followup',p_output_units=5,n_output_units=1)
    return {'format':'pam4_lp_refmirror_v1','status':'REVIEW_PENDING',
            'scope':'Three-corner isolated Iref DC and SS/FF isolated OTA AC',
            'target_reference_A':prior.phy.TARGET*1e-3/14,'cases':cases}


def pmos_pass(deck,case):
    _,r5 = BASE.load_inputs()
    card = BASE.device_cards(r5)['P']
    card,count = re.subn(r'\bl=30n\b','l=120n',card,count=1)
    common.need(count==1,'Unexpected original PMOS card')
    deck = BASE.replace_once(deck,'GMSQNALIGN (GMSR_REF GMSQND_OUT) vsource dc=0',
                             'GMSQNALIGN (GMSR_REF GMSQTOP) vsource dc=0')
    rows = [
        '// Upper PMOS source at GMSQTOP and bulk at GF_VDD.',
        '// Diagnostic only. Rail-limited ideal amplifier, not a physical bias circuit.',
        'GMSQGDRV (GMSQNCG 0) bsource v=min(max(v(GF_VDD)*0.5+1000*v(GMSQND_OUT,GMSQBN),0.05),v(GF_VDD)-0.05)',
    ]
    rows.extend(f'GMSQCAS{i} (GMSQND_OUT GMSQNCG GMSQTOP GF_VDD) {card}'
                for i in range(case['pass_units']))
    return BASE.replace_once(deck,'saveOptions options','\n'.join(rows)+'\nsaveOptions options')


def mirror_ota(deck,case):
    change = r'(?m)^(GMSQ(?:OID|OIR|OT|OBD|OPD|OPM|OP2|ON2)\d+ [^\n]+?\bl=)(?:30|60)n\b'
    deck,count = re.subn(change,r'\g<1>120n',deck)
    common.need(count==13,'Unexpected OTA device count')
    p = re.search(r'(?m)^GMSQOP20 (.+)$',deck)
    common.need(p is not None,'Missing PMOS output unit')
    deck = BASE.replace_once(deck,p.group(),p.group()+'\n'+'\n'.join(
        f'GMSQOP2{i} {p[1]}' for i in range(3,case['p_output_units'])))
    deck,count = re.subn(r'(?m)^GMSQON21 [^\n]+\n','',deck)
    common.need(count==1 and case['n_output_units']==1,'Unexpected NMOS output sizing')
    return deck


def render(case,model_root):
    deck,rails,ac,dc,currents,diff = prior.render(case,model_root)
    if case['revision']=='direct':
        return deck,rails,ac,dc,currents,diff
    if case['revision']=='pmos_pass':
        deck = pmos_pass(deck,case)
        dc.extend(('GMSQTOP','GMSQNCG'))
    else:
        deck = mirror_ota(deck,case)
    save = re.search(r'(?m)^save [^\n]+$',deck)
    deck = BASE.replace_once(deck,save.group(),'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails))))
    validate_save_currents(deck,dict(AC_traces=ac,DC_nodes=dc,DC_currents=currents,rail_voltages_V=rails))
    parent,_ = BASE.load_inputs()
    return deck,rails,ac,dc,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def stage(case, destination, model_root=None):
    return prior.gm.stage(case,destination,model_root,renderer=render)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--model-root',type=Path)
    p.add_argument('--approval',type=Path)
    a = p.parse_args()
    prior.gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan==build_plan(),'Mirror plan differs')
    cases = plan['cases']
    if a.mode=='verify':
        for c in cases:
            render(c,BASE.MODEL_TOKEN)
        print('Mirror manifest, plan and decks verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Use distinct explicit indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.approval and a.model_root,'Provide approved case and model root')
    prior.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,common.read(a.approval),
                           plan=PLAN,stage_case=stage,collect_case=prior.collect)


if __name__=='__main__':
    main()
