"""Offline tests for the LP NEXT AC plan, line fixture, and peaking coil."""
import math
import re
import unittest

import gm_drive_lp as prior
import lp_next as design
from next_summary import book_reports, branch_current_ratio


class SummaryMetrics(unittest.TestCase):
    def test_fine_spacing_skips_unmeasured_steps_and_pairs_matching_seams(self):
        rows = book_reports({('tt',1):{0:{0:-5.2,1:-5.0,8:-4.5},1:{0:-4.47,8:-3.75}},
                             ('ff',-1):{2:{7:3.4,8:3.2}}})
        ff,tt = rows
        self.assertTrue(ff['segments'][0]['monotone_where_measured'])
        self.assertEqual(list(tt['segments'][0]['adjacent_steps_ps']),[0])
        self.assertFalse(tt['segments'][0]['all_nine_resolved'])
        self.assertAlmostEqual(tt['seams'][0]['next_code0_minus_this_code8_ps'],.03)

    def test_drain_probe_uses_differential_paired_bank_currents(self):
        probes = {'GMSAPVD:p':[[1.,0.],[0.,0.]], 'GMSAMVD:p':[[0.,0.],[1.,0.]],
                  'GMSBPVD:p':[[0.,.01],[0.,0.]], 'GMSBMVD:p':[[0.,0.],[0.,.01]]}
        self.assertEqual(branch_current_ratio(probes,0),{'dBc':-40.,'complex':[0.,.01]})
        self.assertIsNone(branch_current_ratio(probes,2))
        self.assertIsNone(branch_current_ratio({},0))


def component(deck, name):
    pattern = rf'(?m)^{re.escape(name)} \(([^\n)]+)\) ([^\n]+)$'
    matches = re.findall(pattern, deck)
    if len(matches) != 1:
        raise AssertionError(f'Expected one {name}, found {len(matches)}')
    nodes, statement = matches[0]
    return tuple(nodes.split()), statement


def scalar(statement, field, suffix=''):
    match = re.search(rf'(?:^| ){field}=([\d.eE+-]+){suffix}(?: |$)', statement)
    if match is None:
        raise AssertionError(f'Missing {field} in {statement}')
    return float(match[1])


class LpNext(unittest.TestCase):
    def setUp(self):
        self.cases = design.build_plan()['cases']
        self.token = prior.parent.gm.original.base.MODEL_TOKEN

    def find(self, **fields):
        fields.setdefault('drive', 'p')
        matches = [case for case in self.cases if all(case.get(k) == v for k, v in fields.items())]
        self.assertTrue(matches, f'Missing planned case {fields}')
        return matches[0]

    def deck(self, case):
        deck, rails, ac, dc, currents, diff = design.render(case, self.token)
        self.assertNotRegex(deck, r'(?m)^\w+ tran\b')
        self.assertTrue(diff.startswith('--- parent.scs\n+++ bench.scs\n'))
        self.assertEqual(len(ac), len(set(ac)))
        return deck

    def test_plan_pairs_share_topology_passive_and_bias_parameters(self):
        identifiers = {case['case_id'] for case in self.cases}
        self.assertEqual(len(identifiers), len(self.cases))
        pairs = {}
        for case in self.cases:
            signature = tuple(sorted((key, repr(value)) for key, value in case.items()
                                     if key not in ('case_id', 'drive')))
            pairs.setdefault(signature, []).append(case['drive'])
        self.assertTrue(all(sorted(drives) == ['n', 'p'] for drives in pairs.values()))
        self.assertEqual({case['stage'] for case in self.cases}, {'power', 'endpoint', 'fine', 'passive'})
        self.assertEqual({case['topology'] for case in self.cases}, {'reference', 'branch', 'shared'})
        self.assertEqual({case['process'] for case in self.cases}, {'tt', 'ss', 'ff'})

    def test_ideal_coil_matches_prior_fixture(self):
        case = self.find(launch='lp14lo120', coil_Q56=None, coil_SRF_GHz=None,
                         coil_scale=1.0, count_b=0)
        rendered = self.deck(case)
        for model_root in (self.token, '/offline/tests/model_root'):
            with self.subTest(model_root=model_root):
                self.assertEqual(design.render(case, model_root), prior.render(case, model_root))
        nodes, statement = component(rendered, 'GMSAPLPK')
        self.assertEqual(nodes, ('GMSAPLP', 'GF_VDD'))
        self.assertEqual(scalar(statement, 'l', 'p'), 120.)
        self.assertNotRegex(rendered, r'(?m)^GMSAP(?:LR|LC) ')

    def test_nonideal_coil_is_series_rl_shunted_at_the_same_terminals(self):
        case = self.find(launch='lp14lo120', coil_Q56=8, coil_SRF_GHz=110)
        deck = self.deck(case)
        old_nodes = {'GMSAPLP', 'GF_VDD'}
        ln, ls = component(deck, 'GMSAPLPK')
        rn, rs = component(deck, 'GMSAPLR')
        cn, cs = component(deck, 'GMSAPLC')
        self.assertEqual(set(cn), old_nodes)
        self.assertEqual(set(ln) ^ set(rn), old_nodes)
        self.assertEqual(len(set(ln) & set(rn)), 1)
        l_h = scalar(ls, 'l', 'p') * 1e-12
        r_ohm = scalar(rs, 'r')
        c_f = scalar(cs, 'c', 'f') * 1e-15
        self.assertAlmostEqual(l_h / 1e-12, 120 * case['coil_scale'], places=6)
        self.assertAlmostEqual(2 * math.pi * 56e9 * l_h / r_ohm, case['coil_Q56'], places=6)
        self.assertAlmostEqual(1 / (2 * math.pi * math.sqrt(l_h * c_f)) / 1e9,
                               case['coil_SRF_GHz'], places=6)

    def test_inductance_tolerance_keeps_declared_q_and_self_resonance(self):
        nonideal = [case for case in self.cases if case['stage'] == 'passive' and
                    case['drive'] == 'p' and case['coil_Q56'] is not None and
                    case['coil_SRF_GHz'] is not None]
        self.assertTrue({.9, 1., 1.1}.issubset({case['coil_scale'] for case in nonideal}))
        for scale in (.9, 1.1):
            case = next(case for case in nonideal if case['coil_scale'] == scale)
            with self.subTest(case=case['case_id']):
                deck = self.deck(case)
                prefix = 'GMSHP' if case['topology'] == 'shared' else 'GMSAP'
                l_h = scalar(component(deck, prefix+'LPK')[1], 'l', 'p') * 1e-12
                r_ohm = scalar(component(deck, prefix+'LR')[1], 'r')
                c_f = scalar(component(deck, prefix+'LC')[1], 'c', 'f') * 1e-15
                self.assertAlmostEqual(l_h / 1e-12, 120*scale, places=6)
                self.assertAlmostEqual(2*math.pi*56e9*l_h/r_ohm, case['coil_Q56'], places=6)
                self.assertAlmostEqual(1/(2*math.pi*math.sqrt(l_h*c_f))/1e9,
                                       case['coil_SRF_GHz'], places=6)

    def test_shared_coil_uses_only_one_peaked_amplifier_per_leg(self):
        case = self.find(launch='shared14lo120z50', coil_Q56=None, coil_SRF_GHz=None, coil_scale=1.0)
        deck = self.deck(case)
        self.assertEqual(sum(bool(re.fullmatch(r'GMSH[PM]CS\d+', name)) for name in
                             re.findall(r'(?m)^(\w+) \(', deck)), 28)
        for leg in 'PM':
            _, coil = component(deck, 'GMSH'+leg+'LPK')
            self.assertEqual(scalar(coil, 'l', 'p'), 120.)
            for bank in 'AB':
                prefix = 'GMS'+bank+leg
                nodes, sensor = component(deck, prefix+'DRV')
                self.assertEqual(nodes, ('GMSH'+leg+'L', prefix+'L'))
                self.assertEqual(sensor, 'vsource dc=0')
                self.assertEqual(scalar(component(deck, prefix+'RT')[1], 'r'), 50.)
        self.assertNotRegex(deck, r'(?m)^GMS[AB][PM]LPK ')

    def test_z50_reference_matches_shared_line_with_independent_matched_sources(self):
        fields = dict(stage='endpoint', process='ss', count_b=2, direction=-1)
        reference = self.find(launch='idealz50', **fields)
        shared = self.find(launch='shared14lo120z50', **fields)
        self.assertEqual(reference['route_thirds'], shared['route_thirds'])
        self.assertEqual(reference['Z0_ohm'], 50.)
        self.assertEqual(shared['Z0_ohm'], 50.)
        ideal_deck, shared_deck = self.deck(reference), self.deck(shared)
        for bank, route in zip('AB', reference['route_thirds']):
            for leg, thirds in zip('PM', route):
                with self.subTest(bank=bank, leg=leg):
                    prefix = 'GMS'+bank+leg
                    feed = 'GDRPIN'+('P' if leg == 'P' else 'N')
                    self.assertEqual(component(ideal_deck, prefix+'DRV'),
                                     ((prefix+'L', 'X_cm', feed, 'X_cm'), 'vcvs gain=1'))
                    self.assertEqual(component(ideal_deck, prefix+'RS'),
                                     ((prefix+'L', prefix+'I'), 'resistor r=50'))
                    self.assertEqual(component(shared_deck, prefix+'RS'),
                                     ((prefix+'L', prefix+'I'), 'resistor r=1m'))
                    for deck in (ideal_deck, shared_deck):
                        self.assertEqual(component(deck, prefix+'RT'),
                                         ((prefix+'G', 'X_cm'), 'resistor r=50'))
                    ladder = rf'(?m)^{prefix}\d{{2}}(?:LA|RA|C|LB|RB) .*?$'
                    ideal_rows = re.findall(ladder, ideal_deck)
                    self.assertEqual(ideal_rows, re.findall(ladder, shared_deck))
                    self.assertEqual(len(ideal_rows), 5*((thirds+2)//3))
                    for row in ideal_rows:
                        section = int(row[len(prefix):len(prefix)+2])
                        scale = min(1., (thirds-3*section)/3)
                        if ' inductor ' in row:
                            self.assertAlmostEqual(scalar(row, 'l', 'p'), 13*scale, places=7)
                        elif ' capacitor ' in row:
                            self.assertAlmostEqual(scalar(row, 'c', 'f'), 10.4*scale, places=7)
                        else:
                            self.assertAlmostEqual(scalar(row, 'r'), .1525*scale, places=7)


if __name__ == '__main__':
    unittest.main()
