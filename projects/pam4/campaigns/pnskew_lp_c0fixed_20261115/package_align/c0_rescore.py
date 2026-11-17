"""Re-score completed C0 runs using one training-only zero-skew calibration."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parent
ORIGINAL = Path(os.environ.get('PAM4_C0_ORIGINAL_PACKAGE',
    ROOT.parent/'PAM4_PNSKEW_LP_GMTAP_C0_RUN_20261115')).resolve()
PLAN_SHA = '14d5d7ca820c639a85f35a68cf7af46392138f90efc43ccbb7922f38242d1072'
ORIGINAL_MANIFEST_SHA = '35d3c9d50b1ef54cdcef09cc58b7aa361783eefb54692e635a8e233331aa59e0'
CASE0_TASK = '757899'
MEASUREMENT = 'c0_aligned_measurements.json'
SCHEMA = 'pam4_c0_aligned_v1'
ORIGINAL_REPORTS = ('measurements.json', 'recovery.json', 'completion.json')


def check_manifest(directory):
    for row in (directory/'SHA256SUMS.txt').read_text(encoding='ascii').splitlines():
        digest, name = row.split('  ', 1)
        path = directory/name
        if not path.resolve().is_relative_to(directory) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Package file SHA differs: '+name)


def pin_original():
    for name, expected in (('c0_review_plan.json', PLAN_SHA), ('SHA256SUMS.txt', ORIGINAL_MANIFEST_SHA)):
        if hashlib.sha256((ORIGINAL/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Original C0 package identity differs: '+name)
    check_manifest(ORIGINAL)


pin_original()
sys.path.insert(0, str(ORIGINAL))
import c0_run as original
from recover_bias import payload

common = original.common
common.need(original.ROOT == ORIGINAL, 'Loaded the wrong original C0 runner')


def verify_package():
    pin_original()
    check_manifest(ROOT)
    return original.verify_package()


def calibration_sha(calibration):
    encoded = json.dumps(calibration, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('ascii')
    return hashlib.sha256(encoded).hexdigest()


def case_directory(root, case):
    directory = root/case['case_id']
    common.need(directory == directory.resolve(strict=True) and directory.is_dir(),
                'C0 case path is redirected: '+case['case_id'])
    return directory


def evidence(case, directory):
    status, hashes = original.execution_evidence(case, directory)
    native = [row for row in status['raw_inventory']
              if row['path'] in ('raw/tranResponse.tran', original.review.RAW_NAME)]
    common.need(len(native) == 1, 'Missing unique native transient in original execution evidence')
    proof = {
        'original_plan_sha256': PLAN_SHA,
        'original_manifest_sha256': ORIGINAL_MANIFEST_SHA,
        'original_execution_files_sha256': hashes,
        'slurm_task_id': status['slurm_job_id'],
        'transient': {'path':native[0]['path'], 'bytes':native[0]['bytes'], 'sha256':native[0]['sha256']},
    }
    prior = None
    if case['case_id'] == original.review.CASES[0][0]:
        common.need(status['slurm_job_id'] == CASE0_TASK, 'Use the retained case 0 from task '+CASE0_TASK)
        prior_hashes = {name:common.sha(common.owned_file(directory, directory/name)[0])
                        for name in ORIGINAL_REPORTS}
        prior = original.read_case(case, directory)
        proof['original_collection_files_sha256'] = prior_hashes
    return status, proof, prior


def validate_report(report, case, proof, collector_manifest_sha, calibration):
    common.need(report['case'] == case and report['frozen_sha256'] == original.review.FROZEN_SHA
                and report['run_status_sha256'] == proof['original_execution_files_sha256']['run_status.json']
                and report['tran_sha256'] == proof['transient']['sha256']
                and report['rescore_schema'] == SCHEMA and report['rescore_evidence'] == proof
                and report['collector_manifest_sha256'] == collector_manifest_sha
                and report['calibration_sha256'] == calibration_sha(report['calibration'])
                and (calibration is None or report['calibration'] == calibration),
                'Aligned score, calibration or original execution SHA differs: '+case['case_id'])
    if case['case_id'] == original.review.CASES[0][0]:
        common.need(report['calibration']['baseline_tran_sha256'] == report['tran_sha256']
                    and report['calibration']['baseline_run_status_sha256'] == report['run_status_sha256'],
                    'Calibration does not reference the original zero-skew waveforms')
    start = original.review.FIRST_PAYLOAD
    stop = start + case['holdout_inputs']
    scoring = report['scoring']
    common.need(scoring['payload_tx_indices'] == [start, stop]
                and scoring['ffe_center_tx_indices'] == [start+8, stop-8]
                and scoring['phase_optimized'] is False,
                'Aligned score changed the original payload indices or optimized phase')
    for point in ('primary', 'secondary'):
        entry = report['metrics'][point]
        metrics = entry['metrics']
        ffe = metrics['ideal7bit_ADC_then_FFE']
        choice = report['calibration']['selections'][point]
        common.need(metrics['ADC_validation_input_count'] == case['holdout_inputs']
                    and metrics['FFE_validation_output_count'] == ffe['sample_count'] == case['FFE_scored_symbols']
                    and metrics['validation_fitting_performed'] is False and entry['lag'] == choice['lag']
                    and choice['last_training_read_s'] < min(entry['first_read_s'], original.review.FIRST_PAYLOAD_S),
                    'Aligned score changed the original payload extent or fitted payload')


def read_report(case, directory, collector_manifest_sha, calibration):
    status, proof, _ = evidence(case, directory)
    path, _ = common.owned_file(directory, directory/MEASUREMENT)
    report = common.read(path)
    validate_report(report, case, proof, collector_manifest_sha, calibration)
    return report, status


def publish_new(path, report):
    # A single file binds score and calibration atomically. Keep original results in place.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f'.{path.name}-', delete=False) as stream:
        temp = Path(stream.name)
        try:
            stream.write(payload(report))
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            os.link(temp, path)
        finally:
            temp.unlink()


def legacy_counts(report):
    counts = {}
    for point in ('primary', 'secondary'):
        metrics = report['metrics'][point]['metrics']
        counts[point] = {name:metrics[name]['symbol_errors'] for name in
                         ('raw_held_FFE_before_ADC', 'ideal7bit_ADC_then_FFE')}
    return counts


def matches_feedback(counts):
    expected = common.read(ROOT/'CASE0_OBSERVED.json')['original_counts']
    for point, original_counts in counts.items():
        if original_counts['raw_held_FFE_before_ADC'] != expected[point]['raw_FFE_errors']:
            return False
        if original_counts['ideal7bit_ADC_then_FFE'] != expected[point]['ideal7bit_FFE_errors']:
            return False
    return True


def collect(cases, index, root, collector_manifest_sha):
    import c0_align

    case = cases[index]
    directory = case_directory(root, case)
    settings = None
    if index != 0:
        baseline = cases[0]
        calibrated, _ = read_report(baseline, case_directory(root, baseline), collector_manifest_sha, None)
        settings = calibrated['calibration']
    target = directory/MEASUREMENT
    with original.lock_case(directory):
        status, before, prior = evidence(case, directory)
        if os.path.lexists(target):
            report = common.read(common.owned_file(directory, target)[0])
            validate_report(report, case, before, collector_manifest_sha, settings)
            return report
        live = common.raw_inventory(directory)
        common.need(common.matches_historical_inventory(status['raw_inventory'], live),
                    'Retained raw differs from recorded evidence: '+case['case_id'])
        report = c0_align.measure(directory, settings)
        _, after, _ = evidence(case, directory)
        common.need(after == before and common.raw_inventory(directory) == live,
                    'Source or raw changed during re-scoring: '+case['case_id'])
        report.update(rescore_schema=SCHEMA, rescore_evidence=before,
                      calibration_sha256=calibration_sha(report['calibration']),
                      collector_manifest_sha256=collector_manifest_sha)
        if prior is not None:
            report['prior_symbol_errors'] = legacy_counts(prior)
            report['prior_result_matches_feedback'] = matches_feedback(report['prior_symbol_errors'])
        validate_report(report, case, before, collector_manifest_sha, settings)
        publish_new(target, report)
        return report


def summarize(cases, root, collector_manifest_sha):
    settings = None
    paths = []
    resources = {}
    for case in cases:
        directory = case_directory(root, case)
        report, status = read_report(case, directory, collector_manifest_sha, settings)
        if settings is None:
            settings = report['calibration']
        paths.append(directory/MEASUREMENT)
        resources[case['case_id']] = {
            'slurm_task_id': status['slurm_job_id'], 'solver_wall_seconds':status['spectre_wall_seconds'],
            'solver_peak_RSS_KiB':status['child_peak_rss_KiB_after_solver'],
            'raw_bytes':sum(row['bytes'] for row in status['raw_inventory']),
        }
    data = original.review.summarize(paths)
    data.update(rescore_schema=SCHEMA, completed_cases=len(cases),
                original_plan_sha256=PLAN_SHA, original_manifest_sha256=ORIGINAL_MANIFEST_SHA,
                collector_manifest_sha256=collector_manifest_sha,
                calibration=settings, calibration_sha256=calibration_sha(settings), resources=resources)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('verify', 'collect-only', 'check-baseline', 'summarize'), required=True)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--index', type=int, choices=range(5), action='append')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    cases = verify_package()
    if args.mode == 'verify':
        print('Original five decks and alignment overlay verified')
        return
    if args.root is None:
        parser.error('Supply the existing original C0 campaign with --root')
    root = args.root.absolute()
    common.need(root == root.resolve(strict=True) and root.is_dir(), 'Expected the original C0 campaign directory')
    manifest_sha = common.sha(ROOT/'SHA256SUMS.txt')
    if args.mode == 'check-baseline':
        directory = case_directory(root, cases[0])
        report, _ = read_report(cases[0], directory, manifest_sha, None)
        print_case(report, directory)
    elif args.mode == 'summarize':
        if args.output is None:
            parser.error('Supply a new --output path for the aligned summary')
        publish_new(args.output, summarize(cases, root, manifest_sha))
        print(args.output)
    else:
        if not args.index or len(set(args.index)) != len(args.index):
            parser.error('Supply one or more distinct --index values')
        for index in args.index:
            report = collect(cases, index, root, manifest_sha)
            print_case(report, root/cases[index]['case_id'])


def print_case(report, directory):
    settings = report['calibration']['selections']
    planes = {point:{'SER':data['metrics']['ideal7bit_ADC_then_FFE']['SER'], 'lag':data['lag'],
                     'zero_skew_training_r':settings[point]['pearson'],
                     'training_sign_matches_circuit':settings[point]['correlation_sign_matches_circuit']}
              for point, data in report['metrics'].items()}
    print(json.dumps({'case_id':report['case']['case_id'], 'planes':planes,
                      'calibration_sha256':report['calibration_sha256'],
                      'measurement':str(directory/MEASUREMENT)}))


if __name__ == '__main__':
    main()
