import itertools
import json
from collections import Counter
import re
import unittest

import sar7_native_decode as pilot


class NativeDecoderTests(unittest.TestCase):
    def test_actual_pullup_and_pulldown_truth_table(self):
        circuits = '\n'.join(pilot.decoder_subcircuits())
        for a, b, conv in itertools.product((0, 1), repeat=3):
            state = dict(a=a, b=b, en=conv, enb=1 - conv)
            for circuit, expected in (('SAR_OAI21', int(not (conv and (a or b)))),
                                      ('SAR_NOR3', int(conv and not (a or b)))):
                body = circuits.split('subckt ' + circuit + ' ', 1)[1].split('ends ' + circuit, 1)[0]
                transistors = re.findall(r'^M\w+ \((\w+) (\w+) (\w+) (\w+)\) ([np])ch', body, re.M)
                self.assertEqual(len(transistors), 6)
                reached = {'y'}
                for _ in transistors:
                    for drain, gate, source, _, polarity in transistors:
                        if state[gate] == (polarity == 'n') and ({drain, source} & reached):
                            reached.update((drain, source))
                self.assertEqual(('vdd' in reached, '0' in reached), (bool(expected), not expected),
                                 (circuit, state, reached))

    def test_bench_delta_and_schedule(self):
        _, old = pilot.fast.build(pilot.fast.case_record())
        source, new = pilot.build(pilot.case_record())
        self.assertEqual(json.loads(json.dumps(new)), new)
        baseline = pilot.fast.build(pilot.fast.case_record())[0].decode().splitlines()
        current = source.decode().splitlines()
        removed = list((Counter(baseline) - Counter(current)).elements())
        added = list((Counter(current) - Counter(baseline)).elements())
        self.assertEqual(len(removed), 43)
        self.assertTrue(all(re.match(r'^(X[OZ]b?[0-6] |V_(trial|clk)[0-6] |save )', line) for line in removed))
        self.assertEqual(len(added), 115)
        self.assertFalse(any('bsource' in line for line in added))
        self.assertEqual(sum(line.startswith('XNDLOAD') for line in added), 28)
        self.assertEqual(sum(line.startswith('XRef') for line in current), 28)
        self.assertEqual(sum(line.startswith('XBitb') for line in current), 7)
        self.assertAlmostEqual(1 / new['wave']['period_s'], 1.75e9)
        self.assertEqual(pilot.timing_schedule()[5], (162, 202, 244, 246))
        for before, after in zip(old['wave']['conversions'], new['wave']['conversions'], strict=True):
            for key in 'sample_s', 'end_s', 'expected_code', 'source_diff_V', 'code_pairs':
                self.assertEqual(before[key], after[key])
            self.assertAlmostEqual(after['read_late_s'] - after['end_s'], 3e-12, places=19)
            self.assertLess(after['trials'][-1]['trial_release_s'], after['end_s'])

    def test_overlap_proxy_includes_either_switch_polarity(self):
        grid = [i * .25e-12 for i in range(5)]
        gates = [[0, .8, .8, 0, 0], [.9] * 5, [0] * 5, [.9, .2, .2, .9, .9]]
        result = pilot.overlap_proxy(grid, gates, grid[0], grid[-1], .45)
        self.assertEqual((result['events'], result['samples']), (1, 2))
        self.assertAlmostEqual(result['max_sample_span_ps'], .25)


if __name__ == '__main__':
    unittest.main()
