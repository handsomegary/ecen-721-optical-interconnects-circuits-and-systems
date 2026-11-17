"""Exercise the actual plan, original stager and paired-analysis rules offline."""
import hashlib
import math
import unittest
from unittest.mock import patch

import prepare_skew as S
import summarize_skew as R


FIXTURE = b'''simulator lang=spectre
include "<PDK_ROOT>/models/spectre/pdk_toplevel.scs" section=tt
PAM4Vp (PAM4_src_p X_cm) vsource type=pwl wave=[0 -0.1 200p -0.1 201p 0.1 209p 0.1]
PAM4Vm (PAM4_src_m X_cm) vsource type=pwl wave=[0 0.1 200p 0.1 201p -0.1 209p -0.1]
CHR1p (PAM4_src_p CH1_p) resistor r=100
CHC1p (CH1_p X_cm) capacitor c=85f
CHB1p (CHB_p X_cm CH1_p X_cm) vcvs gain=1
CHR2p (CHB_p CH2_p) resistor r=100
CHC2p (CH2_p X_cm) capacitor c=85f
CHB2p (X_ip X_cm CH2_p X_cm) vcvs gain=1
CHR1m (PAM4_src_m CH1_m) resistor r=100
CHC1m (CH1_m X_cm) capacitor c=85f
CHB1m (CHB_m X_cm CH1_m X_cm) vcvs gain=1
CHR2m (CHB_m CH2_m) resistor r=100
CHC2m (CH2_m X_cm) capacitor c=85f
CHB2m (X_im X_cm CH2_m X_cm) vcvs gain=1
save X_ip X_im X_o_p X_o_m
tranResponse tran stop=22n maxstep=200f errpreset=conservative
'''


def admit_synthetic(quiet, noise=None):
    sources = {}
    for kind, data in [('noiseless', quiet), ('noise', noise or quiet)]:
        digest = hashlib.sha256(data).hexdigest()
        sources[kind] = dict(sha256=digest, original_vm_sha256=digest)
    return dict(source_decks=sources, original_model_root='<PDK_ROOT>', model_root='/private/pdk')


def point(errors, held_gap):
    return dict(symbol_errors=errors, scored_symbols=2032, held_min_gap_V=held_gap,
                FFE_MSE_target_units_squared=1e-3)


class TestSkew(unittest.TestCase):
    def test_exact_grid_pairs_and_tone_cases(self):
        plan = S.plan()
        rows = plan['cases']
        self.assertEqual(len({row['case_id'] for row in rows}), 77)
        self.assertEqual(tuple(row['delta_ui'] for row in rows if row['kind']=='pam4_noiseless'), S.SKW)
        for seed in S.SEEDS:
            self.assertEqual(tuple(row['delta_ui'] for row in rows if row['noise_seed']==seed), S.NOISY_DELTAS)
        self.assertEqual(sum(row['kind'].startswith('tone_') for row in rows), 8)
        self.assertEqual(plan['ideal_oracle']['additional_native_runs'],0)

    def test_source_overlay_preserves_every_other_byte(self):
        S.check_channel(FIXTURE)
        with self.assertRaises(ValueError):
            S.check_channel(FIXTURE.replace(b'CH2_m X_cm) capacitor c=85f',b'CH2_m X_cm) capacitor c=86f'))
        admission = admit_synthetic(FIXTURE)
        reference, _ = S.pn_stage.render_deck(FIXTURE,admission,dict(kind='pam4_noiseless',delta_ui=0.))
        self.assertEqual(reference,FIXTURE.replace(b'<PDK_ROOT>',b'/private/pdk'))
        for delta in (-.5,.5):
            out, metadata = S.pn_stage.render_deck(FIXTURE,admission,dict(kind='pam4_noiseless',delta_ui=delta))
            self.assertEqual(metadata['p_delay_s'],-metadata['n_delay_s'])
            self.assertAlmostEqual(metadata['p_delay_s']-metadata['n_delay_s'],delta*S.UI_S,places=23)
            a, b = S.pn_stage.pwl_block(out, 'PAM4Vp'), S.pn_stage.pwl_block(out, 'PAM4Vm')
            original_a, original_b = (S.pn_stage.pwl_block(reference, key) for key in ('PAM4Vp','PAM4Vm'))
            self.assertAlmostEqual(a[4][1]-b[4][1],delta*S.UI_S,places=23)
            self.assertEqual(a[5],original_a[5])
            self.assertEqual(b[5],original_b[5])
            a0,a1 = a[:2]; b0,b1 = b[:2]
            r0,r1 = original_a[:2]; s0,s1 = original_b[:2]
            self.assertEqual(out[:a0]+out[a1:b0]+out[b1:],reference[:r0]+reference[r1:s0]+reference[s1:])

    def test_ideal_inverse_has_exact_zero_skew_deck(self):
        original = FIXTURE.replace(b'errpreset=conservative',b'errpreset=conservative noisefmax=150G noisefmin=500M noiseseed=173')
        admission = admit_synthetic(FIXTURE, original)
        for delta in (-.5,.5):
            case = dict(kind='pam4_noise',delta_ui=delta, noise_seed=1001)
            reference, _ = S.pn_stage.render_deck(original,admission,dict(case,delta_ui=0.))
            oracle, _ = S.pn_stage.render_deck(original,admission,dict(case,delta_ui=delta-delta))
            self.assertEqual(oracle,reference)

    def test_56GHz_model_polarity_and_differential_loss(self):
        p, m = R.model_56(.5), R.model_56(-.5)
        self.assertAlmostEqual(p['Nyquist_DM_gain_change_dB'],-10*math.log10(2))
        self.assertAlmostEqual(p['Hdc']['imag'],-math.sqrt(2.))
        self.assertEqual(p['Hdc']['imag'],-m['Hdc']['imag'])

    def test_predeclared_label_and_missing_seed(self):
        ref = point(0, .010)
        self.assertFalse(R.effect(point(20,.0091),ref)['conspicuous_degradation'])
        self.assertTrue(R.effect(point(21,.010),ref)['conspicuous_degradation'])
        self.assertTrue(R.effect(point(0,.0089),ref)['conspicuous_degradation'])
        missing = {(0.,1001):{p:ref for p in R.POINTS},(.5,1001):{p:point(50,.003) for p in R.POINTS}}
        result = R.noise_summary(missing)['0.5']['primary']
        self.assertEqual(result['paired_count'],1)
        self.assertIsNone(result['complete_mean_degradation_label'])

    def test_held_margin_uses_fixed_secondary_inversion(self):
        score = dict(sample_count=2032, symbol_errors=0, SER=0., gray_bit_errors=0,
                     bit_count=4064, gray_BER=0., prediction_RMSE_in_target_symbol_units=.01,
                     p05_p95_eye_gaps_in_target_symbol_units=[1., 1., 1.])
        metrics = {R.SCORE: score, 'raw_held_FFE_before_ADC': score,
                   'ADC_validation_input_clipped_count': 0, 'ADC_validation_input_count': 2048}
        result = {'provenance': {'frozen_r5_sha256': R.admit.FROZEN_SHA256}, 'held_sample_csv': {},
                  'results': {point: {'metrics': metrics} for point in R.POINTS}}

        def measured(secondary_scale):
            rows = []
            for point, polarity, scale in [('primary', 1, 1.), ('secondary', -1, secondary_scale)]:
                for symbol in range(4):
                    held = polarity * scale * (symbol - 1.5) * .01
                    rows.append([point, '0', '0', '0', '0', '0', '0', str(held), str(symbol), '0'])
            with patch.object(R.guard, 'csv_readback', return_value=(None, rows)):
                return R.measured_points(None, result)

        baseline = measured(1.)
        self.assertAlmostEqual(baseline['primary']['held_min_gap_V'], .01)
        self.assertAlmostEqual(baseline['secondary']['held_min_gap_V'], .01)
        self.assertEqual(baseline['secondary']['held_frozen_polarity'], -1)
        reduced = R.effect(measured(.88)['secondary'], baseline['secondary'])
        self.assertAlmostEqual(reduced['held_min_gap_fraction_loss'], .12)
        self.assertTrue(reduced['conspicuous_degradation'])
        result['provenance']['frozen_r5_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'frozen polarity'):
            measured(1.)


if __name__ == '__main__':
    unittest.main()
