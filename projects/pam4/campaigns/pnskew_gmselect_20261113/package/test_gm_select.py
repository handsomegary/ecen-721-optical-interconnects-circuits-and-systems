import re
import unittest

import gm_select as gm
import gm_summary


class GMSelectTests(unittest.TestCase):
    def setUp(self):
        self.cases=gm.build_plan()['cases']
        self.token=gm.original.base.MODEL_TOKEN

    def deck(self,index):
        return gm.render(self.cases[index],self.token)[0]

    def test_scope_and_distinct_mirrored_dormant_cases(self):
        self.assertEqual(len(self.cases),48)
        self.assertEqual(len({c['case_id'] for c in self.cases}),48)
        self.assertEqual({c['stage'] for c in self.cases[:28]},{'tt'})
        self.assertEqual({c['stage'] for c in self.cases[28:]},{'corner'})
        groups={}
        for c in self.cases:
            groups.setdefault(gm_summary.group_key(c),set()).add(c['drive'])
        self.assertEqual(len(groups),24)
        self.assertTrue(all(g=={'p','n'} for g in groups.values()))
        self.assertNotEqual(self.cases[24]['case_id'],self.cases[26]['case_id'])

    def test_two_banks_share_only_drain_rail_and_have_separate_bridges(self):
        deck=self.deck(6)
        self.assertIn('GMSAPVD (X_c_p GMSAPD) vsource dc=0',deck)
        self.assertIn('GMSBPVD (X_c_p GMSBPD) vsource dc=0',deck)
        self.assertIn('GMSARD (GMSAPS GMSAMS) resistor r=250',deck)
        self.assertIn('GMSBCD (GMSBPS GMSBMS) capacitor c=100f',deck)
        self.assertIn('GMSAPT0 (GMSAPS X_vb GMSAPZ 0) nmos_lvt l=60n w=3u',deck)
        self.assertIn('GMSBPT0 (GMSBPS 0 GMSBPZ 0) nmos_lvt l=60n w=3u',deck)
        self.assertIn('GMSBPM0 (GMSBPD GMSBPG GMSBPS 0) nmos_lvt l=30n w=3u',deck)
        self.assertNotIn('pmos_lvt',deck.split('// END GMSELECT')[0])
        self.assertIn('GMSAPT0 (GMSAPS 0 GMSAPZ 0)',self.deck(8))
        self.assertIn('GMSBPT0 (GMSBPS X_vb GMSBPZ 0)',self.deck(8))

    def test_stage2_geometry_and_sampler_devices_unchanged(self):
        parent=gm.original.base.load_inputs()[0]
        deck=self.deck(34)
        self.assertIn('section=ss',deck)
        self.assertIn('temp=85 tnom=25',deck)
        self.assertIn('XVs (X_vdd 0) vsource dc=0.81',deck)
        for prefix in ('XM2','XT2','XR1','XR2','XSN','XSP','XCH','XRH'):
            self.assertEqual([l for l in deck.splitlines() if l.startswith(prefix)],
                             [l for l in parent.splitlines() if l.startswith(prefix)])

    def test_all_active_drivers_are_identical_except_dormant_probe_excitation(self):
        full=self.deck(6)
        off=self.deck(24)
        self.assertIn('GMSAPDRV (GMSAPL X_cm PNC_PREP X_cm) vcvs gain=0',off)
        self.assertIn('GMSBPDRV (GMSBPL X_cm PNC_PREP X_cm) vcvs gain=1',off)
        normalize=lambda deck: re.sub(r'(GMS[AB][PM]DRV .*vcvs gain=)[01]',r'\g<1>1',
                                    re.sub(r'^noiseResponse .*$', '// AC-only column',deck,flags=re.M))
        self.assertEqual(normalize(full),normalize(off))

    def test_stationary_noise_uses_same_track_nodes_in_bypass_and_candidate(self):
        statement='noiseResponse (X_h0p X_h0m) noise start=1M stop=56G dec=40 iprobe=XVin'
        for index in (0,2,4,6,28,32,38,42):
            self.assertIn(statement,self.deck(index))
            self.assertNotIn('noiseResponse ',self.deck(index+1))


if __name__=='__main__':
    unittest.main()
