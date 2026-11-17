import unittest
from unittest.mock import patch

import gm_gmtap_common_summary as summary


def case(process,code,group='codes',bias_kind='divider_lowz'):
    return {'code':code,'group':group,'bias_kind':bias_kind,'process':process,
            'tail_variant':'split64','resolution':64,'vb1_V':.565,'anchors':[6,11,16],
            'match_load':False}


def row(state,delay,*,xt2=True,power=True,rf=True,endpoint_gain=2.5,endpoint_rf=True):
    sign = 1 if state['code']>0 else -1
    stress = -sign*summary.ENDPOINT_PS
    return {'case':state,'AFE_delay_vs_family_center':{'delay_ps':delay},
            'XT2_worst':{'passes_static_screen':xt2},'within_power_budget':power,
            'RF_at_fitted_cancellation':{'within_2dB_population_screen':rf},
            'known_endpoint_skew':{'injected_p_minus_n_ps':stress,
                                   'Hdd_gain_vs_uncorrected_dB':endpoint_gain},
            'same_route_population_oracle':{'injected_skew_ps':stress,
                                            'within_2dB_population_screen':endpoint_rf},
            'tail_current_A':{'P':.0023,'M':.0023},
            'constant_current_target':{'fraction_vs_reference':{'P':-.04,'M':-.04}}}


def test_grid():
    planned,measured = {},{}
    for p in summary.CORNERS:
        key = p,'divider_lowz'
        planned[key] = [case(p,q) for q in range(-10,11)]
        measured[key] = {s['code']:row(s,s['code']*.46) for s in planned[key]}
    return planned,measured


class Common64SummaryTests(unittest.TestCase):
    def test_one_common_code_map_requires_gains_but_not_2percent_tail_current(self):
        planned,measured = test_grid()
        result = summary.common_static_map(planned,measured)
        self.assertTrue(result['verified'])
        self.assertEqual(result['ordered_codes'],list(range(-10,11)))
        for sign in ('negative','positive'):
            self.assertEqual(set(result[sign]['outward_range_ps_by_corner']),set(summary.CORNERS))
            self.assertTrue(all(x['endpoint_RF_pass'] for x in result[sign]['endpoint_0p5_UI_RF_by_corner'].values()))
        local = summary.family_report(planned['ff','divider_lowz'],measured['ff','divider_lowz'])
        self.assertEqual(local['worst_current_target_error_fraction'],.04)

    def test_one_bad_corner_and_measured_optional_code(self):
        planned,measured = test_grid()
        # Nominal code 2 is unqualified at FF. That gap is 0.92 ps if skipped,
        # but a measured optional code can replace it in all corners.
        measured['ff','divider_lowz'][2]['XT2_worst']['passes_static_screen'] = False
        self.assertFalse(summary.common_static_map(planned,measured)['verified'])
        for p in summary.CORNERS:
            key = p,'divider_lowz'
            for q in range(-10,11):
                s = measured[key][q]
                s['case']['code'] = 2*q
            old = measured[key]
            measured[key] = {2*q:v for q,v in old.items()}
            optional = case(p,3,group='extra')
            planned[key].append(optional)
            measured[key][3] = row(optional,.92)
        result = summary.common_static_map(planned,measured)
        self.assertTrue(result['verified'])
        self.assertIn(3,result['ordered_codes'])
        self.assertNotIn(4,result['ordered_codes'])

    def test_path_uses_each_corners_actual_monotonicity(self):
        planned,measured = test_grid()
        # TT can still cover both sides, but position 1 is unreachable and
        # omitting it leaves an oversized step.
        measured['tt','divider_lowz'][1]['AFE_delay_vs_family_center']['delay_ps'] = -.1
        result = summary.common_static_map(planned,measured)
        self.assertFalse(result['verified'])
        self.assertEqual(result['status'],'no_common_static_path_in_measured_codes')

    def test_missing_group_never_permits_implicit_qualification(self):
        planned,measured = test_grid()
        del measured['ss','divider_lowz'][2]
        result = summary.common_static_map(planned,measured)
        self.assertFalse(result['verified'])
        self.assertEqual(result['missing_required_metrics_by_corner']['ss'],[2])
        del planned['tt','divider_lowz']
        result = summary.common_static_map(planned,measured)
        self.assertFalse(result['verified'])
        self.assertEqual(result['status'],'incomplete_or_different_primary_plan')

    def test_endpoint_requires_both_matched_oracle_and_own_center_improvement(self):
        planned,measured = test_grid()
        measured['ss','divider_lowz'][10]['known_endpoint_skew']['Hdd_gain_vs_uncorrected_dB'] = -.1
        self.assertFalse(summary.common_static_map(planned,measured)['verified'])
        measured['ss','divider_lowz'][10]['known_endpoint_skew']['Hdd_gain_vs_uncorrected_dB'] = .1
        measured['ff','divider_lowz'][-10]['same_route_population_oracle']['injected_skew_ps'] = 0
        self.assertFalse(summary.common_static_map(planned,measured)['verified'])
        measured['ff','divider_lowz'][-10]['same_route_population_oracle']['injected_skew_ps'] = summary.ENDPOINT_PS
        self.assertTrue(summary.common_static_map(planned,measured)['verified'])

    def test_chunking_preserves_center_and_exact_oracle_references(self):
        planned = []
        for n in range(20):
            oracle = f'oracle_{n}'
            for name,group,link in ((f'case_{n}','codes',oracle),(oracle,'oracle',None)):
                for side in 'pn':
                    planned.append(dict(case('ss',n,group),case_id=f'{name}_{side}',drive=side,
                                        fixture_id=name,oracle_fixture_id=link))
        calls = []

        def collect(_,cases,plan):
            calls.append([c['fixture_id'] for c in cases if c['drive']=='p'])
            return {c['fixture_id']:(c,) for c in cases if c['drive']=='p'},[],{}

        def measure(fixture,_,center,oracle):
            name = fixture[0]['fixture_id']
            if name.startswith('case_'):
                self.assertEqual(center[0]['fixture_id'],'case_0')
                self.assertEqual(oracle[0]['fixture_id'],fixture[0]['oracle_fixture_id'])
            return {}

        with patch.object(summary.center,'collect',side_effect=collect), \
             patch.object(summary.center,'measure',side_effect=measure), \
             patch.object(summary.mid.tap,'pvt',side_effect=lambda c:c['process']), \
             patch.object(summary.mid,'family',side_effect=summary.process_bias):
            rows,missing,invalid = summary.read_fixture_rows(None,planned,None)
        self.assertEqual(len(rows),40)
        self.assertFalse(missing or invalid)
        self.assertEqual([len(c) for c in calls],[2,32,6])


if __name__=='__main__':
    unittest.main()
