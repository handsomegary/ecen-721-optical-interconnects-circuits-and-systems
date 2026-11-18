"""Run C2 from a hash-bound C1 review and a separately authorized C2 plan."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys

from c2_gate import ARMS, PLANES, SEEDS, check_c1, check_seed_rows, paired_comparison


PACKAGE = Path(__file__).resolve().parent
MANIFEST = PACKAGE / 'SHA256SUMS.txt'
C1 = Path(os.environ.get('PAM4_C1_PACKAGE', PACKAGE.parent / 'PAM4_C1_NOISE_SMOKE_20261115')).resolve()
C1_MANIFEST = 'abc945cc5c34a8fea340b71bde3b56be6199fd28892f37fdb075fb17f08959fe'
C2_SCHEMA = 'pam4_c2_tt_paired_noise_v1'
TOTAL_FRESH = (len(SEEDS) - 1) * len(ARMS)
MAX_PARALLEL = 3
CUTOFF = datetime(2027, 1, 1, 6, tzinfo=timezone.utc)


def digest(data):
    return hashlib.sha256(data).hexdigest()


if digest((C1 / 'SHA256SUMS.txt').read_bytes()) != C1_MANIFEST:
    raise ValueError('C1 package manifest does not match the approved original')
for line in (C1 / 'SHA256SUMS.txt').read_text(encoding='ascii').splitlines():
    expected, name = line.split('  ', 1)
    source = C1 / name
    if source.resolve(strict=True) != source or not source.is_relative_to(C1) or digest(source.read_bytes()) != expected:
        raise ValueError('C1 package file differs: ' + name)
sys.path.insert(0, str(C1))
import c1_run as c1


common = c1.common
formal = c1.formal
original = c1.original


def case_bytes(base, metadata, seed):
    common.need(seed in SEEDS[1:], 'C1 seed is reused from the pilot and must never be rerun by C2')
    matches = tuple(c1.payload.TRANSIENT.finditer(base))
    common.need(len(matches) == 1, 'C1 reference transient line differs')
    match = matches[0]
    seed_token = b' noiseseed=1001'
    common.need(match.group().endswith(seed_token) and base.count(seed_token) == 1,
                'C1 reference noise seed is missing or ambiguous')
    seed_start = match.end() - len(seed_token)
    modified = base[:seed_start] + f' noiseseed={seed}'.encode('ascii') + base[match.end():]
    common.need(metadata['case_id'].startswith('c1n_') and metadata['case_id'].endswith('_s1001'),
                'C1 case identity differs')
    new_id = 'c2n_' + metadata['case_id'][4:-4] + str(seed)
    return modified, dict(metadata, case_id=new_id, deck_sha256=digest(modified),
                          noise=dict(metadata['noise'], seed=seed))


def plan():
    formal.align_package.check_manifest(PACKAGE)
    verified = c1.verify()
    common.need(tuple(c1.payload.CASES) == ARMS and c1.payload.NOISE_SEED == SEEDS[0],
                'Original C1 cases or seed differ from the published C2 plan')
    base = [c1.payload.render(*arm) for arm in ARMS]
    common.need([meta for _, meta in base] == verified, 'C1 render is inconsistent')
    fresh = [case_bytes(bench, meta, seed) for seed in SEEDS[1:] for bench, meta in base]
    return verified, fresh


def measurement_row(report, status, measurement_sha, metadata):
    points = {plane: dict(formal.metric(report, plane),
                          clipped_count=report['metrics'][plane]['ADC_validation_input_clipped_count'])
              for plane in PLANES}
    return dict(case_id=metadata['case_id'], profile=metadata['condition'], code=metadata['code'],
                metrics=points, measurement_sha256=measurement_sha, tran_sha256=report['tran_sha256'],
                job_id=status['slurm_job_id'], solver_seconds=status['spectre_wall_seconds'],
                peak_RSS_KiB=status['child_peak_rss_KiB_after_solver'],
                raw_bytes=sum(row['bytes'] for row in status['raw_inventory']))


def c1_evidence(root, approval, c1_cases, selection, summary_sha, review, review_sha):
    summary_path = common.owned_file(root, root / c1.SUMMARY)[0]
    approval = common.owned_file(root.parent, approval)[0]
    common.need(common.sha(summary_path) == summary_sha and common.sha(review) == review_sha,
                'C1 summary or the explicit scoring review differs from its SHA pin')
    summary = common.read(summary_path)
    check_c1(summary, common.read(review), summary_sha)
    approval_sha = common.sha(approval)
    common.need(common.read(approval) == c1.request(root, selection, c1_cases)
                and summary['approval_sha256'] == approval_sha
                and summary['selection_files_sha256'] == selection
                and summary['design_source_sha256'] == C1_MANIFEST,
                'C1 approval, package or frozen C0 state differs')
    rows = [measurement_row(*c1.read_report(root, case, selection, approval_sha), case) for case in c1_cases]
    common.need(rows == summary['conditions'] and common.sha(summary_path) == summary_sha
                and common.sha(approval) == approval_sha and common.sha(review) == review_sha,
                'C1 summary differs from original execution evidence')
    evidence = dict(run_root=str(root), c1_summary_sha256=summary_sha, scoring_review_sha256=review_sha,
                    c1_approval_sha256=approval_sha, c1_package_manifest_sha256=C1_MANIFEST)
    return rows, evidence


def approval_request(root, c1_receipt, selection, fresh):
    return dict(approved=True, campaign=C2_SCHEMA, platform='Olympus', run_root=str(root),
                package_manifest_sha256=common.sha(MANIFEST), c1_pass_evidence=c1_receipt,
                c0_selection_files_sha256=selection, c1_seed=SEEDS[0], fresh_seeds=list(SEEDS[1:]),
                deck_sha256={meta['case_id']: meta['deck_sha256'] for _, meta in fresh},
                scope='95 fresh TT cases; C1 seed 1001 reused only as descriptive evidence')


def stage(root, case, selection, model_root):
    portable, meta = case
    proof = original.model_preflight.verify_private_kit(model_root, 'tt')
    marker = original.review.gm_center64.BASE.MODEL_TOKEN.encode('ascii')
    private = proof['model_root'].encode('ascii')
    bench = portable.replace(marker, private)
    common.need(portable.count(marker) == 1 and bench.replace(private, marker) == portable,
                'Private model path replacement is not reversible')
    record = dict(meta, model_preflight=proof, selection_files_sha256=selection, bench_sha256=digest(bench))
    directory = root / meta['case_id']
    if directory.exists():
        common.need(directory.resolve(strict=True) == directory and common.read(directory / 'case.json') == record
                    and (directory / 'bench.scs').read_bytes() == bench, 'Existing C2 stage differs')
    else:
        directory.mkdir()
        with (directory / 'bench.scs').open('xb') as file:
            file.write(bench)
        common.write_new(directory / 'case.json', record)
    return directory


def intent_for(directory, meta, selection, approval_sha):
    return dict(format=C2_SCHEMA, case_id=meta['case_id'], case_sha256=common.sha(directory / 'case.json'),
                design_source_sha256=common.sha(MANIFEST), selection_files_sha256=selection,
                approval_sha256=approval_sha)


def execution(directory, meta, selection, approval_sha):
    hashes = {name: common.sha(common.owned_file(directory, directory / name)[0]) for name in formal.EVIDENCE}
    status = common.read(directory / 'run_status.json')
    intent = common.read(directory / 'execution_intent.json')
    staged = common.read(directory / 'case.json')
    expected = dict(intent_for(directory, meta, selection, approval_sha),
                    input_deck_sha256_before=hashes['bench.scs'], solver_mode='classic',
                    simulator_build=common.BUILD, cpus_allocated=1, requested_threads=1, SPECTRE_DEFAULTS='-E')
    marker = original.review.gm_center64.BASE.MODEL_TOKEN.encode('ascii')
    private = staged['model_preflight']['model_root'].encode('ascii')
    bench = (directory / 'bench.scs').read_bytes()
    common.need(all(staged.get(k) == v for k, v in meta.items()) and staged['selection_files_sha256'] == selection
                and all(intent.get(k) == v for k, v in expected.items())
                and all(status.get(k) == v for k, v in intent.items())
                and staged['bench_sha256'] == status['input_deck_sha256_after'] == hashes['bench.scs']
                and digest(bench.replace(private, marker)) == meta['deck_sha256']
                and intent['actual_argv'][1:] == original.ARGUMENTS
                and status['status'] == 'spectre_completed' and status['exit_code'] == 0
                and status['spectre_log_sha256'] == hashes['spectre.log']
                and (directory / '.study_owned').read_text(encoding='ascii').strip() == intent['slurm_job_id'],
                'Incomplete or inconsistent C2 execution evidence')
    log = (directory / 'spectre.log').read_bytes()
    proof = common.classic_log(log.decode('utf-8', errors='replace'))
    original.verify_effective_scale(log)
    common.need(all(status.get(k) == v for k, v in proof.items())
                and not re.search(rb'\b(?:FATAL|USIMUWI-20006|SPECTRE-8059|SPECTRE-8061|SPECTRE-8282|SPECTRE-8287)\b',
                                  log, re.I), 'Spectre reported FATAL or a missing saved signal')
    return status, hashes


def read_measurement(directory, meta, selection, approval_sha):
    status, hashes = execution(directory, meta, selection, approval_sha)
    path = common.owned_file(directory, directory / formal.MEASURE)[0]
    report = common.read(path)
    c1.checked_report(report, meta, status, hashes, selection)
    return report, status, common.sha(path)


def collect(directory, meta, calibration, selection, approval_sha):
    with original.lock_case(directory):
        if (directory / formal.MEASURE).exists():
            return read_measurement(directory, meta, selection, approval_sha)[0]
        status, hashes = execution(directory, meta, selection, approval_sha)
        report = c1.payload.measure(directory, meta, calibration)
        common.need(execution(directory, meta, selection, approval_sha)[1] == hashes,
                    'Execution evidence changed during C2 collection')
        report.update(execution_files_sha256=hashes, selection_files_sha256=selection,
                      run_status_sha256=hashes['run_status.json'])
        c1.checked_report(report, meta, status, hashes, selection)
        formal.align_package.publish_new(directory / formal.MEASURE, report)
        return report


def run(directory, meta, calibration, selection, approval_sha):
    common.need(datetime.now(timezone.utc) + timedelta(seconds=c1.WALL_S) <= CUTOFF,
                'Olympus authorization expires before the reserved wall time')
    if not (directory / 'run_status.json').exists():
        solver, env = common.environment()
        with (directory / '.study_owned').open('x', encoding='ascii') as stream:
            stream.write(os.environ['SLURM_JOB_ID'] + '\n')
        common.run_classic(directory, common.sha(directory / 'bench.scs'),
                           intent_for(directory, meta, selection, approval_sha), c1.TIMEOUT_S, solver, env)
    return collect(directory, meta, calibration, selection, approval_sha)


def write_summary(root, fresh, pilot, selection, approval_sha, c1_receipt):
    grouped = {seed: [] for seed in SEEDS[1:]}
    grouped[SEEDS[0]] = pilot
    for _, meta in fresh:
        output = read_measurement(root / meta['case_id'], meta, selection, approval_sha)
        grouped[meta['noise']['seed']].append(measurement_row(*output, meta))
    for rows in grouped.values():
        check_seed_rows(rows)
    common.need(len({row['job_id'] for rows in grouped.values() for row in rows}) == len(SEEDS) * len(ARMS),
                'Some C1 and C2 records share the same Slurm task ID')
    result = dict(schema=C2_SCHEMA, status='c2_complete', fresh_cases=TOTAL_FRESH, total_cases=len(SEEDS) * len(ARMS),
                  c1_pass_evidence=c1_receipt, c0_training_selection={'P_late': 0, 'N_late': 60},
                  c2_approval_sha256=approval_sha, c2_manifest_sha256=common.sha(MANIFEST),
                  selection_files_sha256=selection, conditions_by_seed={str(seed): rows for seed, rows in grouped.items()},
                  paired_descriptive_all_seeds=paired_comparison(SEEDS, grouped),
                  paired_inference_fresh_seeds_only=paired_comparison(SEEDS[1:], grouped, infer=True),
                  limitations=['Seed 1001 is selected by the C1 gate and is excluded from inference.',
                               'P late −60 is a fixed-code diagnostic.',
                               'The long-run ADC scoring still uses an ideal 7-bit quantizer.'])
    output = root / 'c2_tt_paired_summary.json'
    if output.exists():
        common.need(common.read(output) == result, 'Existing C2 summary differs')
    else:
        formal.align_package.publish_new(output, result)
    return output


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('verify', 'list', 'approval-template', 'submit', 'run', 'collect-only', 'summarize'))
    for name in ('c0-root', 'c1-root', 'c1-approval', 'root', 'approval', 'review', 'model-root'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--review-sha')
    parser.add_argument('--c1-summary-sha')
    parser.add_argument('--index', type=int)
    return parser.parse_args()


def main():
    args = parse_arguments()
    c1_cases, fresh = plan()
    if args.mode in ('verify', 'list'):
        for index, (_, meta) in enumerate(fresh):
            print(index, meta['case_id'], meta['deck_sha256'])
        return
    common.need(all(value is not None for value in (args.c0_root, args.c1_root, args.c1_approval, args.root, args.approval,
                                                    args.review, args.review_sha, args.c1_summary_sha)),
                'Provide the original C0 and C1 run roots, separate C2 root and approval, and explicit C1 review pins')
    c0_root = args.c0_root.resolve(strict=True)
    c1_root = common.checked_root(args.c1_root)
    root = common.checked_root(args.root)
    common.need(all(root != prior and root not in prior.parents and prior not in root.parents
                    for prior in (c0_root, c1_root)), 'Use a separate C2 run root')
    common.need(root not in args.c1_approval.absolute().parents, 'C1 approval must remain in the original campaign')
    review = args.review.resolve(strict=True)
    calibration, selection = c1.inputs(c0_root)
    pilot, c1_receipt = c1_evidence(c1_root, args.c1_approval, c1_cases, selection,
                                    args.c1_summary_sha, review, args.review_sha)
    request = approval_request(root, c1_receipt, selection, fresh)
    approval = args.approval.absolute()
    common.need(approval == root / 'approval_c2.json', 'Approval must be kept in the new C2 run root')
    if args.mode == 'approval-template':
        common.write_new(approval, dict(request, approved=False))
        return
    approval = common.owned_file(root, approval)[0]
    common.need(common.read(approval) == request, 'Separate C2 approval must bind the C1 pass evidence and all C2 deck hashes')
    approval_sha = common.sha(approval)
    if args.mode == 'summarize':
        print(write_summary(root, fresh, pilot, selection, approval_sha, c1_receipt))
        return
    if args.mode == 'submit':
        common.need(args.model_root is not None, 'Supply the existing private model path')
        common.need(datetime.now(timezone.utc) + timedelta(seconds=c1.WALL_S) <= CUTOFF,
                    'Olympus authorization expires before the reserved wall time')
        env = dict(os.environ, PAM4_C1_PACKAGE=str(C1), PAM4_C2_PACKAGE=str(PACKAGE), PAM4_C0_FORMAL_ROOT=str(c0_root),
                   PAM4_C1_ROOT=str(c1_root), PAM4_C1_APPROVAL=str(args.c1_approval.absolute()), PAM4_C2_ROOT=str(root),
                   PAM4_C2_APPROVAL=str(approval), PAM4_C2_REVIEW=str(review), PAM4_C2_REVIEW_SHA=args.review_sha,
                   PAM4_C2_C1_SUMMARY_SHA=args.c1_summary_sha, PAM4_PDK_ROOT=str(args.model_root.resolve(strict=True)))
        script = ['sbatch', '--parsable', '--export=ALL', f'--array=0-{TOTAL_FRESH - 1}%{MAX_PARALLEL}',
                  f'--output={root / "slurm-%A_%a.log"}', str(PACKAGE / 'c2_paired.sbatch')]
        common.write_new(root / 'c2_submission_intent.json',
                         dict(approval_sha256=approval_sha, submit_utc=common.utc(), argv=script))
        result = subprocess.run(script, check=True, env=env, capture_output=True, text=True)
        job = result.stdout.strip()
        common.need(re.fullmatch(r'\d+(;[^;\s]+)?', job), 'Record the Slurm job from the original submission before retry')
        common.write_new(root / 'c2_submission.json', dict(approval_sha256=approval_sha, array_job_id=job.split(';')[0]))
        print(job)
        return
    common.need(args.index is not None and 0 <= args.index < TOTAL_FRESH, 'Select a fresh C2 index 0–94')
    _, meta = fresh[args.index]
    if args.mode == 'collect-only':
        collect(root / meta['case_id'], meta, calibration, selection, approval_sha)
    else:
        common.need(args.model_root is not None, 'Supply the existing private model path')
        common.need(os.environ.get('SLURM_ARRAY_TASK_ID') == str(args.index), 'Run only the allocated Slurm array task')
        directory = stage(root, fresh[args.index], selection, args.model_root)
        run(directory, meta, calibration, selection, approval_sha)
    print(root / meta['case_id'] / formal.MEASURE)


if __name__ == '__main__':
    main()
