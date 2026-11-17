"""Check full native circuit composition and separate bias-error metrics."""
import re
import unittest

import integration_summary as s
import lp_integrate as d


class Integration(unittest.TestCase):
    def test_all_six_native_conditions_have_distinct_paired_columns(self):
        cases=d.build_plan()['cases']
        self.assertEqual(len(cases),34)
        native = [c for c in cases if c['integration']=='native_direct']
        self.assertEqual({(c['process'],c['count_b'],c['drive']) for c in native},
                         {(p,cb,side) for p in ('ss','tt','ff') for cb in (0,2) for side in 'pn'})
        self.assertEqual(len({(s.key(c),c['drive']) for c in cases}),len(cases))

    def test_native_reference_is_direct_and_ota_uses_measured_ratio(self):
        c=d.build_plan()['cases'][18]
        deck,rails,_,_,currents,_=d.render(c,d.BASE.MODEL_TOKEN)
        self.assertIn('GMSQRR (GMSQRS 0) resistor r=1934',deck)
        for device,count in (('RPD',2),('RPM',2),('RND',1),('RNS',4),('RNM',10),('OP2',4),('ON2',1)):
            rows=re.findall(rf'(?m)^GMSQ{device}\d+ .*$',deck)
            self.assertEqual(len(rows),count)
            self.assertTrue(all(' l=120n ' in line for line in rows))
        self.assertIn('GFVDD:p',rails)
        self.assertNotIn('GMSRIREF:p',currents)
        for forbidden in ('GMSRIREF (','GMSQGDRV (','GMSRAMP (','GF_CTL','GMSQCAS0 ('):
            self.assertNotIn(forbidden,deck)

    def test_accurate_servo_can_track_off_nominal_reference(self):
        metrics=s.tracking([4.736,4.737],338.3e-6)
        self.assertTrue(metrics['servo_within_2_percent'])
        self.assertFalse(metrics['nominal_within_2_percent'])
        self.assertAlmostEqual(metrics['iref_error_fraction'],.08878,places=4)
        self.assertFalse(s.tracking([0,0],0)['servo_within_2_percent'])

    def test_diagnostic_uses_the_updated_integrated_deck(self):
        case=d.build_plan()['cases'][18]
        deck=d.diagnostic(case,d.BASE.MODEL_TOKEN,'stb')
        self.assertIn('GMSQRR (GMSQRS 0) resistor r=1934',deck)
        self.assertIn('GMSQOP23 (',deck)
        self.assertIn('probe=GMSQLOOP',deck)
        self.assertNotIn('acResponse ac',deck)
