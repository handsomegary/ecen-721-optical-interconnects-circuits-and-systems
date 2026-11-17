"""Run, collect and select the formal C0 training and payload cases on Olympus."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import math
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
ALIGN = Path(os.environ.get('PAM4_C0_ALIGN_PACKAGE',
                           ROOT.parent/'PAM4_PNSKEW_LP_GMTAP_C0_ALIGN_20261115')).resolve()
ALIGN_MANIFEST = 'affe4a85597261625e742533d4eb784f03e2afe3d4221b1e037adefef838ad7e'
if hashlib.sha256((ALIGN/'SHA256SUMS.txt').read_bytes()).hexdigest() != ALIGN_MANIFEST:
    raise ValueError('Original C0 alignment package identity differs')
sys.path.insert(0, str(ALIGN))
import c0_rescore as align_package

align_package.check_manifest(ALIGN)
import c0_formal_deck as deck


original = align_package.original
common = original.common
MANIFEST = ROOT/'SHA256SUMS.txt'
PHASES = (0,-1,1)
CODES = (0,-60,60)
PROFILES = ('a','b')
TIMEOUT_S = 4200
WALL_S = 5400
SCHEMA = 'pam4_c0_formal_v1'
PHASE_FILE = 'selected_phase.json'
CODE_FILE = 'selected_codes.json'
MEASURE = 'measurements.json'
EVIDENCE = ('case.json','bench.scs','run_status.json','execution_intent.json','spectre.log','.study_owned')


def metric(report, point='primary'):
    return report['metrics'][point]['ideal7bit_ADC_then_FFE']


def symbol_window(stimulus):
    start, stop = (448,640) if stimulus=='training' else (128,640)
    digest = hashlib.sha256(bytes(deck.symbols(stimulus)[start:stop])).hexdigest()
    return start,stop,digest


def rank(items):
    """Rank training scores, preserving declared candidate order on exact ties."""
    common.need(all(math.isfinite(item[1]) and item[1]>=0 for item in items), 'Invalid training RMSE')
    return min(items,key=lambda item:item[1])[0]


def verify():
    align_package.check_manifest(ROOT)
    align_package.verify_package()


def read_choice(path):
    result = common.read(path)
    common.need(result['design_source_sha256']==common.sha(MANIFEST), 'Selection belongs to a different package')
    return result


def phase_choice(root):
    choice = read_choice(root/PHASE_FILE)
    common.need(choice['phase'] in PHASES and choice['calibration']['phase']==choice['phase'],
                'Invalid common phase selection')
    return choice


def code_choice(root):
    choice = read_choice(root/CODE_FILE)
    common.need(choice['phase_sha256']==common.sha(root/PHASE_FILE)
                and set(choice['codes'])==set(PROFILES)
                and all(c in CODES for c in choice['codes'].values()), 'Invalid code selection')
    return choice


def jobs(root, stage):
    if stage=='phase':
        return [('zero',0,p,'training') for p in PHASES]
    phase = phase_choice(root)['phase']
    if stage=='code':
        return [(profile,code,phase,'training') for profile in PROFILES for code in CODES]
    codes = code_choice(root)['codes']
    return [('zero',0,phase,'payload')] + [(profile,code,phase,'payload') for profile in PROFILES
        for code in dict.fromkeys((0,codes[profile]))]


def inputs(root, stage):
    if stage=='phase':
        return None, {}
    phase = phase_choice(root)
    pins = {PHASE_FILE:common.sha(root/PHASE_FILE)}
    if stage=='payload':
        code_choice(root)
        pins[CODE_FILE] = common.sha(root/CODE_FILE)
    return phase['calibration'],pins


def verify_approval(path):
    authorization = common.read(path)
    common.need(authorization['approved'] is True and authorization['platform']=='Olympus'
                and authorization['campaign']==SCHEMA
                and authorization['design_source_sha256']==common.sha(MANIFEST),
                'Formal C0 approval must cover this manifest')


def stage_case(root, job, model_root, pins):
    portable, meta = deck.render(*job)
    proof = original.model_preflight.verify_private_kit(model_root,'tt')
    token = original.review.gm_center64.BASE.MODEL_TOKEN.encode('ascii')
    model = proof['model_root'].encode('ascii')
    bench = portable.replace(token,model)
    common.need(portable.count(token)==1 and bench.replace(model,token)==portable,
                'Model-root replacement changes portable deck')
    record = dict(meta, model_preflight=proof, selection_files_sha256=pins,
                  bench_sha256=hashlib.sha256(bench).hexdigest())
    directory = root/meta['case_id']
    if directory.exists():
        common.need(directory==directory.resolve(strict=True) and common.read(directory/'case.json')==record
                    and (directory/'bench.scs').read_bytes()==bench, 'Existing staged case differs')
    else:
        directory.mkdir()
        with (directory/'bench.scs').open('xb') as stream:
            stream.write(bench)
        common.write_new(directory/'case.json',record)
    return directory,meta


def execution(directory, meta, pins):
    hashes = {n:common.sha(common.owned_file(directory,directory/n)[0]) for n in EVIDENCE}
    status = common.read(directory/'run_status.json')
    intent = common.read(directory/'execution_intent.json')
    staged = common.read(directory/'case.json')
    expected = dict(format=SCHEMA,case_id=meta['case_id'],case_sha256=hashes['case.json'],
                    design_source_sha256=common.sha(MANIFEST),selection_files_sha256=pins,
                    input_deck_sha256_before=hashes['bench.scs'],solver_mode='classic',
                    simulator_build=common.BUILD,cpus_allocated=1,requested_threads=1,
                    SPECTRE_DEFAULTS='-E')
    common.need(all(staged.get(key)==value for key,value in meta.items())
                and staged['bench_sha256']==hashes['bench.scs'] and staged['selection_files_sha256']==pins
                and all(intent.get(k)==v for k,v in expected.items())
                and all(status.get(k)==v for k,v in intent.items())
                and intent['actual_argv'][1:]==original.ARGUMENTS
                and (directory/'.study_owned').read_text(encoding='ascii').strip()==intent['slurm_job_id']
                and status['status']=='spectre_completed' and status['exit_code']==0
                and status['input_deck_sha256_after']==hashes['bench.scs']
                and status['spectre_log_sha256']==hashes['spectre.log'], 'Incomplete or mismatched Spectre evidence')
    token = original.review.gm_center64.BASE.MODEL_TOKEN.encode('ascii')
    bench = (directory/'bench.scs').read_bytes()
    model = staged['model_preflight']['model_root'].encode('ascii')
    common.need(hashlib.sha256(bench.replace(model,token)).hexdigest()==meta['deck_sha256'],
                'Staged bench differs from the selected portable deck')
    log = (directory/'spectre.log').read_bytes()
    text = log.decode('utf-8',errors='replace')
    proof = common.classic_log(text)
    original.verify_effective_scale(log)
    common.need(all(status.get(k)==v for k,v in proof.items())
                and not re.search(r'\b(?:FATAL|USIMUWI-20006|SPECTRE-8059|SPECTRE-8061|SPECTRE-8282|SPECTRE-8287)\b',text,re.I),
                'Spectre reported FATAL or a missing save')
    return status,hashes


def check_report(report, meta, status, hashes, pins):
    transients = [r['sha256'] for r in status['raw_inventory']
                  if r['path'] in ('raw/tranResponse.tran',original.review.RAW_NAME)]
    common.need(report['case_id']==meta['case_id'] and report['execution_files_sha256']==hashes
                and report['run_status_sha256']==hashes['run_status.json']
                and report['selection_files_sha256']==pins and transients==[report['tran_sha256']],
                'Collected evidence differs from the completed run')
    start,stop,digest = symbol_window(meta['stimulus'])
    window = report['capture_window']
    common.need(window['tx_symbol_indices']==[start,stop] and window['FFE_center_symbol_indices']==[start+8,stop-8]
                and window['symbol_sha256']==digest, 'Score used a different transmitted sequence or window')
    counts = (stop-start,stop-start-16)
    for point in ('primary','secondary'):
        metrics = report['metrics'][point]
        common.need((metrics['ADC_validation_input_count'],metric(report,point)['sample_count'])==counts
                    and metrics['validation_fitting_performed'] is False, 'Unexpected scored window')


def read_report(root, job, pins):
    _, meta = deck.render(*job)
    directory = root/meta['case_id']
    status, hashes = execution(directory,meta,pins)
    path, _ = common.owned_file(directory,directory/MEASURE)
    report = common.read(path)
    check_report(report,meta,status,hashes,pins)
    return report,meta,common.sha(path),status


def collect(root, job, calibration, pins):
    from c0_formal_score import measure

    _, meta = deck.render(*job)
    directory = root/meta['case_id']
    with original.lock_case(directory):
        status, hashes = execution(directory,meta,pins)
        if (directory/MEASURE).exists():
            report = common.read(directory/MEASURE)
            check_report(report,meta,status,hashes,pins)
            return report
        report = measure(directory,meta,calibration)
        _, after = execution(directory,meta,pins)
        common.need(after==hashes,'Execution evidence changed while collecting')
        report.update(execution_files_sha256=hashes,selection_files_sha256=pins)
        check_report(report,meta,status,hashes,pins)
        align_package.publish_new(directory/MEASURE,report)
        return report


def run(root, job, calibration, pins, model_root, approval):
    verify_approval(approval)
    common.need(datetime.now(timezone.utc)+timedelta(seconds=WALL_S)<=datetime(2027,1,1,6,tzinfo=timezone.utc),
                'Olympus authorization expired')
    directory, meta = stage_case(common.checked_root(root),job,model_root,pins)
    if not (directory/'run_status.json').exists():
        common.need(not any((directory/name).exists() for name in
                            ('execution_intent.json','raw','spectre.log',MEASURE)), 'Existing solver attempt needs diagnosis')
        solver, env = common.environment()
        with (directory/'.study_owned').open('x',encoding='ascii') as stream:
            stream.write(os.environ['SLURM_JOB_ID']+'\n')
        common.run_classic(directory,common.sha(directory/'bench.scs'),
            dict(format=SCHEMA,case_id=meta['case_id'],case_sha256=common.sha(directory/'case.json'),
                 design_source_sha256=common.sha(MANIFEST),selection_files_sha256=pins),TIMEOUT_S,solver,env)
    return collect(root,job,calibration,pins)


def select_phase(root):
    found = [read_report(root,job,{}) for job in jobs(root,'phase')]
    by_phase = {meta['phase']:(report,digest) for report,meta,digest,_ in found}
    scores = [(phase,metric(report)['prediction_RMSE_in_target_symbol_units'])
              for phase,(report,_) in by_phase.items()]
    best = rank(scores)
    output = dict(design_source_sha256=common.sha(MANIFEST),phase=best,
                  phase_primary_training_rmse=scores,calibration=by_phase[best][0]['calibration'],
                  training_measurement_sha256={str(p):digest for p,(_,digest) in by_phase.items()})
    align_package.publish_new(root/PHASE_FILE,output)
    return output


def select_codes(root):
    _, pins = inputs(root,'code')
    scores = {profile:[] for profile in PROFILES}
    hashes = {}
    for job in jobs(root,'code'):
        report,meta,digest,_ = read_report(root,job,pins)
        scores[meta['condition']].append((meta['code'],metric(report)['prediction_RMSE_in_target_symbol_units']))
        hashes[meta['case_id']] = digest
    # Ranking consumes the same three receiver responses for each opaque profile.
    output = dict(design_source_sha256=common.sha(MANIFEST),phase_sha256=pins[PHASE_FILE],
                  codes={profile:rank(rows) for profile,rows in scores.items()},
                  primary_training_rmse=scores,training_measurement_sha256=hashes)
    align_package.publish_new(root/CODE_FILE,output)
    return output


def summarize(root):
    _, pins = inputs(root,'payload')
    choices = code_choice(root)['codes']
    results = {}
    resources = {}
    for job in jobs(root,'payload'):
        report,meta,digest,status = read_report(root,job,pins)
        results[(meta['condition'],meta['code'])] = {
            point:{key:metric(report,point)[key] for key in ('sample_count','symbol_errors','SER',
                     'gray_bit_errors','prediction_RMSE_in_target_symbol_units')}
            | {'clipped_count':report['metrics'][point]['ADC_validation_input_clipped_count']}
            for point in ('primary','secondary')}
        resources[meta['case_id']] = dict(measurement_sha256=digest, solver_seconds=status['spectre_wall_seconds'],
              peak_RSS_KiB=status['child_peak_rss_KiB_after_solver'],raw_bytes=sum(r['bytes'] for r in status['raw_inventory']))
    pairs = {}
    for profile,code in choices.items():
        before,after = results[(profile,0)],results[(profile,code)]
        pairs[profile] = dict(selected_code=code,code0=before,selected=after,
                              shared_payload_run=code==0, delta_SER={p:after[p]['SER']-before[p]['SER'] for p in before})
    return dict(status='formal_C0_endpoint_payload_complete',phase=phase_choice(root)['phase'],
                zero=results[('zero',0)],pairs=pairs,selection_files_sha256=pins,resources=resources,
                payload_symbol_sha256=symbol_window('payload')[2],
                design_source_sha256=common.sha(MANIFEST))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','list','run','collect-only','select-phase','select-codes','summarize'))
    parser.add_argument('--root',type=Path)
    parser.add_argument('--stage',choices=('phase','code','payload'))
    parser.add_argument('--index',type=int)
    parser.add_argument('--model-root',type=Path)
    parser.add_argument('--approval',type=Path)
    args = parser.parse_args()
    verify()
    if args.mode=='verify':
        print('Formal C0 package and C0 dependencies verified')
        return
    common.need(args.root is not None,'Supply the existing campaign directory')
    root = args.root.absolute()
    common.need(root==root.resolve(strict=True) and root.is_dir(),'Campaign must be a real directory')
    if args.mode=='select-phase':
        result = select_phase(root)
        print('Selected phase:',result['phase'])
    elif args.mode=='select-codes':
        result = select_codes(root)
        print('Selected codes:',result['codes'])
    elif args.mode=='summarize':
        align_package.publish_new(root/'c0_formal_summary.json',summarize(root))
    else:
        common.need(args.stage is not None,'Supply a stage')
        batch = jobs(root,args.stage)
        if args.mode=='list':
            for index,job in enumerate(batch):
                _, meta = deck.render(*job)
                print(index,meta['case_id'],meta['deck_sha256'])
            return
        common.need(args.index is not None and 0<=args.index<len(batch),'Index out of range for this stage')
        calibration,pins = inputs(root,args.stage)
        job = batch[args.index]
        if args.mode=='run':
            common.need(args.model_root is not None and args.approval is not None,'Supply model root and approval')
            result = run(root,job,calibration,pins,args.model_root,args.approval)
        else:
            result = collect(root,job,calibration,pins)
        print(result['case_id'],metric(result)['SER'])


if __name__=='__main__':
    main()
