"""Reconstruct the 48 historical input fingerprints from the local compact archive."""
import argparse
import json
from pathlib import Path
import tarfile

from audit_gmfine_op import apply_diff, sha
import lp_bias
import olympus_common as common
from recover_bias import COHORT, ORIGINAL_PLAN_SHA, ROOT

ARCHIVE_SHA = '36251b58bba9bc3380f7fcedbd17c6b392a983144b71dbe222b8a51da8e509e0'


def pin(archive):
    common.need(common.sha(archive)==ARCHIVE_SHA,'Historical compact SHA differs')
    common.need(common.sha(lp_bias.PLAN)==ORIGINAL_PLAN_SHA,'Historical plan SHA differs')
    plan = common.read(lp_bias.PLAN)['cases']
    base = lp_bias.DRIVE.gm.original.base
    parent,_ = base.load_inputs()
    old_manifest = (ROOT/'ORIGINAL_SHA256SUMS.txt').read_bytes()
    from recover_bias import ORIGINAL_MANIFEST_SHA
    common.need(sha(old_manifest)==ORIGINAL_MANIFEST_SHA,'Historical manifest SHA differs')
    names = ('case.json','run_status.json','execution_intent.json','parent_diff.txt',
             'spectre.log','.study_owned','runner_stdout.log')
    wanted = {'run/'+plan[i]['case_id']+'/'+name for i in COHORT for name in names}
    wanted.update(f'logs/bias-753756_{i}.log' for i in COHORT)
    with tarfile.open(archive) as f:
        members = {m.name:f.extractfile(m).read() for m in f.getmembers()
                   if m.isfile() and m.name in wanted}
    common.need(set(members)==wanted,'Incomplete historical compact metadata')
    result,raw_count,raw_bytes = [],0,0
    for i in COHORT:
        plan_case = plan[i]
        case_id = plan_case['case_id']
        files = {n:members['run/'+case_id+'/'+n] for n in names}
        case,status,intent = [json.loads(files[n]) for n in names[:3]]
        hashes = {n:sha(v) for n,v in files.items()}
        common.need(all(case[k]==v for k,v in plan_case.items()) and
                    status['case_id']==case_id and status['case_sha256']==hashes['case.json'] and
                    status['plan_sha256']==ORIGINAL_PLAN_SHA and status['exit_code']==0 and
                    status['status']=='spectre_completed' and status['solver_completion_errors']==0 and
                    status['spectre_log_sha256']==hashes['spectre.log'] and
                    all(status[k]==v for k,v in intent.items()) and
                    files['.study_owned'].decode().strip()==status['slurm_job_id'],
                    'Historical status or case differs: '+case_id)
        log = files['spectre.log'].decode(errors='replace')
        common.need('SPECTRE-8282' in log and 'GMSRIREF:p' in log and
                    b"KeyError: 'GMSRIREF:p'" in members[f'logs/bias-753756_{i}.log'],
                    'Different collection failure: '+case_id)
        deck = apply_diff(parent.replace(base.MODEL_TOKEN,case['model_preflight']['model_root']),
                          files['parent_diff.txt'].decode('ascii'))
        digest = sha(deck.encode('ascii'))
        common.need(digest==status['input_deck_sha256_before']==status['input_deck_sha256_after'],
                    'Reconstructed bench differs')
        hashes['bench.scs'] = digest
        for n,d in case['staged_source_sha256'].items():
            if n not in hashes:
                common.need(n=='la5_foundry_corners.scs','Unexpected staged source: '+n)
                hashes[n] = d
            common.need(hashes[n]==d,'Staged source digest differs: '+n)
        raw_count += len(status['raw_inventory'])
        raw_bytes += sum(row['bytes'] for row in status['raw_inventory'])
        result.append({'index':i,'case_id':case_id,'files':hashes})
    return {'format':'lp_bias_recovery_inputs_v1','compact_sha256':ARCHIVE_SHA,'cases':result,
            'attested_raw_files':raw_count,'attested_raw_logical_bytes':raw_bytes}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,pin(args.compact))
