"""Check that hardware control words change enables without rewiring LP14."""

import re
import unittest

import global_rf
import lp_integrate as integrated


class GlobalRFTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = next(c for c in integrated.build_plan()['cases']
                        if c['integration']=='native_direct' and c['process']=='tt'
                        and c['drive']=='p' and c['count_b']==0)
        cls.case = dict(cls.case,variant_name='global',tap_a_p=10,tap_a_n=12,
                        tap_b_p=11,tap_b_n=11,switch_mode='native',tg_parallel=2,
                        match_load=True,coil_Q56=15,coil_SRF_GHz=150)

    def render(self, **updates):
        return global_rf.render(dict(self.case,**updates),global_rf.BASE.MODEL_TOKEN)

    def test_native_words_preserve_all_wiring(self):
        first = self.render()[0]
        second = self.render(tap_a_p=12,tap_a_n=10,count_b=7)[0]
        voltage_controls = re.compile(r'(?m)^(GLSEL\d{2}V|GMS[AB]VE\d) (.*) dc=\S+$')
        normalize = lambda text:voltage_controls.sub(r'\1 \2 dc=<control>',text)
        self.assertNotEqual(first,second)
        self.assertEqual(normalize(first),normalize(second))
        for deck,b_count in ((first,0),(second,7)):
            on = re.findall(r'(?m)^GMS([AB])VE\d [^\n]+ dc=0\.9$',deck)
            self.assertEqual((on.count('A'),on.count('B')),(8-b_count,b_count))
            self.assertEqual(len(re.findall(r'(?m)^GL[AB][PM]\d{2}U\d[PN] ',deck)),88)
            self.assertEqual(len(re.findall(r'(?m)^GL[PM]S\d{2}C ',deck)),32)
        self.assertIn('GLAM12U0N (GLMT12 GLSEL10N GMSAML 0)',first)
        self.assertIn('GLAP10U0N (GLPT10 GLSEL10N GMSAPL 0)',first)

    def test_oracle_preserves_matched_through_lines_and_original_saves(self):
        native,_,ac,_,_,_ = self.render()
        ideal,_,oracle_ac,_,_,_ = self.render(switch_mode='ideal')
        line_rows = lambda deck:re.findall(r'(?m)^GL[PM][^\n]+$',deck)
        self.assertEqual(line_rows(native),line_rows(ideal))
        self.assertEqual(ac,oracle_ac)
        self.assertIn('GLAPSHORT (GLPT10 GMSAPL) vsource dc=0',ideal)
        self.assertIn('GLAMSHORT (GLMT12 GMSAML) vsource dc=0',ideal)
        self.assertIn('GLPRT (GLPT16 X_cm) resistor r=50',native)
        self.assertIn('GLPMATCH (GLPI X_cm) resistor r=50',native)
        self.assertIn('GMSHPLPK (GMSHPLP GMSHPLN) inductor l=120p',native)
        self.assertNotIn('GMSAPRT ',native)
        self.assertNotIn('GMSAPI',ac)
        self.assertIn('GLPDRV:p',ac)

    def test_invalid_hardware_word_is_rejected(self):
        for updates in (dict(tap_a_p=11,tap_a_n=11),dict(tap_a_n=10),
                        dict(tap_b_p=15,tap_b_n=7),dict(count_b=9),dict(tg_parallel=3)):
            with self.subTest(updates=updates),self.assertRaises(ValueError):
                self.render(**updates)


if __name__=='__main__':
    unittest.main()
