"""Offline metric regressions with synthetic native PSF values."""
import cmath
import math
import unittest

import diag_metrics as metrics
from pvt.reference.psf_ascii import PsfData, parse_text


def startup_fixture(profile='fast'):
    case = {'profile':profile,'process':'ss','vdd_V':.81,
            'settle_after_s':1e-6,'stop_s':500e-6}
    us = [0,1,2,300,474,480,499,500]
    supply = [0,.81,.81,.81,.81,.81,.81,.81]
    if profile=='restart':
        case.update(settle_after_s=571e-6,stop_s=1050e-6,
                    restart_first_settle_s=1e-6,restart_off_s=500e-6)
        us.extend((510,520,560,570,571,572,1026,1049,1050))
        supply.extend((.4,0,0,0,.81,.81,.81,.81,.81))
    data = PsfData()
    current = 338.3e-6
    values = {'time':[value*1e-6 for value in us],'GF_VDD':supply,
              'GMSR_REF':[v-462*current if v>.8 else 0. for v in supply],
              'GMSR_D':[v-462*current*.999 if v>.8 else 0. for v in supply],
              'GMSR_BIAS':[.44 if v>.8 else 0. for v in supply],
              'GMSQBP':[.5 if v>.8 else 0. for v in supply],
              'GMSQK':[.5 if v>.8 else 0. for v in supply],
              'GMSQBN':[.45 if v>.8 else 0. for v in supply],
              'GMSQST':[.02 if v>.8 else 0. for v in supply]}
    values['GMSQK'][1] = .45
    if profile=='restart':
        values['GMSQK'][us.index(572)] = .40
    data.values.update(values)
    return data,case


class Startup(unittest.TestCase):
    def test_settled_entire_final_window_and_initial_kick(self):
        data,case = startup_fixture()
        result = metrics.startup_metrics(data,case)
        self.assertTrue(result['passed'])
        self.assertAlmostEqual(result['window_requested_start_s'],475e-6)
        self.assertAlmostEqual(result['iref_uA']['final'],338.3)
        self.assertAlmostEqual(result['servo_error_percent']['min'],-.1)
        self.assertAlmostEqual(result['initial_kick']['peak_signed_uA'],1.)
        self.assertAlmostEqual(result['gate_voltages_over_supply']['GMSR_BIAS']['final'],.44/.81)
        data.values['GMSQK'][-2] = .501
        result = metrics.startup_metrics(data,case)
        self.assertFalse(result['passed'])
        self.assertFalse(result['checks']['kick_below_0p01_uA'])

    def test_restart_checks_first_powered_plateau_and_second_kick(self):
        data,case = startup_fixture('restart')
        result = metrics.startup_metrics(data,case)
        self.assertTrue(result['passed'])
        self.assertTrue(result['restart_rail_cycle_observed'])
        self.assertEqual(result['restart_off_samples'],3)
        self.assertAlmostEqual(result['restart_kick']['peak_signed_uA'],2.)
        self.assertAlmostEqual(result['restart_first_plateau']['iref_uA']['final'],338.3)
        data.values['GMSR_REF'][5] = .81
        result = metrics.startup_metrics(data,case)
        self.assertFalse(result['passed'])
        self.assertFalse(result['checks']['first_plateau_settled'])

    def test_truncated_time_or_incomplete_trace_is_review(self):
        data,case = startup_fixture()
        data.values['time'][-1] = 499.1e-6
        self.assertIsNone(metrics.startup_metrics(data,case)['passed'])
        data,case = startup_fixture()
        del data.values['GMSQST']
        self.assertEqual(metrics.startup_metrics(data,case)['status'],'review')


def stb_fixture(pm=65.,gm=12.):
    trace = PsfData()
    trace.values = {'freq':[10.,100.,1000.,10000.],
                    'loopGain':[2j,cmath.rect(1,math.radians(pm)),10**(-gm/20),.05-.05j]}
    trace.sweep_types = {'freq':'Hz'}
    native = parse_text('''HEADER
"analysis type" "margin.stb"
TYPE
"Deg" FLOAT DOUBLE
"dB" FLOAT DOUBLE
"Hz" FLOAT DOUBLE
"string" STRING
VALUE
"phaseMargin" "Deg" %s
"gainMargin" "dB" %s
"phaseMarginFreq" "Hz" 100
"gainMarginFreq" "Hz" 1000
"stb_state" "string" "The circuit is stable. Gain and phase margin are both found."
END
''' % (pm,gm))
    return trace,native


class Stability(unittest.TestCase):
    def test_native_positive_margin_and_all_complex_points(self):
        trace,native = stb_fixture()
        result = metrics.stb_metrics(trace,native)
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['phase_margin_deg'],65.)
        self.assertEqual(result['gain_margin_db'],12.)
        self.assertEqual(result['loopGain_real_imag'],[[z.real,z.imag] for z in trace.values['loopGain']])
        native.values['gainMargin'] = [-12.]
        self.assertEqual(metrics.stb_metrics(trace,native)['status'],'review')

    def test_native_finite_below_threshold_fails(self):
        trace,native = stb_fixture(pm=50.,gm=8.)
        result = metrics.stb_metrics(trace,native)
        self.assertIs(result['passed'],False)
        self.assertEqual(result['status'],'fail')

    def test_missing_nonfinite_or_wrong_unit_never_pass(self):
        trace,native = stb_fixture()
        self.assertIsNone(metrics.stb_metrics(trace,None)['passed'])
        native.values['gainMargin'] = [float('nan')]
        self.assertIsNone(metrics.stb_metrics(trace,native)['passed'])
        trace,native = stb_fixture()
        native.trace_types['gainMargin'] = 'voltage'
        self.assertIsNone(metrics.stb_metrics(trace,native)['passed'])

    def test_multiple_crossings_and_inconsistent_native_frequency_are_review(self):
        trace,native = stb_fixture()
        trace.values['loopGain'][-1] = 2-.05j
        result = metrics.stb_metrics(trace,native)
        self.assertIsNone(result['passed'])
        self.assertGreater(len(result['unity_crossings_Hz']),1)
        trace,native = stb_fixture()
        native.values['phaseMarginFreq'] = [300.]
        self.assertEqual(metrics.stb_metrics(trace,native)['status'],'review')


class Xt2(unittest.TestCase):
    def test_tail_occupancy_preserves_native_region_and_signed_margin(self):
        paths = ['XAFE.'+name for name in metrics.XT2_PATHS]
        case = {'xt2_paths':paths,'settle_after_s':1e-9,'stop_s':4e-9}
        data = PsfData()
        data.values['time'] = [0.,1e-9,2e-9,4e-9]
        for path in paths:
            data.values[path+':vds'] = [.1,.12,.12,.12]
            data.values[path+':vdsat'] = [.11]*4
            data.values[path+':region'] = [0,2,2,2]
        worst = paths[-1]
        data.values[worst+':vds'][2] = .105
        data.values[worst+':region'][2] = 1
        result = metrics.xt2_metrics(data,case)
        self.assertEqual(result['status'],'measured')
        self.assertIsNone(result['passed'])
        self.assertFalse(result['all_positive_margin'])
        self.assertEqual(result['minimum_margin_tail'],worst)
        self.assertAlmostEqual(result['minimum_margin_V'],-.005)
        report = result['devices'][worst]
        self.assertEqual(report['region_at_minimum'],'1')
        self.assertAlmostEqual(report['region_occupancy']['1']['sample_fraction'],1/3)
        self.assertAlmostEqual(report['region_occupancy']['1']['time_fraction'],2/3)
        del data.values[worst+':region']
        self.assertEqual(metrics.xt2_metrics(data,case)['status'],'review')


if __name__ == '__main__':
    unittest.main()
