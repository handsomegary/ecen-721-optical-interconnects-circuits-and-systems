import unittest

import gm_tapmid_summary as summary


def measured(delay):
    return {
        'AFE_delay_vs_family_center':{'delay_ps':delay},
        'RF_at_fitted_cancellation':{'within_2dB_population_screen':True},
        'same_route_population_oracle':{'within_2dB_population_screen':True},
        'within_power_budget':True,
        'XT2_worst':{'passes_static_screen':True},
    }


class MidbiasSummaryTests(unittest.TestCase):
    def test_missing_midcode_blocks_verified_sweep_and_optional_code_only_recovers_measured_gap(self):
        primary = [0,*range(-16,17,2),-30,30]
        plan = [dict(code=c,group='sweep') for c in set(primary)]
        # Ignore nominal count-to-delay linearity. One necessary spatial gap
        # covers 0.60 ps, and the intermediate odd code is measured separately.
        by_code = {c:measured(c*.24) for c in range(-16,17,2)}
        by_code.update({-30:measured(-4.44),30:measured(4.44)})
        plan += [dict(code=c,group='extra') for c in (-29,-27,27,29)]
        by_code.update({-29:measured(-4.68),29:measured(4.68)})
        blocked = summary.sweep_report(plan,by_code)
        self.assertFalse(blocked['SS_ideal_usable_static_window'])
        self.assertIn(27,blocked['optional_unmeasured_codes'])
        by_code.update({-27:measured(-4.14),27:measured(4.14)})
        # Positive/negative code order remains nominal. Terminal codes are
        # above the target while still inside the edge from ±27.
        by_code[29] = measured(4.62)
        by_code[-29] = measured(-4.62)
        self.assertTrue(summary.sweep_report(plan,by_code)['SS_ideal_usable_static_window'])
        del by_code[2]
        self.assertIsNone(summary.sweep_report(plan,by_code)['SS_ideal_usable_static_window'])

    def test_unknown_or_failed_xt2_cannot_be_used_in_path(self):
        self.assertIsNone(summary.gate(dict(measured(0),XT2_worst=None)))
        self.assertFalse(summary.gate(dict(measured(0),XT2_worst={'passes_static_screen':False})))
        self.assertIsNone(summary.side_path({},1))

    def test_divider_vb1_may_droop_but_consumption_must_be_counted_once(self):
        record = {'DC_voltage_V':{'GMSKVBIAS':.5698,'X_vb':.580},
                  'DC_current_A':{'GMSKVDIV:p':10.2e-6,'GMSKV1:p':.2e-6},
                  'DC_supply_power_W':{'XVb:p':5.916e-6}}
        measured_bias = summary.bias_evidence({'bias_kind':'divider','vb1_V':.570},{'p':record,'n':record})
        self.assertTrue(measured_bias['p']['within_2mV_diagnostic'])
        self.assertEqual(measured_bias['p']['Vb2_to_divider_input_A'],10.2e-6)
        self.assertIsNone(measured_bias['p']['ideal_Vb1_supply_power_W'])
        with self.assertRaises(ValueError):
            summary.bias_evidence({'bias_kind':'ideal','vb1_V':.570},{'p':record})
        with self.assertRaises(ValueError):
            summary.bias_evidence({'bias_kind':'divider','vb1_V':.570},{
                'p':dict(record,DC_supply_power_W={'XVb:p':5.916e-6,'GMSKV1:p':0})})

    def test_low_z_subset_is_not_a_complete_endpoint_family(self):
        rows = {0:measured(0),-29:measured(-4.48),29:measured(4.48)}
        report = summary.local_report([dict(group='divider',code=c) for c in rows],rows)
        self.assertTrue(report['complete_scheduled_measurements'])
        self.assertFalse(report['planned_complete_edge'])
        self.assertIsNone(report['covers_and_resolves_all_local_endpoint_codes'])


if __name__=='__main__':
    unittest.main()
