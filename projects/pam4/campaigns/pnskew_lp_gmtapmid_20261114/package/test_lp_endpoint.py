import re
import unittest

import lp_endpoint as endpoint
import lp_integrate as integrated
import lp_next as coil


class EndpointCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = endpoint.build_plan()['cases']

    def deck(self, index):
        return endpoint.render(self.cases[index],endpoint.BASE.MODEL_TOKEN)[0]

    def test_balanced_unique_paired_plan(self):
        cases = self.cases
        self.assertEqual(len(cases),296)
        self.assertEqual(len({c['case_id'] for c in cases}),296)
        for p,n in zip(cases[::2],cases[1::2]):
            fields = p.keys()-{'drive','case_id'}
            self.assertEqual({k:p[k] for k in fields},{k:n[k] for k in fields})
            self.assertEqual((p['drive'],n['drive']),('p','n'))

    def test_nominal_stays_identical_to_integrated_native(self):
        case = self.cases[32]
        self.assertEqual(self.deck(32),integrated.render(case,endpoint.BASE.MODEL_TOKEN)[0])
        self.assertIn('XVb (X_vb 0) vsource dc=0.58',self.deck(32))
        self.assertIn('GMSRRD (GF_VDD GMSR_D) resistor r=462',self.deck(32))

    def test_ablation_preserves_the_other_components(self):
        def matches(index):
            return {name:row for row in self.deck(index).splitlines() if
                    re.fullmatch(r'GMSH[PM]L(?:PK|R|C)',name:=row.split(' ',1)[0])}
        ideal,nominal = matches(30),matches(32)
        r_only,c_only = matches(36),matches(38)
        for prefix in ('GMSHP','GMSHM'):
            self.assertEqual(r_only[prefix+'LR'],nominal[prefix+'LR'])
            self.assertNotIn(prefix+'LC',r_only)
            self.assertEqual(c_only[prefix+'LC'],nominal[prefix+'LC'])
            self.assertNotIn(prefix+'LR',c_only)
            self.assertEqual(c_only[prefix+'LPK'],ideal[prefix+'LPK'])
        for i,lengths in ((58,(108,108)),(60,(132,132)),(62,(108,132)),(64,(132,108))):
            row = matches(i)
            for leg,length in zip('PM',lengths):
                prefix = 'GMSH'+leg
                self.assertTrue(row[prefix+'LPK'].endswith(f'l={length}p'))
                self.assertEqual(row[prefix+'LR'],nominal[prefix+'LR'])
                self.assertEqual(row[prefix+'LC'],nominal[prefix+'LC'])

    def test_endpoint_sign_mirror_and_fine_seam_not_collapsed(self):
        self.assertEqual(self.cases[82]['route_thirds'],
                         [list(reversed(x)) for x in self.cases[74]['route_thirds']])
        first,last = self.cases[138],self.cases[140]
        self.assertEqual((first['count_b'],last['count_b']),(8,0))
        self.assertEqual(first['route_thirds'][1],last['route_thirds'][0])
        self.assertNotEqual(first['route_thirds'][0],last['route_thirds'][1])
        self.assertIn('GMSBVE7 (GMSBEN7 0) vsource dc=0.9',self.deck(138))
        self.assertIn('GMSBVE7 (GMSBEN7 0) vsource dc=0',self.deck(140))
        self.assertNotEqual(self.deck(138),self.deck(140))
