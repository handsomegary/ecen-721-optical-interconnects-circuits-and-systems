"""Offline checks for the revised reference and OTA smoke deck."""
import re
import unittest

import ref_trim as t
from ref_summary import tt_bracket


class RefTrim(unittest.TestCase):
    def setUp(self):
        self.cases = t.build_plan()['cases']

    def deck(self,i):
        return t.render(self.cases[i],t.BASE.MODEL_TOKEN)[0]

    def test_bounded_first_group(self):
        self.assertEqual(len(self.cases),14)
        self.assertTrue(all(c['stage']=='smoke' for c in self.cases[:7]))
        self.assertTrue(all(c['stage']=='followup' for c in self.cases[7:]))
        self.assertEqual([c['ref_R_ohm'] for c in self.cases[:2]],[1800,2050])

    def test_series_cascode_keeps_pmos_direct(self):
        d = self.deck(2)
        self.assertIn('GMSQPALIGN (GMSQPD_OUT GMSQBN) vsource dc=0',d)
        self.assertIn('GMSQNALIGN (GMSR_REF GMSQTOP) vsource dc=0',d)
        self.assertIn('GMSQNCTRL (GMSQNCG 0 GMSQBN GMSQND_OUT) vcvs gain=1000',d)
        self.assertEqual(len(re.findall(r'(?m)^GMSQCAS\d+ \(GMSQTOP GMSQNCG GMSQND_OUT 0\)',d)),20)
        self.assertNotIn('acResponse ac',d)

    def test_symmetric_ota_keeps_negative_feedback_and_exact_reference(self):
        d = self.deck(3)
        for line in ('GMSQOL0 (GF_VDD GMSQO1) resistor r=39000',
                     'GMSQOL1 (GF_VDD GMSQOM) resistor r=39000',
                     'GMSQOID0 (GMSQO1 GMSR_D GMSQOS 0)',
                     'GMSQOIR0 (GMSQOM GMSR_REF GMSQOS 0)',
                     'GMSQOP20 (GMSR_BIAS GMSQO1 GF_VDD GF_VDD)',
                     'GMSRIREF (GMSR_REF 0) isource dc=0.000310714'):
            self.assertIn(line,d)
        self.assertNotIn('GMSQOPD',d)
        self.assertNotIn('GMSRIREF:p',d)
        self.assertTrue(all('l=120n ' in row for row in
                            re.findall(r'(?m)^GMSQ(?:OID|OIR|OP2|ON2)\d+ .+$',d)))

    def test_bracket_reports_estimate_only_with_target_enclosed(self):
        data = [dict(revision='r_bracket',process='tt',ref_R_ohm=1800,
                     measurement={'core_current_A':34e-6}),
                dict(revision='r_bracket',process='tt',ref_R_ohm=2050,
                     measurement={'core_current_A':30e-6})]
        self.assertIsNone(tt_bracket(data[:1])['interpolated_R_ohm'])
        self.assertTrue(1800<tt_bracket(data)['interpolated_R_ohm']<2050)
