"""Offline topology, geometry and current-map checks for the sixteen-half-tail bank."""

import re
import unittest

import gm_tap as prior
import gm_tap16_rf as rf


class Fine16RF(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = prior.build_plan()['cases'][10]

    def case(self, weights=(15,1,0), **updates):
        return self.parent | {'resolution':16,'weights':list(weights)} | updates

    def render(self, weights=(15,1,0), **updates):
        return rf.render(self.case(weights,**updates),rf.BASE.MODEL_TOKEN)

    def test_only_enable_changes_between_codes(self):
        center,rails,ac,dc,currents,_ = self.render((0,16,0))
        near,*_ = self.render()
        normalize = lambda deck: re.sub(
            r'(?m)^(GMSK\d{2}VE\d+ .*?dc=)\S+$',r'\g<1>CODE',deck)
        self.assertEqual(normalize(center),normalize(near))
        self.assertEqual(len([k for k in rails if k.startswith('GMSK')]),48)
        self.assertEqual(sum(v>0 for k,v in rails.items() if k.startswith('GMSK')),16)
        self.assertIn('GMSK06PDRV (GLPT06 GMSK06PG) vsource dc=0',near)
        self.assertIn('GMSK06MDRV (GLMT16 GMSK06MG) vsource dc=0',near)
        self.assertNotIn('GLPMATCH',near)
        self.assertIn('GMSK06PDRV:p',ac)
        self.assertIn('GMSK16VB15',dc)
        self.assertIn('GMSK11MVT:p',currents)

    def test_geometry_and_controls_are_independent(self):
        deck,rails,*_ = self.render()
        tails = re.findall(r'(?m)^GMSK\d{2}[PM]T\d+ .*$',deck)
        rf_inputs = re.findall(r'(?m)^GMSK\d{2}[PM]M\d+ .*$',deck)
        self.assertEqual((len(tails),len(rf_inputs)),(96,48))
        self.assertTrue(all('l=60n w=1.5u multi=1 nf=1' in row for row in tails))
        self.assertTrue(all('ad=1.125e-13 as=1.125e-13 pd=3.15u ps=3.15u' in row
                            for row in tails))
        self.assertTrue(all('l=30n w=3u' in row for row in rf_inputs))
        self.assertIn('GMSK06PT14 (GMSK06PS GMSK06VB14 GMSK06PZ 0)',deck)
        self.assertIn('GMSK06PT15 (GMSK06PS GMSK06VB15 GMSK06PZ 0)',deck)
        self.assertEqual(rails['GMSK06VE14:p'],.81)
        self.assertEqual(rails['GMSK06VE15:p'],0.)
        for index in range(15):
            self.assertEqual(rails[f'GMSK06VE{index}:p'],.81)
        self.assertEqual(rails['GMSK11VE0:p'],.81)
        self.assertEqual(rails['GMSK11VE1:p'],0.)

    def test_oracle_and_invalid_weights(self):
        real,*_ = self.render()
        oracle,*_ = self.render((15,1),anchors=[6,11],group='oracle')
        line = lambda deck:re.findall(r'(?m)^GL[PM]\w+ .*$',deck)
        self.assertEqual(line(real),line(oracle))
        self.assertNotIn('GMSK16PM0',oracle)
        for weights in ((15,0,1),(16,1,0),(14,1,0),(15,1.0,0)):
            with self.subTest(weights=weights),self.assertRaises(ValueError):
                self.render(weights)

    def test_native_op_retains_geometry_diagnostics(self):
        case = self.case()
        deck,*_ = self.render()
        op = {name:{'vds':.3,'vdsat':.2,'vbs':0.,'vgs':.58,'ids':.0001,'gm':.01}
              for name in re.findall(r'(?m)^(\w+) \([^)]+\) [np]mos_lvt ',deck)}
        audit = rf.headroom(case,{'saved_mos_oppoint':op},deck)
        self.assertIn('XT2p0',audit)
        self.assertEqual(audit['GMSK06PT14']['ids_A'],.0001)
        self.assertEqual(audit['GMSK06PT14']['vbs_V'],0.)
        self.assertNotIn('GMSK06PT15',audit)
        self.assertNotIn('GMSK16PM0',audit)
