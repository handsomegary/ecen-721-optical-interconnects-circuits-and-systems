import re
import unittest

import gm_tap16
import gm_taptrim_rf as trim


class Trim32Renderer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = next(c for c in gm_tap16.build_plan()['cases'] if c['group']=='pilot'
                        and c['drive']=='p' and c['code']==0)

    @classmethod
    def settings(cls,weights,**kwargs):
        return dict(cls.base,**({'resolution':32,'tail_variant':'split32','weights':weights,
                                 'vb1_V':.57}|kwargs))

    def test_tail_unit_decoder_always_preserves_nominal_width(self):
        for q in range(33):
            cells = trim.active_cells(q)
            self.assertEqual(len(cells),len(set(cells)))
            self.assertEqual(sum(2 if i<15 else 1 for i in cells),q)
        self.assertEqual(trim.active_cells(29),(*range(14),15))
        self.assertEqual(trim.active_cells(3),(0,15))
        self.assertEqual(trim.active_cells(32),tuple(range(17)))

    def test_voltage_rail_names_and_counts(self):
        case = self.settings([29,3,0])
        deck,rails,ac,dc,currents,_ = trim.render(case,trim.BASE.MODEL_TOKEN)
        self.assertIn('XVb (X_vb 0) vsource dc=0.58\n',deck)
        self.assertIn('GMSKV1 (GMSKVBIAS 0) vsource dc=0.57\n',deck)
        self.assertEqual(rails['GMSKV1:p'],.57)
        self.assertIn('GMSKVBIAS',dc)
        self.assertIn('GMSK11VB16',dc)
        self.assertIn('GMSK06PVT:p',currents)
        self.assertIn('GMSK06PVD:p',ac)
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d+B[NP]\d+ .* GMSKVBIAS ',deck)),102)
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d+[PM]T\d+ .* w=0\.75u ',deck)),12)
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d+[PM]T\d+ .* w=1\.5u ',deck)),90)
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d+[PM]M\d+ .* w=3u ',deck)),48)
        self.assertEqual(rails['GMSK06VE15:p'],case['vdd_V'])
        self.assertEqual(rails['GMSK06VE14:p'],0.)
        self.assertEqual(rails['GMSK06VE16:p'],0.)

    def test_split_control_reuses_fixed_circuit(self):
        def normal(weights):
            deck=trim.render(self.settings(weights),trim.BASE.MODEL_TOKEN)[0]
            return re.sub(r'(?m)^(GMSK\d+VE\d+ [^\n]+ dc=)\S+',r'\g<1>CODE',deck)
        self.assertEqual(normal([29,3,0]),normal([0,3,29]))
        self.assertEqual(normal([29,3,0]),normal([0,32,0]))

    def test_minimal_load_reference_has_no_off_rf_bank(self):
        case = self.settings([29,3],group='oracle',anchors=[6,11])
        deck = trim.render(case,trim.BASE.MODEL_TOKEN)[0]
        self.assertNotRegex(deck,r'(?m)^GMSK16[PM]')
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d+[PM]T\d+ ',deck)),68)
        with self.assertRaises(ValueError):
            trim.render(self.settings([31,0,1]),trim.BASE.MODEL_TOKEN)

    def test_trimmed_half16_preserves_tail_width_and_vb2(self):
        case = self.settings([14,2,0],resolution=16,tail_variant='half16')
        deck = trim.render(case,trim.BASE.MODEL_TOKEN)[0]
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d+[PM]T\d+ .* w=1\.5u ',deck)),96)
        self.assertNotIn('GMSK06VB16',deck)
        self.assertIn('XVb (X_vb 0) vsource dc=0.58\n',deck)
        self.assertIn('GMSKV1 (GMSKVBIAS 0) vsource dc=0.57\n',deck)
