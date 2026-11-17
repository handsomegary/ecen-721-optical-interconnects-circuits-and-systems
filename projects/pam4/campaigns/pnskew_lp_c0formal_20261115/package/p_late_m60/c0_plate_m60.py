"""Run exactly one approved frozen formal-C0 P-late payload diagnostic."""

import argparse
from datetime import datetime, timedelta, timezone
from functools import partial
import hashlib
import math
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT/'SHA256SUMS.txt'
RESCORE = Path(os.environ.get('PAM4_C0_RESCORE_PACKAGE', ROOT.parent/
    'PAM4_PNSKEW_LP_GMTAP_C0_FORMAL_RESCORE_20261115')).resolve()
if hashlib.sha256((RESCORE/'SHA256SUMS.txt').read_bytes()).hexdigest() != (
        '12a595821ffe83a7bfe04dbc7313136e678754923120914211fa29a60dda061a'):
    raise ValueError('Original C0 rescore manifest SHA differs')
sys.path.insert(0, str(RESCORE))
import c0_payload_rescore as previous


formal = previous.formal
common = previous.common
score = previous.formal_score
review = previous.review
SCHEMA = 'pam4_c0_p_late_m60_v1'
BASELINE = ('a', 0, -1, 'payload')
CANDIDATE = ('a', -60, -1, 'payload')
BASELINE_SHA = '42c7f8e5683846aa67f29a40cd34cb078990e80a3d77e671df046bdf65bf934d'
CANDIDATE_SHA = 'e7c33e4757f0976b3b59e5fb15dfdf17061c7f89a1a1e653dcc8c7417e4c8d63'
CHANGED = {f'GMSK06VE{i}' for i in range(15)} | {f'GMSK11VE{i}' for i in range(1,18)}
AUTH_END = datetime(2027, 1, 1, 6, tzinfo=timezone.utc)


def deck_delta():
    source, ref = formal.deck.render(*BASELINE)
    proposed, meta = formal.deck.render(*CANDIDATE)
    changed = set()
    common.need(ref['deck_sha256']==BASELINE_SHA and meta['deck_sha256']==CANDIDATE_SHA
                and ref['clock_spec']==meta['clock_spec'], 'Frozen deck or clock inventory differs')
    for left, right in zip(source.splitlines(), proposed.splitlines(), strict=True):
        if left == right:
            continue
        label = left.split()[0].decode('ascii')
        after, count = re.subn(rb'\bdc=(0(?:\.0)?|0\.9)$', b'dc=*', left)
        normalized = re.sub(rb'\bdc=(0(?:\.0)?|0\.9)$', b'dc=*', right)
        common.need(count==1 and after==normalized and label in CHANGED,
                    'Deck differs beyond the approved switch control')
        changed.add(label)
    common.need(changed==CHANGED, 'Not all expected control voltages changed')
    return meta


def base_evidence(root):
    common.need(formal.jobs(root,'payload')==previous.EXPECTED_JOBS, 'Original four-case payload selection differs')
    calibration, pins = formal.inputs(root,'payload')
    common.need(formal.code_choice(root)['codes']=={'a':0,'b':60} and calibration['phase']==-1,
                'Expected original P-late selection 0 and common phase -1/8 UI')
    summary, _ = common.owned_file(root,root/previous.ORIGINAL_SUMMARY)
    original = common.read(summary)
    common.need(original['selection_files_sha256']==pins and original['phase']==-1
                and original['design_source_sha256']==previous.FORMAL_SHA
                and original['payload_symbol_sha256']==formal.symbol_window('payload')[2],
                'Original summary, payload labels or selections differ')
    _, meta, report_sha, _ = formal.read_report(root,BASELINE,pins)
    cached, _ = common.owned_file(root,root/previous.OUTPUT)
    data = common.read(cached)
    baseline = data['cases'][meta['case_id']]
    common.need(data['schema']==previous.SCHEMA and data['selection_files_sha256']==pins
                and data['original_summary_sha256']==common.sha(summary)
                and data['rescore_manifest_sha256']==common.sha(previous.MANIFEST)
                and data['original_payload_symbol_sha256']==original['payload_symbol_sha256']
                and data['original_496_payload_score_reproduced'] is True
                and baseline['original_measurement_sha256']==report_sha,
                'Existing 176-symbol baseline is not bound to original P-late measurement')
    return calibration, pins, baseline, common.sha(cached)


def authorization(pins, rescore_sha, root):
    return dict(approved=True, platform='Olympus', campaign=SCHEMA,
                case_id=deck_delta()['case_id'], deck_sha256=CANDIDATE_SHA,
                package_manifest_sha256=common.sha(MANIFEST), selection_files_sha256=pins,
                baseline_rescore_sha256=rescore_sha, authorized_new_run_root=str(root),
                basis='20261115T1700_user_approves_plate_m60.md', max_new_solves=1)


def run(root, calibration, pins, model_root, approval, expected):
    common.need(common.read(approval)==expected and expected['authorized_new_run_root']==str(root),
                'Approval must bind the exact single-case manifest and evidence')
    common.need(datetime.now(timezone.utc)+timedelta(seconds=formal.WALL_S)<=AUTH_END,
                'Olympus authorization expired')
    directory, meta = formal.stage_case(common.checked_root(root),CANDIDATE,model_root,pins)
    if not (directory/'run_status.json').exists():
        common.need(not any((directory/name).exists() for name in
             ('execution_intent.json','raw','spectre.log',formal.MEASURE)), 'Existing solver attempt needs diagnosis')
        solver, env = common.environment()
        with (directory/'.study_owned').open('x',encoding='ascii') as stream:
            stream.write(os.environ['SLURM_JOB_ID']+'\n')
        settings = dict(format=formal.SCHEMA,case_id=meta['case_id'],case_sha256=common.sha(directory/'case.json'),
             design_source_sha256=common.sha(formal.MANIFEST),selection_files_sha256=pins,
             extension_approval_sha256=common.sha(approval),extension_manifest_sha256=common.sha(MANIFEST))
        common.run_classic(directory,common.sha(directory/'bench.scs'),settings,formal.TIMEOUT_S,solver,env)
    check_approval_receipt(directory, approval)
    return formal.collect(root,CANDIDATE,calibration,pins)


def check_approval_receipt(directory, approval):
    intent = common.read(directory/'execution_intent.json')
    common.need(intent.get('extension_approval_sha256')==common.sha(approval)
                and intent.get('extension_manifest_sha256')==common.sha(MANIFEST),
                'Extension execution receipt differs')


def paired(baseline, candidate):
    out = {}
    for plane in score.aligned.PLANES:
        points = {}
        for window,count in (('full',496),('late_rescore',176)):
            before,after = baseline['planes'][plane][window],candidate['planes'][plane][window]
            common.need(before['sample_count']==after['sample_count']==count
                        and before['ffe_center_tx_indices']==after['ffe_center_tx_indices'],
                        'Pair has incompatible time windows')
            points[window] = dict(code0=before,code_minus60=after,
                    delta_symbol_errors=after['symbol_errors']-before['symbol_errors'],
                    delta_SER=after['SER']-before['SER'],
                    delta_RMSE=after['prediction_RMSE_in_target_symbol_units']-
                               before['prediction_RMSE_in_target_symbol_units'])
        out[plane] = points
    return out


def context():
    functions = score.aligned.scoring_functions()
    required = {'time',*review.save_names((review.R5/'quiet.scs').read_text('ascii'))}
    return functions,required


def publish(path, result):
    if path.exists():
        trusted, _ = common.owned_file(path.parent,path)
        common.need(common.read(trusted)==result, 'Existing report differs')
    else:
        formal.align_package.publish_new(path,result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','list','approval-template','stage','run','collect-only','summarize','offset-audit'))
    parser.add_argument('--root',type=Path,help='Original formal C0 campaign')
    parser.add_argument('--run-root',type=Path,help='New, designated one-case campaign')
    parser.add_argument('--model-root',type=Path)
    parser.add_argument('--approval',type=Path)
    args = parser.parse_args()
    formal.align_package.check_manifest(ROOT)
    formal.align_package.check_manifest(RESCORE)
    formal.verify()
    meta = deck_delta()
    if args.mode in ('verify','list'):
        print(meta['case_id'],meta['deck_sha256'])
        return
    calibration,pins,baseline,rescore_sha = base_evidence(args.root.resolve(strict=True))
    if args.mode=='approval-template':
        expected = authorization(pins,rescore_sha,args.approval.parent.resolve(strict=True))
        common.write_new(args.approval,dict(expected,approved=False))
        return
    if args.mode=='offset-audit':
        from c0_offset_audit import audit
        output = args.root.resolve(strict=True)/'c0_formal_offset_audit.json'
        publish(output,audit(args.root.resolve(strict=True),calibration,pins,*context()))
        print(output)
        return
    root = args.run_root.resolve(strict=True)
    common.need(root!=args.root.resolve(strict=True), 'Use a separate run root for the approved case')
    expected = authorization(pins,rescore_sha,root)
    common.need(common.read(args.approval)==expected, 'The exact one-case approval is missing or differs')
    if args.mode=='stage':
        directory,_ = formal.stage_case(common.checked_root(root),CANDIDATE,args.model_root,pins)
        print(directory/'bench.scs')
        return
    if args.mode=='run':
        run(root,calibration,pins,args.model_root,args.approval,expected)
    elif args.mode=='collect-only':
        check_approval_receipt(root/meta['case_id'],args.approval)
        formal.collect(root,CANDIDATE,calibration,pins)
    check_approval_receipt(root/meta['case_id'],args.approval)
    _, candidate = previous.measure_case(root,CANDIDATE,calibration,pins,*context())
    output = root/'c0_formal_plate_m60_summary.json'
    publish(output,dict(schema=SCHEMA,formal_phase=-1,selected_codes={'a':0,'b':60},
             case_id=meta['case_id'],case_deck_sha256=meta['deck_sha256'],payload_symbol_sha256=formal.symbol_window('payload')[2],
             approval_sha256=common.sha(args.approval),baseline_rescore_sha256=rescore_sha,selection_files_sha256=pins,
             baseline=baseline,candidate=candidate,pair=paired(baseline,candidate)))
    print(output)


if __name__=='__main__':
    main()
