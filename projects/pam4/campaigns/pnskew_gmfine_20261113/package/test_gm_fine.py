import re
import unittest

import gm_fine as fine
import fine_summary
import transient_plan


class GMFine(unittest.TestCase):
    def setUp(self):
        self.cases=fine.build_plan()['cases']
        self.token=fine.gm.original.base.MODEL_TOKEN

    def deck(self,k):
        return fine.render(self.cases[k],self.token)[0]

    def test_plan_pairs_have_unique_ids_and_local_constant_mean(self):
        pairs={}
        for c in self.cases:
            pairs.setdefault(fine_summary.key(c),set()).add(c['drive'])
            self.assertEqual(sum(c['route_a']),22 if c['route_a']!=[1,1] else 2)
            self.assertEqual(sum(c['route_b']),22)
        self.assertEqual(len({c['case_id'] for c in self.cases}),len(self.cases))
        self.assertEqual(len(pairs)*2,len(self.cases))
        self.assertTrue(all(v=={'p','n'} for v in pairs.values()))

    def test_all_nine_codes_preserve_eight_enabled_tail_slices_each_leg(self):
        codes=[c for c in self.cases if c['mode']=='interpolation' and c['route_a']==[6,16] and c['drive']=='p']
        self.assertEqual([c['count_b'] for c in codes],list(range(9)))
        for c in codes:
            deck=fine.render(c,self.token)[0]
            for leg in 'PM':
                on=re.findall(r'^GMS[AB]'+leg+r'T\d+ \([^ ]+ X_vb [^\n]+',deck,re.M)
                self.assertEqual(len(on),8)

    def test_native_bias_and_clamp_preserve_rf_topology(self):
        text=self.deck(10)
        self.assertIn('GMSAVE0 (GMSAEN0 0) vsource dc=0.9',text)
        self.assertIn('GMSBVE0 (GMSBEN0 0) vsource dc=0',text)
        self.assertIn('GMSABP0 (GMSAVB0 GMSAEB0 X_vb GF_VDD)',text)
        self.assertIn('GMSBPF0 (GF_VDD GMSBPFG GMSBPFO 0)',text)
        self.assertIn('GMSBPCL0 (GMSBPFO GF_CTL 0 0)',text)
        self.assertIn('GMSAPCL0 (GMSAPFO 0 0 0)',text)
        self.assertIn('GMSBPDRV (PNC_PREP GMSBPVIN) vsource dc=0',text)
        self.assertIn('GMSBPRT (GMSBPG X_cm) resistor r=25',text)
        self.assertIn('GMSBPCOUT (GMSBPFO GMSBPL) capacitor c=10p',text)
        self.assertIn('GMSAPT0 (GMSAPS GMSAVB0 GMSAPZ 0)',text)
        self.assertIn('GMSBPT0 (GMSBPS GMSBVB0 GMSBPZ 0)',text)

    def test_dormant_probe_has_same_tail_bias(self):
        full=self.deck(10)
        off=self.deck(12)
        self.assertIn('GMSAPDRV (GMSAPVIN X_cm) vsource dc=0',off)
        self.assertIn('GMSBPDRV (PNC_PREP GMSBPVIN) vsource dc=0',off)
        for name in ('GMSAVE','GMSBVE','GMSAPVFG','GMSBPVFG','GMSAPCL','GMSBPCL'):
            self.assertEqual([l for l in full.splitlines() if l.startswith(name)],
                             [l for l in off.splitlines() if l.startswith(name)])

    def test_transient_seed_census(self):
        cases=transient_plan.build()['paired_noise_cases']
        self.assertEqual(len(cases),60)
        self.assertEqual({(x['seed'],x['injected_UI']) for x in cases},
                         {(s,d) for s in range(1001,1021) for d in (0,-.5,.5)})
        self.assertEqual(sum(x['wave']=='first_nine' for x in cases),9)


if __name__=='__main__':
    unittest.main()
