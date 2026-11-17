"""Small TT Iref and SS/FF replica OTA revision for the shared LP14."""
import argparse
from pathlib import Path
import re

import ref_smoke as prior
from recover_bias import validate_save_currents

ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'trim_plan.json'
common = prior.common
BASE = prior.BASE


def build_plan():
    old = prior.build_plan()['cases']
    cases = []
    def add(case,stage,revision,**updates):
        cases.append(dict(case,case_id=f'lptrim_{len(cases):02d}_{case["process"]}_{revision}_{case["drive"]}',
                          stage=stage,revision=revision,**updates))
    for r in (1800,2050):
        add(dict(old[5],ref_R_ohm=r),'smoke','r_bracket')
    add(dict(old[4],ref_R_ohm=2050),'smoke','regulated_n',upper_units=20)
    for case in old[:4]:
        add(case,'smoke','symmetric_ota',ota_load_ohm=39_000)
    add(dict(old[4],ref_R_ohm=2050),'followup','long_control')
    for i in (6,8):
        add(dict(old[i],ref_R_ohm=2050),'followup','regulated_n',upper_units=20)
    for case in old[:4]:
        add(case,'followup','symmetric_ota',ota_load_ohm=33_000)
    return {'format':'pam4_lp_reftrim_v1','status':'REVIEW_PENDING',
            'scope':'Isolated reference DC and replica OTA RF AC, with ideal stimulus controls',
            'target_reference_A':prior.phy.TARGET*1e-3/14,'cases':cases}


def regulated_n(deck, case, dc):
    # OTA controlled series transistor. The auxiliary amplifier is deliberately
    # ideal and the resulting gate voltage is checked against the available rail.
    deck = BASE.replace_once(deck,'GMSQNALIGN (GMSR_REF GMSQND_OUT) vsource dc=0',
                             'GMSQNALIGN (GMSR_REF GMSQTOP) vsource dc=0')
    card = re.search(r'(?m)^GMSQRNM0 \([^\n)]+\) ([^\n]+)$',deck)
    common.need(card is not None,'Missing reference device card')
    rows = ['GMSQNCTRL (GMSQNCG 0 GMSQBN GMSQND_OUT) vcvs gain=1000']
    rows.extend(f'GMSQCAS{i} (GMSQTOP GMSQNCG GMSQND_OUT 0) {card[1]}'
                for i in range(case['upper_units']))
    deck = BASE.replace_once(deck,'saveOptions options','\n'.join(rows)+'\nsaveOptions options')
    dc.extend(('GMSQNCG','GMSQTOP'))
    return deck


def symmetric_ota(deck,case):
    deck,n = re.subn(r'(?m)^GMSQ(?:OPD|OPM)\d+ [^\n]+\n','',deck)
    common.need(n==4,'Expected four original mirror units')
    resistors = '\n'.join(f'GMSQOL{i} (GF_VDD {node}) resistor r={case["ota_load_ohm"]}'
                          for i,node in enumerate(('GMSQO1','GMSQOM')))
    deck = BASE.replace_once(deck,'// END GMFINE',resistors+'\n// END GMFINE')
    # Same input-pair L and device unit in both halves. A longer output stage
    # is a separate lever on ro; keep the original branch counts and Miller RC.
    names = r'(?m)^(GMSQ(?:OID|OIR|OP2|ON2)\d+ [^\n]+?\bl=)(?:30|60)n\b'
    deck,n = re.subn(names,r'\g<1>120n',deck)
    common.need(n==7,'Unexpected OTA device count')
    return deck


def render(case,model_root):
    deck,rails,ac,dc,currents,_ = prior.render(case,model_root)
    if case['revision']=='regulated_n':
        deck = regulated_n(deck,case,dc)
    elif case['revision']=='symmetric_ota':
        deck = symmetric_ota(deck,case)
    save = re.search(r'(?m)^save [^\n]+$',deck)
    deck = BASE.replace_once(deck,save.group(),'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails))))
    validate_save_currents(deck,dict(AC_traces=ac,DC_nodes=dc,DC_currents=currents,rail_voltages_V=rails))
    parent,_ = BASE.load_inputs()
    return deck,rails,ac,dc,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def stage(case,dest,model_root=None):
    return prior.gm.stage(case,dest,model_root,renderer=render)


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
    common.need(plan==build_plan(),'Trim plan differs')
    if a.mode=='verify':
        for c in plan['cases']:
            render(c,BASE.MODEL_TOKEN)
        print('Trim manifest, plan and all decks verified')
        return
    cases = plan['cases']
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Supply distinct explicit indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.model_root and a.approval,'Supply one approved case and private model root')
    prior.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,common.read(a.approval),
                           plan=PLAN,stage_case=stage,collect_case=prior.collect)


if __name__=='__main__':
    main()
