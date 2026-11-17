import cmath
import json
import math
import re
import unittest

import ac_next
import summarize_acnext
import weighted_delay


class SparseAC(unittest.TestCase):
    def setUp(self):
        self.cases = ac_next.build_plan()['cases']

    def test_exact_pairing_for_every_case(self):
        pairs = {}
        for case in self.cases:
            pairs.setdefault(summarize_acnext.key(case),[]).append(case['drive'])
        self.assertEqual(len(pairs),47)
        self.assertTrue(all(sorted(v)==['n','p'] for v in pairs.values()))
        self.assertEqual(len({x['case_id'] for x in self.cases}),94)

    def test_ttd_native_switch_routing_and_pvt_keeps_afe_bytes(self):
        parent,r5=ac_next.base.load_inputs()
        case=self.cases[22]
        self.assertEqual((case['process'],case['p_code'],case['n_code']),('ss',6,16))
        deck,rails,ports,diff=ac_next.render(case,ac_next.base.MODEL_TOKEN)
        self.assertIn('section=ss',deck)
        self.assertIn('temp=85 tnom=25',deck)
        self.assertIn('ACNPRT (X_ip X_cm) resistor r=25',deck)
        self.assertIn('ACNPFVN (ACNPFGN 0) vsource dc=0.81',deck)
        self.assertIn('ACNNFVN (ACNNFGN 0) vsource dc=0',deck)
        self.assertIn('ACNNSVN (ACNNSGN 0) vsource dc=0.81',deck)
        self.assertEqual(len(re.findall(r'^ACN[PN][FS]\d\dLA ',deck,re.M)),44)
        self.assertEqual(len(re.findall(r'^ACN[PN][FS][AB][NP] ',deck,re.M)),16)
        for prefix in ('XM','XT','XRdeg','XCdeg','XS'):
            self.assertEqual([l for l in parent.splitlines() if l.startswith(prefix)],
                             [l for l in deck.splitlines() if l.startswith(prefix)])

    def test_carry_ablation_changes_only_declared_trim_and_load(self):
        native=next(x for x in self.cases if x['variant']=='lc_native' and x['p_code']==32 and x['n_code']==31)
        ideal=dict(native,variant='lc_ideal')
        ron=dict(native,variant='lc_ron')
        cap=dict(ideal,load='cap')
        cases=[ac_next.render(x,ac_next.base.MODEL_TOKEN)[0] for x in (native,ideal,ron,cap)]
        self.assertIn('PNCP0TN5',cases[0])
        self.assertIn('PNCP0CI5 (PNCP0M 0) capacitor c=40f',cases[1])
        self.assertNotIn('PNCP0TN5',cases[1])
        self.assertIn('PNCP0RD5 (PNCP0M PNCP0C5) resistor r=50',cases[2])
        self.assertIn('ACNCLP (X_ip 0) capacitor c=8.4f',cases[3])
        self.assertNotIn('XM1p0',cases[3])
        self.assertIn('XM1p0',cases[1])

    def test_sparse_metric_uses_full_modal_matrix_and_input_skew_sign(self):
        fs=[k*1e9 for k in range(1,61)]
        dt=4.464285714285714
        # A common delay drops out. The second branch is the slower one.
        rows=[(1,0,0,cmath.exp(-2j*math.pi*f*dt*1e-12)) for f in fs]
        bypass=[(1,0,0,1)]*len(fs)
        results=weighted_delay.evaluate(fs,rows,bypass,bypass)
        band=results['bands']['7_to_56_GHz']
        self.assertAlmostEqual(band['tau_effective_ps'],-dt,places=9)
        self.assertLess(band['worst_phase_error_ps'],1e-10)
        shifted=summarize_acnext.cancel_input_skew(fs,rows,dt)
        response=summarize_acnext.plane56(fs,shifted,bypass)
        self.assertAlmostEqual(response['Hdd_vs_bypass_dB'],0,places=9)
        self.assertAlmostEqual(response['Hdc_increment_over_abs_Hdd_bypass'],0,places=9)
        json.dumps(results,allow_nan=False)


if __name__=='__main__':
    unittest.main()
