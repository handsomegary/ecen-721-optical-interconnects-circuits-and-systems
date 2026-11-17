"""Protect long-window alignment and matched-case deck invariants."""

import copy
import os
from pathlib import Path
import re
import sys
import unittest


OUTPUTS = Path(__file__).resolve().parent.parent
for variable,sibling in (
    ('PAM4_C0_ORIGINAL_PACKAGE','PAM4_PNSKEW_LP_GMTAP_C0_RUN_20261115'),
    ('PAM4_C0_ALIGN_PACKAGE','PAM4_PNSKEW_LP_GMTAP_C0_ALIGN_20261115'),
    ('PAM4_C0_FORMAL_PACKAGE','PAM4_PNSKEW_LP_GMTAP_C0_FORMAL_20261115'),
):
    sys.path.insert(0,os.environ.get(variable,str(OUTPUTS/sibling)))

import c1_payload as c1


def normalize_pwl_and_analysis(deck):
    for name in ('PAM4Vp','PAM4Vm'):
        start,end,*_ = c1.review.pn_stage.pwl_block(deck,name)
        deck = deck[:start] + deck[end:]
    return c1.TRANSIENT.sub(b'',deck)


def synthetic_records(symbols):
    return {plane: [(i+3, sign*.012*(symbol-1.5), t, t, i%8)
                    for i,symbol in enumerate(symbols)
                    for t in (c1.design.T0 + (i+3+extra_ui)*c1.review.UI,)]
            for plane,sign,extra_ui in (('primary',1,.4),('secondary',-1,4.))}


class C1PayloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = c1.formal_score.aligned.scoring_functions()
        fitting = c1.design.symbols('training')
        observations = {plane:{r[0]:r for r in records}
                        for plane,records in synthetic_records(fitting).items()}
        cls.calibration = c1.formal_score.fit_calibration(
            dict(stimulus='training',condition='zero',code=0,phase=-1,case_id='c0f_training_zero_cp00_phm1'),
            observations,fitting[:c1.formal_score.FIT[1]],cls.functions,c1.review.pinned_r5())

    def test_decks_only_extend_pwl_and_enable_matched_noise(self):
        zero,zero_meta = c1.render('zero',0)
        historical_quiet = (c1.review.R5/'quiet.scs').read_bytes()
        for name in ('PAM4Vp','PAM4Vm'):
            self.assertEqual(c1.review.pn_stage.pwl_block(zero,name)[-2:],
                             c1.review.pn_stage.pwl_block(historical_quiet,name)[-2:])
        for condition,code in c1.CASES:
            deck,meta = c1.render(condition,code)
            matched_quiet,_ = c1.design.render(condition,code,-1,'payload')
            self.assertEqual(normalize_pwl_and_analysis(deck),normalize_pwl_and_analysis(matched_quiet))
            self.assertEqual(meta['noise'],dict(seed=1001,fmin_Hz=500e6,fmax_Hz=150e9))
            self.assertEqual(meta['clock_spec']['stop_s'],c1.STOP_S)
            self.assertEqual(meta['symbol_sha256'],zero_meta['symbol_sha256'])
            line, = c1.TRANSIENT.findall(deck)
            self.assertEqual(float(line[0]),c1.STOP_S)
            self.assertEqual(re.findall(rb'noise\w+=\S+',line[1]),
                             [b'noisefmax=150G',b'noisefmin=500M',b'noiseseed=1001'])

    def test_each_same_direction_pair_changes_control_voltages_only(self):
        for condition,code in (('a',-60),('b',60)):
            before,_ = c1.render(condition,0)
            after,_ = c1.render(condition,code)
            left,right = before.splitlines(),after.splitlines()
            self.assertEqual(len(left),len(right))
            diff = [(a,b) for a,b in zip(left,right,strict=True) if a!=b]
            self.assertTrue(diff)
            for a,b in diff:
                self.assertRegex(a,rb'^GMSK(?:06|11|16)VE\d+ .* vsource dc=')
                self.assertEqual(a.rsplit(b'=',1)[0],b.rsplit(b'=',1)[0])

    def test_frozen_clocked_scoring_uses_all_2032_centers(self):
        _,meta = c1.render('a',-60)
        records = synthetic_records(c1.stimulus())
        calibration = copy.deepcopy(self.calibration)
        result = c1.score_records(meta,records,calibration,self.functions)
        self.assertEqual(calibration,self.calibration)
        self.assertEqual(result['capture_window']['tx_symbol_indices'],[1152,3200])
        self.assertEqual(result['capture_window']['FFE_center_symbol_indices'],[1160,3192])
        for plane in ('primary','secondary'):
            scores = result['metrics'][plane]
            self.assertEqual(result['capture_window'][plane]['lag'],3)
            self.assertEqual(scores['ADC_validation_input_count'],2048)
            self.assertEqual(scores['ideal7bit_ADC_then_FFE']['sample_count'],2032)
            self.assertEqual(scores['ideal7bit_ADC_then_FFE']['symbol_errors'],0)
        result['noise'] = dict(result['noise'],seed=1002)
        with self.assertRaisesRegex(ValueError,'different physical case'):
            c1.validate_report(result,meta)

    def test_missing_long_window_sample_is_rejected(self):
        _,meta = c1.render('zero',0)
        records = synthetic_records(c1.stimulus())
        records['primary'] = [row for row in records['primary'] if row[0]!=2900]
        with self.assertRaisesRegex(ValueError,'complete historical long window'):
            c1.score_records(meta,records,self.calibration,self.functions)


if __name__=='__main__':
    unittest.main()
