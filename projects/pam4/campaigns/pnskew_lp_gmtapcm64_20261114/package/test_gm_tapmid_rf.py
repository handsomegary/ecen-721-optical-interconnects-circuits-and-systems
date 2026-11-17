import unittest

import gm_tapmid_rf as mid
import gm_taptrim as trim
import gm_taptrim_rf


class MidBiasRenderer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model_root = trim.fine.endpoint.BASE.MODEL_TOKEN
        cls.cases = trim.build_plan()['cases']
        cls.nominal = next(case for case in cls.cases if case['group']=='pilot' and
                           case['code']==29 and case['vb1_V']==.570 and case['drive']=='p')

    def test_ideal_and_old_baselines_are_exact_passthrough(self):
        for case in (self.cases[0], self.nominal):
            self.assertEqual(mid.render(dict(case, bias_kind='ideal'), self.model_root),
                             trim.render(case, self.model_root))
        self.assertIs(mid.headroom, gm_taptrim_rf.headroom)

    def test_divider_only_replaces_vb1_and_saves_current_without_another_supply(self):
        reference, old_rails, old_ac, old_dc, old_currents, _ = (
            trim.render(self.nominal, self.model_root)
        )
        for kind, (upper, lower) in mid.DIVIDERS.items():
            with self.subTest(kind=kind):
                deck, rails, ac, dc, currents, diff = mid.render(
                    dict(self.nominal, bias_kind=kind), self.model_root
                )
                ideal_source = 'GMSKV1 (GMSKVBIAS 0) vsource dc=0.57'
                divider_lines = '\n'.join((
                    'GMSKVDIV (X_vb GMSKVDIVIN) vsource dc=0',
                    f'GMSKVRU (GMSKVDIVIN GMSKV1RAW) resistor r={upper}',
                    f'GMSKVRD (GMSKV1RAW 0) resistor r={lower}',
                    'GMSKV1 (GMSKV1RAW GMSKVBIAS) vsource dc=0',
                    'GMSKVC1 (GMSKVBIAS 0) capacitor c=2p',
                ))
                restored = deck.replace(divider_lines, ideal_source, 1).replace(' GMSKVDIV:p\n', '\n', 1)
                self.assertEqual(restored, reference)
                self.assertIn(divider_lines, deck)
                self.assertIn('XVb (X_vb 0) vsource dc=0.58\n', deck)
                self.assertIn('GMSKVBIAS', dc)
                self.assertIn('+GMSKV1 (GMSKV1RAW GMSKVBIAS) vsource dc=0', diff)
                self.assertEqual(set(old_rails)-set(rails), {'GMSKV1:p'})
                self.assertEqual(rails['XVb:p'], old_rails['XVb:p'])
                self.assertEqual(ac, old_ac)
                self.assertEqual(dc, old_dc)
                self.assertEqual(currents, old_currents+['GMSKVDIV:p', 'GMSKV1:p'])
                self.assertAlmostEqual(.58*lower/(upper+lower), .57)

    def test_rejects_unknown_bias_kind_and_wrong_reference(self):
        for case in (dict(self.nominal, bias_kind='unknown'),
                     dict(self.nominal, bias_kind='divider', vb1_V=.58),
                     dict(self.cases[0], bias_kind='divider')):
            with self.assertRaises(ValueError):
                mid.render(case, self.model_root)


if __name__=='__main__':
    unittest.main()
