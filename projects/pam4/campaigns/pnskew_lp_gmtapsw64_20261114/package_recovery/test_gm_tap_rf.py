"""Offline checks for the fixed-wire native tap bank circuit."""

import re
import unittest

import gm_tap_rf as rf
import lp_endpoint


class GmTapRFTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = lp_endpoint.build_plan()['cases'][2]

    def render(self,anchors,weights,**changes):
        case = dict(self.parent,anchors=list(anchors),weights=list(weights),match_load=True)
        case.update(changes)
        return rf.render(case,rf.BASE.MODEL_TOKEN)

    def test_physical_banks_remain_present_across_codes(self):
        center,rails,ac,dc,currents,_ = self.render(rf.ANCHORS,(0,0,0,8,0,0,0))
        edge,*_ = self.render(rf.ANCHORS,(4,4,0,0,0,0,0))
        normalize = lambda d:re.sub(r'(?m)^(GMSK\d{2}VE[0-7].*?dc=)\S+$',r'\g<1>ON_OFF',d)
        self.assertEqual(normalize(center),normalize(edge))
        for deck in (center,edge):
            self.assertEqual(len(re.findall(r'(?m)^GMSK\d{2}VE[0-7] .*?dc=0.81$',deck)),8)
            self.assertEqual(len(re.findall(r'(?m)^GMSK\d{2}[PM]M[0-7] ',deck)),112)
            self.assertEqual(len(re.findall(r'(?m)^GMSK\d{2}[PM]T[0-7] ',deck)),112)
            self.assertNotIn('GLSEL',deck)
        self.assertIn('GMSK06PDRV (GLPT06 GMSK06PG) vsource dc=0',center)
        self.assertIn('GMSK06MDRV (GLMT16 GMSK06MG) vsource dc=0',center)
        self.assertIn('GMSK11MDRV (GLMT11 GMSK11MG) vsource dc=0',center)
        self.assertIn('GLPRT (GLPT16 X_cm) resistor r=50',center)
        self.assertNotRegex(center,r'(?m)^GMS[AB]\w+ ')
        self.assertEqual(sum(v>0 for k,v in rails.items() if k.startswith('GMSK')),8)
        self.assertIn('GMSK06PDRV:p',ac)
        self.assertIn('GMSK16MVD:p',ac)
        self.assertIn('GMSK06PD',dc)
        self.assertIn('GMSK16MVT:p',currents)

    def test_oracle_preserves_line_and_only_discards_idle_banks(self):
        actual,*_ = self.render((6,11,16),(0,8,0))
        oracle,*_ = self.render((11,),(8,),group='oracle')
        self.assertEqual(re.findall(r'(?m)^GL[PM]\w+ .*$',actual),
                         re.findall(r'(?m)^GL[PM]\w+ .*$',oracle))
        self.assertNotIn('GMSK06PDRV',oracle)
        self.assertNotIn('GMSK16PDRV',oracle)
        self.assertIn('GMSK11PDRV (GLPT11 GMSK11PG) vsource dc=0',oracle)
        with self.assertRaisesRegex(ValueError,'only retain'):
            self.render((6,11),(0,8),group='oracle')

    def test_invalid_native_tap_controls_are_rejected(self):
        rejected = [((6,11,16),(2,0,6)),((6,11,16),(4,0,3)),
                    ((6,8,11,16),(8,0,0,0)),((16,11,6),(8,0,0))]
        for anchors,weights in rejected:
            with self.subTest(anchors=anchors,weights=weights),self.assertRaises(ValueError):
                self.render(anchors,weights)

    def test_headroom_contains_active_devices_and_original_tail(self):
        anchors,weights = (6,11,16),(0,7,1)
        deck,*_ = self.render(anchors,weights)
        op = {name:{'vds':.3,'vdsat':.2,'ids':.001,'gm':.01} for name in
              re.findall(r'(?m)^(\w+) \([^)]+\) [np]mos_lvt ',deck)}
        result = rf.headroom(dict(self.parent,anchors=anchors,weights=weights),
                             {'saved_mos_oppoint':op},deck)
        self.assertIn('XT2p0',result)
        self.assertIn('GMSK16PM7',result)
        self.assertIn('GMSK16PT0',result)
        self.assertNotIn('GMSK16PT1',result)
        self.assertNotIn('GMSK06PM0',result)
