"""Stage, run and collect the five frozen TT C1 noise smoke cases."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT/'SHA256SUMS.txt'
C0 = Path(os.environ.get('PAM4_C0_FORMAL_PACKAGE',ROOT.parent/
    'PAM4_PNSKEW_LP_GMTAP_C0_FORMAL_20261115')).resolve()
C0_SHA = '3d9ebc0211077ef611dd17910412fa22388b0615163148357f7b68681b8f267e'
if hashlib.sha256((C0/'SHA256SUMS.txt').read_bytes()).hexdigest()!=C0_SHA:
    raise ValueError('Unexpected formal C0 package manifest')
sys.path.insert(0,str(C0))
import c0_formal as formal
import c1_payload as payload


common = formal.common
original = formal.original
SCHEMA = 'pam4_c1_tt_noise_smoke_v1'
TIMEOUT_S = 16200
WALL_S = 18000
SUMMARY = 'c1_noise_smoke_summary.json'


def verify():
    formal.align_package.check_manifest(ROOT)
    formal.verify()
    return [payload.render(*row)[1] for row in payload.CASES]


def inputs(c0_root):
    calibration,pins = formal.inputs(c0_root,'payload')
    common.need(formal.code_choice(c0_root)['codes']=={'a':0,'b':60} and calibration['phase']==-1,
                'Unexpected frozen C0 phase or selection')
    return calibration,pins


def request(root,pins,cases):
    return dict(approved=True,campaign=SCHEMA,platform='Olympus',run_root=str(root),
        package_manifest_sha256=common.sha(MANIFEST),c0_selection_files_sha256=pins,
        case_sha256={case['case_id']:case['deck_sha256'] for case in cases},
        scope='Five TT C1 smoke arms, seed 1001, validate zero-skew pilot before the four pairs')


def stage(root,index,model_root,pins):
    portable,meta = payload.render(*payload.CASES[index])
    proof = original.model_preflight.verify_private_kit(model_root,'tt')
    token = original.review.gm_center64.BASE.MODEL_TOKEN.encode('ascii')
    model = proof['model_root'].encode('ascii')
    bench = portable.replace(token,model)
    common.need(portable.count(token)==1 and bench.replace(model,token)==portable,
                'Model-root substitution is not reversible')
    record = dict(meta,model_preflight=proof,selection_files_sha256=pins,
                  bench_sha256=hashlib.sha256(bench).hexdigest())
    directory = root/meta['case_id']
    if directory.exists():
        common.need(directory.resolve(strict=True)==directory and common.read(directory/'case.json')==record
                    and (directory/'bench.scs').read_bytes()==bench, 'Existing staged C1 case differs')
    else:
        directory.mkdir()
        with (directory/'bench.scs').open('xb') as stream:
            stream.write(bench)
        common.write_new(directory/'case.json',record)
    return directory


def execution(directory,meta,pins,approval_sha):
    hashes = {name:common.sha(common.owned_file(directory,directory/name)[0]) for name in formal.EVIDENCE}
    status = common.read(directory/'run_status.json')
    intent = common.read(directory/'execution_intent.json')
    staged = common.read(directory/'case.json')
    expected = dict(format=SCHEMA,case_id=meta['case_id'],case_sha256=hashes['case.json'],
                    design_source_sha256=common.sha(MANIFEST),selection_files_sha256=pins,
                    approval_sha256=approval_sha,input_deck_sha256_before=hashes['bench.scs'],
                    solver_mode='classic',simulator_build=common.BUILD,cpus_allocated=1,
                    requested_threads=1,SPECTRE_DEFAULTS='-E')
    want = original.review.gm_center64.BASE.MODEL_TOKEN.encode('ascii')
    private = staged['model_preflight']['model_root'].encode('ascii')
    bench = (directory/'bench.scs').read_bytes()
    common.need(all(staged.get(k)==v for k,v in meta.items()) and staged['selection_files_sha256']==pins
                and all(intent.get(k)==v for k,v in expected.items())
                and all(status.get(k)==v for k,v in intent.items())
                and staged['bench_sha256']==status['input_deck_sha256_after']==hashes['bench.scs']
                and hashlib.sha256(bench.replace(private,want)).hexdigest()==meta['deck_sha256']
                and intent['actual_argv'][1:]==original.ARGUMENTS
                and status['status']=='spectre_completed' and status['exit_code']==0
                and status['spectre_log_sha256']==hashes['spectre.log']
                and (directory/'.study_owned').read_text(encoding='ascii').strip()==intent['slurm_job_id'],
                'Incomplete or mismatched C1 execution evidence')
    log = (directory/'spectre.log').read_bytes()
    proof = common.classic_log(log.decode('utf-8',errors='replace'))
    original.verify_effective_scale(log)
    common.need(all(status.get(k)==v for k,v in proof.items())
                and not re.search(rb'\b(?:FATAL|USIMUWI-20006|SPECTRE-8059|SPECTRE-8061|SPECTRE-8282|SPECTRE-8287)\b',log,re.I),
                'Spectre reported FATAL or a missing saved signal')
    return status,hashes


def checked_report(report,meta,status,hashes,pins):
    transients = [r['sha256'] for r in status['raw_inventory']
                  if r['path'] in ('raw/tranResponse.tran',original.review.RAW_NAME)]
    common.need(report['case_id']==meta['case_id'] and report['execution_files_sha256']==hashes
                and report['run_status_sha256']==hashes['run_status.json']
                and report['selection_files_sha256']==pins and transients==[report['tran_sha256']],
                'Collected result differs from the completed C1 run')
    payload.validate_report(report,meta)


def read_report(root,meta,pins,approval_sha):
    directory = root/meta['case_id']
    status,hashes = execution(directory,meta,pins,approval_sha)
    path,_ = common.owned_file(directory,directory/formal.MEASURE)
    report = common.read(path)
    checked_report(report,meta,status,hashes,pins)
    return report,status,common.sha(path)


def collect(root,meta,calibration,pins,approval_sha):
    directory = root/meta['case_id']
    with original.lock_case(directory):
        status,hashes = execution(directory,meta,pins,approval_sha)
        path = directory/formal.MEASURE
        if path.exists():
            return read_report(root,meta,pins,approval_sha)[0]
        report = payload.measure(directory,meta,calibration)
        _,after = execution(directory,meta,pins,approval_sha)
        common.need(after==hashes, 'Execution evidence changed during C1 collection')
        report.update(execution_files_sha256=hashes,selection_files_sha256=pins,
                      run_status_sha256=hashes['run_status.json'])
        checked_report(report,meta,status,hashes,pins)
        formal.align_package.publish_new(path,report)
        return report


def run(root,index,cases,calibration,pins,model_root,approval_sha):
    common.need(datetime.now(timezone.utc)+timedelta(seconds=WALL_S)<=datetime(2027,1,1,6,tzinfo=timezone.utc),
                'Olympus authorization expired')
    if index:
        read_report(root,cases[0],pins,approval_sha)
    directory = stage(common.checked_root(root),index,model_root,pins)
    meta = cases[index]
    if not (directory/'run_status.json').exists():
        solver,env = common.environment()
        with (directory/'.study_owned').open('x',encoding='ascii') as stream:
            stream.write(os.environ['SLURM_JOB_ID']+'\n')
        common.run_classic(directory,common.sha(directory/'bench.scs'),
            dict(format=SCHEMA,case_id=meta['case_id'],case_sha256=common.sha(directory/'case.json'),
                 design_source_sha256=common.sha(MANIFEST),selection_files_sha256=pins,
                 approval_sha256=approval_sha),TIMEOUT_S,solver,env)
    return collect(root,meta,calibration,pins,approval_sha)


def summary(root,cases,pins,approval_sha):
    rows = []
    for meta in cases:
        report,status,measurement_sha = read_report(root,meta,pins,approval_sha)
        points = {point:dict(formal.metric(report,point),
                       clipped_count=report['metrics'][point]['ADC_validation_input_clipped_count'])
                  for point in ('primary','secondary')}
        rows.append(dict(case_id=meta['case_id'],profile=meta['condition'],code=meta['code'],
                  metrics=points,measurement_sha256=measurement_sha,tran_sha256=report['tran_sha256'],
                  job_id=status['slurm_job_id'],solver_seconds=status['spectre_wall_seconds'],
                  peak_RSS_KiB=status['child_peak_rss_KiB_after_solver'],
                  raw_bytes=sum(row['bytes'] for row in status['raw_inventory'])))
    pairs = {profile:{point:dict(
                  delta_errors=rows[b]['metrics'][point]['symbol_errors']-rows[a]['metrics'][point]['symbol_errors'],
                  delta_SER=rows[b]['metrics'][point]['SER']-rows[a]['metrics'][point]['SER'])
                  for point in ('primary','secondary')}
             for profile,a,b in (('P_late_diagnostic',1,2),('N_late_frozen_selection',3,4))}
    result = dict(schema=SCHEMA,status='c1_complete',conditions=rows,pairs=pairs,
                  c0_training_selection={'P_late':0,'N_late':60},noise_seed=payload.NOISE_SEED,
                  selection_files_sha256=pins,approval_sha256=approval_sha,
                  design_source_sha256=common.sha(MANIFEST))
    target = root/SUMMARY
    if target.exists():
        common.need(common.read(target)==result,'Existing C1 summary differs')
    else:
        formal.align_package.publish_new(target,result)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','list','approval-template','stage','run','collect-only','summarize'))
    parser.add_argument('--c0-root',type=Path)
    parser.add_argument('--root',type=Path)
    parser.add_argument('--approval',type=Path)
    parser.add_argument('--model-root',type=Path)
    parser.add_argument('--index',type=int)
    args = parser.parse_args()
    cases = verify()
    if args.mode in ('verify','list'):
        for index,meta in enumerate(cases):
            print(index,meta['case_id'],meta['deck_sha256'])
        return
    common.need(args.c0_root is not None and args.root is not None and args.approval is not None,
                'Supply original C0 run root, new C1 run root, and approval file')
    c0_root = args.c0_root.resolve(strict=True)
    root = common.checked_root(args.root)
    common.need(root!=c0_root and c0_root not in root.parents, 'Use a distinct C1 run root')
    calibration,pins = inputs(c0_root)
    wanted = request(root,pins,cases)
    if args.mode=='approval-template':
        common.write_new(args.approval,dict(wanted,approved=False))
        return
    common.need(common.read(args.approval)==wanted, 'Approval must bind main C0 selection, C1 run root and all five decks')
    approval_sha = common.sha(args.approval)
    if args.mode=='summarize':
        print(summary(root,cases,pins,approval_sha))
        return
    index = args.index
    common.need(index is not None and 0<=index<len(cases), 'Select one approved C1 index')
    if args.mode=='collect-only':
        collect(root,cases[index],calibration,pins,approval_sha)
    else:
        common.need(args.model_root is not None, 'Supply the existing private kit root')
        if args.mode=='stage':
            print(stage(root,index,args.model_root,pins))
            return
        run(root,index,cases,calibration,pins,args.model_root,approval_sha)
    print(root/cases[index]['case_id']/formal.MEASURE)


if __name__=='__main__':
    main()
