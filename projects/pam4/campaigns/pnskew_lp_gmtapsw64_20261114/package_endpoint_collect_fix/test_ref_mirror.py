"""Offline checks for PMOS pass headroom and mirror-loaded OTA sizing."""
import re
import unittest

import ref_mirror as m


class RefMirror(unittest.TestCase):
    def setUp(self):
        self.cases = m.build_plan()['cases']

    def deck(self,i):
        return m.render(self.cases[i],m.BASE.MODEL_TOKEN)[0]

    def test_first_six_compare_identical_reference_loads_at_all_corners(self):
        for i,proc in enumerate(('ss','tt','ff')):
            a,b = self.cases[i],self.cases[i+3]
            self.assertEqual(a['process'],proc)
            self.assertEqual(a['process'],b['process'])
            self.assertEqual(a['ref_R_ohm'],b['ref_R_ohm'])
            self.assertEqual(a['ref_R_ohm'],1934)
            for deck in (self.deck(i),self.deck(i+3)):
                self.assertIn('GMSRRREF (GF_VDD GMSR_REF) resistor r=462',deck)
                self.assertIn('GMSQPALIGN (GMSQPD_OUT GMSQBN) vsource dc=0',deck)

    def test_pass_controller_polarity_and_supply_limits(self):
        d = self.deck(3)
        self.assertIn('1000*v(GMSQND_OUT,GMSQBN),0.05),v(GF_VDD)-0.05)',d)
        self.assertEqual(len(re.findall(
            r'(?m)^GMSQCAS\d+ \(GMSQND_OUT GMSQNCG GMSQTOP GF_VDD\) pmos_lvt l=120n ',d)),20)
        self.assertIn('GMSQNALIGN (GMSR_REF GMSQTOP) vsource dc=0',d)
        self.assertNotIn('GMSQGDRV:p',d)

    def test_mirror_ota_matched_lengths_and_current_ratios(self):
        for i,n in ((6,4),(13,5)):
            d = self.deck(i)
            for name,count in (('OPD',2),('OPM',2),('OP2',n),('ON2',1),('OT',1),('OBD',1)):
                rows = re.findall(rf'(?m)^GMSQ{name}\d+ .+$',d)
                self.assertEqual(len(rows),count)
                self.assertTrue(all(' l=120n ' in row for row in rows))
            self.assertIn('GMSQOP20 (GMSR_BIAS GMSQO1 GF_VDD GF_VDD)',d)
            self.assertIn('GMSRIREF (GMSR_REF 0) isource dc=0.000310714',d)
            self.assertNotIn('GMSRIREF:p',d)
