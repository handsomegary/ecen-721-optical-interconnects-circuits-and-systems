import unittest

import gm_switch64 as design


class Switch64Plan(unittest.TestCase):
    def test_four_dense_families_and_operation_count(self):
        cases=design.build_plan()['cases']
        self.assertEqual(len(cases),87)
        self.assertEqual(len({c['case_id'] for c in cases}),87)
        for profile in design.dense.PROFILES:
            ac=[c for c in cases[:48] if c['dense_profile']==profile]
            self.assertEqual(len(ac),12)
            self.assertTrue(all(c['process']=='ff' for c in ac))
            self.assertEqual({c['code'] for c in ac if c['group']!='baseline'},{-2,-1,0,1,2})

    def test_each_switch_uses_identical_stimulus_and_destination_reference(self):
        cases=design.build_plan()['cases']
        lookup={c['case_id']:c for c in cases}
        seen=set()
        for case in cases[48:]:
            self.assertEqual(case['code'],case['initial_code'])
            self.assertIn(case['initial_code'],design.prior.GRID)
            self.assertIn(case['final_code'],design.prior.GRID)
            if case['group']=='hold':
                self.assertEqual(case['initial_code'],case['final_code'])
                continue
            ref=lookup[case['reference_case_id']]
            self.assertEqual(ref['group'],'hold')
            self.assertEqual(ref['initial_code'],case['final_code'])
            self.assertTrue(all(case[k]==ref[k] for k in design.metrics.PAIR_FIELDS))
            seen.add((case['process'],case['initial_code'],case['final_code']))
        for corner in ('ss','tt','ff'):
            self.assertTrue(all((corner,start,finish) in seen for start,finish in design.CORE))
