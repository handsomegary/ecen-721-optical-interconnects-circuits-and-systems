import math
import re
import unittest

import selector
import selector_summary


class SelectorTests(unittest.TestCase):
    def setUp(self):
        self.rows=selector.build_plan()['cases']

    def test_plan_is_paired_and_has_required_tt_controls(self):
        self.assertEqual(len(self.rows),90)
        self.assertEqual(len({x['case_id'] for x in self.rows}),90)
        paired={}
        for case in self.rows:
            paired.setdefault(tuple(case[k] for k in selector_summary.KEY),set()).add(case['drive'])
        self.assertTrue(all(v=={'p','n'} for v in paired.values()))
        self.assertEqual({(x['p_code'],x['n_code']) for x in self.rows
                          if x['process']=='tt' and x['variant']=='ttd_mid_mux' and x['fingers']==4},
                         {(6,6),(6,16),(16,6),(9,13)})

    def test_center_bias_and_width_use_original_device_cards(self):
        baseline=selector.render(self.rows[0],selector.previous.base.MODEL_TOKEN)[0]
        centered=selector.render(self.rows[8],selector.previous.base.MODEL_TOKEN)[0]
        ss=selector.render(self.rows[16],selector.previous.base.MODEL_TOKEN)[0]
        self.assertIn('dc=0.7 mag=1',baseline)
        self.assertIn('dc=0.45 mag=1',centered)
        self.assertIn('dc=0.405 mag=1',ss)
        self.assertIn('section=ss',ss)
        for deck,count in ((baseline,2),(centered,8),(ss,8)):
            devices=[x for x in deck.splitlines() if x.startswith('SELDUT')]
            self.assertEqual(len(devices),count)
            self.assertTrue(all('l=30n w=3u multi=1 nf=1' in x for x in devices))

    def test_bias_restore_does_not_add_a_second_low_value_termination(self):
        case=self.rows[54]
        deck,rails,ports,nodes,_=selector.render(case,selector.previous.base.MODEL_TOKEN)
        self.assertEqual(rails['SELVM:p'],.45)
        self.assertIn('SELPRT (SELPOUT SEL_VM) resistor r=25',deck)
        self.assertIn('SELPCOUT (SELPOUT X_ip) capacitor c=10p',deck)
        self.assertIn('SELPREST (X_ip X_cm) resistor r=100K',deck)
        self.assertNotIn('(X_ip X_cm) resistor r=25\n',deck)
        self.assertIn('SELPOFFI',nodes)
        self.assertIn('SELPSELI',ports)
        parent=selector.previous.base.load_inputs()[0]
        for prefix in ('XM','XT','XRdeg','XCdeg','XS'):
            self.assertEqual([x for x in deck.splitlines() if x.startswith(prefix)],
                             [x for x in parent.splitlines() if x.startswith(prefix)])

    def test_on_only_ablation_removes_dormant_route(self):
        on=selector.render(self.rows[52],selector.previous.base.MODEL_TOKEN)[0]
        mux=selector.render(self.rows[54],selector.previous.base.MODEL_TOKEN)[0]
        a=set(on.splitlines())
        b=set(mux.splitlines())
        self.assertFalse(any(x.startswith('SELPOFF') for x in a))
        self.assertTrue(any(x.startswith('SELPOFF') for x in b))
        self.assertTrue(all(x in b for x in a if re.match(r'^SEL[PN]SEL',x)))

    def test_device_y_fixture_recovers_known_R_and_mutual_C(self):
        fs=[1e3,7e9,14e9,28e9,42e9,56e9,150e9]
        g=[1/170.7+1j*2*math.pi*f*3e-15 for f in fs]
        def trace(v): return [[x.real,x.imag] for x in v]
        p={'frequency_Hz':fs,'traces':{'XVin:p':trace([-x for x in g]),'PNCVN:p':trace(g)}}
        n={'frequency_Hz':fs,'traces':{'XVin:p':trace(g),'PNCVN:p':trace([-x for x in g])}}
        result=selector_summary.device_metrics({'p':p,'n':n})
        self.assertAlmostEqual(result['1000']['apparent_transfer_impedance_ohm'][0],170.7,places=7)
        self.assertAlmostEqual(result['56000000000']['signed_mutual_capacitance_equivalent_fF'],3.)
        self.assertEqual(result['56000000000']['input_ground_admittance_equivalent_S'],[[0.,0.],[0.,0.]])


if __name__=='__main__':
    unittest.main()
