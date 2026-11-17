import unittest

from global_codes import codes, decode, seam_aliases
from select_global_codes import CORNERS, select


def fixtures():
    rows = []
    for row in (*codes(),*seam_aliases()):
        gain = .125*(row['logical_code']-40)
        rows.append(dict(row,metrics_per_corner={c:{'delay_ps':gain+i*.02,'gain_power_pass':True}
                                                for i,c in enumerate(CORNERS)}))
    return rows


class SelectGlobalCodes(unittest.TestCase):
    def test_full_path_prefers_canonical(self):
        outcome = select(fixtures())
        self.assertEqual(outcome['status'],'verified_map')
        self.assertEqual(len(outcome['selected']),81)
        self.assertEqual(outcome['zero_code']['hardware_word'],decode(40)['hardware_word'])
        self.assertEqual(outcome['endpoints_by_corner']['tt']['min_delay_ps'],-5.)

    def test_alias_can_replace_bad_canonical_and_skip_overlap(self):
        rows = fixtures()
        rows[8]['metrics_per_corner']['ff']['delay_ps'] = -4.25
        rows[16]['metrics_per_corner']['tt']['gain_power_pass'] = False
        outcome = select(rows)
        self.assertTrue(outcome['global_code_map_verified'])
        self.assertEqual(len(outcome['selected']),81)
        self.assertNotEqual(outcome['selected'][8]['hardware_word'],decode(8)['hardware_word'])
        self.assertNotEqual(outcome['selected'][16]['hardware_word'],decode(16)['hardware_word'])

    def test_incomplete_result_blocks_global_publication(self):
        outcome = select(fixtures()[:-1])
        self.assertEqual(outcome['status'],'blocked_incomplete')
        self.assertEqual(len(outcome['missing_metrics']),3)
        self.assertEqual(outcome['selected'],[])

    def test_local_steps_cannot_hide_lost_range_or_broken_gradient(self):
        rows = fixtures()
        for row in rows:
            row['metrics_per_corner']['ff']['delay_ps'] *= .85
        self.assertEqual(select(rows)['status'],'blocked_no_common_monotone_path')
        rows = fixtures()
        for row in rows:
            if 46<=row['logical_code']<=55:
                row['metrics_per_corner']['tt']['gain_power_pass'] = False
        self.assertEqual(select(rows)['status'],'blocked_no_common_monotone_path')


if __name__=='__main__':
    unittest.main()
