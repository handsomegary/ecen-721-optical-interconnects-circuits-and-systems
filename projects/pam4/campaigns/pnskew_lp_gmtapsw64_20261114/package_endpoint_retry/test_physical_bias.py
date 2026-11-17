"""Offline physical bias circuit and diagnostic invariants."""
import re
import unittest

import physical_bias as d
from physical_summary import key


class PhysicalBias(unittest.TestCase):
    def setUp(self):
        self.cases = d.build_plan()['cases']
        self.token = d.old.DRIVE.gm.original.base.MODEL_TOKEN

    def find(self,hardware):
        return next(c for c in self.cases if c['hardware']==hardware and c['stage']=='core')

    def test_unique_pairs(self):
        self.assertEqual(len(self.cases),len({(key(c),c['drive']) for c in self.cases}))
        self.assertEqual(len(self.cases),102)

    def test_integrated_removes_ideal_bias_elements_and_unused_control(self):
        deck,rails,_,_,currents,_ = d.render(self.find('native_both'),self.token)
        for token in ('GMSRIREF','GMSRAMP','GFVCTL','GF_CTL','GMSHPVFG','GMSHMVFG'):
            self.assertNotIn(token,deck)
        self.assertIn('GFVDD:p',rails)
        self.assertNotIn('GMSRIREF:p',currents)
        self.assertEqual(len(re.findall(r'(?m)^GMSQRNM\d+ ',deck)),10)
        self.assertEqual(len(re.findall(r'(?m)^GMSQRNS\d+ ',deck)),4)

    def test_ablation_keeps_only_appropriate_ideal_element(self):
        ref = d.render(self.find('native_ref'),self.token)[0]
        ota = d.render(self.find('native_ota'),self.token)[0]
        self.assertIn('GMSRAMP ',ref)
        self.assertNotIn('GMSRIREF ',ref)
        self.assertNotIn('GMSRAMP ',ota)
        self.assertIn('GMSRIREF ',ota)

    def test_ota_polarity_and_filter(self):
        deck = d.render(self.find('native_both'),self.token)[0]
        for line in ('GMSQOID0 (GMSQO1 GMSR_D GMSQOS 0)',
                     'GMSQOIR0 (GMSQOM GMSR_REF GMSQOS 0)',
                     'GMSQOPD0 (GMSQOM GMSQOM GF_VDD GF_VDD)',
                     'GMSQOP20 (GMSR_BIAS GMSQO1 GF_VDD GF_VDD)',
                     'GMSRCS0 (GMSR_D GMSR_BIAS 0 0)',
                     'GMSHPGB (GMSHPFG GMSQ_RF) resistor r=10K',
                     'GMSQORF (GMSR_BIAS GMSQ_RF) resistor r=100K'):
            self.assertIn(line,deck)

    def test_diagnostics_separate_from_rf_ac(self):
        case = self.find('native_both')
        stb = d.diagnostic(case,self.token,'stb')
        startup = d.diagnostic(case,self.token,'startup_slow')
        self.assertIn('GMSQLOOP (GMSR_BIAS GMSQ_REPG) iprobe',stb)
        self.assertIn('probe=GMSQLOOP',stb)
        self.assertIn('type=pwl wave=[0 0 100u 0.81]',startup)
        self.assertIn('biasStartup tran stop=500u',startup)
        for deck in (stb,startup):
            self.assertNotIn('acResponse ac',deck)
            self.assertNotIn('noiseResponse (',deck)
