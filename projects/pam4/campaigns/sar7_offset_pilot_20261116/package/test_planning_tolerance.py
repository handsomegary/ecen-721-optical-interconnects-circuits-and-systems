"""Keep cross-platform float tolerance separate from codes and receipt identity."""

import copy
import math
from unittest import TestCase

import planning


class PredictionToleranceTest(TestCase):
    def test_accepts_last_bit_float_difference(self):
        expected = dict(current_A=.00026069066274725524, codes=[64, 0, 127], source='sha-original')
        actual = copy.deepcopy(expected)
        actual['current_A'] = math.nextafter(actual['current_A'], math.inf)
        planning.tolerant_equal(actual, expected)

    def test_rejects_changed_codes_identity_and_material_numbers(self):
        expected = dict(current_A=.00026069066274725524, codes=[64, 0, 127], source='sha-original')
        for field, value in (('codes', [64., 0, 127]), ('codes', [65, 0, 127]),
                             ('source', 'sha-other'), ('current_A', .0003)):
            actual = copy.deepcopy(expected)
            actual[field] = value
            with self.assertRaises(ValueError):
                planning.tolerant_equal(actual, expected)
