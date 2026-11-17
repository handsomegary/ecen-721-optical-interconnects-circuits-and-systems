"""Lock the circuit delta and check that rail diagnostics distinguish two failures."""

from unittest import TestCase

import sar7_isolate as bench


class IsolationTest(TestCase):
    def test_only_seven_inputs_and_two_sources_differ(self):
        old = bench.common.read(bench.relaxed.PLAN)['cases'][0]
        case = bench.common.read(bench.PLAN)['cases'][0]
        baseline,ref = bench.relaxed.build(old)
        result,meta = bench.build(case)
        parent = baseline.decode('ascii').splitlines()
        current = [line for line in result.decode('ascii').splitlines() if not line.startswith('EISO_')]
        changed = [(a,b) for a,b in zip(parent,current,strict=True) if a!=b]
        self.assertEqual(len(changed),7)
        self.assertTrue(all(a.startswith('XCMP') and a.replace('(mp mn ','(isop ison ')==b for a,b in changed))
        self.assertEqual(result.count(b' vcvs gain=1'),1+baseline.count(b' vcvs gain=1')+1)
        self.assertEqual(meta['wave'],ref['wave'])

    def test_rails_localize_compare_retention_vs_readout(self):
        wave = dict(vdd_V=.9,conversions=[dict(index=0,expected_code=0,end_s=2.,
                    trials=[dict(bit=6,read_s=1.,cmp_pair=['qp','qn'])],code_pairs=[['p','n']])])
        data = {'time':[0.,1.,2.],'qp':[0.,0.,0.],'qn':[.9,.9,.9],'p':[0.,0.,.3],'n':[.9,.9,.9]}
        row = bench.rails_table(data,wave)[0]['bits'][0]
        self.assertEqual((row['original_cmp'],row['final_cmp'],row['final_out']),(0,0,None))
        data.update(qp=[0.,0.,.4],qn=[.9,.9,.4])
        row = bench.rails_table(data,wave)[0]['bits'][0]
        self.assertEqual((row['original_cmp'],row['final_cmp']),(0,None))
