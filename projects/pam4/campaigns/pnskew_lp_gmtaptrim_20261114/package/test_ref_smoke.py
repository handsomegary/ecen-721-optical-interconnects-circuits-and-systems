"""Offline checks for isolated Iref and fixed-current OTA smoke."""
import re
import unittest

import ref_smoke as design


class RefSmoke(unittest.TestCase):
    def setUp(self):
        self.plan = design.build_plan()['cases']

    def deck(self,i):
        return design.render(self.plan[i],design.BASE.MODEL_TOKEN)[0]

    def test_ota_reuses_previous_true_fixed_reference_cases(self):
        original = design.phy.build_plan()['cases']
        for i,case in enumerate(self.plan[:4]):
            self.assertEqual(self.deck(i),design.phy.render(original[case['old_index']],design.BASE.MODEL_TOKEN)[0])
            self.assertRegex(self.deck(i),r'GMSRIREF \(GMSR_REF 0\) isource dc=0\.000310714')
            self.assertNotIn('GMSRIREF:p',self.deck(i))

    def test_dc_scope_and_matching_probe_polarity(self):
        normal,matched = self.deck(4),self.deck(5)
        self.assertNotIn('acResponse ac',matched)
        self.assertNotIn('XM2p0',matched)
        self.assertIn('GMSQPALIGN (GMSQPD_OUT GMSQBN GMSQBP GMSQBN) vcvs gain=1',matched)
        self.assertIn('GMSQNALIGN (GMSR_REF GMSQND_OUT GMSR_REF GMSQBN) vcvs gain=1',matched)
        self.assertIn('GMSQPALIGN (GMSQPD_OUT GMSQBN) vsource dc=0',normal)
        self.assertIn('GMSQNALIGN (GMSR_REF GMSQND_OUT) vsource dc=0',normal)

    def test_long_channels_and_r_bracket(self):
        for i in range(4,len(self.plan)):
            case = self.plan[i]
            deck = self.deck(i)
            devices = re.findall(r'(?m)^GMSQ(?:RPD|RPM|RND|RNS|RNM)\d+ .*$',deck)
            self.assertEqual(len(devices),19)
            self.assertTrue(all(f' l={case["length_nm"]}n ' in line for line in devices))
            self.assertIn(f'GMSQRR (GMSQRS 0) resistor r={case["ref_R_ohm"]}',deck)
        self.assertEqual({c['ref_R_ohm'] for c in self.plan if c['process']=='tt' and c['kind']=='dc'},
                         {1300,1600,2200})
