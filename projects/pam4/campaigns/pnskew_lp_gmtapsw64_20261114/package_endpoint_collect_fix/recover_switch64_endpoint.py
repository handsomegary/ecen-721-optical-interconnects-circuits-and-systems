"""Collect the two completed endpoint retries without starting Spectre."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket

from ac_next import verify_package
import gm_switch64 as switch
import gm_switch64_metrics as metrics
from gm_switch64_retry import verify_plan
import olympus_common as common
from recover_bias import publish
from recover_switch64 import (
    ARGUMENTS, EVIDENCE_FILES, MANIFEST, PLAN_SHA, ROOT, SIDECARS, SOURCE_FILES, TRAN_PATH,
    live_raw, lock_case, run_root, verify_committed, verify_effective_scale, verify_staged_sources,
)


RETRY_MANIFEST = ROOT/'ORIGINAL_ENDPOINT_RETRY_SHA256SUMS.txt'
RETRY_MANIFEST_SHA = '3ca95ec2ccde424ecad4f4b3e1e86cfbd3a801771b36e62adce72ea0a7fa935d'
RETRY_ZIP_SHA = 'b4efaeb797f38d0496c0a7dd5980ed65b5c19dbabbece8dd2c7cd364d67aa0eb'
REPORTED_RETRY_ARRAY = '757729'
RETRY_TRAN_BYTES = {84: 576370217, 86: 560309741}


def verify_approval(approval):
    ids = approval.get('case_ids', [])
    allowed = set(metrics.ENDPOINT_RETRY_CASE_IDS.values())
    common.need(approval.get('approved') is True and approval.get('platform') == 'Olympus'
                and approval.get('plan_sha256') == PLAN_SHA
                and approval.get('design_source_sha256') == RETRY_MANIFEST_SHA
                and isinstance(ids, list) and len(ids) == len(allowed) and set(ids) == allowed
                and approval.get('stages') == ['switch'] and approval.get('retire_new_raw') is not True,
                'Supply the original Olympus approval for endpoint retries 84 and 86')


def historical_evidence(original, retried, case, tran_bytes):
    case_id = case['case_id']
    common.need(case_id in metrics.ENDPOINT_RETRY_CASE_IDS.values()
                and case['kind'] == 'transient' and case['stage'] == case['group'] == 'switch'
                and all(path.is_dir() and path.resolve(strict=True) == path and path.name == case_id
                        for path in (original, retried)), 'Use the original and retry endpoint case directories')
    hashes = {name: common.sha(common.owned_file(retried, retried/name)[0]) for name in EVIDENCE_FILES}
    old_hashes = {name: common.sha(common.owned_file(original, original/name)[0])
                  for name in (*SOURCE_FILES, 'case.json', 'run_status.json')}
    prior = common.read(original/'run_status.json')
    stored = common.read(retried/'case.json')
    intent = common.read(retried/'execution_intent.json')
    status = common.read(retried/'run_status.json')
    common.need(all(old_hashes[name] == hashes[name] for name in (*SOURCE_FILES, 'case.json'))
                and switch.prior_endpoint_incomplete(prior, original)
                and all(prior[key] == intent[key] for key in ('format', 'case_id', 'case_sha256',
                         'plan_sha256', 'input_deck_sha256_before'))
                and prior['input_deck_sha256_after'] == hashes['bench.scs'],
                'Retry inputs do not match the original failed case')
    verify_staged_sources(stored, case, hashes)

    log = (retried/'spectre.log').read_bytes()
    log_text = log.decode('utf-8', errors='replace')
    verify_effective_scale(log)
    log_proof = common.classic_log(log_text)
    common.need(not re.search(r'SPECTRE-(8059|8061|8282|8287)\b', log_text),
                'Spectre skipped a required endpoint transient save')
    expected = dict(format='pam4_gmdrive_run_v1', case_id=case_id, case_sha256=hashes['case.json'],
                    plan_sha256=PLAN_SHA, input_deck_sha256_before=hashes['bench.scs'],
                    solver_mode='classic', simulator_build=common.BUILD, cpus_allocated=1,
                    requested_threads=1, SPECTRE_DEFAULTS='-E',
                    max_solver_file_bytes=metrics.ENDPOINT_RETRY_FILE_BYTES)
    argv = intent['actual_argv']
    job = intent['slurm_job_id']
    common.need(all(intent.get(key) == value for key, value in expected.items())
                and all(status.get(key) == value for key, value in intent.items())
                and all(status.get(key) == value for key, value in log_proof.items())
                and argv[1:] == ARGUMENTS and PurePosixPath(argv[0]).name == 'spectre'
                and bool(intent['solver_hostname']) and bool(intent['started_utc'])
                and isinstance(job, str) and job.isdecimal()
                and (retried/'.study_owned').read_text(encoding='utf-8').strip() == job
                and status['status'] == 'spectre_completed' and status['exit_code'] == 0
                and status['input_deck_sha256_after'] == hashes['bench.scs']
                and status['spectre_log_sha256'] == hashes['spectre.log'] == hashlib.sha256(log).hexdigest(),
                'Completed 640 MiB endpoint solver provenance differs')
    inventory = status['raw_inventory']
    transient = [row for row in inventory if metrics.SWEEP_RE.fullmatch(row['path'])]
    common.need(len(transient) == 1 and transient[0]['path'] == TRAN_PATH
                and common.DEFAULT_SOLVER_FILE_BYTES < transient[0]['bytes'] == tran_bytes
                <= metrics.ENDPOINT_RETRY_FILE_BYTES,
                'Completed endpoint PSF path or size differs from the retained retry evidence')
    pin = dict(case_id=case_id, slurm_job_id=job, reported_slurm_array_job_id=REPORTED_RETRY_ARRAY,
               solver_hostname=intent['solver_hostname'], source_files_sha256=hashes,
               failed_source_files_sha256=old_hashes, original_raw_inventory=inventory)
    return pin, stored, status, transient[0]


def recover(original_root, retry_root, case, tran_bytes, collector_manifest_sha, approval_sha):
    retry_root = switch.retry_campaign(original_root, retry_root)
    original = original_root.resolve(strict=True)/case['case_id']
    retried = retry_root/case['case_id']
    with lock_case(retried):
        pin, stored, status, transient = historical_evidence(original, retried, case, tran_bytes)
        receipt = dict(pin, format='pam4_switch64_endpoint_collect_only_v1', original_plan_sha256=PLAN_SHA,
                       original_manifest_sha256=RETRY_MANIFEST_SHA, original_zip_sha256=RETRY_ZIP_SHA,
                       original_approval_sha256=approval_sha, collector_manifest_sha256=collector_manifest_sha,
                       collector_hostname=socket.gethostname())
        if os.path.lexists(retried/'completion.json'):
            verify_committed(retried, case, receipt, transient['sha256'])
            switch.read_endpoint_retry(original.parent, retry_root, case)
            return 'already_recovered'
        for name in SIDECARS[:-1]:
            if os.path.lexists(retried/name):
                common.owned_file(retried, retried/name)
        observed = live_raw(retried, pin)
        data = metrics.native_transient(retried, dict(status, raw_inventory=observed),
                                        max_bytes=metrics.ENDPOINT_RETRY_FILE_BYTES)
        report = metrics.measurement(data, stored)
        common.need(report['format'] == metrics.FORMAT and report['case_id'] == case['case_id']
                    and report['tran_sha256'] == transient['sha256'],
                    'Endpoint measurement does not match the attested transient')
        latest, *_ = historical_evidence(original, retried, case, tran_bytes)
        common.need(latest == pin and live_raw(retried, pin) == observed, 'Source changed during collection')
        report.update(measurement_complete=True, recovery_mode='collect-only',
                      bench_sha256=pin['source_files_sha256']['bench.scs'],
                      run_status_sha256=pin['source_files_sha256']['run_status.json'])
        outcome = publish(retried, report, receipt)
        verify_committed(retried, case, receipt, transient['sha256'])
        switch.read_endpoint_retry(original.parent, retry_root, case)
        return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('collect-only',), required=True)
    parser.add_argument('--root', type=Path, required=True, help='Original run root before the endpoint retry')
    parser.add_argument('--retry-root', type=Path, required=True, help='Existing endpoint retry run root')
    parser.add_argument('--approval', type=Path, required=True, help='Existing endpoint retry approval')
    parser.add_argument('--index', type=int, action='append', choices=tuple(RETRY_TRAN_BYTES))
    options = parser.parse_args()
    indices = options.index or list(RETRY_TRAN_BYTES)
    common.need(len(set(indices)) == len(indices), 'Select each endpoint retry at most once')
    verify_package()
    common.need(common.sha(RETRY_MANIFEST) == RETRY_MANIFEST_SHA, 'Original endpoint retry manifest SHA differs')
    cases = verify_plan()
    approval_data = options.approval.read_bytes()
    verify_approval(json.loads(approval_data))
    approval_sha = hashlib.sha256(approval_data).hexdigest()
    collector_sha = common.sha(MANIFEST)
    original, retry_root = run_root(options.root), run_root(options.retry_root)
    for index in sorted(indices):
        case = cases[index]
        result = recover(original, retry_root, case, RETRY_TRAN_BYTES[index], collector_sha, approval_sha)
        print(f"{case['case_id']} {result}")


if __name__ == '__main__':
    main()
