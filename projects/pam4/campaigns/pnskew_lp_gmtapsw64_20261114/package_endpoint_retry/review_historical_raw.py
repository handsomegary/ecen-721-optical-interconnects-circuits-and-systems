"""Inventory completed PAM4 runs on Olympus for a separate retirement review."""
import argparse
from pathlib import Path
import re

import ac_next
import gm_summary
import olympus_common as common


ROOT = Path(__file__).resolve().parent
CAMPAIGNS = {
    'refsmoke': 'smoke_plan.json',
    'reftrim': 'trim_plan.json',
    'refmirror': 'mirror_plan.json',
    'integrate': 'integration_plan.json',
    'diag': 'diagnostic_plan.json',
    'diag_next': 'next_diagnostic_plan.json',
    'signoff': 'signoff_plan.json',
    'endpoint': 'endpoint_plan.json',
    'common64': 'gm_gmtap_common_plan.json',
}
KEEPERS = ('bench.scs','case.json','run_status.json','spectre.log',
           '.study_owned','execution_intent.json','measurements.json','completion.json')
SOURCE_NAMES = {'bench.scs','parent_diff.txt','la5_foundry_corners.scs'}


def inspect_case(root, case, plan_path):
    case_id = case['case_id']
    common.need(re.fullmatch(r'[A-Za-z0-9_-]+',case_id),'Unsafe case ID')
    directory = root/case_id
    common.need(directory.resolve(strict=True)==directory,'Redirected case directory')
    common.need(not any((directory/name).exists() for name in
            ('raw_retirement.json','raw_retirement.jsonl')),'Existing retirement evidence needs separate review')
    names = list(KEEPERS)
    for name in names:
        common.owned_file(directory,directory/name)
    stored = common.read(directory/'case.json')
    status = common.read(directory/'run_status.json')
    intent = common.read(directory/'execution_intent.json')
    sources = stored['staged_source_sha256']
    common.need({'bench.scs','parent_diff.txt'}<=set(sources)<=SOURCE_NAMES,
                'Unexpected retained staged source list')
    if case.get('process')!='tt':
        common.need('la5_foundry_corners.scs' in sources,'Missing staged corner wrapper')
    common.need((directory/'.study_owned').read_text(encoding='utf-8').strip()==str(status['slurm_job_id'])
                and all(status.get(key)==value for key,value in intent.items()),
                'Historical run identity or execution intent differs')
    names.extend(name for name in sources if name not in names)
    compact_path = directory/'measurements.json'
    if common.read(compact_path).get('recovery_mode')=='collect-only':
        names.append('recovery.json')
    keeper_sha = {name:common.sha(common.owned_file(directory,directory/name)[0]) for name in names}
    common.need(all(keeper_sha[name]==digest for name,digest in sources.items()),'Staged source SHA differs')
    measurement = gm_summary.read_case(root,case,plan_path)
    common.need(measurement.get('status') not in ('review','fail','failed') and
                measurement.get('passed') is not False and case.get('stage')!='xt2',
                'Unresolved diagnostic or XT2 readback hold')
    observed = common.raw_inventory(directory)
    common.need(common.matches_historical_inventory(status['raw_inventory'],observed),'Raw inventory differs')
    common.need(all(common.sha(common.owned_file(directory,directory/name)[0])==digest
                    for name,digest in keeper_sha.items()),'Evidence changed during review')
    return {'case_id':case_id,'status':'verified_inventory_for_review',
            'job_id':status['slurm_job_id'],'solver_hostname':status.get('solver_hostname'),
            'simulator_build':status.get('simulator_build'),'source_and_compact_sha256':keeper_sha,
            'raw_files':[{key:row[key] for key in ('path','bytes','sha256')} for row in observed],
            'raw_logical_bytes':sum(row['bytes'] for row in observed)}


def review(root, plan_path, ids=()):
    cases = {c['case_id']:c for c in common.read(plan_path)['cases']}
    common.need(set(ids)<=set(cases),'At least one requested case is outside the selected campaign')
    selected = ids or [name for name in cases if (root/name).exists() or (root/name).is_symlink()]
    candidates,blocked = [],[]
    for name in dict.fromkeys(selected):
        try:
            candidates.append(inspect_case(root,cases[name],plan_path))
        except (KeyError,TypeError,ValueError,OSError) as error:
            blocked.append({'case_id':name,'reason':str(error)})
    return {'format':'pam4_historical_raw_review_v1','case_plan':plan_path.name,
            'case_plan_sha256':common.sha(plan_path),'run_root':str(root),
            'verified_raw_logical_bytes':sum(row['raw_logical_bytes'] for row in candidates),
            'created_utc':common.utc(),
            'inventory_candidates':candidates,'blocked':blocked,
            'pending_external_checks':['user authorization covers the listed case and file evidence',
                    'Slurm job is terminal and no process across Olympus nodes has raw open',
                    'no pending diagnostic or downstream dependence on retained waveforms',
                    'approved original sources and private model available for replay',
                    'small critical waveforms and provenance have been archived'],
            'raw_deleted':False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',choices=tuple(CAMPAIGNS),required=True)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--case-id',action='append',default=[])
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    ac_next.verify_package()
    root = args.run_root.absolute()
    allowed = (Path.home()/'ecen720_28nm'/'runs').resolve(strict=True)
    common.need(root==root.resolve(strict=True) and root.is_dir() and allowed in root.parents,
                'Use a real historical campaign directory under ~/ecen720_28nm/runs')
    output = args.output.resolve()
    common.need(root not in output.parents,'Write the inventory outside the historical run')
    common.write_new(output,review(root,ROOT/CAMPAIGNS[args.campaign],args.case_id))


if __name__=='__main__':
    main()
