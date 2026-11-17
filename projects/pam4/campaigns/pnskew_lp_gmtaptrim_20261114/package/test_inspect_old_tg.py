import cmath
import math
import unittest

import inspect_old_tg


class NotchDiagnostic(unittest.TestCase):
    def test_balanced_branches_cancel_near_nyquist(self):
        grid = [f*1e9 for f in range(40,91)]
        delay = .5/56e9
        matrix = [(cmath.exp(1j*math.pi*f*delay),0j,0j,cmath.exp(-1j*math.pi*f*delay))
                  for f in grid]
        compare = inspect_old_tg.analyze(grid,matrix,0.)
        self.assertEqual(compare['minimum']['frequency_Hz'],56e9)
        self.assertGreater(compare['minimum']['branch_p_abs'],.99)
        compensated = inspect_old_tg.analyze(grid,matrix,delay*1e12)
        self.assertAlmostEqual(compensated['at_56GHz']['Hdd_V_per_V'],1.)
