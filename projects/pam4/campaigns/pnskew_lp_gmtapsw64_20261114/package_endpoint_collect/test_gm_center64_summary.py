import unittest

import gm_center64_summary as summary


def scored(delay, *, margin=.005, xt2=True, rf=True, power=True):
    return {'AFE_delay_vs_family_center':{'delay_ps':delay},
            'RF_at_fitted_cancellation':{'within_2dB_population_screen':rf},
            'within_power_budget':power,
            'XT2_worst':{'margin_V':margin,'passes_static_screen':xt2}}


class Center64SummaryTests(unittest.TestCase):
    def test_center_requires_both_signs_and_rejects_old_large_step(self):
        old = summary.center_report({-2:scored(-.606),0:scored(0),2:scored(.606)},32)
        self.assertFalse(old['all_checked_center_steps_and_static_screens_pass'])
        new = {-2:scored(-.606),-1:scored(-.35),0:scored(0),1:scored(.35),2:scored(.606)}
        center = summary.center_report(new,64)
        self.assertTrue(center['all_checked_center_steps_and_static_screens_pass'])
        self.assertAlmostEqual(center['maximum_measured_step_ps'],.35)
        del new[-1]
        center = summary.center_report(new,64)
        self.assertIsNone(center['all_checked_center_steps_and_static_screens_pass'])
        self.assertEqual(center['missing_codes'],[-1])

    def test_reversal_at_center_fails(self):
        data = {-2:scored(-.606),-1:scored(-.34),0:scored(0),1:scored(.66),2:scored(.61)}
        center = summary.center_report(data,64)
        self.assertFalse(center['all_checked_center_steps_and_static_screens_pass'])
        self.assertLess(center['steps'][-1]['step_ps'],0)

    def test_sparse_mids_cannot_qualify_entire_reference_grid(self):
        representative = {-32,32}
        report = summary.midband_report(representative,{c:scored(0) for c in representative})
        self.assertTrue(report['all_planned_mids_pass_XT2'])
        self.assertIsNone(report['reference_even_midband_grid_pass'])
        self.assertIn(16,report['undecked_reference_grid_mids'])
        full = {c:scored(0) for c in summary.MIDBAND_CODES}
        full[32] = scored(3,margin=.0024,xt2=False)
        report = summary.midband_report(summary.MIDBAND_CODES,full)
        self.assertFalse(report['reference_even_midband_grid_pass'])
        self.assertAlmostEqual(report['worst_margin_V'],.0024)

    def test_missing_oracle_blocks_rf_gate_even_with_valid_xt2(self):
        full = {c:scored(0) for c in summary.MIDBAND_CODES}
        full[-32] = scored(-2,rf=None)
        report = summary.midband_report(summary.MIDBAND_CODES,full)
        self.assertTrue(report['all_planned_mids_pass_XT2'])
        self.assertIsNone(report['reference_even_midband_grid_pass'])

    def test_same_code_split32_comparison_requires_same_bias_and_weight(self):
        case = dict(code=2,process='ss',temperature_C=85,vdd_V=.81,source_R_ohm=25,
                    anchors=[6,11,16],match_load=False,bias_kind='ideal',vb1_V=.565)
        base = dict(scored(.60),case=dict(case,resolution=32,weights=[0,31,1],fixture_id='old'),
                    output_56GHz={'Hdd_dB':-22},tail_current_A={'P':.0024,'M':.0024})
        new = dict(scored(.61),case=dict(case,resolution=64,weights=[0,62,2],fixture_id='new'),
                   output_56GHz={'Hdd_dB':-21.9},tail_current_A={'P':.00242,'M':.00242})
        report = summary.compare_split32(new,base)
        self.assertAlmostEqual(report['weighted_delay_delta_ps'],.01)
        self.assertAlmostEqual(report['zero_input_Hdd_delta_dB'],.1)
        new['case']['vb1_V'] = .570
        with self.assertRaises(ValueError):
            summary.compare_split32(new,base)
