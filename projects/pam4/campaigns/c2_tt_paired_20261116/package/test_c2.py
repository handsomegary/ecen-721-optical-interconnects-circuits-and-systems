"""Exercise C2 admission and paired statistics without any Spectre or Slurm jobs."""

from copy import deepcopy
import hashlib
from unittest import TestCase

from c2_gate import ARMS, DENOMINATOR, PLANES, SEEDS, check_c1, paired_comparison
import c2_run


def fixture():
    rows = []
    for index, ((profile, code), counts) in enumerate(zip(ARMS, ((9, 19), (16, 25), (5, 25), (17, 32), (6, 10)))):
        rows.append(dict(
            profile=profile, code=code, job_id=str(100 + index), measurement_sha256='b' * 64,
            tran_sha256='c' * 64, solver_seconds=5300., peak_RSS_KiB=340000, raw_bytes=139460608,
            metrics={p: dict(symbol_errors=count, sample_count=DENOMINATOR, SER=count / DENOMINATOR,
                             clipped_count=0, prediction_RMSE_in_target_symbol_units=.23)
                     for p, count in zip(PLANES, counts)}))
    summary = dict(schema='pam4_c1_tt_noise_smoke_v1', status='c1_complete', noise_seed=1001,
                   c0_training_selection={'P_late': 0, 'N_late': 60}, conditions=rows,
                   pairs={name: {p: dict(delta_errors=count, delta_SER=count / DENOMINATOR)
                                 for p, count in zip(PLANES, counts)}
                          for name, counts in (('P_late_diagnostic', (-11, 0)), ('N_late_frozen_selection', (-11, -22)))})
    review = dict(schema='pam4_c1_scoring_review_v1', c1_summary_sha256='a' * 64, reviewer='Offline test',
                  scoring_review='pass', notes='Fixture: replace with C1 evidence')
    return summary, review


class C1AdmissionTests(TestCase):
    def test_accept_primary_improvements_and_equal_secondary(self):
        summary, review = fixture()
        check_c1(summary, review, 'a' * 64)

    def test_decline_incomplete_clipping_and_stale_receipt(self):
        summary, review = fixture()
        with self.assertRaisesRegex(ValueError, 'hash-bound review'):
            check_c1(summary, review, 'f' * 64)
        missing = deepcopy(summary)
        missing['conditions'].pop()
        with self.assertRaisesRegex(ValueError, 'five cases'):
            check_c1(missing, review, 'a' * 64)
        summary['conditions'][0]['metrics']['primary']['clipped_count'] = 1
        with self.assertRaisesRegex(ValueError, 'clipping'):
            check_c1(summary, review, 'a' * 64)

    def test_recompute_pairs_and_decline_secondary_regression(self):
        summary, review = fixture()
        metric = summary['conditions'][2]['metrics']['secondary']
        metric.update(symbol_errors=26, SER=26 / DENOMINATOR)
        with self.assertRaisesRegex(ValueError, 'summary differs'):
            check_c1(summary, review, 'a' * 64)
        summary['pairs']['P_late_diagnostic']['secondary'].update(delta_errors=1, delta_SER=1 / DENOMINATOR)
        with self.assertRaisesRegex(ValueError, 'performance gate failed'):
            check_c1(summary, review, 'a' * 64)

    def test_decline_neutral_primary(self):
        summary, review = fixture()
        metric = summary['conditions'][4]['metrics']['primary']
        metric.update(symbol_errors=17, SER=17 / DENOMINATOR)
        summary['pairs']['N_late_frozen_selection']['primary'].update(delta_errors=0, delta_SER=0.)
        with self.assertRaisesRegex(ValueError, 'performance gate failed'):
            check_c1(summary, review, 'a' * 64)


class NoisePlanTests(TestCase):
    def test_actual_pinned_decks_change_only_noise_seed(self):
        base, fresh = c2_run.plan()
        self.assertEqual(len(fresh), 95)
        self.assertEqual(len({meta['case_id'] for _, meta in fresh}), 95)
        self.assertEqual(len({meta['deck_sha256'] for _, meta in fresh}), 95)
        for offset, (deck, meta) in enumerate(fresh):
            original = base[offset % 5]
            seed = SEEDS[1 + offset // 5]
            self.assertEqual(meta['noise']['seed'], seed)
            self.assertEqual(meta['condition'], original['condition'])
            self.assertEqual(meta['code'], original['code'])
            self.assertEqual(meta['specimen'], original['specimen'])
            normalized = deck.replace(f' noiseseed={seed}'.encode('ascii'), b' noiseseed=1001')
            self.assertEqual(hashlib.sha256(normalized).hexdigest(), original['deck_sha256'])

    def test_pilot_reuse_is_descriptive_only(self):
        summary, _ = fixture()
        rows = {seed: summary['conditions'] for seed in SEEDS}
        pilot_included = paired_comparison(SEEDS, rows)['P_late_fixed_code_diagnostic']['primary']
        self.assertEqual(pilot_included['symbols_per_arm'], 20 * DENOMINATOR)
        self.assertNotIn('one_sided_paired_seed_sign_p', pilot_included)
        fresh_only = paired_comparison(SEEDS[1:], rows, infer=True)['P_late_fixed_code_diagnostic']['primary']
        self.assertEqual(fresh_only['symbols_per_arm'], 19 * DENOMINATOR)
        self.assertEqual(fresh_only['one_sided_paired_seed_sign_p'], 2**-19)
        self.assertNotIn('1001', fresh_only['seed_delta_errors'])
