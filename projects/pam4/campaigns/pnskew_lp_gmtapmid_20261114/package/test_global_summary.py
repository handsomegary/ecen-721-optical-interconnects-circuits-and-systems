"""Offline regressions for global-code AC scoring and campaign status."""
import cmath
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import global_summary as summary


FS = (1e9,7e9,14e9,28e9,56e9)


def fixture(case,delay=0.,amp=1.,power_mW=1.):
    pair = {}
    for side in 'pn':
        taps = {'GMSAPG':[[.5,0.]]*len(FS),'GLPT06':[[1.,0.]]*len(FS)}
        tracks = {'X_h0p':[[1. if side=='p' else 0.,0.]]*len(FS),
                  'X_h0m':[[1. if side=='n' else 0.,0.]]*len(FS)}
        pair[side] = {'frequency_Hz':list(FS),'DC_supply_power_W':{'XVs:p':power_mW/1000},
                      'traces':dict(taps,**tracks)}
    matrix = [(amp*cmath.exp(-1j*math.pi*f*delay*1e-12),0,0,
               amp*cmath.exp(1j*math.pi*f*delay*1e-12)) for f in FS]
    return case,pair,matrix,{}


def get_case(group,process,logical,switch,parallel=0):
    cases = summary.design.build_plan()['cases']
    return next(c for c in cases if (c['group'],c['process'],c['logical_code'],c['switch_mode'],
                                    c['tg_parallel'],c['drive'])==
                (group,process,logical,switch,parallel,'p') and
                (c['match_load'] or switch=='r3'))


class GlobalSummaryTests(unittest.TestCase):
    def test_endpoint_counterfactual_same_selector_hardware(self):
        case = get_case('map','ss',0,'native',4)
        ref = fixture(get_case('reference','ss',40,'r3'))
        center = fixture(get_case('map','ss',40,'native',4))
        oracle = fixture(get_case('map','ss',0,'ideal'),-summary.TARGET_PS,1.)
        active = fixture(case,-summary.TARGET_PS,.90,8.)
        row = summary.measurement(active,ref,center,oracle)
        self.assertTrue(row['within_2dB'])
        self.assertTrue(row['within_power_budget'])
        self.assertAlmostEqual(row['selected_tap_to_gate_56GHz_dB']['AP'],-6.02059991)
        known = row['known_endpoint_skew']
        self.assertAlmostEqual(known['incremental_residual_ps'],0)
        self.assertAlmostEqual(known['uncorrected_same_hardware']['Hdd_dB'],-10*math.log10(2))
        self.assertTrue(known['within_2dB_vs_same_state_oracle'])
        self.assertGreater(known['Hdd_gain_vs_uncorrected_dB'],0)

    def test_map_requires_strict_monotonic_and_measured_evidence(self):
        cases = summary.design.build_plan()['cases']
        states = [c for c in cases if c['group']=='map' and c['process']=='tt'
                  and c['switch_mode']=='native' and c['drive']=='p']
        rows = [{'case':c,'AFE_delay_vs_neutral':{'delay_ps':(c['logical_code']-40)*.12},
                 'within_2dB':True,'within_power_budget':True,'known_endpoint_skew':{}}
                for c in states]
        key = summary.family(states[0])
        fit = summary.map_report(cases,rows,key)
        self.assertTrue(fit['ac_map_pass'])
        self.assertIsNone(summary.map_report(cases,rows[:-1],key)['ac_map_pass'])
        rows[11]['AFE_delay_vs_neutral']=rows[10]['AFE_delay_vs_neutral']
        fit = summary.map_report(cases,rows,key)
        self.assertFalse(fit['ac_map_pass'])
        self.assertEqual(fit['violating_steps'][0]['step_ps'],0)

    def test_no_campaign_evidence_keeps_selector_blocked(self):
        plan = summary.design.build_plan()
        with patch.object(summary.common,'read',return_value=plan),patch(
                'gm_summary.read_case',side_effect=FileNotFoundError):
            output = summary.summarize(Path('missing-global-run-root'))
        self.assertEqual(len(output['missing_cases']),len(plan['cases']))
        self.assertFalse(output['selected_global_ac_map_verified'])
        self.assertIsNone(output['canonical_all_corners_ac_map_pass'])
        self.assertEqual(output['selector_result']['status'],'blocked_incomplete')

    def test_native_selector_candidates_keep_corners_and_alias_separate(self):
        plan = summary.design.build_plan()
        cases = plan['cases']
        native = get_case('map','ss',0,'native',4)
        row = {'case':native,'AFE_delay_vs_neutral':{'delay_ps':-5.},
               'AFE_delay_vs_r3':{'delay_ps':-4.9},'within_2dB':True,'within_power_budget':True}
        found = summary.selector_candidates(cases,[row],4,True)
        row = next(c for c in found if c['hardware_word']==native['hardware_word'])
        self.assertEqual(len(found),90)
        self.assertTrue(row['metrics_per_corner']['ss']['gain_power_pass'])
        self.assertEqual(list(row['metrics_per_corner']),['ss'])
