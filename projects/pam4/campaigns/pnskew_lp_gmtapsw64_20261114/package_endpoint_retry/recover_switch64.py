"""Recover the two existing SWITCH64 smoke measurements without a solver."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import sys

from ac_next import verify_package
import gm_summary
import gm_switch64_metrics as metrics
import gm_switch64_rf
import olympus_common as common
from pvt import model_preflight
from recover_bias import publish


ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'gm_switch64_plan.json'
MANIFEST = ROOT/'SHA256SUMS.txt'
ORIGINAL_MANIFEST = ROOT/'ORIGINAL_SWITCH64_SHA256SUMS.txt'
PLAN_SHA = 'a2f8774d9887630fd9a1d5138f2758207bd01c3648299673a76eb2017d991dcc'
ORIGINAL_MANIFEST_SHA = 'e4a1b61de0d81f13798f2654e77acaadc2fa4acaa1bb6a4c3a366a6adc3d7bbb'
ORIGINAL_ZIP_SHA = '63d0272a2e9b93c64ef1c79519133806bc86e559ea1ddebbf8cd1e528fc6fe28'
SMOKE = {
    48: ('gmsw_048_ss_hold_p01_p01_zero', 369909297),
    49: ('gmsw_049_ss_switch_p00_p01_zero', 378504236),
}
REPORTED_SMOKE_ARRAY = '757441'
TRAN_PATH = 'raw/codeSwitch.tran.tran'
SOURCE_FILES = ('bench.scs', 'parent_diff.txt', 'la5_foundry_corners.scs')
EVIDENCE_FILES = (*SOURCE_FILES, 'case.json', 'execution_intent.json', 'run_status.json',
                  'spectre.log', 'runner_stdout.log', '.study_owned')
SIDECARS = ('measurements.json', 'recovery.json', 'completion.json')
ARGUMENTS = ['-64','+mt=1','bench.scs','-format','psfascii','-raw','raw',
             '+log','spectre.log','+lqtimeout','30']


def run_root(path):
    path = path.absolute()
    canonical = path.resolve(strict=True)
    allowed = (Path.home()/'ecen720_28nm'/'runs').resolve(strict=True)
    common.need(canonical == path and canonical.is_dir() and allowed in path.parents,
                'Use the original real case parent under ~/ecen720_28nm/runs')
    return canonical


def verify_approval(approval, cases):
    common.need(approval.get('approved') is True and approval.get('platform') == 'Olympus'
                and approval.get('plan_sha256') == PLAN_SHA
                and approval.get('design_source_sha256') == ORIGINAL_MANIFEST_SHA
                and all(case['case_id'] in approval.get('case_ids', [])
                        and case['stage'] in approval.get('stages', []) for case in cases),
                'Supply the original Olympus SWITCH64 approval for the selected smoke cases')


def verify_staged_sources(stored, case, hashes):
    expected = {name: hashes[name] for name in SOURCE_FILES}
    common.need(stored['staged_source_sha256'] == expected, 'Original staged source SHA differs')
    model = stored['model_preflight']
    model_root = model['model_root']
    portable = (model_preflight.REFERENCE/model_preflight.CORNER_FILE).read_bytes()
    corner = model_preflight.materialize_corner(portable, model_root)
    portable_sha = hashlib.sha256(portable).hexdigest()
    corner_sha = hashlib.sha256(corner).hexdigest()
    expected_model = {'schema': 'PAM4_PRIVATE_VM_KIT_PREFLIGHT_V1',
                      'static_identity_verified': True, 'active_static_mos_scale': .9,
                      'process': case['process'], 'root_section': 'top_'+case['process'],
                      'active_shrink_sections': model_preflight.verify_wrapper(portable, case['process']),
                      'model_files_written': False, 'model_bodies_exported': False,
                      'simulation_started': False,
                      'root_substitution_reversible': True,
                      'portable_corner_wrapper_sha256': portable_sha,
                      'corner_wrapper_sha256': corner_sha,
                      'kit_fingerprints': {name: {'bytes': size, 'sha256': digest}
                                           for name, (size, digest) in model_preflight.KIT_PINS.items()}}
    common.need(PurePosixPath(model_root).is_absolute() and
                not any(c in model_root for c in ('"', '\n', '\r', '\\')) and
                all(model.get(k) == value for k, value in expected_model.items()) and
                corner_sha == expected['la5_foundry_corners.scs'], 'Staged private-kit provenance differs')
    deck, rails, ac, dc, currents, diff = gm_switch64_rf.render(case, model_root)
    expected_metadata = dict(case, rail_voltages_V=rails, AC_traces=ac, DC_nodes=dc,
                             DC_currents=currents, model_preflight=model,
                             staged_source_sha256=expected)
    regenerated = {name: hashlib.sha256(data.encode('ascii')).hexdigest()
                   for name, data in (('bench.scs', deck), ('parent_diff.txt', diff))}
    common.need(stored == expected_metadata and
                all(expected[name] == digest for name, digest in regenerated.items()),
                'Frozen generator does not reproduce the original staged inputs')


def verify_effective_scale(log):
    # The frozen standalone PVT collector imports its siblings as top-level modules.
    sys.path.insert(0, str(ROOT/'pvt'))
    try:
        from pvt.collect_ac import require_effective_scale
    finally:
        sys.path.pop(0)
    require_effective_scale(log)


def historical_evidence(case_dir, case, tran_bytes):
    common.need(case_dir.is_dir() and case_dir.resolve(strict=True) == case_dir
                and case_dir.name == case['case_id'], 'Use the original smoke case directory')
    hashes = {name: common.sha(common.owned_file(case_dir, case_dir/name)[0])
              for name in EVIDENCE_FILES}
    stored = common.read(case_dir/'case.json')
    status = common.read(case_dir/'run_status.json')
    intent = common.read(case_dir/'execution_intent.json')
    log = (case_dir/'spectre.log').read_bytes()
    log_text = log.decode('utf-8', errors='replace')
    verify_effective_scale(log)
    log_proof = common.classic_log(log_text)
    common.need(not re.search(r'SPECTRE-(8059|8061|8282|8287)\b', log_text),
                'Spectre skipped a required switch transient save')
    expected = dict(format='pam4_gmdrive_run_v1', case_id=case['case_id'],
                    case_sha256=hashes['case.json'], plan_sha256=PLAN_SHA,
                    input_deck_sha256_before=hashes['bench.scs'], solver_mode='classic',
                    simulator_build=common.BUILD, cpus_allocated=1, requested_threads=1,
                    SPECTRE_DEFAULTS='-E', max_solver_file_bytes=512*1024**2)
    argv = intent['actual_argv']
    job_id = intent['slurm_job_id']
    common.need(all(intent.get(key) == value for key, value in expected.items())
                and all(status.get(key) == value for key, value in intent.items())
                and argv[1:] == ARGUMENTS and PurePosixPath(argv[0]).name == 'spectre'
                and bool(intent['solver_hostname']) and bool(intent['started_utc'])
                and bool(re.fullmatch(r'[0-9]+', job_id))
                and (case_dir/'.study_owned').read_text(encoding='utf-8').strip() == job_id
                and status['status'] == 'spectre_completed' and status['exit_code'] == 0
                and all(status.get(k) == value for k, value in log_proof.items())
                and status['input_deck_sha256_after'] == hashes['bench.scs']
                and status['spectre_log_sha256'] == hashes['spectre.log'] == hashlib.sha256(log).hexdigest(),
                'Historical Spectre execution provenance differs')
    verify_staged_sources(stored, case, hashes)
    recorded = status['raw_inventory']
    transient = [row for row in recorded if metrics.SWEEP_RE.fullmatch(row['path'])]
    common.need(len(transient) == 1 and transient[0]['path'] == TRAN_PATH and
                transient[0]['bytes'] == tran_bytes, 'Historical smoke PSF name or size differs')
    pin = dict(case_id=case['case_id'], slurm_job_id=job_id,
               reported_slurm_array_job_id=REPORTED_SMOKE_ARRAY,
               solver_hostname=intent['solver_hostname'], source_files_sha256=hashes,
               original_raw_inventory=recorded)
    return pin, stored, status, transient[0]


def live_raw(case_dir, pin):
    observed = common.raw_inventory(case_dir)
    common.need(common.matches_historical_inventory(pin['original_raw_inventory'], observed),
                'Original raw inventory differs')
    return observed


def receipt_from(pin, collector_manifest_sha, approval_sha):
    return dict(pin, format='pam4_switch64_collect_only_v1', original_plan_sha256=PLAN_SHA,
                original_manifest_sha256=ORIGINAL_MANIFEST_SHA, original_zip_sha256=ORIGINAL_ZIP_SHA,
                original_approval_sha256=approval_sha,
                collector_manifest_sha256=collector_manifest_sha, collector_hostname=socket.gethostname())


def verify_committed(case_dir, case, receipt, transient_sha):
    for name in SIDECARS:
        common.owned_file(case_dir, case_dir/name)
    report = gm_summary.read_case(case_dir.parent, case, PLAN)
    proof = common.read(case_dir/'recovery.json')
    expected = dict(receipt, collector_hostname=proof['collector_hostname'],
                    measurement_sha256=common.sha(case_dir/'measurements.json'))
    common.need(proof == expected and bool(proof['collector_hostname'])
                and report.get('recovery_mode') == 'collect-only'
                and report['tran_sha256'] == transient_sha, 'Committed recovery provenance differs')


@contextmanager
def lock_case(case_dir):
    import fcntl

    # NFS translates an exclusive flock to a write lock. Open the existing
    # regular owner marker read/write without changing its contents.
    marker, expected = common.owned_file(case_dir, case_dir/'.study_owned')
    fd = os.open(marker, os.O_RDWR | os.O_NOFOLLOW)
    try:
        common.need(os.path.samestat(expected, os.fstat(fd)), 'Case owner marker changed before lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def recover(case_dir, case, tran_bytes, expected_pin, collector_manifest_sha, approval_sha):
    with lock_case(case_dir):
        pin, stored, status, tran = historical_evidence(case_dir, case, tran_bytes)
        common.need(expected_pin is None or expected_pin == pin, 'Original smoke snapshot differs')
        receipt = receipt_from(pin, collector_manifest_sha, approval_sha)
        if os.path.lexists(case_dir/'completion.json'):
            verify_committed(case_dir, case, receipt, tran['sha256'])
            return 'already_recovered'
        # A partial prior publication can open only our single-link sidecars.
        for name in SIDECARS[:-1]:
            if os.path.lexists(case_dir/name):
                common.owned_file(case_dir, case_dir/name)
        observed = live_raw(case_dir, pin)
        report = metrics.measurement(metrics.native_transient(case_dir, dict(status, raw_inventory=observed)), stored)
        common.need(report['case_id'] == case['case_id'] and report['tran_sha256'] == tran['sha256'],
                    'Transient measurement differs from pinned native evidence')
        latest, *_ = historical_evidence(case_dir, case, tran_bytes)
        common.need(latest == pin and live_raw(case_dir, pin) == observed, 'Source changed during collection')
        report.update(measurement_complete=True, recovery_mode='collect-only',
                      bench_sha256=pin['source_files_sha256']['bench.scs'],
                      run_status_sha256=pin['source_files_sha256']['run_status.json'])
        outcome = publish(case_dir, report, receipt)
        verify_committed(case_dir, case, receipt, tran['sha256'])
        return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('snapshot', 'collect-only'), required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--index', type=int, action='append')
    options = parser.parse_args()
    indices = options.index or list(SMOKE)
    common.need(len(set(indices)) == len(indices) and all(index in SMOKE for index in indices),
                'Select distinct original smoke indices 48 and 49')
    if options.mode == 'snapshot':
        common.need(options.snapshot is not None, 'Specify a new snapshot path')
    else:
        common.need(options.approval is not None, 'Supply the original smoke approval')
    verify_package()
    common.need(common.sha(PLAN) == PLAN_SHA and common.sha(ORIGINAL_MANIFEST) == ORIGINAL_MANIFEST_SHA,
                'Original SWITCH64 plan or manifest SHA differs')
    plan = common.read(PLAN)
    entries = [(plan['cases'][index], SMOKE[index][1]) for index in sorted(indices)]
    common.need(all(case['case_id'] == SMOKE[index][0] for index, (case, _) in zip(sorted(indices), entries)),
                'Original SWITCH64 smoke catalog differs')
    root = run_root(options.root)
    snapshot = dict(format='pam4_switch64_original_smoke_snapshot_v1', root=str(root),
                    plan_sha256=PLAN_SHA, original_manifest_sha256=ORIGINAL_MANIFEST_SHA)
    if options.mode == 'snapshot':
        pins = {}
        for case, size in entries:
            case_dir = root/case['case_id']
            pin, *_ = historical_evidence(case_dir, case, size)
            live_raw(case_dir, pin)
            pins[case['case_id']] = pin
        common.write_new(options.snapshot, dict(snapshot, cases=pins))
        return
    approval_data = options.approval.read_bytes()
    # Hash and authorize the same bytes even if the external approval path changes.
    verify_approval(json.loads(approval_data), [case for case, _ in entries])
    approved_pins = {}
    if options.snapshot is not None:
        stored = common.read(options.snapshot)
        approved_pins = stored.pop('cases')
        common.need(stored == snapshot and
                    all(isinstance(approved_pins.get(case['case_id']), dict) for case, _ in entries),
                    'Snapshot must bind the historical run and contain selected cases')
    collector_sha = common.sha(MANIFEST)
    approval_sha = hashlib.sha256(approval_data).hexdigest()
    for case, size in entries:
        case_id = case['case_id']
        result = recover(root/case_id, case, size, approved_pins.get(case_id), collector_sha, approval_sha)
        print(f'{case_id} {result}')


if __name__ == '__main__':
    main()
