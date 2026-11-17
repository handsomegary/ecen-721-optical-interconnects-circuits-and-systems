"""Offline tests of native PSF extraction and destination-reference screening."""
from copy import deepcopy
import unittest

from diag_metrics import XT2_PATHS
import gm_switch64_metrics as metrics
from pvt.reference.psf_ascii import PsfData


def fixtures():
    ui = metrics.UI
    start = round(290*ui,18)
    stop = round(630*ui,18)
    end = start+2e-12
    case = dict(initial_code=0,final_code=1,switch_time_s=start,stop_s=stop,
                slew_s=2e-12,offset_s=0.,process='ss',temperature_C=85,vdd_V=.81,
                bias_kind='divider_lowz',vb1_V=.565,resolution=64,tail_variant='split64',
                anchors=[6,11,16],skew_ps=0.,amplitude_Vppd=.4,max_step_s=ui/4,
                reference_case_id='hold',group='switch',case_id='toggle')
    t = sorted({i*ui/4 for i in range(2520)}|{start,stop,end})
    values = {'time':t,'GMSKVBIAS':[.56396]*len(t),'X_vb':[.580]*len(t)}
    for leg,names in metrics.TAIL_NODES.items():
        for i,n in enumerate(names):
            values[n] = [0. if i!=1 else .0023]*len(t)
    for lane in range(8):
        values[f'X_ck{lane}'] = [.81 if ((round(x/(ui/4),6)-4*lane)%32)<16 else 0.
                                for x in t]
        values[f'X_h{lane}p'] = [.215]*len(t)
        values[f'X_h{lane}m'] = [.205]*len(t)
    for tail in XT2_PATHS:
        values[tail+':vds'] = [.2]*len(t)
        values[tail+':vdsat'] = [.19]*len(t)
        values[tail+':region'] = [2.]*len(t)
    data = PsfData()
    data.sweep_names = ['time']
    data.sweep_properties = {'time':{'units':'s'}}
    data.values = values
    data.sha256 = 'synthetic'
    reference_case = dict(case,initial_code=1,group='hold',case_id='hold',reference_case_id=None)
    return data,case,reference_case


class NativeSwitchMetrics(unittest.TestCase):
    def test_measurement_summarizes_native_tails_and_all_lanes(self):
        data,case,_ = fixtures()
        report = metrics.measurement(data,dict(case,model_preflight={'path':'PRIVATE'}))
        self.assertEqual(report['format'],metrics.FORMAT)
        self.assertNotIn('model_preflight',report['case'])
        self.assertEqual(len(report['held_by_lane']),8)
        self.assertTrue(all(len(lane)>8 for lane in report['held_by_lane']))
        self.assertEqual(len(report['XT2_by_window']['transition']),16)
        self.assertAlmostEqual(report['XT2_by_window']['transition']['XT2p0']['minimum_margin_V'],.01)
        self.assertEqual(report['XT2_by_window']['final']['XT2m7']['native_region_at_minimum'],'2')

    def test_wrong_or_missing_phase_matched_hold_is_unresolved(self):
        data,case,reference_case = fixtures()
        switched = metrics.measurement(data,case)
        reference = metrics.measurement(data,dict(reference_case,skew_ps=1.))
        self.assertIsNone(metrics.compare(switched,None)['settled'])
        self.assertIsNone(metrics.compare(switched,reference)['settled'])

    def test_hold_transition_window_can_have_no_native_interior_sample(self):
        data,case,_ = fixtures()
        case = dict(case,switch_time_s=case['switch_time_s']+.2e-12,slew_s=.2e-12)
        report = metrics.measurement(data,case)
        self.assertAlmostEqual(report['signal_window_statistics']['transition']['vb1_V']['min'],.56396)
        self.assertAlmostEqual(report['XT2_by_window']['transition']['XT2m4'][
            'native_region_time_fraction_left_hold']['2'],1.)

    def test_phase_matched_steady_reference_and_no_late_violations(self):
        data,case,reference_case = fixtures()
        reference = metrics.measurement(data,reference_case)
        switched = metrics.measurement(data,case)
        time = switched['signals']['time_s']
        end = switched['switch_end_s']
        switched['signals']['vb1_V'] = [.559 if end<t<end+100e-12 else .56396 for t in time]
        result = metrics.compare(switched,reference)
        self.assertEqual(result['status'],'observed_recovery',result)
        self.assertGreaterEqual(result['recovery_s_after_event'],100e-12)
        self.assertTrue(all(n>=8 for n in result['post_settle_samples_by_lane']))
        switched['signals']['vb1_V'][-1] -= .002
        censored = metrics.compare(switched,reference)
        self.assertEqual(censored['status'],'right_censored')
        self.assertIsNone(censored['recovery_s_after_event'])

    def test_late_sample_and_unsettled_reference_cannot_qualify(self):
        data,case,reference_case = fixtures()
        reference = metrics.measurement(data,reference_case)
        switched = metrics.measurement(data,case)
        switched['held_by_lane'][7][-1][1] += .004
        result = metrics.compare(switched,reference)
        self.assertEqual(result['status'],'right_censored')
        drifting = deepcopy(reference)
        drifting['signals']['vb1_V'][-1] += .003
        unresolved = metrics.compare(switched,drifting)
        self.assertEqual(unresolved['status'],'unresolved')
        self.assertFalse(unresolved['reference_screen']['stationary'])

    def test_native_nonsaturation_dwell_is_reported_per_tail(self):
        data,case,reference_case = fixtures()
        reference = metrics.measurement(data,reference_case)
        switched = metrics.measurement(data,case)
        record = switched['XT2_by_window']['final']['XT2p0']
        record['native_region_time_fraction_left_hold'] = {'2':.75,'1':.25}
        result = metrics.compare(switched,reference)
        region = result['final_XT2_native_region_comparison']
        self.assertEqual(len(region),16)
        self.assertEqual(region['XT2p0']['difference_fraction'],.25)
        self.assertEqual(result['status'],'observed_recovery')
