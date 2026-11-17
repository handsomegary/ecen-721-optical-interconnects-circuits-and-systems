"""Check all seven clock substitutions and their scorer timing."""

import unittest

import sar7_timing as pilot


class TimingPilotTests(unittest.TestCase):
    def setUp(self):
        self.original = pilot.common.read(pilot.base_plan)['cases'][0]
        self.case = pilot.common.read(pilot.PLAN)['cases'][0]

    def test_only_seven_clock_lines_change(self):
        prior, prior_meta = pilot.base_build(self.original)
        proposed, next_meta = pilot.build(self.case)
        changes = [(a.decode('ascii'), b.decode('ascii')) for a,b in
                   zip(prior.splitlines(),proposed.splitlines(),strict=True) if a!=b]
        self.assertEqual(len(changes),7)
        for index,(initial,shifted) in enumerate(changes):
            bit = pilot.native.BITS[index]
            self.assertEqual(initial,pilot.native.pulse(f'clk{bit}',116+66*index,560))
            self.assertEqual(shifted,pilot.native.pulse(f'clk{bit}',99+66*index,560))
        self.assertEqual(prior_meta['wave']['period_s'],next_meta['wave']['period_s'])
        self.assertEqual(prior_meta['wave']['saved_signals'],next_meta['wave']['saved_signals'])

    def test_same_centers_and_read_times(self):
        _, prior = pilot.base_build(self.original)
        _, new = pilot.build(self.case)
        for last,this in zip(prior['wave']['conversions'],new['wave']['conversions'],strict=True):
            for key in ('expected_code','source_diff_V','sample_s','end_s'):
                self.assertEqual(last[key],this[key])
            for old,trial in zip(last['trials'],this['trials'],strict=True):
                self.assertEqual(old['read_s'],trial['read_s'])
                self.assertEqual(old['trial_release_s'],trial['trial_release_s'])
                self.assertAlmostEqual((trial['read_s']-trial['compare_s'])*1e12,42)
                self.assertAlmostEqual((trial['compare_s']-trial['launch_s'])*1e12,21)
                self.assertAlmostEqual((trial['compare_s']-trial['pre_s'])*1e12,.5)

    def test_rejects_other_cases(self):
        with self.assertRaisesRegex(ValueError,'preserve'):
            pilot.build(dict(self.case,input_cm_V=.8))
