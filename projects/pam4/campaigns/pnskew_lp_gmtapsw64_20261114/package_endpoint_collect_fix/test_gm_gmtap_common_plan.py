import unittest

import gm_gmtap_common as design


class Common64Plan(unittest.TestCase):
    def test_same_hardware_candidate_and_minimal_load_reference(self):
        cases=design.build_plan()['cases']
        self.assertEqual(len(cases),1228)
        fixtures={c['fixture_id']:c for c in cases[::2]}
        self.assertEqual(len(fixtures),614)
        for p,n in zip(cases[::2],cases[1::2]):
            self.assertEqual((p['drive'],n['drive']),('p','n'))
            self.assertTrue(all(p[k]==n[k] for k in p if k not in ('case_id','drive')))
            if p['oracle_fixture_id']:
                ref=fixtures[p['oracle_fixture_id']]
                for field in ('process','code','bias_kind','vb1_V','resolution','tail_variant'):
                    self.assertEqual(p[field],ref[field])
                self.assertEqual([(a,w) for a,w in zip(p['anchors'],p['weights']) if w],
                                 list(zip(ref['anchors'],ref['weights'])))
            if p['ideal_reference_fixture_id']:
                ideal=fixtures[p['ideal_reference_fixture_id']]
                self.assertEqual((p['process'],p['code'],p['weights']),
                                 (ideal['process'],ideal['code'],ideal['weights']))
                self.assertEqual(ideal['bias_kind'],'ideal')

    def test_ranges_cover_requested_missing_transition_and_endpoint(self):
        cases=design.build_plan()['cases']
        self.assertEqual({c['code'] for c in cases[:160] if c['group']=='ideal'},set(design.SS_IDEAL))
        self.assertTrue({q for n in (*range(3,12),*range(56,61)) for q in (-n,n)}<=set(design.SS_IDEAL))
        for corner in design.CORNERS:
            self.assertEqual({c['code'] for c in cases[:964] if c['process']==corner and
                              c['group'] in ('divider','codes')},set(design.GRID))
            self.assertEqual({c['code'] for c in cases[964:] if c['process']==corner and
                              c['group']=='extra'},set(design.EXTRA_GRID))

    def test_physical_word_and_architecture(self):
        words=design.word_table()['candidate_words']
        masks=set()
        for w in words:
            bw=w['weights_by_bank']
            self.assertEqual(sum(bw.values()),64)
            for tap,cells in w['enabled_tail_indices_by_bank'].items():
                self.assertEqual(bw[tap],sum(4 if i<15 else 2 if i==15 else 1 for i in cells))
            masks.add(tuple(w['enable_mask_by_bank'].values()))
        self.assertEqual(len(masks),77)
        cases=design.build_plan()['cases']
        deck,rails,_,_,currents,_=design.prior.render(cases[306],design.BASE.MODEL_TOKEN)
        self.assertIn('resistor r=14125',deck)
        self.assertIn('XVb (X_vb 0) vsource dc=0.58',deck)
        self.assertNotIn('GMSKV1:p',rails)
        self.assertIn('GMSKVDIV:p',currents)
