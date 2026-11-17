"""Verify the slower control keeps electrical values and changes only timing."""

from unittest import TestCase

import sar7_relaxed as pilot


class RelaxedTest(TestCase):
    def setUp(self):
        self.case = pilot.common.read(pilot.PLAN)['cases'][0]
        self.old,self.base = pilot.base_build(pilot.common.read(pilot.base_plan)['cases'][0])
        self.new,self.meta = pilot.build(self.case)

    def test_diff_and_source_voltages(self):
        changes = [(x,y) for x,y in zip(self.old.splitlines(),self.new.splitlines(),strict=True) if x!=y]
        self.assertEqual(len(changes),25)
        for old,new in changes:
            if old.startswith((b'V_srcp ',b'V_srcn ')):
                self.assertEqual(old.split(b' wave=[')[1][:-1].split()[1::2],
                                 new.split(b' wave=[')[1][:-1].split()[1::2])

    def test_windows_and_centers(self):
        old = self.base['wave']['conversions']
        wave = self.meta['wave']
        for a,b in zip(old,wave['conversions'],strict=True):
            self.assertEqual(a['expected_code'],b['expected_code'])
            self.assertEqual(a['source_diff_V'],b['source_diff_V'])
            self.assertAlmostEqual(b['sample_s']/1e-12-b['index']*pilot.PERIOD_PS,67)
            for t in b['trials']:
                self.assertAlmostEqual((t['compare_s']-t['launch_s'])/1e-12,60)
                self.assertAlmostEqual((t['read_s']-t['compare_s'])/1e-12,60)
                self.assertLess(t['trial_release_s'],b['end_s'])
        self.assertGreater(wave['stop_s'],wave['conversions'][-1]['end_s'])

    def test_limits_to_one_case(self):
        with self.assertRaises(ValueError):
            pilot.build(dict(self.case,source_resistance_ohm=500))
