"""Offline regression coverage for shared replica bias and matched controls."""
import json
from pathlib import Path
import re
import unittest

import lp_bias as design
import lp_next as prior
from test_lp_next import component, scalar


ROOT = Path(__file__).resolve().parent
MODEL_TOKEN = prior.prior.parent.gm.original.base.MODEL_TOKEN


def current_A(statement):
    match = re.search(r'\bdc=([\d.eE+-]+)([munp]?)(?: |$)', statement)
    if match is None:
        raise AssertionError(f'Missing current in {statement}')
    return float(match[1]) * {'': 1., 'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12}[match[2]]


class LpBias(unittest.TestCase):
    def setUp(self):
        self.cases = design.build_plan()['cases']

    def find(self, **fields):
        fields.setdefault('drive', 'p')
        matches = [case for case in self.cases
                   if all(case.get(key) == value for key, value in fields.items())]
        self.assertTrue(matches, f'No planned case matches {fields}')
        return matches[0]

    def test_plan_separates_budget_candidates_and_upper_bounds(self):
        self.assertEqual(len({case['case_id'] for case in self.cases}), len(self.cases))
        self.assertEqual({case['bias_mode'] for case in self.cases},
                         {'reference', 'fixed_v', 'replica'})
        self.assertEqual({case['process'] for case in self.cases}, {'ss', 'tt', 'ff'})
        self.assertEqual({case['count_b'] for case in self.cases}, {0, 2})
        pairs = {}
        for case in self.cases:
            signature = json.dumps({key: val for key, val in case.items()
                                    if key not in ('case_id', 'drive')}, sort_keys=True)
            pairs.setdefault(signature, []).append(case['drive'])
            self.assertEqual(case['kind'], 'ac')
        self.assertTrue(all(sorted(drives) == ['n', 'p'] for drives in pairs.values()))
        budgets = {case['target_mA_per_leg'] for case in self.cases
                   if case['stage'] == 'bias' and case['bias_mode'] == 'replica'}
        self.assertEqual(budgets, {4.2, 4.5, 4.7, 5.0})
        upper = [case for case in self.cases if case['stage'] == 'upper']
        self.assertEqual({case['target_mA_per_leg'] for case in upper}, {5.5, 6.0})
        self.assertTrue(all(case['bias_mode'] == 'replica' for case in upper))

    def test_each_replica_sweep_has_the_required_pvt_and_bank_controls(self):
        fixed = [case for case in self.cases if case['bias_mode'] == 'fixed_v']
        fields = ('process', 'temperature_C', 'vdd_V', 'count_b', 'launch', 'route_thirds',
                  'source_R_ohm', 'Z0_ohm', 'drive')
        for case in fixed:
            for target in (4.2, 4.5, 4.7, 5.0, 5.5, 6.0):
                with self.subTest(control=case['case_id'], target=target):
                    matches = [trial for trial in self.cases if trial['bias_mode'] == 'replica'
                               and trial['target_mA_per_leg'] == target
                               and all(trial[key] == case[key] for key in fields)]
                    expected = 0 if case['process'] == 'ss' and target > 5.0 else 1
                    self.assertEqual(len(matches), expected)

    def test_fixed_and_reference_cases_match_measured_power_fixtures(self):
        measured = json.loads((ROOT/'lp_next_power_plan.json').read_text(encoding='utf-8'))['cases']
        fields = ('launch', 'topology', 'process', 'temperature_C', 'vdd_V', 'source_R_ohm',
                  'Z0_ohm', 'route_thirds', 'count_b', 'coil_Q56', 'coil_SRF_GHz', 'coil_scale', 'drive')
        control = [case for case in self.cases if case['bias_mode'] != 'replica']
        self.assertEqual({case['launch'] for case in control},
                         {'bypass', 'idealz50', 'shared14lo120z50'})
        for case in control:
            with self.subTest(case=case['case_id']):
                matches = [old for old in measured if old['stage'] == 'power' and
                           all(old[key] == case[key] for key in fields)]
                self.assertEqual(len(matches), 1)
                self.assertEqual(design.render(case, MODEL_TOKEN), prior.render(matches[0], MODEL_TOKEN))

    def test_replica_is_one_matching_unit_with_negative_feedback(self):
        case = self.find(bias_mode='replica', target_mA_per_leg=4.7)
        deck, rails, ac, dc, currents, diff = design.render(case, MODEL_TOKEN)
        self.assertEqual(component(deck, 'GMSRRD'),
                         (('GF_VDD', 'GMSR_D'), 'resistor r=462'))
        self.assertEqual(component(deck, 'GMSRRREF'),
                         (('GF_VDD', 'GMSR_REF'), 'resistor r=462'))
        self.assertEqual(component(deck, 'GMSRAMP'),
                         (('GMSR_E', '0', 'GMSR_D', 'GMSR_REF'), 'vcvs gain=1000'))
        nodes, unit = component(deck, 'GMSRCS0')
        self.assertEqual(nodes, ('GMSR_D', 'GMSR_BIAS', '0', '0'))
        self.assertEqual(re.findall(r'(?m)^GMSRCS\d+ ', deck), ['GMSRCS0 '])
        for leg in 'PM':
            self.assertEqual(component(deck, 'GMSH'+leg+'CS0')[1], unit)
            self.assertEqual(len(re.findall(r'(?m)^GMSH'+leg+r'CS\d+ ', deck)), 14)
        filter_r = re.findall(r'(?m)^\w+ \(GMSR_E GMSR_BIAS\) resistor r=(\S+)$', deck)
        filter_c = re.findall(r'(?m)^\w+ \(GMSR_BIAS 0\) capacitor c=(\S+)$', deck)
        self.assertEqual([r.lower() for r in filter_r], ['100k'])
        self.assertEqual(filter_c, ['10p'])
        self.assertTrue({'GMSR_D', 'GMSR_REF', 'GMSR_BIAS'}.issubset(dc))
        self.assertIn('GMSRIREF:p', currents)
        self.assertEqual(rails['GFVDD:p'], case['vdd_V'])
        self.assertFalse(any(name.startswith('GMSR') for name in rails))
        self.assertNotRegex(deck, r'(?m)^\w+ tran\b')
        self.assertTrue(diff.startswith('--- parent.scs\n+++ bench.scs\n'))
        saves = re.search(r'(?m)^save (.*)$', deck)[1].split()
        for trace in ('GMSR_D', 'GMSR_REF', 'GMSR_BIAS', 'GMSRIREF:p', 'GFVDD:p'):
            self.assertEqual(saves.count(trace), 1)

    def test_target_current_divides_by_fourteen_at_each_setting(self):
        for target in (4.2, 4.5, 4.7, 5.0, 5.5, 6.0):
            case = self.find(bias_mode='replica', target_mA_per_leg=target)
            with self.subTest(target=target):
                deck = design.render(case, MODEL_TOKEN)[0]
                nodes, statement = component(deck, 'GMSRIREF')
                self.assertEqual(nodes, ('GMSR_REF', '0'))
                self.assertTrue(statement.startswith('isource '))
                self.assertAlmostEqual(current_A(statement)*14, target/1000, places=11)

    def test_replica_shares_bias_and_preserves_rf_launch_and_excitation(self):
        for drive in 'pn':
            case = self.find(bias_mode='replica', target_mA_per_leg=4.7, drive=drive)
            with self.subTest(drive=drive):
                deck, rails, *_ = design.render(case, MODEL_TOKEN)
                for pn, leg, source in (('P', 'P', 'XVin'), ('N', 'M', 'PNCVN')):
                    prefix = 'GMSH'+leg
                    self.assertEqual(scalar(component(deck, source)[1], 'mag'), float(drive == pn.lower()))
                    self.assertEqual(component(deck, prefix+'CIN'),
                                     (('GDRPIN'+pn, prefix+'FG'), 'capacitor c=10p'))
                    nodes, gate_resistor = component(deck, prefix+'GB')
                    self.assertEqual(nodes, (prefix+'FG', 'GMSR_BIAS'))
                    self.assertEqual(gate_resistor.lower(), 'resistor r=10k')
                    self.assertEqual(component(deck, prefix+'LPK'),
                                     ((prefix+'LP', 'GF_VDD'), 'inductor l=120p'))
                    for bank in 'AB':
                        branch = 'GMS'+bank+leg
                        self.assertEqual(component(deck, branch+'DRV'),
                                         ((prefix+'L', branch+'L'), 'vsource dc=0'))
                        self.assertEqual(scalar(component(deck, branch+'RT')[1], 'r'), 50.)
                    self.assertNotIn(prefix+'VFG:p', rails)
                    self.assertNotRegex(deck, rf'(?m)^{prefix}VFG ')


if __name__ == '__main__':
    unittest.main()
