import re
import unittest

import gm_center64_rf as centre
import gm_taptrim as prior


class Centre64Renderer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = next(c for c in prior.build_plan()['cases'] if c['group']=='pilot'
                        and c['drive']=='p' and c['code']==0 and c['vb1_V']==.57)

    @classmethod
    def settings(cls,weights,**kwargs):
        return dict(cls.base,**({'resolution':64,'tail_variant':'split64','weights':weights,
                                'vb1_V':.565}|kwargs))

    def test_every_code_decodes_to_exact_nominal_width(self):
        cell_weights = {i:4 for i in range(15)} | {15:2,16:1,17:1}
        for code in range(65):
            cells = centre.active_cells(code)
            self.assertEqual(len(cells),len(set(cells)))
            self.assertEqual(sum(cell_weights[i] for i in cells),code)
        self.assertEqual(centre.active_cells(1),(16,))
        self.assertEqual(centre.active_cells(2),(15,))
        self.assertEqual(centre.active_cells(63),(*range(16),16))
        self.assertEqual(centre.active_cells(64),tuple(range(18)))
        for code in (-1,65,1.0,True):
            with self.assertRaises(ValueError):
                centre.active_cells(code)

    def test_one_step_engages_a_native_eighth_without_altering_rf_inputs(self):
        case = self.settings([1,63,0])
        deck,rails,ac,dc,currents,_ = centre.render(case,centre.BASE.MODEL_TOKEN)
        self.assertIn('XVb (X_vb 0) vsource dc=0.58\n',deck)
        self.assertIn('GMSKV1 (GMSKVBIAS 0) vsource dc=0.565\n',deck)
        self.assertEqual(rails['GMSKV1:p'],.565)
        self.assertIn('GMSKVBIAS',dc)
        self.assertIn('GMSK11VB17',dc)
        self.assertIn('GMSK06PVT:p',currents)
        self.assertIn('GMSK06PVD:p',ac)
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d+B[NP]\d+ .* GMSKVBIAS ',deck)),108)
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d+[PM]T\d+ .* w=375n .* nrd=0\.872783081 ',deck)),12)
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d+[PM]T\d+ .* w=0\.75u ',deck)),6)
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d+[PM]T\d+ .* w=1\.5u ',deck)),90)
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d+[PM]M\d+ .* w=3u ',deck)),48)
        self.assertEqual(rails['GMSK06VE16:p'],case['vdd_V'])
        self.assertEqual(rails['GMSK06VE15:p'],0.)
        self.assertEqual(rails['GMSK06VE17:p'],0.)
        self.assertEqual(rails['GMSK11VE15:p'],case['vdd_V'])
        self.assertEqual(rails['GMSK11VE16:p'],case['vdd_V'])
        self.assertEqual(rails['GMSK11VE17:p'],0.)

    def test_static_hardware_is_identical_across_fine_and_coarse_codes(self):
        def normal(weights):
            deck = centre.render(self.settings(weights),centre.BASE.MODEL_TOKEN)[0]
            return re.sub(r'(?m)^(GMSK\d+VE\d+ [^\n]+ dc=)\S+',r'\g<1>CODE',deck)
        baseline = normal([0,64,0])
        for weights in ([1,63,0],[0,63,1],[32,32,0],[0,4,60]):
            self.assertEqual(normal(weights),baseline)

    def test_oracle_and_split32_compatibility(self):
        case = self.settings([1,63],group='oracle',anchors=[6,11])
        deck = centre.render(case,centre.BASE.MODEL_TOKEN)[0]
        self.assertNotRegex(deck,r'(?m)^GMSK16[PM]')
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d+[PM]T\d+ ',deck)),72)
        out = self.settings([0,32,0],resolution=32,tail_variant='split32')
        self.assertEqual(centre.render(out,centre.BASE.MODEL_TOKEN),centre.trim.render(out,centre.BASE.MODEL_TOKEN))
        with self.assertRaises(ValueError):
            centre.render(self.settings([63,0,1]),centre.BASE.MODEL_TOKEN)

    def test_native_headroom_uses_active_eighth_and_retains_xt2(self):
        case = self.settings([1,63,0])
        deck,*_ = centre.render(case,centre.BASE.MODEL_TOKEN)
        op = {name:{'vds':.3,'vdsat':.2,'vbs':0.,'vgs':.565,'ids':.0001,'gm':.01,'region':2}
              for name in re.findall(r'(?m)^(\w+) \([^)]+\) [np]mos_lvt ',deck)}
        audit = centre.headroom(case,{'saved_mos_oppoint':op},deck)
        self.assertEqual(len([name for name in audit if name.startswith('XT2')]),16)
        self.assertEqual(audit['GMSK06PT16']['ids_A'],.0001)
        self.assertEqual(audit['GMSK06PT16']['region'],2)
        self.assertNotIn('GMSK06PT15',audit)
        self.assertNotIn('GMSK11PT17',audit)
        self.assertNotIn('GMSK16PM0',audit)
