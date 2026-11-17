"""Check actual control-state features and bounded retrospective observations."""

from random import Random
from unittest import TestCase

import sar7_cdac_round2_audit as audit


class RetainedAuditTest(TestCase):
    def test_actual_control_word_is_not_replaced_by_final_prefix(self):
        bits = [1,0,1,0,1,1,0]
        pairs = [[f'p{bit}',f'n{bit}'] for bit in range(6,-1,-1)]
        values = {'time':[0.,1.]}
        for (p,n),bit in zip(pairs,bits,strict=True):
            values[p] = [.9*bit]*2
            values[n] = [.9*(1-bit)]*2
        state = audit.control_state(values,values['time'],pairs,.5,.9)
        self.assertEqual(state['bits_b6_to_b0'],bits)
        self.assertEqual(state['control_word'],86)
        final_code,current_bit = 64,4
        inferred = (final_code>>(current_bit+1)<<(current_bit+1)) | (1<<current_bit)
        self.assertEqual(inferred,80)
        self.assertNotEqual(state['control_word'],inferred)

    def test_identifiable_fit_with_actual_sample_feature(self):
        random = Random(760874)
        known = [64.,32.,16.,8.,3.9,2.05,1.02]
        rows = []
        for index in range(12):
            sample_lsb = random.uniform(-60,60)
            for _ in range(7):
                bits = [random.randrange(2) for _ in known]
                target = 63.25+.992*sample_lsb-sum(w*b for w,b in zip(known,bits,strict=True))
                rows.append((index,[1.,sample_lsb/64,*bits],target))
        result = audit.old_audit.gain_record(rows)
        self.assertEqual(result['heldout_points'],84)
        self.assertAlmostEqual(result['sample_gain'],.992)
        self.assertAlmostEqual(result['offset_lsb'],63.25)
        for actual,expected in zip(result['weight_b6_to_b0_lsb'],known,strict=True):
            self.assertAlmostEqual(actual,expected)
        self.assertLess(result['heldout_rmse_lsb'],1e-9)

    def test_sparse_observations_keep_native_seconds_and_read_boundary(self):
        values = dict(time=[0.,100e-12],hp=[0.,.1],hn=[0.,0.],
                      sensep=[0.,.05],sensen=[0.,0.],qp=[0.,.9],qn=[.9,0.])
        wave = dict(dac_pair=['hp','hn'],vdd_V=.9)
        trial = dict(compare_s=10e-12,read_s=50e-12,cmp_pair=['qp','qn'])
        observations = audit.sparse_observations(values,wave,trial)
        self.assertEqual([r['offset_from_compare_ps'] for r in observations],[0.,.25,.5,1.,2.,5.,15.,30.])
        self.assertTrue(all(r['at_s']<=trial['read_s'] for r in observations))
        self.assertAlmostEqual(observations[0]['held_diff_V'],.01)
        self.assertAlmostEqual(observations[0]['sense_diff_V'],.005)
        self.assertEqual(observations[0]['comparator_class'],0)
