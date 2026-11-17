"""Exercise measured fine16 range, residual signs, and even-code parity."""
import cmath
import math
import unittest

import gm_tap16_summary as summary


def case(proc, group='map', code=0, resolution=16):
    moved = abs(code)*resolution//16
    all_banks = (6,11,16),(moved if code<0 else 0,resolution-moved,moved if code>0 else 0)
    taps,weights = all_banks
    if group=='oracle':
        taps,weights = map(tuple,zip(*((a,w) for a,w in zip(taps,weights) if w)))
    return {'process':proc,'temperature_C':85,'vdd_V':.81,'source_R_ohm':25,
            'anchor_set':'coarse3','anchors':taps,'weights':weights,'match_load':False,
            'resolution':resolution,'group':group,'code':code,'point':'center' if not code else 'near',
            'variant_name':'r3' if group=='baseline' else 'gmtap',
            'fixture_id':f'{proc}_{group}_{code}_{resolution}',
            'injected_skew_ps':-math.copysign(summary.ENDPOINT_PS,code) if code else 0.}


def fit_row(code, delay=None, power=True, rf=True, proc='ss', group='map'):
    c = case(proc,group,code)
    return {'case':c,'AFE_delay_vs_family_center':{'delay_ps':delay},
            'within_power_budget':power,'RF_at_fitted_cancellation':{'within_2dB_population_screen':rf},
            'residual_diagnostics':{'injected_skew_ps':c['injected_skew_ps'],
                                    'weighted_residual_ps':None,'phase_residual_56GHz_ps':None},
            'known_endpoint_skew':None,'same_route_population_oracle':None}


def fixture(c,tau=0.):
    freq = [7e9,14e9,28e9,56e9,80e9]
    columns = {}
    for side,(p,n) in {'p':(1.,0.),'n':(0.,1.)}.items():
        columns[side] = {'frequency_Hz':freq,'DC_supply_power_W':{'x':0.001},
                         'traces':{'X_h0p':[[p,0.] for _ in freq],'X_h0m':[[n,0.] for _ in freq]},
                         'DC_current_A':{}}
    phase = [cmath.exp(-1j*math.pi*f*tau*1e-12) for f in freq]
    return c,columns,[(z,0j,0j,z.conjugate()) for z in phase],{}


class Fine16Summary(unittest.TestCase):
    def test_fitted_RF_uses_same_injection_on_both_circuits(self):
        baseline = fixture(case('ss','baseline'))
        center = fixture(case('ss','pilot'))
        for code in (-15,15):
            sign = math.copysign(1,code)
            active = fixture(case('ss','map',code),sign*4.1)
            reference = fixture(case('ss','oracle',code),sign*4.1)
            row = summary.measure(active,baseline,center,reference,None)
            rf = row['RF_at_fitted_cancellation']
            self.assertEqual(row['case']['group'],'map')
            self.assertAlmostEqual(rf['injected_skew_ps'],-sign*4.1)
            self.assertAlmostEqual(rf['Hdd_drop_or_gain_dB'],0.)
            self.assertAlmostEqual(row['residual_diagnostics']['weighted_residual_ps'],
                                   sign*(4.1-summary.ENDPOINT_PS))
            self.assertAlmostEqual(row['residual_diagnostics']['phase_residual_56GHz_ps'],
                                   sign*(4.1-summary.ENDPOINT_PS))
            self.assertEqual(row['budget_mW'],14)

    def test_map_can_trim_an_oversize_step_outside_required_window(self):
        rows = []
        for proc in summary.CORNERS:
            for code in summary.CODES:
                tau = .33*code if abs(code)<16 else math.copysign(5.8,code)
                rows.append(fit_row(code,tau,proc=proc,group='pilot' if abs(code)>=14 else 'map'))
        reports = summary.map_report([r['case'] for r in rows],rows)
        self.assertTrue(all(r['static_all_codes_pass'] is False for r in reports))
        usable = summary.common_usable_window(reports)
        self.assertTrue(usable['global_code_map_verified'])
        self.assertEqual(usable['usable_codes'],list(range(-14,15)))

    def test_required_step_and_missing_corner_block_verification(self):
        rows = []
        for proc in summary.CORNERS:
            for code in summary.CODES:
                tau = .34*code if abs(code)<14 else math.copysign(.34*abs(code)+.28,code)
                rows.append(fit_row(code,tau,proc=proc))
        reports = summary.map_report([r['case'] for r in rows],rows)
        self.assertEqual(summary.common_usable_window(reports)['status'],'required_window_failed')
        self.assertEqual(summary.common_usable_window(reports[:-1])['status'],'incomplete')
        self.assertTrue(reports[0]['outer_code_step_diagnostics']['positive'][0]['straddles_target'])

    def test_pilot_is_not_a_global_map(self):
        rows = [fit_row(0,0.),fit_row(-16,-5.7),fit_row(16,5.7)]
        reports = summary.map_report([r['case'] for r in rows],rows)
        self.assertIsNone(reports[0]['largest_step_within_0p50ps_and_strictly_monotone'])
        self.assertTrue(reports[0]['extremes_cover_both_0p5_UI'])
        self.assertFalse(summary.common_usable_window(reports)['global_code_map_verified'])

    def test_even_code_checks_matched_weights_and_sums_measured_branch_currents(self):
        def operating(resolution,code,total,delay):
            return {'case':case('ss','legacy' if resolution==8 else 'pilot',code,resolution),
                    'AC_path_diagnostics_56GHz':{leg:{'total_tail_current_A':total} for leg in ('P','M')},
                    'AFE_delay_vs_family_center':{'delay_ps':delay,'phase_delay_at_56GHz_ps':delay},
                    'output_56GHz':{'Hdd_dB':-22.},'total_mW':10.}
        old = operating(8,14,0.001,4.1)
        new = operating(16,14,0.00102,4.2)
        parity = summary.compare_even_state(new,old)
        self.assertAlmostEqual(parity['per_leg_total_tail_current']['P']['fine_vs_legacy_fraction'],.02)
        self.assertAlmostEqual(parity['weighted_delay_change_ps'],.1)
        self.assertIsNone(summary.compare_even_state(operating(16,12,.001,4.0),old))


if __name__ == '__main__':
    unittest.main()
