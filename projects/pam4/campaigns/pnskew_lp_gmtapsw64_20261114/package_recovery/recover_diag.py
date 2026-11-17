"""Snapshot and re-collect the two original Olympus diagnostic cases."""
import argparse
import hashlib
import os
from pathlib import Path
import socket

import lp_diagnostics as diag
import olympus_common as common
from recover_bias import payload

ROOT = diag.ROOT
PLAN_SHA = 'b74093eb9fc686d83afc27218aed8d39e966e695dd5613ebe4971a558bab34d9'
OLD_MANIFEST = '6acebdb55b371119172337903fc38f77ecf0dcb0ef81e1ba9cbea1145a49f3a8'
COHORT = (0,11)
BASE_FILES = ('case.json','run_status.json','execution_intent.json','bench.scs',
              'parent_diff.txt','la5_foundry_corners.scs','spectre.log','.study_owned')
OLD_OUTPUTS = ('measurements.json','completion.json')
NAMES = ('diagnostic_recovered.json','diagnostic_recovery_receipt.json','diagnostic_recovered_completion.json')


def original_snapshot(case_dir,case,*,verify_raw=True):
    common.need(case_dir.is_dir() and case_dir.resolve()==case_dir and case_dir.name==case['case_id'],
                'Use the original case directory')
    names = (*BASE_FILES,*OLD_OUTPUTS) if case['stage']=='stb' else BASE_FILES
    hashes = {name:common.sha(common.owned_file(case_dir,case_dir/name)[0]) for name in names}
    stored = common.read(case_dir/'case.json')
    status = common.read(case_dir/'run_status.json')
    intent = common.read(case_dir/'execution_intent.json')
    common.need(all(stored[k]==v for k,v in case.items()) and
                status['case_id']==case['case_id'] and status['plan_sha256']==PLAN_SHA and
                status['status']=='spectre_completed' and status['exit_code']==0 and
                status['solver_completion_errors']==0 and status['solver_mode']=='classic' and
                status['simulator_build']==common.BUILD and
                status['case_sha256']==hashes['case.json'] and
                status['spectre_log_sha256']==hashes['spectre.log'] and
                status['input_deck_sha256_before']==status['input_deck_sha256_after']==hashes['bench.scs'] and
                all(status[k]==v for k,v in intent.items()) and
                (case_dir/'.study_owned').read_text().strip()==status['slurm_job_id'],
                'Historical execution evidence differs')
    expected_sources = {'bench.scs','parent_diff.txt','la5_foundry_corners.scs'}
    common.need(set(stored['staged_source_sha256'])==expected_sources and
                all(hashes[name]==digest for name,digest in stored['staged_source_sha256'].items()),
                'Original staged source mismatch')
    deck,_,_,_,_,diff = diag.render(case,stored['model_preflight']['model_root'])
    common.need(hashlib.sha256(deck.encode('ascii')).hexdigest()==hashes['bench.scs'] and
                hashlib.sha256(diff.encode('ascii')).hexdigest()==hashes['parent_diff.txt'],
                'Frozen generator does not reproduce original deck')
    if case['stage']=='stb':
        old = common.read(case_dir/'measurements.json')
        done = common.read(case_dir/'completion.json')
        common.need(old['status']=='review' and old['reason']=='STB frequency unit does not establish Hz'
                    and old['case_id']==case['case_id'] and old['bench_sha256']==hashes['bench.scs']
                    and old['run_status_sha256']==hashes['run_status.json']
                    and done['measurement_sha256']==hashes['measurements.json'],
                    'Historical STB review result differs')
    else:
        common.need(not any(os.path.lexists(case_dir/n) for n in OLD_OUTPUTS),
                    'Unexpected historical startup output')
    recorded = status['raw_inventory']
    live = common.raw_inventory(case_dir) if verify_raw else None
    if verify_raw:
        common.need(common.matches_historical_inventory(recorded,live),'Original raw inventory differs')
    evidence = dict(case_id=case['case_id'], files=hashes,slurm_job_id=status['slurm_job_id'],
                    solver_hostname=status.get('solver_hostname'),raw_files=len(recorded))
    return evidence,live,stored,status


def publish(case_dir,report,receipt):
    import tempfile
    data = payload(report)
    receipt = dict(receipt,measurement_sha256=hashlib.sha256(data).hexdigest())
    receipt_data = payload(receipt)
    done = payload({'measurement_complete':True,'measurement_sha256':receipt['measurement_sha256'],
                    'receipt_sha256':hashlib.sha256(receipt_data).hexdigest()})
    items = list(zip(NAMES,(data,receipt_data,done)))
    for name,value in items:
        dest = case_dir/name
        if os.path.lexists(dest):
            common.need(common.owned_file(case_dir,dest)[0].read_bytes()==value,'Recovery sidecar differs: '+name)
    for name,value in items:
        dest = case_dir/name
        if dest.exists():
            continue
        with tempfile.NamedTemporaryFile(dir=case_dir,prefix='.diag-recover-',delete=False) as f:
            temp = Path(f.name)
            try:
                f.write(value)
                f.flush()
                os.fsync(f.fileno())
                f.close()
                os.link(temp,dest)
            finally:
                temp.unlink()
    return receipt


def recover(case_dir,case,approved):
    import fcntl

    fd = os.open(case_dir,os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX | fcntl.LOCK_NB)
        pinned,live,stored,status = original_snapshot(case_dir,case)
        common.need(pinned==approved,'Source snapshot differs from new approval')
        report = diag.measure(case_dir,stored,dict(status,raw_inventory=live))
        latest,after,*_ = original_snapshot(case_dir,case)
        common.need(latest==pinned and after==live,'Source changed during collection')
        receipt = dict(pinned,original_plan_sha256=PLAN_SHA,original_manifest_sha256=OLD_MANIFEST,
                       collector_manifest_sha256=common.sha(ROOT/'SHA256SUMS.txt'),
                       collector_hostname=socket.gethostname())
        if (case_dir/NAMES[1]).exists():
            old = common.read(common.owned_file(case_dir,case_dir/NAMES[1])[0])
            receipt['collector_hostname'] = old['collector_hostname']
        publish(case_dir,report,receipt)
        return report
    finally:
        os.close(fd)


def read_recovered(case_dir,case):
    pinned,*_ = original_snapshot(case_dir,case,verify_raw=False)
    files = [common.owned_file(case_dir,case_dir/name)[0] for name in NAMES]
    report,receipt,done = [common.read(f) for f in files]
    common.need(all(receipt[k]==v for k,v in pinned.items()) and
                receipt['collector_manifest_sha256']==common.sha(ROOT/'SHA256SUMS.txt') and
                receipt['original_plan_sha256']==PLAN_SHA and receipt['original_manifest_sha256']==OLD_MANIFEST and
                done['measurement_complete'] is report['measurement_complete'] is True and
                common.sha(files[0])==done['measurement_sha256']==receipt['measurement_sha256'] and
                common.sha(files[1])==done['receipt_sha256'] and
                report['case_id']==case['case_id'] and report['bench_sha256']==pinned['files']['bench.scs'] and
                report['run_status_sha256']==pinned['files']['run_status.json'],
                'Recovered diagnostic provenance differs')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('snapshot','collect-only'),required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--approval',type=Path)
    a = p.parse_args()
    diag.integrated.mirror.prior.gm.original.verify_package()
    common.need(common.sha(diag.PLAN)==PLAN_SHA and
                common.sha(ROOT/'ORIGINAL_DIAG_SHA256SUMS.txt')==OLD_MANIFEST,'Historical sources differ')
    root = a.root.absolute()
    allowed = (Path.home()/'ecen720_28nm'/'runs').resolve(strict=True)
    common.need(root==root.resolve(strict=True) and allowed in root.parents,'Use original Olympus campaign')
    cases = [common.read(diag.PLAN)['cases'][i] for i in COHORT]
    if a.mode=='snapshot':
        common.write_new(a.snapshot,{'original_plan_sha256':PLAN_SHA,'original_manifest_sha256':OLD_MANIFEST,
                                     'cases':[original_snapshot(root/c['case_id'],c)[0] for c in cases]})
        return
    common.need(a.approval is not None,'Supply the new collect-only approval')
    approval = common.read(a.approval)
    pins = common.read(a.snapshot)
    ids = [c['case_id'] for c in cases]
    common.need(approval.get('approved') is True and approval.get('platform')=='Olympus' and
                approval.get('mode')=='collect-only' and approval.get('case_ids')==ids and
                approval.get('original_plan_sha256')==pins['original_plan_sha256']==PLAN_SHA and
                approval.get('original_manifest_sha256')==pins['original_manifest_sha256']==OLD_MANIFEST and
                approval.get('snapshot_sha256')==common.sha(a.snapshot) and
                approval.get('recovery_manifest_sha256')==common.sha(ROOT/'SHA256SUMS.txt') and
                [pin['case_id'] for pin in pins['cases']]==ids,
                'New approval must bind the snapshot and collector')
    for case,pin in zip(cases,pins['cases']):
        report = recover(root/case['case_id'],case,pin)
        print(case['case_id'],report['status'])


if __name__=='__main__':
    main()
