import unittest

import gm_taptrim as design


class Trim32Plan(unittest.TestCase):
    def test_same_state_reference_and_bias_families(self):
        cases = design.build_plan()['cases']
        self.assertEqual(len(cases),166)
        self.assertEqual(len({c['case_id'] for c in cases}),166)
        lookup = {c['fixture_id']:c for c in cases[::2]}
        for p,n in zip(cases[::2],cases[1::2]):
            self.assertEqual((p['drive'],n['drive']),('p','n'))
            self.assertTrue(all(p[k]==n[k] for k in p if k not in ('case_id','drive')))
            if p['group']!='pilot':
                continue
            oracle = lookup[p['oracle_fixture_id']]
            active = [(tap,w) for tap,w in zip(p['anchors'],p['weights']) if w]
            self.assertEqual(active,list(zip(oracle['anchors'],oracle['weights'])))
            self.assertEqual((p['vb1_V'],p['injected_skew_ps']),
                             (oracle['vb1_V'],oracle['injected_skew_ps']))
            self.assertIn(p['reference_current_fixture_id'],lookup)
            self.assertIn(p['target_current_fixture_id'],lookup)
        for bias in design.BIAS_MV:
            self.assertEqual({c['code'] for c in cases if c['group']=='pilot'
                              and c['vb1_V']==bias/1000},set(design.CODES))
        self.assertEqual({c['vb1_V'] for c in cases[:82] if c['group']=='pilot'},{.58,.57})

    def test_legacy_decks_reproduce_prior_bias_and_topology(self):
        cases = design.build_plan()['cases']
        historical = design.fine.build_plan()['cases']
        token = design.fine.endpoint.BASE.MODEL_TOKEN
        for i,j in ((0,0),(2,2),(4,4),(6,6),(8,8),(10,10)):
            self.assertEqual(design.render(cases[i],token)[0],design.fine.render(historical[j],token)[0])

    def test_code_grid_brackets_new_local_state(self):
        self.assertEqual(design.distribution(-30,32),(30,2,0))
        self.assertEqual(design.distribution(-29,32),(29,3,0))
        self.assertEqual(design.distribution(-28,32),(28,4,0))
        self.assertEqual(design.distribution(29,32),(0,3,29))
        with self.assertRaises(ValueError):
            design.distribution(29,16)
