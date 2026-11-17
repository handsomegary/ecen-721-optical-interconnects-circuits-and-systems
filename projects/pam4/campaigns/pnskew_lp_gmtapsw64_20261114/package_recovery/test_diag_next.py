"""Offline tests for the extended beta and unchanged diagnostics."""
import unittest

import diag_next as d
from pvt.reference.psf_ascii import PsfData


class ExtendedDiagnostics(unittest.TestCase):
    def test_beta_only_extends_stb_and_pending_startup_xt2_are_preserved(self):
        cases=d.build_plan()['cases']
        old=d.prior.build_plan()['cases']
        self.assertEqual(len(cases),22)
        for c in cases:
            deck=d.render(c,d.BASE.MODEL_TOKEN)[0]
            prev=d.prior.render(old[c['prior_index']],d.BASE.MODEL_TOKEN)[0]
            if c['stage']=='beta20':
                self.assertEqual(deck,prev.replace('betaSTB stb start=1 stop=1G dec=50',
                                                  'betaSTB stb start=1 stop=20G dec=100'))
            elif c['stage']=='kick':
                self.assertNotIn('GMSQREFLOOP (',deck)
                self.assertIn('GMSQKTEST (GMSR_REF 0) isource',deck)
                self.assertNotIn('GMSQKTEST:p',deck)
                self.assertIn('betaKick tran stop=25u',deck)
            else:
                self.assertEqual(deck,prev)

    def test_extended_stable_shaped_curve_remains_evidence_not_formal_pass(self):
        data=PsfData()
        data.sweep_types={'freq':'Hz'}
        freq=[10**(i/100) for i in range(1031)]
        data.values={'freq':freq,'loopGain':[.505/(1+1j*f/1e9) for f in freq]}
        result=d.beta_extended(data,None)
        self.assertEqual(result['status'],'screen_pass')
        self.assertFalse(result['legacy_10dB_screen_pass'])
        self.assertIsNone(result['passed'])
        self.assertGreater(result['min_distance_to_critical'],.49)
        data.values['loopGain'][-1]=complex(1.01,0)
        self.assertFalse(d.beta_extended(data,None)['sampled_screen_pass'])
        data.sweep_types={'freq':'sweep'}
        self.assertFalse(d.beta_extended(data,None)['sampled_screen_pass'])
