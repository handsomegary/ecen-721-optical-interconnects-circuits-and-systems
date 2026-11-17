"""Check the linear transfer calculation against known resolved weights."""

from random import Random
from unittest import TestCase

import sar7_cdac_audit as audit


class AuditTest(TestCase):
    def test_fit_and_held_out_conversions(self):
        random = Random(431)
        known = (64.,32.,16.,8.,4.,2.,1.)
        rows = []
        for index in range(12):
            x = random.uniform(-1,1)
            for _ in range(7):
                bits = [random.randrange(2) for b in known]
                ideal = 63.5+64*x-sum(w*b for w,b in zip(known,bits,strict=True))
                rows.append((index,[1.,x,*bits],ideal))
        result = audit.gain_record(rows)
        self.assertEqual(result['heldout_points'],84)
        self.assertAlmostEqual(result['sample_gain'],1.)
        self.assertTrue(all(abs(a-b)<1e-9 for a,b in zip(result['weight_b6_to_b0_lsb'],known,strict=True)))
        self.assertLess(result['heldout_rmse_lsb'],1e-9)

    def test_reject_unidentifiable_words(self):
        with self.assertRaisesRegex(ValueError,'identify every weight'):
            audit.coefficients([(i,[1.,0.,0,0,0,0,0,0,0],0.) for i in range(12)])
