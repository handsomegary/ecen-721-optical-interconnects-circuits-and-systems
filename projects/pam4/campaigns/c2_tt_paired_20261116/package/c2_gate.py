"""Check the predeclared C1 gate and summarize paired errors by noise seed."""

from collections import defaultdict
import math


PLANES = ('primary', 'secondary')
ARMS = (('zero', 0), ('a', 0), ('a', -60), ('b', 0), ('b', 60))
PAIRS = (('P_late_fixed_code_diagnostic', 1, 2), ('N_late_frozen_selection', 3, 4))
SEEDS = tuple(range(1001, 1021))
DENOMINATOR = 2032


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_seed_rows(rows, *, reject_clipping=False):
    require(len(rows) == len(ARMS), 'Expected all five cases for one noise seed')
    require([(row['profile'], row['code']) for row in rows] == list(ARMS),
            'Cases or code settings differ from the frozen plan')
    require(len({row['job_id'] for row in rows}) == len(rows), 'Duplicate Slurm task ID')
    for row in rows:
        for field in ('measurement_sha256', 'tran_sha256'):
            digest = row[field]
            require(isinstance(digest, str) and len(digest) == 64
                    and all(c in '0123456789abcdef' for c in digest), 'Invalid case evidence SHA')
        require(isinstance(row['job_id'], str) and row['job_id'].isdigit(), 'Invalid Slurm task ID')
        require(math.isfinite(row['solver_seconds']) and row['solver_seconds'] > 0
                and type(row['peak_RSS_KiB']) is int and row['peak_RSS_KiB'] > 0
                and type(row['raw_bytes']) is int and row['raw_bytes'] > 0, 'Missing case resource evidence')
        for plane in PLANES:
            metrics = row['metrics'][plane]
            errors = metrics['symbol_errors']
            clipped = metrics['clipped_count']
            require(type(errors) is int and 0 <= errors <= DENOMINATOR
                    and metrics['sample_count'] == DENOMINATOR
                    and math.isclose(metrics['SER'], errors / DENOMINATOR, rel_tol=1e-12, abs_tol=1e-15)
                    and type(clipped) is int and 0 <= clipped <= DENOMINATOR + 16
                    and math.isfinite(metrics['prediction_RMSE_in_target_symbol_units']),
                    'Missing or inconsistent scoring evidence')
            require(not reject_clipping or clipped == 0, 'C1 clipping gate failed')


def check_c1(summary, review, summary_sha):
    require(summary['schema'] == 'pam4_c1_tt_noise_smoke_v1'
            and summary['status'] == 'c1_complete' and summary['noise_seed'] == 1001
            and summary['c0_training_selection'] == {'P_late': 0, 'N_late': 60},
            'C1 did not complete the approved seed and operating point')
    rows = summary['conditions']
    check_seed_rows(rows, reject_clipping=True)
    for label, base, corrected in PAIRS:
        delta = {p: rows[corrected]['metrics'][p]['symbol_errors'] - rows[base]['metrics'][p]['symbol_errors']
                 for p in PLANES}
        recorded_label = 'P_late_diagnostic' if base == 1 else label
        for plane in PLANES:
            result = summary['pairs'][recorded_label][plane]
            require(result['delta_errors'] == delta[plane]
                    and math.isclose(result['delta_SER'], delta[plane] / DENOMINATOR,
                                     rel_tol=1e-12, abs_tol=1e-15), 'C1 paired summary differs from counts')
        require(delta['primary'] < 0 and delta['secondary'] <= 0, f'C1 performance gate failed: {label}')
    require(set(review) == {'schema', 'c1_summary_sha256', 'reviewer', 'scoring_review', 'notes'}
            and review['schema'] == 'pam4_c1_scoring_review_v1' and review['c1_summary_sha256'] == summary_sha
            and review['scoring_review'] == 'pass' and isinstance(review['reviewer'], str)
            and review['reviewer'].strip() and isinstance(review['notes'], str) and review['notes'].strip(),
            'Missing hash-bound review of C1 scoring, timing and window anomalies')


def paired_comparison(seeds, rows_by_seed, *, infer=False):
    outcomes = defaultdict(dict)
    for label, base, corrected in PAIRS:
        for plane in PLANES:
            before = [rows_by_seed[seed][base]['metrics'][plane]['symbol_errors'] for seed in seeds]
            after = [rows_by_seed[seed][corrected]['metrics'][plane]['symbol_errors'] for seed in seeds]
            differences = [corrected_errors - base_errors for base_errors, corrected_errors in zip(before, after)]
            improved = sum(delta < 0 for delta in differences)
            worsened = sum(delta > 0 for delta in differences)
            non_ties = improved + worsened
            outcomes[label][plane] = dict(
                errors_before=sum(before), errors_after=sum(after), symbols_per_arm=len(seeds) * DENOMINATOR,
                delta_SER=sum(differences) / (len(seeds) * DENOMINATOR),
                seed_delta_errors={str(seed): delta for seed, delta in zip(seeds, differences)}, improved_seeds=improved,
                unchanged_seeds=len(seeds) - non_ties, worsened_seeds=worsened)
            if infer:
                outcomes[label][plane]['one_sided_paired_seed_sign_p'] = (
                    sum(math.comb(non_ties, count) for count in range(improved, non_ties + 1)) / 2**non_ties)
    return dict(outcomes)
