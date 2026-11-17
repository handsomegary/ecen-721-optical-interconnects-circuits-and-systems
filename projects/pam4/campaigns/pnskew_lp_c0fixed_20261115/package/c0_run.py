"""Run and collect the five reviewed C0 fixed-code diagnostics on Olympus."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import socket

import c0_review as review
from pvt import model_preflight
from recover_bias import publish
from recover_switch64 import lock_case, verify_effective_scale


ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'c0_review_plan.json'
MANIFEST = ROOT/'SHA256SUMS.txt'
STAGE = 'c0_fixed'
SOLVER_TIMEOUT_S = 3300
common = review.common
ARGUMENTS = ['-64','+mt=1','bench.scs','-format','psfascii','-raw','raw',
             '+log','spectre.log','+lqtimeout','30']


def verify_package():
    for line in MANIFEST.read_text(encoding='ascii').splitlines():
        digest, name = line.split('  ',1)
        path = ROOT/name
        common.need(path.resolve().is_relative_to(ROOT) and common.sha(path)==digest,
                    'C0 package SHA differs: '+name)
    common.need(common.sha(review.SWITCH/'SHA256SUMS.txt')==review.SWITCH_MANIFEST_SHA,
                'Wrong reviewed SWITCH64 dependency')
    review.gm_center64.trim.fine.endpoint.integrated.mirror.prior.gm.original.verify_package()
    review.pinned_r5()
    plan = common.read(PLAN)
    common.need(plan['unchanged_frozen_sha256']==review.FROZEN_SHA and len(plan['cases'])==5,
                'C0 review plan differs')
    candidates = {c['code']:c for c in review.gm_gmtap_common.build_plan()['cases']
                  if c['process']=='tt' and c['group']=='divider' and c['drive']=='p'
                  and c['code'] in (-60,0,60)}
    r5 = (review.R5/'quiet.scs').read_bytes().decode('ascii')
    for case, (name, skew, code) in zip(plan['cases'],review.CASES,strict=True):
        deck, expected = review.render(name,skew,code,candidates,r5)
        common.need(case==expected and (ROOT/'decks'/f'{name}.scs').read_bytes()==deck.encode('ascii'),
                    'Reviewed C0 deck or case differs: '+name)
    return plan['cases']


def verify_approval(case, approval):
    ids = approval.get('case_ids', [])
    allowed = {name for name, *_ in review.CASES}
    common.need(approval.get('approved') is True and approval.get('platform')=='Olympus'
                and approval.get('plan_sha256')==common.sha(PLAN)
                and approval.get('design_source_sha256')==common.sha(MANIFEST)
                and isinstance(ids,list) and len(ids)==len(set(ids)) and set(ids)<=allowed
                and case['case_id'] in ids and approval.get('stages')==[STAGE]
                and approval.get('retire_new_raw') is not True,
                'C0 approval must bind the reviewed package, plan and selected fixed-code cases')


def staged_record(case, proof):
    portable = (ROOT/'decks'/f"{case['case_id']}.scs").read_bytes()
    token = review.gm_center64.BASE.MODEL_TOKEN.encode('ascii')
    model = proof['model_root'].encode('utf-8')
    common.need(common.sha(ROOT/'decks'/f"{case['case_id']}.scs")==case['deck_sha256']
                and portable.count(token)==1, 'Portable model-root token or deck SHA differs')
    deck = portable.replace(token,model)
    common.need(deck.replace(model,token)==portable, 'Model-root substitution is not reversible')
    record = dict(case,stage=STAGE,model_preflight=proof,plan_sha256=common.sha(PLAN),
                  staged_source_sha256={'bench.scs':hashlib.sha256(deck).hexdigest()})
    return deck, record


def stage(case, root, model_root):
    root = common.checked_root(root)
    proof = model_preflight.verify_private_kit(model_root,'tt')
    deck, record = staged_record(case,proof)
    directory = root/case['case_id']
    if directory.exists():
        common.need(directory.resolve(strict=True)==directory and directory.is_dir()
                    and (directory/'bench.scs').read_bytes()==deck
                    and common.read(directory/'case.json')==record,
                    'Existing C0 stage differs from the selected source or model root')
        return directory
    directory.mkdir()
    (directory/'bench.scs').write_bytes(deck)
    common.write_new(directory/'case.json',record)
    return directory


def execution_evidence(case, directory):
    names = ('bench.scs','case.json','execution_intent.json','run_status.json',
             'spectre.log','runner_stdout.log','.study_owned')
    hashes = {name:common.sha(common.owned_file(directory,directory/name)[0]) for name in names}
    record = common.read(directory/'case.json')
    deck, expected_record = staged_record(case,record['model_preflight'])
    common.need(record==expected_record and hashes['bench.scs']==hashlib.sha256(deck).hexdigest(),
                'Staged C0 provenance differs')
    intent = common.read(directory/'execution_intent.json')
    status = common.read(directory/'run_status.json')
    expected = dict(format='pam4_c0_run_v1',case_id=case['case_id'],case_sha256=hashes['case.json'],
                    plan_sha256=common.sha(PLAN),design_source_sha256=common.sha(MANIFEST),
                    input_deck_sha256_before=hashes['bench.scs'],solver_mode='classic',
                    simulator_build=common.BUILD,cpus_allocated=1,requested_threads=1,
                    SPECTRE_DEFAULTS='-E',max_solver_file_bytes=common.DEFAULT_SOLVER_FILE_BYTES)
    argv, job = intent['actual_argv'],intent['slurm_job_id']
    common.need(all(intent.get(k)==v for k,v in expected.items())
                and all(status.get(k)==v for k,v in intent.items())
                and argv[1:]==ARGUMENTS and PurePosixPath(argv[0]).name=='spectre'
                and isinstance(job,str) and job.isdecimal() and bool(intent['solver_hostname'])
                and bool(intent['started_utc'])
                and (directory/'.study_owned').read_text(encoding='utf-8').strip()==job
                and status['status']=='spectre_completed' and status['exit_code']==0
                and status['input_deck_sha256_after']==hashes['bench.scs']
                and status['spectre_log_sha256']==hashes['spectre.log'],
                'Completed C0 Spectre execution evidence differs')
    log = (directory/'spectre.log').read_bytes()
    text = log.decode('utf-8',errors='replace')
    proof = common.classic_log(text)
    verify_effective_scale(log)
    common.need(all(status.get(k)==v for k,v in proof.items())
                and not re.search(r'\bFATAL\b|\bSPECTRE-(8059|8061|8282|8287)\b',text,re.IGNORECASE),
                'C0 log reports fatal simulation or missing saved traces')
    return status, hashes


def read_case(case, directory):
    status, hashes = execution_evidence(case,directory)
    report = common.read(directory/'measurements.json')
    receipt = common.read(directory/'recovery.json')
    completion = common.read(directory/'completion.json')
    transient = [row for row in status['raw_inventory']
                 if row['path'] in ('raw/tranResponse.tran',review.RAW_NAME)]
    common.need(len(transient)==1 and report['case']==case
                and report['measurement_complete'] is True and completion['measurement_complete'] is True
                and report['run_status_sha256']==hashes['run_status.json']
                and report['bench_sha256']==hashes['bench.scs']
                and report['tran_sha256']==transient[0]['sha256']
                and report['frozen_sha256']==review.FROZEN_SHA
                and receipt['case_id']==case['case_id'] and receipt['source_files_sha256']==hashes
                and receipt['original_plan_sha256']==common.sha(PLAN)
                and receipt['collector_manifest_sha256']==common.sha(MANIFEST)
                and receipt['measurement_sha256']==completion['measurement_sha256']==common.sha(directory/'measurements.json')
                and completion['recovery_sha256']==common.sha(directory/'recovery.json')
                and completion['mode']=='collect-only', 'C0 collection receipt or measurement differs')
    return report


def collect(case, directory, approval):
    verify_approval(case,approval)
    directory = directory.absolute()
    common.need(directory.resolve(strict=True)==directory and directory.is_dir(),
                'C0 collection directory must not use a symlink')
    with lock_case(directory):
        status, hashes = execution_evidence(case,directory)
        if (directory/'completion.json').exists():
            read_case(case,directory)
            return 'already_collected'
        inventory = common.raw_inventory(directory)
        common.need(common.matches_historical_inventory(status['raw_inventory'],inventory),
                    'Native C0 raw evidence changed')
        report = review.measure_existing(directory)
        _, after = execution_evidence(case,directory)
        common.need(after==hashes and common.raw_inventory(directory)==inventory,
                    'C0 source or waveform changed during collection')
        report.update(measurement_complete=True,bench_sha256=hashes['bench.scs'])
        receipt = dict(format='pam4_c0_collection_v1',case_id=case['case_id'],
                       original_plan_sha256=common.sha(PLAN),collector_manifest_sha256=common.sha(MANIFEST),
                       source_files_sha256=hashes,collector_hostname=socket.gethostname())
        result = publish(directory,report,receipt)
        read_case(case,directory)
        return result


def run(case, root, model_root, approval):
    verify_approval(case,approval)
    common.need(datetime.now(timezone.utc)+timedelta(hours=1)<=datetime(2027,1,1,6,tzinfo=timezone.utc),
                'Olympus authorization expired')
    directory = stage(case,root,model_root)
    if (directory/'run_status.json').exists():
        return collect(case,directory,approval)
    spectre, env = common.environment()
    common.need(not any((directory/name).exists() for name in
                        ('.study_owned','execution_intent.json','spectre.log','raw','measurements.json')),
                'Existing C0 attempt must be preserved and diagnosed')
    with (directory/'.study_owned').open('x',encoding='ascii') as marker:
        marker.write(os.environ['SLURM_JOB_ID']+'\n')
    common.run_classic(directory,common.sha(directory/'bench.scs'),
        dict(format='pam4_c0_run_v1',case_id=case['case_id'],case_sha256=common.sha(directory/'case.json'),
             plan_sha256=common.sha(PLAN),design_source_sha256=common.sha(MANIFEST)),
        SOLVER_TIMEOUT_S,spectre,env)
    return collect(case,directory,approval)


def summarize(root):
    cases = common.read(PLAN)['cases']
    resources = {}
    for case in cases:
        directory = root/case['case_id']
        read_case(case,directory)
        status = common.read(directory/'run_status.json')
        resources[case['case_id']] = {
            'slurm_task_id':status['slurm_job_id'], 'solver_wall_seconds':status['spectre_wall_seconds'],
            'solver_peak_RSS_KiB':status['child_peak_rss_KiB_after_solver'],
            'raw_bytes':sum(row['bytes'] for row in status['raw_inventory']),
        }
    result = review.summarize([root/case['case_id']/'measurements.json' for case in cases])
    result.update(completed_cases=len(cases),plan_sha256=common.sha(PLAN),
                  design_source_sha256=common.sha(MANIFEST),resources=resources)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('verify','stage','run','collect-only','summarize'),required=True)
    parser.add_argument('--index',type=int,choices=range(5),action='append')
    parser.add_argument('--root',type=Path)
    parser.add_argument('--model-root',type=Path)
    parser.add_argument('--approval',type=Path)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    cases = verify_package()
    if args.mode=='verify':
        print('Five C0 decks, package, and pinned r5/SWITCH64 dependencies verified')
        return
    common.need(args.root is not None,'Supply C0 campaign root')
    root = common.checked_root(args.root)
    if args.mode=='summarize':
        common.need(args.output is not None,'Supply a new C0 summary path')
        common.write_new(args.output,summarize(root))
        return
    common.need(args.index and len(set(args.index))==len(args.index),'Supply distinct C0 case indices')
    if args.mode=='stage':
        common.need(args.model_root is not None,'Supply the existing private model root')
        for index in args.index:
            print(stage(cases[index],root,args.model_root))
        return
    common.need(args.approval is not None,'Supply C0 approval JSON')
    approval = common.read(args.approval)
    if args.mode=='run':
        common.need(len(args.index)==1 and args.model_root is not None,'Run exactly one case per Slurm task')
        print(run(cases[args.index[0]],root,args.model_root,approval))
    else:
        for index in args.index:
            print(cases[index]['case_id'],collect(cases[index],root/cases[index]['case_id'],approval))


if __name__=='__main__':
    main()
