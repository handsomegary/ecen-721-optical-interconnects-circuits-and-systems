"""Replay measurements from the actual retained Olympus SWITCH64 files in read-only mode."""

import argparse
import json
from pathlib import Path

from c0_review import SWITCH, SWITCH_MANIFEST_SHA, common
import gm_switch64 as design
import recover_switch64_endpoint as recovery


def replay(original_root, retry_root):
    common.need(common.sha(SWITCH/'SHA256SUMS.txt')==SWITCH_MANIFEST_SHA, 'Wrong SWITCH64 recovery package')
    recovery.verify_package()
    cases = recovery.verify_plan()
    original_root = recovery.run_root(original_root)
    retry_root = design.retry_campaign(original_root,recovery.run_root(retry_root))
    results = {}
    for index, original_task, retry_task, prefix in ((84,'757710','757730','fea911b3'),
                                                   (86,'757597','757729','10c96868')):
        case = cases[index]
        name = case['case_id']
        original = original_root/name
        retried = retry_root/name
        pin, stored, status, row = recovery.historical_evidence(original,retried,case,recovery.RETRY_TRAN_BYTES[index])
        prior = common.read(original/'run_status.json')
        common.need(prior['slurm_job_id']==original_task and pin['slurm_job_id']==retry_task
                    and row['sha256'].startswith(prefix), f'Recorded Olympus task or PSF SHA differs for {index}')
        inventory = recovery.live_raw(retried,pin)
        proof = design.metrics.native_transient(retried,dict(status,raw_inventory=inventory),
                                                max_bytes=design.metrics.ENDPOINT_RETRY_FILE_BYTES)
        measured = json.loads(json.dumps(design.metrics.measurement(proof,stored),allow_nan=False))
        committed, evidence = design.read_endpoint_retry(original_root,retry_root,case)
        common.need(all(committed.get(key)==value for key,value in measured.items()),
                    f'Recomputed measurements differ for {index}')
        results[name] = {'case_index':index,'original_task':original_task,'retry_task':retry_task,
                         'raw_bytes':row['bytes'],'raw_sha256':proof.sha256,'replayed_measurements_match':True,
                         'evidence':evidence}
        del proof, measured, committed
    summary = design.summarize(original_root,retry_root)
    common.need(summary['ready_to_design_C0'] is True and summary['total_measured_case_count']==87
                and len(summary['transitions'])==21, 'Live merged SWITCH64 evidence is incomplete')
    for transition in summary['transitions']:
        if transition['case_id'] in results:
            results[transition['case_id']]['recovery_s'] = transition['comparison']['recovery_s_after_event']
    return {'cases':results,'total_measured_case_count':87,'dynamic_measured_case_count':39,
            'transitions_recovered':21,'ready_to_design_C0':True}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-root',type=Path,required=True)
    parser.add_argument('--retry-root',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(replay(args.original_root,args.retry_root),indent=2,allow_nan=False))
