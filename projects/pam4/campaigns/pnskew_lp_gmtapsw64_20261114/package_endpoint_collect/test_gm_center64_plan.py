import unittest

import gm_center64 as design


class Center64Plan(unittest.TestCase):
    def test_groups_and_balanced_reference(self):
        c = design.build_plan()['cases']
        self.assertEqual(len(c),188)
        self.assertEqual(len({x['case_id'] for x in c}),188)
        lut = {x['fixture_id']:x for x in c[::2]}
        self.assertEqual({x['code'] for x in c[:104] if x['group']=='control'},
                         {0,-2,2,*design.MID_CODES})
        self.assertEqual({x['code'] for x in c[104:124] if x['group']=='pilot'},set(design.CENTER_CODES))
        for p,n in zip(c[::2],c[1::2]):
            self.assertEqual((p['drive'],n['drive']),('p','n'))
            self.assertTrue(all(p[k]==n[k] for k in p if k not in ('case_id','drive')))
            if p['oracle_fixture_id']:
                ref = lut[p['oracle_fixture_id']]
                self.assertEqual([(a,w) for a,w in zip(p['anchors'],p['weights']) if w],
                                 list(zip(ref['anchors'],ref['weights'])))
                for field in ('process','resolution','code','bias_kind','vb1_V'):
                    self.assertEqual(ref[field],p[field])

    def test_split32_and_split64_equivalent_weight_codes(self):
        c = design.build_plan()['cases']
        lut = {x['fixture_id']:x for x in c[::2]}
        for case in c[::2]:
            ref = case['same_weight_32_fixture_id']
            if ref:
                self.assertEqual(case['code'],lut[ref]['code'])
                self.assertEqual([2*w for w in lut[ref]['weights']],case['weights'])
        with self.assertRaises(ValueError):
            design.distribution(1,32)

    def test_lowz_has_correct_unloaded_bias_and_no_power_double_count(self):
        plan = design.build_plan()['cases']
        case = plan[150]
        self.assertEqual(case['bias_kind'],'divider_lowz')
        deck,rails,_,dc,currents,_ = design.render(case,design.BASE.MODEL_TOKEN)
        self.assertIn('GMSKVRU (GMSKVDIVIN GMSKV1RAW) resistor r=375',deck)
        self.assertIn('GMSKVRD (GMSKV1RAW 0) resistor r=14125',deck)
        self.assertIn('GMSKVC1 (GMSKVBIAS 0) capacitor c=2p',deck)
        self.assertAlmostEqual(.58*14125/(375+14125),.565)
        self.assertEqual(rails['XVb:p'],.58)
        self.assertNotIn('GMSKV1:p',rails)
        self.assertIn('GMSKV1:p',currents)
        self.assertIn('GMSKVDIV:p',currents)
        self.assertIn('GMSKVBIAS',dc)
