"""Check identifiable transfer fits and sense-stage voltage units."""

from random import Random
from unittest import TestCase

import sar7_cml_rdeg_audit as audit


class AuditTest(TestCase):
    def test_identifiable_nine_parameter_cdac_fit(self):
        random = Random(760348)
        weights = (60.,30.,15.,7.5,3.75,1.875,.9375)
        rows = []
        for index in range(12):
            sampled = random.uniform(-1,1)
            for _ in range(7):
                bits = [random.randrange(2) for _ in weights]
                target = 61.25+64*.991*sampled-sum(w*b for w,b in zip(weights,bits,strict=True))
                rows.append((index,[1.,sampled,*bits],target))
        result = audit.old_audit.gain_record(rows)
        self.assertEqual(result['usable_points'],84)
        self.assertEqual(result['heldout_points'],84)
        self.assertAlmostEqual(result['offset_lsb'],61.25)
        self.assertAlmostEqual(result['sample_gain'],.991)
        self.assertAlmostEqual(result['full_code_span_lsb'],sum(weights))
        for actual,known in zip(result['weight_b6_to_b0_lsb'],weights,strict=True):
            self.assertAlmostEqual(actual,known)
        self.assertLess(result['heldout_rmse_lsb'],1e-9)

    def test_sense_affine_zero_crossing_units_and_small_signal_signs(self):
        # 0.0005 V output intercept with gain 0.5 crosses at -0.001 V = -1 LSB.
        points = [dict(held_diff_V=x,sense_diff_V=.5*x+.0005)
                  for x in (-.004,-.0002,0.,.0001,.004)]
        result = audit.sense_fit(points,.001)
        self.assertAlmostEqual(result['slope_V_per_V'],.5)
        self.assertAlmostEqual(result['output_intercept_V'],.0005)
        self.assertAlmostEqual(result['sense_stage_zero_crossing_input_V'],-.001)
        self.assertAlmostEqual(result['sense_stage_zero_crossing_input_LSB'],-1.)
        self.assertLess(result['fit_rmse_output_V'],1e-15)
        self.assertEqual(result['sign_all'],dict(points=5,same_sign=3,opposite_sign=1,zero_product=1))
        self.assertEqual(result['sign_abs_held_ge_0p25_LSB'],dict(points=2,same_sign=2,opposite_sign=0,zero_product=0))
        self.assertEqual(result['sign_abs_held_lt_0p25_LSB'],dict(points=3,same_sign=1,opposite_sign=1,zero_product=1))
        self.assertIn('not comparator offset',result['zero_crossing_label'])

    def test_reject_nonpositive_lsb(self):
        for lsb in (0.,-1.,float('nan')):
            with self.assertRaisesRegex(ValueError,'positive finite LSB'):
                audit.sense_fit([dict(held_diff_V=0.,sense_diff_V=0.)]*2,lsb)
