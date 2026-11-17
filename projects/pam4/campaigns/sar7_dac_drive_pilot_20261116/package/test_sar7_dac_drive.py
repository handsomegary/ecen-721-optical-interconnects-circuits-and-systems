import re
import unittest

import sar7_dac_drive as drive


class DacDriveTests(unittest.TestCase):
    def test_narrow_diff_and_truth_table(self):
        case, summary = drive.verify()
        actual, meta = drive.build(case)
        original, parent = drive.fast.build(drive.fast.case_record())
        new = actual.decode('ascii').splitlines()
        old = original.decode('ascii').splitlines()
        restored = [re.sub(r'\bff_(c(?:b)?[0-6][zo])\b', r'\1', line) if line.startswith('XRef') else
                    (' '.join(line.split()[:-len(drive.EXTRA_SAVES)]) if line.startswith('save ') else line)
                    for line in new if not line.startswith('FF_')]
        self.assertEqual(restored, old)
        self.assertEqual(len(new) - len(old), 36)
        self.assertEqual(len([line for line in new if line.startswith('XRef') and ' ff_c' in line]), 28)
        self.assertEqual(meta['wave']['conversions'], parent['wave']['conversions'])
        env = dict(vdd=.9, clip=lambda v: min(max(v, 0), 1))
        for conv, trial, q in ((c,t,q) for c in (0,.9) for t in (0,.9) for q in (0,.9)):
            voltages = dict(vdd=.9, conv=conv)
            voltages.update({f'trial{k}':trial for k in drive.BITS})
            voltages.update({f'q{k}p':q for k in drive.BITS})
            for card in drive.bsource_cards():
                output = card.split()[1][1:]
                expr = re.sub(r'v\((\w+)\)', r'v["\1"]', card.split(' bsource v=', 1)[1])
                voltages[output] = eval(expr, {'__builtins__': {}, 'min': min, 'max': max, 'v': voltages})
            one = conv and (trial or q)
            zero = conv and not (trial or q)
            for k in drive.BITS:
                self.assertEqual(voltages[f'ff_c{k}o'], .9 if one else 0.)
                self.assertEqual(voltages[f'ff_c{k}z'], .9 if zero else 0.)
                self.assertEqual(voltages[f'ff_cb{k}o'], 0. if one else .9)
                self.assertEqual(voltages[f'ff_cb{k}z'], 0. if zero else .9)

    def test_edge_time_not_dependent_on_an_exact_sample(self):
        ps = drive.native.PS
        times = [x*ps for x in (0, 1, 2, 3, 4, 5)]
        xs = [0, .3, .6, .9, .8, .2]
        self.assertEqual(drive.crossings_ps(times, xs, .45, .5*ps, 5*ps, 1*ps),
                         [[.5, 'rise'], [3.5833, 'fall']])


if __name__ == '__main__':
    unittest.main()
