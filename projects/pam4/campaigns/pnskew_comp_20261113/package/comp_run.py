"""Stage, review and run one explicitly approved Olympus compensation case."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import os
import sys

import comp_cell as cell
import comp_measure as measure
import comp_plan as study
import olympus_common as common
from pilot_controller import select, read_pilot
import admit


def leaf(name):
    common.need(isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]{0,140}',name),
                'Expected a single case directory name')
    return name


def check_approval(approval, plan_path, stage, case_id):
    common.need(approval.get('approved') is True and approval.get('platform')=='Olympus' and
                approval.get('plan_sha256')==common.sha(plan_path) and
                approval.get('design_source_sha256')==common.sha(cell.ROOT/'SHA256SUMS.txt') and
                case_id in approval.get('case_ids', []) and stage in approval.get('stages', []),
                'Approved plan and specific case/stage required')
    common.need(datetime.now(timezone.utc).timestamp()+4*3600 <=
                datetime(2027,1,1,6,tzinfo=timezone.utc).timestamp(),
                'Olympus user authorization expired')


def check_source_manifest():
    for line in (cell.ROOT/'SHA256SUMS.txt').read_text(encoding='ascii').splitlines():
        expected, relative = line.split('  ',1)
        path = cell.ROOT/relative
        common.need(path.resolve().is_relative_to(cell.ROOT) and common.sha(path)==expected,
                    'Package file differs from reviewed SHA: '+relative)


def pilot_case(row, p_code, n_code):
    common.need(any([p_code,n_code]==[k,63-k] for k in range(64)), 'Expected complementary pilot codes')
    common.need(not row['added_differential_stress_ps'], 'Calibration uses unmodified pilot stimulus')
    return dict(row, case_id='pilot_'+row['case_id']+'_c%02d'%p_code,
                kind='pilot',stage='pilot',p_code=p_code,n_code=n_code)


def payload_case(row, observations, approval):
    pilot = read_pilot(observations)
    # The selection function receives only code IDs and measured training/check phasors.
    selected = select(pilot['observations'],approval['residual_ps'],approval['repeat_ps'])
    common.need(selected['status']=='LOCK', 'Calibration NO_LOCK; preserve observation evidence')
    common.need(pilot.get('calibration_id')==calibration_id(row), 'Pilot evidence condition differs')
    imposed = row['added_differential_stress_ps']
    if row['study']=='stress':
        imposed -= selected['verification_fit']['estimated_residual_ps']
    return dict(row,kind='payload',stage='payload',p_code=selected['p_code'],n_code=selected['n_code'],
                actual_added_offset_ps=imposed,
                pilot_observations_sha256=common.sha(observations),code_selection=selected)


def calibration_id(row):
    return '%s_%+07d' % (study.tag((row['process'],row['temperature_C'],row['vdd_V'])),
                        round(1e5*row['injected_skew_UI']))


def load_case(args, plan):
    ac = args.kind=='ac'
    rows = plan['cases' if ac else 'integrated_plan']
    common.need(0 <= args.index < len(rows), 'Case index outside frozen plan')
    row = rows[args.index]
    if ac:
        return row
    if args.kind=='pilot':
        common.need(args.code is not None and 0<=args.code<=63, 'Choose a valid pilot code')
        row = dict(row,seed=None,added_differential_stress_ps=0.)
        row['case_id'] = calibration_id(row)
        return pilot_case(row,args.code,63-args.code)
    if args.observations is None:
        raise ValueError('Payload requires aggregated blind observations')
    return payload_case(row,args.observations,common.read(args.approval))


def materialize(case, destination, model_root, admission_path):
    if case['kind']=='ac':
        cell.stage_ac(case,destination,model_root)
        return
    _, r5_parent = cell.load_inputs()
    admitted = admit.read_admission(admission_path,verify=True)
    common.need(Path(admitted['model_root']).resolve()==model_root.resolve(),
                'Staged private kit differs from original admission')
    corner = case['process']!='tt'
    seed = case['seed']
    source = admitted['source_decks']['noiseless' if seed is None else 'noise']
    r5 = Path(source['path']).read_bytes().decode('ascii')
    stim = dict(case_id=case['case_id'],kind='pam4_noiseless' if seed is None else 'pam4_noise',
                delta_ui=case['injected_skew_UI'],noise_seed=seed)
    if corner:
        stim.update(pvt_corner=True,process=case['process'],temperature_C=case['temperature_C'],vdd_V=case['vdd_V'])
    case['stimulus'] = stim
    if case['kind']=='payload':
        case['target_residual_stress_ps'] = case['added_differential_stress_ps']
        case['added_differential_stress_ps'] = case['actual_added_offset_ps']
    cards = cell.device_cards(r5_parent)
    renderer = cell.pilot_deck if case['kind']=='pilot' else cell.tran_deck
    parent, bench, profile = renderer(r5,admitted,case,cards)
    destination.mkdir()
    if corner:
        wrapper, proof = cell.model_preflight.stage_corner(case['process'],model_root)
        (destination/'la5_foundry_corners.scs').write_bytes(wrapper)
        common.write_new(destination/'corner_preflight.json',proof)
    (destination/'bench.scs').write_bytes(bench.encode('ascii'))
    (destination/'parent_diff.txt').write_bytes(cell.unified(parent,bench).encode('ascii'))
    case.update(stop_s=profile.get('pilot_stop_s',profile['stop_s']),
                model_preflight_sha256=common.sha(admission_path),
                staged_source_sha256={p.name:common.sha(p) for p in destination.iterdir()})
    common.write_new(destination/'case.json',case)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('stage','run'),required=True)
    p.add_argument('--kind',choices=('ac','pilot','payload'),required=True)
    p.add_argument('--index',type=int,required=True)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--model-root',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--admission',type=Path)
    p.add_argument('--approval',type=Path)
    p.add_argument('--observations',type=Path)
    p.add_argument('--code',type=int)
    a = p.parse_args()
    plan = common.read(a.plan)
    common.need(plan==study.build(),'Review plan changed')
    case = load_case(a,plan)
    case_id = leaf(case['case_id'])
    if a.mode=='stage':
        materialize(case,a.root.resolve()/case_id,a.model_root,a.admission)
        return
    import resource
    sys.path.insert(0,str(cell.ROOT/'pvt'))
    approved = common.read(a.approval)
    check_approval(approved,a.plan,case['stage'],case_id)
    check_source_manifest()
    spectre, env = common.environment()
    dest = common.checked_root(a.root)/case_id
    materialize(case,dest,a.model_root,a.admission)
    (dest/'.study_owned').write_text(os.environ['SLURM_JOB_ID']+'\n',encoding='utf-8')
    source_sha = common.sha(dest/'bench.scs')
    timeout = {'ac':1200,'pilot':6000,'payload':12600}[a.kind]
    common.run_classic(dest,source_sha,dict(format='pn_comp_run_v1',case_id=case_id,
                       plan_sha256=common.sha(a.plan),case_sha256=common.sha(dest/'case.json')),timeout,spectre,env)
    from pvt.collect_ac import require_effective_scale
    require_effective_scale((dest/'spectre.log').read_bytes())
    report = measure.collect(dest,a.admission)
    common.write_new(dest/'completion.json',{'measurement_complete':True,
                     'measurement_sha256':common.sha(dest/'measurements.json'),'completed_utc':common.utc()})
    common.write_new(dest/'resource_observation.json',{
        'child_peak_rss_KiB':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        'spectre_wall_seconds':common.read(dest/'run_status.json')['spectre_wall_seconds']})
    from comp_summary import completed
    completed(dest)
    if approved.get('retire_new_raw') is True:
        keep = [p.name for p in dest.iterdir() if p.is_file()]
        report = common.retire_case_raw(dest,keep)
        if report['status']=='deferred':
            print('Measurement complete. Raw retirement deferred: '+report['reason'])
    print(str(dest))


if __name__ == '__main__':
    main()
