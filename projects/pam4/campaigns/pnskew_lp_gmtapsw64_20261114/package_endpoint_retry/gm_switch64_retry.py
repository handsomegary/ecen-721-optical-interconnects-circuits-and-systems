"""Run only the retained SWITCH64 endpoint retries at the reviewed file-size limit."""

import argparse
from functools import partial
import hashlib
from pathlib import Path

import gm_drive
import gm_switch64 as switch
import gm_switch64_metrics as metrics
import olympus_common as common


PLAN_SHA256 = 'a2f8774d9887630fd9a1d5138f2758207bd01c3648299673a76eb2017d991dcc'
PRIOR_MANIFEST_SHA256 = '759c951d9f5ec0a670570ff90ccd0f609aa3852192124427c3bf77ad892ee06a'
PRIOR_MANIFEST = switch.ROOT/'ORIGINAL_RECOVERY_SHA256SUMS.txt'


def verify_plan():
    common.need(common.sha(switch.PLAN) == PLAN_SHA256 and
                common.sha(PRIOR_MANIFEST) == PRIOR_MANIFEST_SHA256,
                'Switch64 endpoint source plan or prior manifest differs')
    plan = common.read(switch.PLAN)
    common.need(plan == switch.build_plan(), 'Switch64 plan differs from the generator')
    prior_hashes = {name: digest for digest, name in
                    (line.split('  ', 1) for line in PRIOR_MANIFEST.read_text(encoding='ascii').splitlines())}
    cases = {}
    for index, name in metrics.ENDPOINT_RETRY_CASE_IDS.items():
        case = plan['cases'][index]
        common.need(case['case_id'] == name and case['stage'] == 'switch', 'Endpoint case identity differs')
        deck, *_, diff = switch.render(case, switch.BASE.MODEL_TOKEN)
        for filename, source in (('bench.scs', deck), ('parent_diff.txt', diff)):
            digest = hashlib.sha256(source.encode('ascii')).hexdigest()
            common.need(digest == prior_hashes[f'portable_review/{name}/{filename}'],
                        f'Switch64 endpoint {filename} differs from the prior deck for {name}')
        cases[index] = case
    return cases


def run(case, root, model_root, approval):
    retry_ids = set(metrics.ENDPOINT_RETRY_CASE_IDS.values())
    approved_ids = approval.get('case_ids', [])
    common.need(case['case_id'] in retry_ids and case['stage'] == 'switch'
                and gm_drive.approved_case(case, approval, switch.PLAN)
                and set(approved_ids) <= retry_ids and len(set(approved_ids)) == len(approved_ids)
                and approval.get('stages') == ['switch'] and approval.get('retire_new_raw') is not True,
                'Approval must bind only the SWITCH64 endpoint retries with raw retained')
    root = common.checked_root(root)
    common.need(all(entry.name in retry_ids and entry.is_dir() and not entry.is_symlink()
                    for entry in root.iterdir()) and not (root/case['case_id']).exists(),
                'Use a separate retry campaign directory with no prior attempt for this case')
    max_bytes = metrics.ENDPOINT_RETRY_FILE_BYTES
    gm_drive.run(case, root, model_root, approval, plan=switch.PLAN, stage_case=switch.stage,
                 collect_case=partial(metrics.collect, max_bytes=max_bytes), max_solver_file_bytes=max_bytes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('verify', 'run'), required=True)
    parser.add_argument('--index', type=int, choices=tuple(metrics.ENDPOINT_RETRY_CASE_IDS))
    parser.add_argument('--root', type=Path)
    parser.add_argument('--model-root', type=Path)
    parser.add_argument('--approval', type=Path)
    options = parser.parse_args()
    switch.hardware.trim.fine.endpoint.integrated.mirror.prior.gm.original.verify_package()
    cases = verify_plan()
    if options.mode == 'verify':
        print('Switch64 endpoint retry package and original decks 84 and 86 verified')
        return
    if options.index is None or options.root is None or options.model_root is None or options.approval is None:
        parser.error('Supply the retry index, separate run root, private model root and approval')
    run(cases[options.index], options.root, options.model_root, common.read(options.approval))


if __name__ == '__main__':
    main()
