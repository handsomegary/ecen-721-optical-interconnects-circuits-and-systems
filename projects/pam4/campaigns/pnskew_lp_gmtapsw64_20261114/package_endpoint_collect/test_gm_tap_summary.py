import cmath
import math
import unittest

from gm_tap_summary import comparable_oracle, measure, report_families
from weighted_delay import ENDPOINT_PS


FS = [1e9,7e9,14e9,28e9,45e9,56e9,80e9]


def fixture(variant,group,point,delay_ps,scale=1.,power=1.,anchors=(6,11,16),weights=(8,0,0)):
    case = dict(variant_name=variant,group=group,point=point,process='ss',temperature_C=85,
                source_R_ohm=25,vdd_V=.81,anchors=anchors,weights=weights,anchor_set='coarse3',
                fixture_id=f'{group}_{point}',match_load=True)
    phase = [cmath.exp(-1j*math.pi*f*delay_ps*1e-12) for f in FS]
    matrix = [(scale*p,0j,0j,scale*p.conjugate()) for p in phase]
    zero,one = [[0.,0.]]*len(FS),[[1.,0.]]*len(FS)
    p = dict(frequency_Hz=FS,traces={'X_h0p':one,'X_h0m':zero},DC_supply_power_W={'rail':power/1000})
    n = dict(frequency_Hz=FS,traces={'X_h0p':zero,'X_h0m':one},DC_supply_power_W={'rail':power/1000})
    return case,{'p':p,'n':n},matrix,{}


class GmTapSummaryTests(unittest.TestCase):
    def setUp(self):
        self.r3 = fixture('r3','baseline','center',0.)
        self.zero = fixture('gmtap','pilot','center',0.,power=8.,weights=(0,8,0))
        self.endpoint = fixture('gmtap','pilot','neg_end',-ENDPOINT_PS,scale=.8,power=10.5)
        self.oracle = fixture('gmtap','oracle','neg_end',-ENDPOINT_PS,anchors=(6,),weights=(8,))

    def test_signed_corrected_hdd_and_control(self):
        row = measure(self.endpoint,self.r3,self.zero,self.oracle,None)
        corrected = row['known_endpoint_skew']
        self.assertAlmostEqual(corrected['incremental_residual_ps'],0.,places=5)
        self.assertAlmostEqual(corrected['corrected']['Hdd_dB'],20*math.log10(.8))
        self.assertAlmostEqual(corrected['corrected']['Hdc_over_abs_Hdd'],0.)
        self.assertAlmostEqual(corrected['Hdd_gain_vs_uncorrected_dB'],20*math.log10(.8)+10*math.log10(2))
        self.assertTrue(row['same_route_population_oracle']['within_2dB_population_screen'])
        self.assertTrue(row['within_power_budget'])

    def test_unmatched_or_missing_reference_does_not_pass(self):
        different = fixture('gmtap','oracle','neg_end',-ENDPOINT_PS,anchors=(11,),weights=(8,))
        self.assertFalse(comparable_oracle(self.endpoint[0],different))
        row = measure(self.endpoint,None,None,different,None)
        self.assertIsNone(row['within_power_budget'])
        self.assertIsNone(row['same_route_population_oracle'])
        self.assertIsNone(row['known_endpoint_skew'])

    def test_power_uses_count_of_enabled_banks(self):
        dual = fixture('gmtap','pilot','neg_end',-4.,power=14.5,weights=(4,4,0))
        row = measure(dual,self.r3,self.zero,None,None)
        self.assertEqual(row['budget_mW'],14)
        self.assertTrue(row['within_power_budget'])
        self.assertIsNone(row['same_route_population_oracle'])

    def test_partial_family_has_no_range_pass(self):
        row = measure(self.endpoint,self.r3,self.zero,self.oracle,None)
        positive = fixture('gmtap','pilot','pos_end',ENDPOINT_PS,weights=(0,0,8))
        families = report_families([self.endpoint[0],positive[0]],[row])
        self.assertEqual(families[0]['missing_points'],['pos_end'])
        self.assertIsNone(families[0]['measured_extremes_cover_both_0p5_UI'])
        self.assertFalse(families[0]['full_codebook_measured'])
