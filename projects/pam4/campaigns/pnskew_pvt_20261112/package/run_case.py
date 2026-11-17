"""Run one selected PAM4 study case from an existing 1-CPU Slurm allocation."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import olympus_common as common

PACKAGE = Path(__file__).resolve().parent
sys.path.insert(0,str(PACKAGE/'native'))


def case_name(name):
    common.need(isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,120}',name), 'Invalid case ID')
    return name


def run_script(script, args):
    subprocess.run([sys.executable,'-B',str(script)]+[str(arg) for arg in args],check=True)


def retain_and_finish(directory, extras, retire, verify):
    from resource import RUSAGE_CHILDREN, getrusage
    report = common.read(directory/'measurements.json')
    common.need(report.get('measurement_complete') is True, 'Incomplete collector output. Preserve raw.')
    common.write_new(directory/'completion.json',{'measurement_complete':True,
                     'measurement_sha256':common.sha(directory/'measurements.json'),
                     'completed_utc':common.utc(),'new_Olympus_case_only':True})
    keepers = verify(report)
    profile = {'child_peak_rss_KiB':getrusage(RUSAGE_CHILDREN).ru_maxrss,
               'spectre_wall_seconds':common.read(directory/'run_status.json')['spectre_wall_seconds'],
               'raw_bytes':sum(row['bytes'] for row in common.read(directory/'run_status.json')['raw_inventory']),
               'retained_measurements_sha256':common.sha(directory/'measurements.json'),
               'collector_readback_pass':True}
    common.write_new(directory/'resource_observation.json',profile)
    if retire:
        retirement = common.retire_case_raw(
            directory, list(extras) + list(keepers) + ['resource_observation.json', 'execution_intent.json'])
        if retirement['status'] == 'deferred':
            print('Measurement complete. Raw retirement deferred: ' + retirement['reason'], file=sys.stderr)


def run_skew(args, root, spectre, env):
    import collect_r5
    import collect_tone
    import pn_stage
    import readback_guard
    from skew.prepare_skew import write_diff

    plan_path = PACKAGE/('pvt/transient_plan.json' if args.study=='pvt-transient' else 'skew/skew_plan.json')
    plan = common.read(plan_path)
    common.need(0 <= args.case_index < len(plan['cases']),'Unknown skew case index')
    case = plan['cases'][args.case_index]
    directory = root/case_name(case['case_id'])
    profile = pn_stage.prepare(args.admission,plan_path,args.case_index,directory)
    common.write_new(directory/'case.json',case)
    write_diff(args.admission,directory)
    (directory/'.study_owned').write_text(os.environ['SLURM_JOB_ID']+'\n',encoding='utf-8')
    metadata = {'format':'pn_skew_native_run_v1','case_id':case['case_id'],
                'admission_sha256':profile['admission_sha256'],'plan_sha256':profile['plan_sha256']}
    common.run_classic(directory,profile['staged_deck_sha256'],metadata,9000,spectre,env)
    pn_stage.verify_stage(args.admission,directory)
    output = directory/'measurements.json'
    if case['kind'].startswith('tone_'):
        collect_tone.collect(args.admission,directory,output)
    else:
        collect_r5.collect(args.admission,directory,directory/'case.json',output)

    def verify(report):
        readback_guard.verify_run(directory,expected_case=case,expected_plan_sha256=profile['plan_sha256'],
                                  admission_path=args.admission,require_raw=True)
        return [Path(report[key]['path']).resolve().relative_to(directory).as_posix()
                for key in ('held_sample_csv','short_waveform_csv') if report.get(key)]

    keep = ['profile.json','stimulus_overlay.diff','stimulus_overlay.json','.pn_skew_owned']
    if case.get('pvt_corner') is True:
        keep.extend(['la5_foundry_corners.scs','corner_preflight.json'])
    retain_and_finish(directory,keep,args.retire_new_raw,verify)
    return directory


def verify_compact(directory, report):
    status_path = directory/'run_status.json'
    status = common.read(status_path)
    common.need(report.get('measurement_complete') is True and
                report['input_deck_sha256'] == status['input_deck_sha256_after'] == common.sha(directory/'bench.scs'),
                'PVT measure/bench binding differs')
    if status.get('format')=='pam4_pvt_run_v1':
        expected = {row['path'][4:]: row['sha256'] for row in status['raw_inventory']
                    if row['path'].startswith('raw/')}
        observed = report['raw_analysis_sha256']
        common.need(report['case_id']==status['case_id'] and report['run_status_sha256']==common.sha(status_path)
                    and set(observed)=={'acResponse.ac','dcOp.dc','dcOpInfo.info','noiseResponse.noise'}
                    and all(expected.get(name)==digest for name,digest in observed.items()),
                    'PVT output raw/receipt identity differs')
    files = report.get('compact_outputs',{})
    common.need(isinstance(files,dict), 'Invalid compact output inventory')
    for name,digest in files.items():
        rel = Path(name)
        common.need(not rel.is_absolute() and rel.parts and '..' not in rel.parts and rel.parts[0]!='raw', 'Unsafe compact output')
        path,_ = common.owned_file(directory,directory/rel)
        common.need(common.sha(path)==digest,'Compact output SHA differs: '+name)
    return list(files)


def run_pvt(args, root, spectre, env):
    source = args.case_dir.resolve(strict=True)
    case = common.read(source/'case.json')
    directory = root/case_name(case['case_id'])
    common.need(not directory.exists(), 'Existing case directory. Preserve original run.')
    run_script(PACKAGE/'pvt/model_preflight.py',['--case-dir',source,'--pdk-root',args.pdk_root,'--runtime-dir',directory])
    (directory/'.study_owned').write_text(os.environ['SLURM_JOB_ID']+'\n',encoding='utf-8')
    metadata = {'format':'pam4_pvt_run_v1','case_id':case['case_id'],'portable_case_sha256':common.sha(source/'case.json')}
    common.run_classic(directory,common.sha(directory/'bench.scs'),metadata,1200,spectre,env)
    run_script(PACKAGE/'pvt/collect_ac.py',['--case-dir',directory,'--raw-dir',directory/'raw',
               '--output',directory/'measurements.json'])
    extra = sorted(p.relative_to(directory).as_posix() for p in directory.iterdir()
                   if p.is_file() and p.name not in ('runner_stdout.log',))
    retain_and_finish(directory,extra,args.retire_new_raw,lambda report: verify_compact(directory,report))
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='study')
    skew = commands.add_parser('skew')
    skew.add_argument('--admission',type=Path,required=True)
    skew.add_argument('--case-index',type=int,required=True)
    pvt_tran = commands.add_parser('pvt-transient')
    pvt_tran.add_argument('--admission',type=Path,required=True)
    pvt_tran.add_argument('--case-index',type=int,required=True)
    pvt = commands.add_parser('pvt')
    pvt.add_argument('--case-dir',type=Path,required=True)
    pvt.add_argument('--pdk-root',type=Path,required=True)
    for p in (skew,pvt,pvt_tran):
        p.add_argument('--run-root',type=Path,required=True)
        p.add_argument('--retire-new-raw',action='store_true',help='Remove this job’s new raw only after full compact readback')
    args = parser.parse_args()
    if args.study is None:
        parser.error('Choose skew, pvt-transient, or pvt')
    spectre, env = common.environment()
    root = common.checked_root(args.run_root)
    started = time.monotonic()
    handler = run_pvt if args.study=='pvt' else run_skew
    print('Completed case',handler(args,root,spectre,env),'total wrapper seconds',time.monotonic()-started)


if __name__=='__main__':
    main()
