import difflib
import types
import unittest

import lp_signoff as signoff
import xt2_readback as xt2


class SignoffTests(unittest.TestCase):
    def test_replica_diff(self):
        cases = signoff.build_plan()['cases']
        for c in cases[:4]:
            token = signoff.BASE.MODEL_TOKEN
            old = signoff.diag.render(dict(c,stage='stb'),token)[0]
            new = signoff.render(c,token)[0]
            self.assertIn('replicaSTB stb start=1 stop=1G dec=50',old)
            self.assertEqual(new,old.replace('replicaSTB stb start=1 stop=1G dec=50',
                                              'replicaSTB stb start=1 stop=20G dec=100'))

    def test_coils_are_only_circuit_change(self):
        cases = signoff.build_plan()['cases']
        self.assertEqual(len(cases),40)
        for c in cases[26:]:
            token = signoff.BASE.MODEL_TOKEN
            ideal = signoff.render(dict(c,coil_Q56=None,coil_SRF_GHz=None),token)[0]
            lossy = signoff.render(c,token)[0]
            edits = [line for line in difflib.ndiff(ideal.splitlines(),lossy.splitlines())
                     if line[:2] in ('- ','+ ')]
            self.assertEqual(sorted(line.split()[1] for line in edits),
                             ['GMSHMLC','GMSHMLPK','GMSHMLPK','GMSHMLR',
                              'GMSHPLC','GMSHPLPK','GMSHPLPK','GMSHPLR'])

    def test_held_samples_scale_and_pair(self):
        time = [i*xt2.diag.UI for i in range(100)]
        data = {'time':time}
        for lane in range(8):
            data.update({f'X_ck{lane}':[.81 if (i-lane)%8<4 else 0. for i in range(100)],
                         f'X_h{lane}p':[i/1000 for i in range(100)],
                         f'X_h{lane}m':[0.]*100})
        waves = xt2.falling_samples(types.SimpleNamespace(values=data),
                                    dict(stop_s=time[-1],settle_after_s=0,vdd_V=.81))
        self.assertEqual(len(waves),8)
        half = waves[0]
        full = [(t,2*y) for t,y in half]
        result = xt2.metrics(full,half,2.)
        self.assertAlmostEqual(result['gain_change_dB'],0)
        self.assertAlmostEqual(result['affine_residual_rms_mV'],0)
        with self.assertRaises(ValueError):
            xt2.metrics(full[1:],half[:-1],2.)
