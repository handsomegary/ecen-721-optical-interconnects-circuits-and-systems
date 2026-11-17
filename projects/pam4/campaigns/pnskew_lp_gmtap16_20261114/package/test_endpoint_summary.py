"""Regression checks for AC endpoint and sensitivity summaries."""
import cmath
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import endpoint_summary as summary
import lp_endpoint as design


FREQ = [1e9,7e9,14e9,28e9,56e9]


def case(group,variant,cb=0,segment=None,direction=1):
    return {'group':group,'variant_name':variant,'fixture_id':f'{group}-{variant}-{segment}-{cb}',
            'process':'ss','temperature_C':85,'vdd_V':.81,'source_R_ohm':25,
            'count_b':cb,'segment':segment,'direction':direction,'drive':'p',
            'route_thirds':design.EDGE if group=='endpoint' else design.ZERO}


def diagonal(tau_ps=0.,gain=1.):
    return [(gain*cmath.exp(-1j*math.pi*f*tau_ps*1e-12),0j,0j,
             gain*cmath.exp(1j*math.pi*f*tau_ps*1e-12)) for f in FREQ]


def fixture(c,matrix,total=1):
    pair = {side:{'frequency_Hz':FREQ,'DC_supply_power_W':{'XVs:p':total/1000},
                  'traces':{'X_h0p':[[1.,0.]]*len(FREQ) if side=='p' else [[0.,0.]]*len(FREQ),
                            'X_h0m':[[1.,0.]]*len(FREQ) if side=='n' else [[0.,0.]]*len(FREQ)},
                  'noise':None} for side in 'pn'}
    return c,pair,matrix,{}


class EndpointSummaryTests(unittest.TestCase):
    def test_same_native_uncorrected_keeps_injected_skew(self):
        skew = summary.delay.ENDPOINT_PS
        r3 = fixture(case('baseline','r3'),diagonal())
        zero = fixture(case('coverage','native'),diagonal(),9)
        endpoint = fixture(case('endpoint','native',2),diagonal(-skew,.95),9)
        ref = fixture(case('endpoint','ideal_route',2),diagonal(-skew),9)
        index = {summary.fixture_key(item[0]):item for item in (r3,zero,endpoint,ref)}
        row = summary.row_for(endpoint,{summary.operating_key(r3[0]):r3},index)
        scores = row['known_skew_offline_only']
        self.assertAlmostEqual(summary.fitted_delay(row),-skew)
        self.assertAlmostEqual(scores['uncorrected_same_native_vs_r3_zero_skew']['Hdd_vs_reference_dB'],
                               -10*math.log10(2))
        self.assertAlmostEqual(scores['vs_r3_zero_skew']['Hdc_over_own_Hdd'],0)
        self.assertTrue(scores['gain_and_power_pass'])
        _,coverage = summary.endpoint_reports([row],[endpoint[0],case('fine','native',3,1)])
        self.assertEqual(coverage[0]['status'],'partial')
        self.assertAlmostEqual(coverage[0]['closest_measured_fixture_known_target_only']['signed_residual_ps'],0)

    def test_negative_orientation_and_seam_changes(self):
        cases = [case('fine','native',cb,segment,-1) for segment in (0,1) for cb in (0,1,7,8)]
        values = [4.9,4.8,3.9,3.81,3.79,3.7,3.2,3.1]
        rows = [{'case':c,'incremental_delay_vs_native_zero':{'bands':{'7_to_56_GHz':{'tau_effective_ps':v}}},
                 'Hdd_56GHz_dB':-20+c['segment'],'Hdc_56GHz_complex':[float(c['segment']),0.], 'total_mW':11.}
                for c,v in zip(cases,values)]
        books,seams = summary.fine_reports(rows,cases)
        self.assertEqual(books[0]['status'],'sparse')
        self.assertTrue(books[0]['monotone_where_measured'])
        self.assertIsNone(books[0]['all_steps_pass'])
        self.assertAlmostEqual(seams[0]['next_code0_minus_this_code8_ps'],-.02)
        self.assertAlmostEqual(seams[0]['along_increasing_code_ps'],.02)
        self.assertEqual(seams[0]['Hdd_56GHz_change_dB'],1)
        self.assertEqual(seams[0]['Hdc_56GHz_change_V_per_V'],[1.,0.])

    def test_factorial_uses_only_matched_group_and_reports_missing_arms(self):
        labels = ('ideal_coil','r15_only','c150_only','native','r8_only')
        cases = [case('coil_split',label) for label in labels]
        rows = [{'case':c,'Hdd_56GHz_dB':v} for c,v in zip(cases,(-20.,-20.2,-19.7,-19.6))]
        rows.append({'case':case('coverage','native'),'Hdd_56GHz_dB':99})
        complete,partial = summary.coil_reports(rows,cases)
        self.assertAlmostEqual(complete['Hdd_56GHz_dB']['interaction'],.3)
        self.assertEqual(partial['missing_arms'],['r8_only','c110_only','q8'])
        self.assertIsNone(partial['Hdd_56GHz_dB'])

    def test_summary_refuses_to_pair_single_evidence_column(self):
        c = case('fine','native',0,0)
        p = dict(c,case_id='p')
        n = dict(c,case_id='n',drive='n')
        def read_case(root,case,plan):
            if case['drive']=='n':
                raise FileNotFoundError()
            return {'unused':True}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            plan = path/'plan.json'
            summary.common.write_new(plan,{'cases':[p,n]})
            with patch.object(design,'PLAN',plan),patch('gm_summary.read_case',read_case):
                output = summary.summarize(path)
        self.assertEqual(output['rows'],[])
        self.assertEqual(output['missing_cases'],['n'])
        self.assertEqual(output['fixtures_with_missing_or_invalid_cases'],[c['fixture_id']])
        self.assertEqual(output['local_fine_codebooks'][0]['status'],'partial')


if __name__=='__main__':
    unittest.main()
