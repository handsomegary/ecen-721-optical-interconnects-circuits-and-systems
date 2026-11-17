"""Render and run the next PAM4 PN-skew AC fixtures."""
import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import sys

import gm_fine as fine
import gm_select as gm
import olympus_common as common

ROOT = Path(__file__).resolve().parent
LAUNCHES = {
    'cs12': (12, 33, 0, .53),
    'cs12lo': (12, 33, 0, .48),
    'cs12r27': (12, 27, 0, .53),
    'cs16': (16, 33, 0, .53),
    'cs12l20': (12, 33, 20, .53),
}
# Route lengths are in thirds of the original 25-ohm LC section.
EDGE = ((18, 48), (20, 46), (22, 44), (24, 42))
SHORT = ((3, 3), (24, 42))


def build_plan():
    cases = []

    def add(corner, stage, launch, routes=SHORT, *, code=0, direction=1,
            source_r=0, probe='full', segment=None, offset_mV=0):
        a, b = routes if direction == 1 else tuple(tuple(reversed(r)) for r in routes)
        process, temp, vdd = corner
        mode = 'bypass' if launch == 'bypass' else 'bias'
        for drive in ('p', 'n'):
            case_id = f'gmdrive_{len(cases):03d}_{process}_{launch}_{drive}'
            cases.append(dict(case_id=case_id, stage=stage, process=process,
                              temperature_C=temp, vdd_V=vdd, launch=launch,
                              mode=mode, variant='bypass' if mode == 'bypass' else 'fine',
                              route_a=[k // 3 for k in a], route_b=[k // 3 for k in b],
                              route_thirds=[list(a), list(b)], segment=segment, direction=direction,
                              source_R_ohm=source_r, gate_offset_mV=offset_mV, count_b=code, kind='ac',
                              active='a', probe=probe, drive=drive, off_probe=probe != 'full',
                              cpus=1, memory_GiB=4, wall_limit_min=30,
                              estimated_solver_s=[3, 30]))

    add(fine.SS, 'short', 'bypass')
    add(fine.SS, 'short', 'ideal')
    for launch in LAUNCHES:
        add(fine.SS, 'short', launch)
    add(fine.SS, 'short', 'cs12', probe='dormant')
    add(fine.SS, 'short', 'ideal', probe='dormant')
    for launch in ('ideal', 'cs12'):
        add(fine.SS, 'short_loaded', launch, source_r=25)
    for offset in (-100, 100):
        add(fine.SS, 'short_swing', 'cs12', offset_mV=offset)
    for corner in (fine.TT, fine.SS, fine.FF):
        if corner != fine.SS:
            add(corner, 'corner_short', 'bypass')
            add(corner, 'corner_short', 'ideal')
            add(corner, 'corner_short', 'cs12')
        for launch in ('ideal', 'cs12'):
            add(corner, 'zero', launch, ((33, 33), (30, 36)))
        for direction in (1, -1):
            for code in (0, 2):
                for launch in ('ideal', 'cs12'):
                    add(corner, 'edge', launch, (EDGE[0], EDGE[-1]), code=code,
                        direction=direction)
            add(corner, 'edge', 'cs12', (EDGE[0], EDGE[-1]), direction=direction,
                probe='dormant')
    for corner in (fine.TT, fine.SS, fine.FF):
        for direction in (1, -1):
            for segment, codes in ((0, (0, 1, 8)), (2, (0, 7, 8))):
                for code in codes:
                    for launch in ('ideal', 'cs12'):
                        if corner == fine.TT and direction == 1 and launch == 'cs12':
                            continue
                        add(corner, 'fine', launch, EDGE[segment:segment+2],
                            code=code, direction=direction, segment=segment)
    for segment in range(3):
        for code in range(9):
            add(fine.TT, 'fine_full_tt', 'cs12', EDGE[segment:segment+2],
                code=code, segment=segment)
    return {'format': 'pam4_gmdrive_review_v1', 'status': 'REVIEW_PENDING',
            'scope': 'AC, DC operating point, and small-signal noise only',
            'cases': cases}


def scaled_path(prefix, pin, gate, thirds):
    sections, tail = divmod(thirds, 3)
    scales = [1.] * sections
    if tail:
        scales += [tail / 3]
    rows = []
    start = pin
    for k, scale in enumerate(scales):
        tag = f'{prefix}{k:02d}'
        end = gate if k == len(scales) - 1 else tag + 'O'
        rows.extend((
            f'{tag}LA ({start} {tag}A) inductor l={6.5*scale:.10g}p',
            f'{tag}RA ({tag}A {tag}M) resistor r={.1525*scale:.10g}',
            f'{tag}C ({tag}M 0) capacitor c={20.8*scale:.10g}f',
            f'{tag}LB ({tag}M {tag}B) inductor l={6.5*scale:.10g}p',
            f'{tag}RB ({tag}B {end}) resistor r={.1525*scale:.10g}',
        ))
        start = end
    return '\n'.join(rows)


def launch_block(prefix, feed, on, design, template, offset_mV):
    count, rd, peak, bias = design
    gate, drain, launch = (prefix + node for node in ('FG', 'FD', 'L'))
    rail = prefix + 'VGB'
    upper = prefix + 'LP'
    # Connect each physical RF gate through a DC block. The disabled branch
    # keeps its actual drain/load and MOS feedthrough.
    rows = [
        f'{prefix}VFG ({rail} 0) vsource dc={bias + offset_mV / 1000 if on else .10:.9g}',
        f'{prefix}CIN ({feed} {gate}) capacitor c=10p',
        f'{prefix}GB ({gate} {rail}) resistor r=10K',
        f'{prefix}COUT ({drain} {launch}) capacitor c=10p',
        f'{prefix}LB ({launch} X_cm) resistor r=100K',
        f'{prefix}RD ({drain} {upper if peak else "GF_VDD"}) resistor r={rd}',
    ]
    if peak:
        rows.append(f'{prefix}LPK ({upper} GF_VDD) inductor l={peak}p')
    rows.extend(gm.geometry(template, prefix + f'CS{k}', (drain, gate, '0', '0'))
                for k in range(count))
    return '\n'.join(rows), (gate, drain)


def render(case, model_root):
    deck, rails, ac, dc, currents, diff = fine.render(case, model_root)
    launch = case['launch']
    if launch == 'bypass':
        return deck, rails, ac, dc, currents, diff
    parent, _ = gm.original.base.load_inputs()
    physical_launch = launch in LAUNCHES
    source_r = case['source_R_ohm']
    if source_r:
        point = 'PNCVN (PNC_PREN X_cm) vsource dc=0 mag=' + str(int(case['drive'] == 'n'))
        deck = gm.original.base.replace_once(
            deck, point, point + f'\nGDRP (PNC_PREP GDRPINP) resistor r={source_r}'
            + f'\nGDRN (PNC_PREN GDRPINN) resistor r={source_r}')
    signal = gm.frontend_parts(parent)[1]
    routes = (case['route_a'], case['route_b'])
    for bank, route, thirds, enabled in zip('AB', routes, case['route_thirds'],
                                           (8-case['count_b'], case['count_b'])):
        for leg, length, sublength in zip('PM', route, thirds):
            prefix = 'GMS' + bank + leg
            original_path = []
            gm.original.passive_path(original_path, prefix, prefix+'I', prefix+'G', length)
            deck = gm.original.base.replace_once(deck, '\n'.join(original_path),
                                                scaled_path(prefix, prefix+'I', prefix+'G', sublength))
            feed = ('GDRPIN' if source_r else 'PNC_PRE') + ('P' if leg == 'P' else 'N')
            active_ac = not case['off_probe'] or enabled == 0
            original = re.search(rf'^{prefix}DRV .*$', deck, re.M).group()
            if physical_launch:
                # A zero-volt sensor takes the place of the original VCVS, so
                # its documented current trace is still available.
                sensor = f'{prefix}DRV ({feed if active_ac else "X_cm"} {prefix}VIN) vsource dc=0'
                offset = case['gate_offset_mV'] * (1 if leg == 'P' else -1)
                block, nodes = launch_block(prefix, prefix+'VIN', enabled > 0,
                                            LAUNCHES[launch], signal['XM1p0'], offset)
                deck = gm.original.base.replace_once(deck, original, sensor+'\n'+block)
                deck = gm.original.base.replace_once(
                    deck, f'{prefix}RS ({prefix}L {prefix}I) resistor r=25',
                    f'{prefix}RS ({prefix}L {prefix}I) resistor r=1m')
                rails[prefix+'VFG:p'] = LAUNCHES[launch][3] + offset/1000 if enabled else .10
                ac.extend(nodes)
                ac.append(prefix+'VIN')
                dc.extend(nodes)
            else:
                replacement = (f'{prefix}DRV ({prefix}L X_cm {feed} X_cm) '
                               f'vcvs gain={int(active_ac and enabled > 0)}')
                deck = gm.original.base.replace_once(deck, original, replacement)
    if physical_launch:
        # The common-source stage inverts each leg. Cross stage-2 gates once
        # after the delay and r3 stage-1 summing so the P/N timing labels stay put.
        deck, count = re.subn(r'(^XM2([pm])\d+ \(X_o_\2 )X_c_\2( X_s2_\2 0\))',
                              lambda m: m[1] + ('X_c_m' if m[2] == 'p' else 'X_c_p') + m[3],
                              deck, flags=re.M)
        common.need(count == 16, 'Expected 16 original stage-2 gate connections')
    save = re.search(r'^save PNC_PREP [^\n]+$', deck, re.M).group()
    deck = gm.original.base.replace_once(deck, save, 'save ' + ' '.join(
        dict.fromkeys(ac + dc + currents + list(rails))))
    common.need(not re.search(r'^\w+ tran\b', deck, re.M), 'Unexpected transient analysis')
    return (deck, rails, ac, dc, currents,
            gm.original.base.unified(parent.replace(gm.original.base.MODEL_TOKEN, model_root), deck))


def plan_path():
    return ROOT / 'case_plan.json'


def stage(case, destination, model_root=None):
    return gm.stage(case, destination, model_root, renderer=render)


def approved_case(case, approval):
    return (approval.get('approved') is True and approval.get('platform') == 'Olympus'
            and approval.get('plan_sha256') == common.sha(plan_path())
            and approval.get('design_source_sha256') == common.sha(ROOT/'SHA256SUMS.txt')
            and case['case_id'] in approval.get('case_ids', [])
            and case['stage'] in approval.get('stages', []))


def run(case, root, model, approval):
    common.need(approved_case(case, approval), 'Approval must bind this case and package')
    common.need(datetime.now(timezone.utc)+timedelta(minutes=30)
                <= datetime(2027,1,1,6,tzinfo=timezone.utc), 'Olympus authorization expired')
    spectre, env = common.environment()
    dest = common.checked_root(root) / case['case_id']
    record = stage(case, dest, model)
    (dest/'.study_owned').write_text(os.environ['SLURM_JOB_ID']+'\n', encoding='utf-8')
    result = common.run_classic(dest, common.sha(dest/'bench.scs'),
                                dict(format='pam4_gmdrive_run_v1', case_id=case['case_id'],
                                     case_sha256=common.sha(dest/'case.json'),
                                     plan_sha256=common.sha(plan_path())),
                                1200, spectre, env)
    sys.path.insert(0, str(ROOT/'pvt'))
    from pvt.collect_ac import require_effective_scale
    require_effective_scale((dest/'spectre.log').read_bytes())
    gm.collect(dest, record, result)
    import resource
    common.write_new(dest/'resource_observation.json', {
        'spectre_wall_s': result['spectre_wall_seconds'],
        'peak_child_RSS_KiB': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        'raw_bytes': sum(row['bytes'] for row in result['raw_inventory']),
    })
    if approval.get('retire_new_raw') is True:
        receipt = common.retire_case_raw(dest, [p.name for p in dest.iterdir() if p.is_file()])
        print('Raw retirement:', receipt['status'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('verify', 'stage', 'run'), required=True)
    parser.add_argument('--index', type=int, action='append')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--model-root', type=Path)
    parser.add_argument('--approval', type=Path)
    args = parser.parse_args()
    gm.original.verify_package()
    plan = common.read(plan_path())
    common.need(plan == build_plan(), 'Case plan differs')
    if args.mode == 'verify':
        print('Package SHA and case plan verified')
        return
    common.need(args.root and args.index and all(0 <= i < len(plan['cases']) for i in args.index),
                'Select explicit case indices and a root')
    if args.mode == 'stage':
        for index in args.index:
            case = plan['cases'][index]
            stage(case, args.root.resolve()/case['case_id'], args.model_root)
        return
    common.need(len(args.index) == 1 and args.model_root and args.approval,
                'An approved Olympus run requires one case, a private model root, and approval')
    run(plan['cases'][args.index[0]], args.root, args.model_root, common.read(args.approval))


if __name__ == '__main__':
    main()
