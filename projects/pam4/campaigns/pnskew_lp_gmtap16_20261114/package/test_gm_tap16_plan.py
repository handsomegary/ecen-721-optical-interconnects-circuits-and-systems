import unittest

import gm_tap16 as design


class Fine16Plan(unittest.TestCase):
    def test_controls_symmetric_and_legacy_consistent(self):
        for code in range(-16,17):
            weights = design.distribution(code,16)
            self.assertEqual(sum(weights),16)
            self.assertEqual(weights,design.distribution(-code,16)[::-1])
            if code%2==0:
                self.assertEqual(weights,tuple(2*x for x in design.distribution(code,8)))
        with self.assertRaises(ValueError):
            design.distribution(15,8)

    def test_first_batch_and_every_pair_reference(self):
        cases = design.build_plan()['cases']
        first = cases[:design.PILOT_COUNT]
        self.assertEqual((len(first),len(cases)),(48,432))
        self.assertEqual({c['code'] for c in first if c['group']=='pilot'},
                         {0,13,-13,14,-14,15,-15,16,-16})
        index = {c['fixture_id']:c for c in cases[::2]}
        self.assertEqual(len(index),len(cases)//2)
        for pos,neg in zip(cases[::2],cases[1::2]):
            self.assertEqual((pos['drive'],neg['drive']),('p','n'))
            self.assertEqual({k:v for k,v in pos.items() if k not in ('case_id','drive')},
                             {k:v for k,v in neg.items() if k not in ('case_id','drive')})
            if pos['oracle_fixture_id']:
                reference = index[pos['oracle_fixture_id']]
                self.assertEqual(reference['process'],pos['process'])
                self.assertEqual(reference['code'],pos['code'])
                loads = [(a,w) for a,w in zip(pos['anchors'],pos['weights']) if w]
                self.assertEqual(loads,list(zip(reference['anchors'],reference['weights'])))
        for proc in design.CORNERS:
            self.assertEqual({c['code'] for c in cases if c['group'] in ('pilot','map') and c['process']==proc},
                             set(range(-16,17)))

    def test_legacy_ss_controls_reproduce_prior_decks(self):
        cases = design.build_plan()['cases']
        old = design.prior.build_plan()['cases']
        model = design.endpoint.BASE.MODEL_TOKEN
        for i,j in ((0,0),(2,10),(4,14),(6,18),(8,34),(10,38)):
            self.assertEqual(design.render(cases[i],model)[0],design.prior.render(old[j],model)[0])
