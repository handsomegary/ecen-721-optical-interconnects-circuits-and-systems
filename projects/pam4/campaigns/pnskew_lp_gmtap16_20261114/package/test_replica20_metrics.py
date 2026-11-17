"""Offline native STB and no-GM screening regressions."""
import cmath
import math
import unittest

from diag_metrics import stb_metrics
from pvt.reference.psf_ascii import PsfData
from replica20_metrics import replica20_metrics
from test_diag_metrics import stb_fixture


def fixture():
    trace = PsfData()
    frequency = [10**(i/100) for i in range(1031)]+[20e9]
    # Two poles put the low-frequency return on the negative real axis. The
    # native critical point is +1, and the phase approaches 0 from above.
    response = [-451/(1+1j*f/25e3)/(1+1j*f/75e6) for f in frequency]
    trace.values = {'freq':frequency,'loopGain':response}
    trace.sweep_types = {'freq':'Hz'}
    trace.header['probe'] = 'GMSQLOOP'
    hi = next(i for i,value in enumerate(response) if abs(value)<1)
    a,b = (20*math.log10(abs(response[i])) for i in (hi-1,hi))
    fraction = a/(a-b)
    pm = math.degrees((1-fraction)*cmath.phase(response[hi-1])+fraction*cmath.phase(response[hi]))
    margins = PsfData()
    margins.header['probe'] = 'GMSQLOOP'
    margins.trace_types = {'phaseMargin':'Deg','phaseMarginFreq':'Hz','gainMargin':'dB'}
    margins.values = {'phaseMargin':[pm], 'gainMargin':[float('nan')],
                      'phaseMarginFreq':[frequency[hi-1]*(frequency[hi]/frequency[hi-1])**fraction],
                      'stb_state':['The circuit is stable. No gain margin found.']}
    return trace,margins


class Replica20(unittest.TestCase):
    def test_native_finite_margins_match_existing_stb_measurement(self):
        trace,margins = stb_fixture()
        native = stb_metrics(trace,margins)
        result = replica20_metrics(trace,margins)
        self.assertTrue(result['formal_margin_pass'])
        self.assertFalse(result['sampled_screen_pass'])
        self.assertEqual({key:result[key] for key in native},native)

    def test_missing_gm_uses_signed_dense_trace_but_is_not_formal(self):
        trace,margins = fixture()
        result = replica20_metrics(trace,margins)
        self.assertEqual(result['status'],'screen_pass',result.get('reason'))
        self.assertIsNone(result['passed'])
        self.assertIsNone(result['gain_margin_db'])
        self.assertFalse(result['formal_margin_pass'])
        self.assertTrue(result['sampled_screen_pass'])
        self.assertLess(result['low_frequency_return'][0],0)
        self.assertTrue(result['low_frequency_plateau'])
        self.assertTrue(result['high_frequency_rolloff'])
        self.assertGreater(result['persistent_low_return_from_Hz'],result['unity_crossings_Hz'][0])
        self.assertEqual(len(result['loopGain_real_imag']),len(trace.values['freq']))

    def test_positive_real_contact_above_limit_blocks_screen(self):
        trace,margins = fixture()
        row = next(i for i,f in enumerate(trace.values['freq']) if f>=20e6)
        trace.values['loopGain'][row] = .45+0j
        result = replica20_metrics(trace,margins)
        self.assertEqual(result['status'],'review')
        self.assertTrue(any(contact['absolute_return']>.316 for contact in result['critical_ray_contacts']))
        self.assertIsNone(result['gain_margin_db'])

    def test_invalid_native_state_or_phase_margin_is_review(self):
        for field,value in (('stb_state','The circuit is not stable.'),
                            ('stb_state','The circuit is stable. Gain and phase margin are both found.'),
                            ('phaseMargin',50.),('phaseMargin',110.),('phaseMarginFreq',1e9),
                            ('gainMargin',float('inf'))):
            with self.subTest(field=field,value=value):
                trace,margins = fixture()
                margins.values[field] = [value]
                result = replica20_metrics(trace,margins)
                self.assertEqual(result['status'],'review')
                self.assertFalse(result['sampled_screen_pass'])

    def test_incomplete_grid_bad_tail_and_second_unity_are_review(self):
        for kind in ('short','sparse','tail','unity'):
            with self.subTest(kind=kind):
                trace,margins = fixture()
                if kind=='short':
                    for key in trace.values:
                        trace.values[key] = trace.values[key][:901]
                elif kind=='sparse':
                    for key in trace.values:
                        trace.values[key] = trace.values[key][::2]
                else:
                    trace.values['loopGain'][-3] = .1+(.4j if kind=='tail' else 2j)
                result = replica20_metrics(trace,margins)
                self.assertEqual(result['status'],'review')
                self.assertFalse(result['sampled_screen_pass'])


if __name__=='__main__':
    unittest.main()
