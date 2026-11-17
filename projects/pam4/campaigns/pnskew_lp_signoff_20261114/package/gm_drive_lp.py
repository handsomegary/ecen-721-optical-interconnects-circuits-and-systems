"""Generate the SS low-power driver pilot and conditional fallback fixtures."""
import argparse
from pathlib import Path
import re

import gm_drive as parent
import olympus_common as common

ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'case_plan.json'
LOW = {'lp12lo80': (12, 33, 80, .48),
       'lp14lo120': (14, 33, 120, .48),
       'lp12l120': (12, 33, 120, .53)}
LAUNCHES = parent.LAUNCHES | LOW
SHARED = {'shared16': LAUNCHES['cs16'], 'shared16z50': LAUNCHES['cs16'],
          'shared14lo120z50': LOW['lp14lo120']}
TT, SS, FF = parent.fine.TT, parent.fine.SS, parent.fine.FF
SHORT = parent.SHORT
DUAL = ((3, 3), (3, 3))
EDGE = (parent.EDGE[0], parent.EDGE[-1])
ZERO = ((33, 33), (30, 36))
STAGES = ('pilot', 'architecture', 'fallback_short', 'fallback_edge', 'fallback_fine')


def build_plan():
    cases = []

    def add(launch, *, corner=SS, stage='pilot', topology=None, source_r=25,
            routes=SHORT, code=0, direction=1, probe='full', segment=None):
        if topology is None:
            topology = 'branch' if launch in LAUNCHES else 'reference'
        proc, temp, vdd = corner
        a, b = routes if direction == 1 else tuple(tuple(reversed(r)) for r in routes)
        for drive in 'pn':
            cases.append(dict(case_id=f'gmdrivelp_{len(cases):03d}_{proc}_{launch}_{drive}',
                              stage=stage, process=proc, temperature_C=temp, vdd_V=vdd,
                              launch=launch, topology=topology,
                              Z0_ohm=50 if launch.endswith('z50') else 25,
                              kind='ac', mode='bypass' if launch=='bypass' else 'bias',
                              variant='bypass' if launch=='bypass' else 'fine',
                              source_R_ohm=source_r, route_thirds=[list(a),list(b)],
                              route_a=[k//3 for k in a], route_b=[k//3 for k in b],
                              count_b=code, direction=direction, gate_offset_mV=0,
                              segment=segment, active='a', probe=probe, drive=drive,
                              off_probe=probe != 'full', cpus=1, memory_GiB=4,
                              wall_limit_min=30, estimated_solver_s=[3,30]))

    for r in (0, 25):
        for launch in ('bypass', 'ideal', 'cs16', *LOW):
            add(launch, source_r=r)
    for launch in ('cs16', 'lp14lo120'):
        add(launch, source_r=0, probe='dormant')
    for launch, top, r in (('ideal','reference',25), ('cs16','branch',25),
                          ('lp14lo120','branch',25), ('shared16','shared',25),
                          ('shared16z50','shared',25), ('shared14lo120z50','shared',25),
                          ('direct_ideal','direct',0), ('direct_idealz50','direct',0), ('direct','direct',0),
                          ('directz50','direct',0)):
        add(launch, stage='architecture', topology=top, source_r=r, routes=DUAL, code=2)
    for launch in SHARED:
        add(launch, stage='architecture', topology='shared', routes=DUAL)
    for launch in ('ideal','cs16','lp14lo120'):
        add(launch, stage='architecture', routes=DUAL)
    for launch in ('direct_ideal','direct_idealz50','direct','directz50'):
        add(launch, stage='architecture', topology='direct', routes=DUAL, source_r=0)
    for corner in (TT, FF):
        for launch in ('bypass','ideal','cs16'):
            add(launch, corner=corner, stage='fallback_short')
    for corner in (SS, TT, FF):
        for launch in ('ideal','cs16'):
            add(launch, corner=corner, stage='fallback_edge', routes=ZERO)
            for direction in (1,-1):
                for code in (0,2):
                    add(launch, corner=corner, stage='fallback_edge', routes=EDGE,
                        code=code, direction=direction)
        for segment, codes in ((0,(0,1,8)), (1,(0,8)), (2,(0,7,8))):
            for code in codes:
                add('cs16', corner=corner, stage='fallback_fine', segment=segment,
                    routes=parent.EDGE[segment:segment+2], code=code)
    return {'format':'pam4_gmdrive_low_power_v1', 'status':'REVIEW_PENDING',
            'scope':'AC, DC operating point and stationary output noise',
            'cases':cases}


def source_rc(deck, case, feed_p, feed_m):
    for side, source, feed in (('P','XVin',feed_p), ('N','PNCVN',feed_m)):
        pre = 'PNC_PRE'+side
        line = f'{source} ({pre} X_cm) vsource dc=0 mag={int(case["drive"]==side.lower())}'
        deck = parent.gm.original.base.replace_once(
            deck, line, line+f'\nLPR{side} ({pre} {feed}) resistor r=100'
            + f'\nLPC{side} ({feed} X_cm) capacitor c=85.26157665637249f')
    return deck


def render(case, model_root):
    launch, topology = case['launch'], case['topology']
    replace = parent.gm.original.base.replace_once
    if topology == 'branch':
        return parent.render(case, model_root, LAUNCHES)
    if topology == 'reference' and launch != 'bypass':
        return parent.render(case, model_root)
    base = case if launch == 'bypass' else dict(case, launch='ideal')
    deck, rails, ac, dc, currents, diff = parent.render(base, model_root)
    if launch == 'bypass':
        if not case['source_R_ohm']:
            return deck, rails, ac, dc, currents, diff
        for leg, node in (('P','X_ip'),('N','X_im')):
            old = f'ACN{leg}RS (PNC_PRE{leg} {node}) resistor r=25'
            deck = replace(deck, old, f'LPBR{leg} (PNC_PRE{leg} LPBP{leg}) resistor r={case["source_R_ohm"]}'
                           + f'\nACN{leg}RS (LPBP{leg} {node}) resistor r=25')
    else:
        original, _ = parent.gm.original.base.load_inputs()
        template = parent.gm.frontend_parts(original)[1]['XM1p0']
        blocks = []
        if launch in ('direct','directz50'):
            deck = source_rc(deck, case, 'LP2P', 'LP2N')
        for leg, pn in (('P','P'), ('M','N')):
            stem = 'GMSH'+leg
            pre = ('GDRPIN' if case['source_R_ohm'] else 'PNC_PRE')+pn
            feed = 'LP2'+pn if launch in ('direct','directz50') else pre
            if topology == 'shared':
                bias = SHARED[launch]
                block, nodes = parent.launch_block(stem, pre, True, bias, template, 0)
                blocks.append(block)
                rails[stem+'VFG:p'] = bias[3]
                ac.extend(nodes)
                dc.extend(nodes)
                feed = stem+'L'
            else:
                ac.append(feed)
            for bank, route in zip('AB', case['route_thirds']):
                prefix = 'GMS'+bank+leg
                line = re.search(rf'^{prefix}DRV .*$', deck, re.M).group()
                deck = replace(deck, line, f'{prefix}DRV ({feed} {prefix}L) vsource dc=0')
                old_rs = f'{prefix}RS ({prefix}L {prefix}I) resistor r=25'
                deck = replace(deck, old_rs, old_rs.replace('r=25','r=1m'))
                if case['Z0_ohm'] == 50:
                    term = f'{prefix}RT ({prefix}G X_cm) resistor r=25'
                    deck = replace(deck, term, term.replace('r=25','r=50'))
                    original_path = parent.scaled_path(prefix, prefix+'I', prefix+'G', route[int(leg=='M')])
                    line_lc = re.sub(r'(inductor l=)([\d.]+)p',
                                     lambda m: f'{m[1]}{2*float(m[2]):.10g}p', original_path)
                    line_lc = re.sub(r'(capacitor c=)([\d.]+)f',
                                     lambda m: f'{m[1]}{.5*float(m[2]):.10g}f', line_lc)
                    deck = replace(deck, original_path, line_lc)
        if topology == 'shared':
            deck = replace(deck, '// END GMFINE', '\n'.join(blocks)+'\n// END GMFINE')
            deck = parent.cross_stage2(deck)
        ac.extend(n for n in currents if n.endswith('VD:p'))
        save = re.search(r'^save PNC_PREP [^\n]+$', deck, re.M).group()
        deck = replace(deck, save, 'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails))))
    original, _ = parent.gm.original.base.load_inputs()
    diff = parent.gm.original.base.unified(original.replace(parent.gm.original.base.MODEL_TOKEN,model_root),deck)
    return deck, rails, list(dict.fromkeys(ac)), dc, currents, diff


def stage(case, destination, model_root=None):
    return parent.gm.stage(case, destination, model_root, renderer=render)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('verify','stage','run'), required=True)
    parser.add_argument('--index', type=int, action='append')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--model-root', type=Path)
    parser.add_argument('--approval', type=Path)
    args = parser.parse_args()
    parent.gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan == build_plan(), 'Plan differs')
    if args.mode == 'verify':
        print('GMDRIVE LP manifest and plan verified')
        return
    cases = plan['cases']
    common.need(args.root and args.index and all(0<=i<len(cases) for i in args.index),
                'Provide root and explicit case indices')
    if args.mode == 'stage':
        for i in args.index:
            stage(cases[i], args.root.resolve()/cases[i]['case_id'], args.model_root)
        return
    common.need(len(args.index)==1 and args.model_root and args.approval,
                'Provide one approved case, private model root and approval')
    parent.run(cases[args.index[0]], args.root, args.model_root, common.read(args.approval),
               plan=PLAN, stage_case=stage)


if __name__ == '__main__':
    main()
