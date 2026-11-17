"""Check lag recovery, fit isolation, and frozen scoring on a new symbol stream."""

import os
from pathlib import Path
import sys
import unittest


OUTPUTS = Path(__file__).resolve().parent.parent
for variable, sibling in (
    ('PAM4_C0_ORIGINAL_PACKAGE', 'PAM4_PNSKEW_LP_GMTAP_C0_RUN_20261115'),
    ('PAM4_C0_ALIGN_PACKAGE', 'PAM4_PNSKEW_LP_GMTAP_C0_ALIGN_20261115'),
):
    sys.path.insert(0, os.environ.get(variable, str(OUTPUTS/sibling)))

import c0_formal_score as score


def samples(stimulus, reverse_scored_training_block=False):
    symbols = score.design.symbols(stimulus)
    data = {}
    for plane, sign, extra_ui in (('primary', 1, .4), ('secondary', -1, 4.)):
        once = []
        for index, symbol in enumerate(symbols, start=3):
            value = sign * .012 * (symbol - 1.5)
            if reverse_scored_training_block and index >= score.VERIFY[0] + 3:
                value = -value
            time = score.design.T0 + (index + extra_ui) * score.review.UI
            once.append((index, value, time, time, index % 8))
        data[plane] = once
    return data


class FormalScore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = score.aligned.scoring_functions()
        cls.frozen = score.review.pinned_r5()

    def measure(self, stimulus, records, calibration=None, phase=1, condition='zero', code=0):
        meta = dict(stimulus=stimulus, condition=condition, code=code, phase=phase,
                    case_id=f'fixture_{stimulus}_{condition}_{code}_{phase}')
        return score.score_records(meta, records, calibration, self.functions, self.frozen)

    def test_phase_score_does_not_fit_its_verification_block(self):
        normal = self.measure('training', samples('training'))
        reversed_block = self.measure('training', samples('training', True))
        self.assertEqual(normal['calibration'], reversed_block['calibration'])
        for plane in score.aligned.PLANES:
            fit = normal['calibration']['selections'][plane]
            self.assertEqual(fit['lag'], 3)
            self.assertTrue(fit['correlation_sign_matches_circuit'])
            self.assertLess(fit['last_train_read_s'], normal['capture_window'][plane]['first_read_s'])
            self.assertEqual(normal['metrics'][plane]['FFE_validation_output_count'], 176)
            self.assertEqual(normal['metrics'][plane]['ideal7bit_ADC_then_FFE']['symbol_errors'], 0)
            self.assertEqual(reversed_block['metrics'][plane]['ideal7bit_ADC_then_FFE']['symbol_errors'], 176)

    def test_code_selection_and_payload_apply_the_same_frozen_receiver(self):
        trial = self.measure('training', samples('training'))
        calibration = trial['calibration']
        code = self.measure('training', samples('training'), calibration, condition='b', code=60)
        holdout = self.measure('payload', samples('payload'), calibration, condition='b', code=60)
        self.assertEqual(code['metrics'], trial['metrics'])
        self.assertNotIn('calibration', holdout)
        self.assertEqual(holdout['capture_window']['tx_symbol_indices'], [128, 640])
        self.assertNotEqual(holdout['capture_window']['symbol_sha256'], trial['capture_window']['symbol_sha256'])
        for plane in score.aligned.PLANES:
            self.assertEqual(holdout['metrics'][plane]['FFE_validation_output_count'], 496)
            self.assertEqual(holdout['metrics'][plane]['ideal7bit_ADC_then_FFE']['symbol_errors'], 0)
            self.assertFalse(holdout['metrics'][plane]['validation_fitting_performed'])
        with self.assertRaisesRegex(ValueError, 'actual phase or fit window'):
            self.measure('payload', samples('payload'), calibration, phase=0)
        with self.assertRaisesRegex(ValueError, 'zero-skew code-0 training'):
            self.measure('payload', samples('payload'))


if __name__ == '__main__':
    unittest.main()
