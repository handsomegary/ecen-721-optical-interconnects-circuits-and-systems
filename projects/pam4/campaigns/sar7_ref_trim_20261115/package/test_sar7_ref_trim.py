"""Check the reference midpoint, scope and final-read margin."""

from unittest import TestCase

import sar7_ref_trim as trim


class TrimTest(TestCase):
    def setUp(self):
        self.case = trim.common.read(trim.PLAN)['cases'][0]
        old = trim.common.read(trim.relaxed.PLAN)['cases'][0]
        self.prev,self.ref = trim.relaxed.build(old)
        self.result,self.meta = trim.build(self.case)

    def test_only_reference_pair_changes(self):
        rows = [a.split()[0] for a,b in zip(self.prev.splitlines(),self.result.splitlines(),strict=True) if a!=b]
        self.assertEqual(rows,[b'V_RHI',b'V_RLO'])
        hi,lo = (float(x[1]) for x in trim.REFERENCE.findall(self.result))
        self.assertAlmostEqual((hi+lo)/2,.45)
        self.assertAlmostEqual(hi-lo,self.ref['wave']['nominal_reference_span_V']*(127/107.16))

    def test_only_final_read_moves(self):
        for a,b in zip(self.ref['wave']['conversions'],self.meta['wave']['conversions'],strict=True):
            self.assertEqual({k:v for k,v in a.items() if k!='end_s'},{k:v for k,v in b.items() if k!='end_s'})
            self.assertAlmostEqual((b['end_s']-a['end_s'])*1e12,3)
            at_ps = b['end_s']*1e12-b['index']*trim.relaxed.PERIOD_PS
            self.assertLess(at_ps,trim.relaxed.END_PS+3.5)
        self.assertEqual(self.meta['wave']['stop_s'],self.ref['wave']['stop_s'])
