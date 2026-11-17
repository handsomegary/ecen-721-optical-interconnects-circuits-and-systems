import unittest

import gm_tapmid as design


class MidbiasPlan(unittest.TestCase):
    def test_all_pairs_have_matching_same_bias_oracle(self):
        cases = design.build_plan()['cases']
        self.assertEqual((len(cases),len({c['case_id'] for c in cases})),(408,408))
        fixtures = {c['fixture_id']:c for c in cases[::2]}
        for p,n in zip(cases[::2],cases[1::2]):
            self.assertEqual((p['drive'],n['drive']),('p','n'))
            self.assertTrue(all(p[k]==n[k] for k in p if k not in ('case_id','drive')))
            if p['oracle_fixture_id']:
                ref = fixtures[p['oracle_fixture_id']]
                for field in ('process','bias_kind','code','vb1_V','injected_skew_ps'):
                    self.assertEqual(p[field],ref[field])
                self.assertEqual([(a,w) for a,w in zip(p['anchors'],p['weights']) if w],
                                 list(zip(ref['anchors'],ref['weights'])))
            if p['ideal_reference_fixture_id']:
                ref = fixtures[p['ideal_reference_fixture_id']]
                self.assertEqual(ref['bias_kind'],'ideal')
                self.assertEqual((ref['process'],ref['code']),(p['process'],p['code']))

    def test_required_and_optional_ranges(self):
        cases = design.build_plan()['cases']
        ss = {c['code'] for c in cases[:136] if c['group']=='sweep'}
        extra = {c['code'] for c in cases[296:] if c['group']=='extra'}
        self.assertEqual(len(ss),33)
        self.assertFalse(ss & extra)
        self.assertEqual(ss | extra,set(range(-30,31)))
        for process in ('tt','ff'):
            self.assertEqual({c['code'] for c in cases if c['process']==process and c['group']=='pvt'},
                             set(design.END_CODES))

    def test_ideal_ss_endpoint_decks_reproduce_trim32(self):
        cases = design.build_plan()['cases']
        old = design.trim.build_plan()['cases']
        for case in cases[:32]:
            if case['group'] not in ('sweep','oracle'):
                continue
            reference, = (c for c in old if c['vb1_V']==.570 and c['code']==case['code'] and
                          c['drive']==case['drive'] and
                          c['group']==('pilot' if case['group']=='sweep' else 'oracle'))
            model = design.BASE.MODEL_TOKEN
            self.assertEqual(design.render(case,model)[0],design.trim.render(reference,model)[0])
