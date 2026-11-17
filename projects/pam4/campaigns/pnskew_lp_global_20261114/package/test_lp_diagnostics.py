"""Verify the startup rails, loop cuts, and finite-swing fixture."""
import re
import unittest

import lp_diagnostics as d


class Diagnostics(unittest.TestCase):
    def setUp(self):
        self.cases = d.build_plan()['cases']

    def deck(self,i):
        return d.render(self.cases[i],d.BASE.MODEL_TOKEN)[0]

    def test_restart_ramps_all_enabled_rails_and_drops_to_zero(self):
        deck=self.deck(2)
        ramps=re.findall(r'(?m)^\w+ \([^\n]+\) vsource dc=0 type=pwl wave=\[([^\n]+)\]$',deck)
        self.assertEqual(len(ramps),12)
        self.assertTrue(all('520u 0 570u 0 571u ' in r for r in ramps))
        self.assertIn('GMSBVE0 (GMSBEN0 0) vsource dc=0',deck)

    def test_stb_moves_only_the_selected_loop_gate(self):
        replica,beta=self.deck(11),self.deck(12)
        self.assertIn('GMSRCS0 (GMSR_D GMSQ_REPG 0 0)',replica)
        self.assertIn('probe=GMSQLOOP',replica)
        self.assertIn('GMSRCS0 (GMSR_D GMSR_BIAS 0 0)',beta)
        self.assertEqual(len(re.findall(r'(?m)^GMSQRPM\d+ \(GMSQBN GMSQPB_GATE ',beta)),2)
        self.assertIn('GMSQRPD0 (GMSQBP GMSQBP GF_VDD GF_VDD)',beta)
        self.assertIn('probe=GMSQREFLOOP',beta)
        self.assertNotIn('GMSQREFLOOP:p',beta)

    def test_swing_keeps_tail_bias_and_visits_all_pam4_transitions(self):
        self.assertEqual(len(set(zip(d.WORD,d.WORD[1:]))),16)
        full,half=self.deck(21),self.deck(22)
        for deck in (full,half):
            self.assertIn('XT2p0 (X_s2_p X_vb 0 0)',deck)
            self.assertIn('XT2m7:region',deck)
            self.assertIn('XSN7p (X_h7p X_ck7 X_o_p 0)',deck)
            self.assertIn('XSP7p (X_h7p X_kb7 X_o_p X_vdd)',deck)
            self.assertIn('XTCC2p (TXC_p X_cm) capacitor c=85.26157665637249f',deck)
            self.assertNotIn('acResponse ac',deck)
        self.assertIn('-0.1 ',full)
        self.assertIn('-0.05 ',half)
