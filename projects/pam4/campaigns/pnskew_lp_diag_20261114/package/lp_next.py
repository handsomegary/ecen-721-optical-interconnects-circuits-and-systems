"""Render the lp14 AC power, endpoint, fine, and passive campaign."""
import argparse
import math
from pathlib import Path
import re

import gm_drive_lp as prior
import olympus_common as common

ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'case_plan.json'
BRANCH = 'lp14lo120'
SHARED = 'shared14lo120z50'
ZERO = ((33,33),(33,33))
EDGE = prior.EDGE
SEGMENTS = prior.parent.EDGE


def build_plan():
    cases = []
    seen = set()

    def add(stage, corner, launch, routes=ZERO, *, code=0, direction=1,
            q=None, srf=None, scale=1., segment=None):
        if direction == -1:
            routes = tuple(tuple(reversed(row)) for row in routes)
        proc, temp, vdd = corner
        key = (proc,launch,routes,code,q,srf,scale)
        common.need(key not in seen,'Duplicate fixture: '+str(key))
        seen.add(key)
        topology = ('branch' if launch==BRANCH else 'shared' if launch==SHARED else 'reference')
        for side in 'pn':
            cases.append(dict(case_id=f'lpnext_{len(cases):03d}_{proc}_{launch}_{side}', stage=stage,
                              process=proc, temperature_C=temp, vdd_V=vdd,
                              launch=launch, topology=topology, Z0_ohm=50 if launch in
                              (SHARED,'idealz50') else 25, kind='ac',
                              mode='bypass' if launch=='bypass' else 'bias',
                              variant='bypass' if launch=='bypass' else 'fine',
                              source_R_ohm=25, route_thirds=[list(a) for a in routes],
                              route_a=[v//3 for v in routes[0]], route_b=[v//3 for v in routes[1]],
                              count_b=code, direction=direction, gate_offset_mV=0,
                              segment=segment, active='a', probe='full', drive=side, off_probe=False,
                              coil_Q56=q, coil_SRF_GHz=srf, coil_scale=scale,
                              cpus=1, memory_GiB=4, wall_limit_min=30, estimated_solver_s=[3,30]))

    corners = (prior.SS,prior.TT,prior.FF)
    for corner in corners:
        add('power',corner,'bypass')
        for code in (0,2):
            for launch in ('ideal','idealz50',BRANCH,SHARED):
                add('power',corner,launch,code=code)

    # Keep the pilot's inactive branch length too when replaying its 25-ohm fixture.
    for launch in ('ideal','idealz50',BRANCH,SHARED):
        add('passive',prior.SS,launch,prior.SHORT if launch in ('ideal',BRANCH) else prior.DUAL)
    for launch in (BRANCH,SHARED):
        for q,srf,scale in ((15,None,1.),(None,150,1.),(15,150,1.),(8,110,1.),
                            (15,150,.9),(15,150,1.1)):
            add('passive',prior.SS,launch,prior.SHORT if launch==BRANCH else prior.DUAL,
                q=q,srf=srf,scale=scale)

    for corner in corners:
        for direction in (1,-1):
            for code in (0,2):
                for launch in ('ideal','idealz50',BRANCH,SHARED):
                    add('endpoint',corner,launch,EDGE,code=code,direction=direction)

    for launch in (BRANCH,SHARED):
        for corner in corners:
            for direction in (1,-1):
                add('passive',corner,launch,EDGE,code=2,direction=direction,q=15,srf=150)
    for corner in (prior.TT,prior.FF):
        add('passive',corner,SHARED,code=2,q=15,srf=150)

    for corner in (prior.TT,prior.SS,prior.FF):
        for direction in (1,-1):
            for segment in range(3):
                if corner==prior.TT and direction==1:
                    codes = tuple(range(9))
                else:
                    codes = ((0,1,8),(0,8),(0,7,8))[segment]
                for code in codes:
                    # Only the shared topology has a plausible two-bank budget
                    # with the presently measured bias.
                    add('fine',corner,SHARED,SEGMENTS[segment:segment+2],code=code,
                        direction=direction,segment=segment)
                    if code in (0,1,2,7,8):
                        add('fine',corner,'idealz50',SEGMENTS[segment:segment+2],code=code,
                            direction=direction,segment=segment)
    return {'format':'pam4_gmdrive_lp_next_v1','status':'REVIEW_PENDING',
            'scope':'AC, DC operating point, stationary output noise only',
            'cases':cases}


def nonideal_values(case):
    l_h = 120e-12*case['coil_scale']
    q, srf = case['coil_Q56'],case['coil_SRF_GHz']
    resistance = math.tau*56e9*l_h/q if q else 0.
    capacitance = 1/((math.tau*srf*1e9)**2*l_h) if srf else 0.
    return l_h,resistance,capacitance


def replace_peaking(deck, case):
    l_h, r, c = nonideal_values(case)
    if (l_h,r,c)==(120e-12,0.,0.):
        return deck

    def coil(match):
        name, source, sink = match.groups()
        end = name+'LN' if r else sink
        rows = [f'{name}LPK ({source} {end}) inductor l={l_h*1e12:.12g}p']
        if r:
            rows.append(f'{name}LR ({end} {sink}) resistor r={r:.12g}')
        if c:
            rows.append(f'{name}LC ({source} {sink}) capacitor c={c*1e15:.12g}f')
        return '\n'.join(rows)

    deck,count = re.subn(r'^(GMS[ABH][PM])LPK \((\w+) (GF_VDD)\) inductor l=120p$',
                        coil,deck,flags=re.M)
    common.need(count==(2 if case['topology']=='shared' else 4),'Missing peaking coils')
    return deck


def reference_z50(case, model_root):
    deck, rails, ac, dc, currents, _ = prior.render(dict(case,launch='ideal'),model_root)
    replace = prior.parent.gm.original.base.replace_once
    for bank, route in zip('AB',case['route_thirds']):
        for leg, length in zip('PM',route):
            stem = 'GMS'+bank+leg
            rs = f'{stem}RS ({stem}L {stem}I) resistor r=25'
            rt = f'{stem}RT ({stem}G X_cm) resistor r=25'
            # Reference pins get separate matched 50-ohm Thevenin drivers,
            # with exactly the same LC and far-end termination as shared Z50.
            deck = replace(deck,rs,rs.replace('r=25','r=50'))
            deck = replace(deck,rt,rt.replace('r=25','r=50'))
            ladder = prior.parent.scaled_path(stem,stem+'I',stem+'G',length)
            revised = re.sub(r'(inductor l=)([\d.]+)p',
                             lambda m:f'{m[1]}{2*float(m[2]):.10g}p',ladder)
            revised = re.sub(r'(capacitor c=)([\d.]+)f',
                             lambda m:f'{m[1]}{.5*float(m[2]):.10g}f',revised)
            deck = replace(deck,ladder,revised)
    return deck, rails, ac, dc, currents


def render(case, model_root):
    if case['launch']=='idealz50':
        deck, rails, ac, dc, currents = reference_z50(case,model_root)
    else:
        deck, rails, ac, dc, currents, _ = prior.render(case,model_root)
    deck = replace_peaking(deck,case)
    original, _ = prior.parent.gm.original.base.load_inputs()
    diff = prior.parent.gm.original.base.unified(
        original.replace(prior.parent.gm.original.base.MODEL_TOKEN,model_root),deck)
    return deck, rails, list(dict.fromkeys(ac)), dc, currents, diff


def stage(case, destination, model_root=None):
    return prior.parent.gm.stage(case,destination,model_root,renderer=render)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('verify','stage','run'),required=True)
    parser.add_argument('--index',type=int,action='append')
    parser.add_argument('--root',type=Path)
    parser.add_argument('--model-root',type=Path)
    parser.add_argument('--approval',type=Path)
    args = parser.parse_args()
    prior.parent.gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan==build_plan(),'Plan differs')
    if args.mode=='verify':
        print('LP NEXT manifest and plan verified')
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
    prior.parent.run(cases[args.index[0]],args.root,args.model_root,common.read(args.approval),
                     plan=PLAN,stage_case=stage)


if __name__=='__main__':
    main()
