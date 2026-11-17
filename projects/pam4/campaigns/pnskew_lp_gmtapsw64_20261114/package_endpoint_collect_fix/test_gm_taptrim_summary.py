import copy
import unittest

import gm_taptrim_summary as summary


def case(code=0,vb1=.57,resolution=32):
    move = abs(code)*resolution//32
    weights = ([move,resolution-move,0] if code<0 else [0,resolution-move,move])
    return {'code':code,'vb1_V':vb1,'tail_variant':'split32' if resolution==32 else 'old8',
            'case_id':f'case{code}','fixture_id':f'fixture{code}', 'resolution':resolution,
            'anchors':[6,11,16],'match_load':False,'group':'pilot','process':'ss',
            'temperature_C':85,'vdd_V':.81,'source_R_ohm':25,'weights':weights}


def row(code,delay,vb1=.57):
    return {'case':case(code,vb1),'tail_current_A':{'P':.00241,'M':.00243},
            'AFE_delay_vs_family_center':{'delay_ps':delay},'within_power_budget':True,
            'XT2_worst':{'margin_V':.004,'passes_static_screen':True},
            'constant_current_target':{'fraction_vs_reference':{'P':.01,'M':-.01}},
            'RF_at_fitted_cancellation':{'within_2dB_population_screen':True},
            'same_route_population_oracle':{'within_2dB_population_screen':True}}


class TrimSummaryTests(unittest.TestCase):
    def test_gate_uses_both_native_region_and_margin_for_sixteen_devices(self):
        all_xt2 = {tag:{'vds':.265,'vdsat':.260,'region':2}
                   for tag in summary.XT2_INSTANCES}
        pair = {arm:{'saved_mos_oppoint':copy.deepcopy(all_xt2)} for arm in 'pn'}
        self.assertIs(summary.xt2_minimum(pair)['passes_static_screen'],True)
        n = pair['n']['saved_mos_oppoint']
        n['XT2p0']['region'] = 1
        fail = summary.xt2_minimum(pair)
        self.assertIs(fail['passes_static_screen'],False)
        self.assertGreater(fail['margin_V'],0)
        n['XT2p0']['region'] = 2
        del n['XT2m7']['region']
        self.assertIsNone(summary.xt2_minimum(pair)['passes_static_screen'])

    def test_current_comparison_separates_exact_legacy_and_nearest_anchor(self):
        baseline = row(28,4.142)
        baseline['case'] = case(28,.58,8)
        fine = row(28,4.142)
        fine['tail_current_A']['P'] *= 1.03
        exact = summary.current_comparison(fine,baseline)
        self.assertTrue(exact['matched_weight_distribution'])
        self.assertAlmostEqual(exact['fraction_vs_reference']['P'],.03)
        interp = summary.current_comparison(row(29,4.43),baseline)
        self.assertFalse(interp['matched_weight_distribution'])

    def test_inserted_code_splits_signed_step_and_checks_actual_span(self):
        states = {c:row(c,d) for c,d in zip(summary.EDGE_CODES,[-4.688,-4.43,-4.142,0,4.142,4.43,4.688])}
        result = summary.prepare_report([r['case'] for r in states.values()],list(states.values()))[0]
        self.assertIs(result['local_trim_pass'],True)
        self.assertTrue(all(arm['covers_0p5_UI'] for arm in result['signed_endpoint_steps'].values()))
        self.assertAlmostEqual(result['signed_endpoint_steps']['negative']['steps'][0]['outward_step_ps'],.288)
        del states[-29]
        missing = summary.prepare_report([r['case'] for r in states.values()],list(states.values()))[0]
        self.assertEqual(missing['missing_required_codes'],[-29])
        self.assertIsNone(missing['local_trim_pass'])

    def test_common_bias_preferred_and_current_diagnostic_separate(self):
        first = {'local_trim_pass':True,'within_diagnostic_current_target_and_span':False,
                 'worst_absolute_current_target_error_fraction':.015,'vb1_V':.575}
        second = {'local_trim_pass':True,'within_diagnostic_current_target_and_span':True,
                  'worst_absolute_current_target_error_fraction':.018,'vb1_V':.565}
        fail = {'local_trim_pass':False,'within_diagnostic_current_target_and_span':True,
                'worst_absolute_current_target_error_fraction':.00001,'vb1_V':.57}
        self.assertIs(summary.rank_common_bias([first,second,fail]),second)
        self.assertIsNone(summary.rank_common_bias([fail]))
