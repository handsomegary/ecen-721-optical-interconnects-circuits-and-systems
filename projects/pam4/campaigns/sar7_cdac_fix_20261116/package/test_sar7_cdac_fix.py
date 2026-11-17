"""Verify bounded deck mutations, complete approvals and measured-gate decisions."""

import copy
from pathlib import Path
import re
from unittest import TestCase
from unittest.mock import patch

import sar7_cdac_fix as fix


class CorrectionTests(TestCase):
    def test_only_reference_and_planned_capacitors_change(self):
        old_case, = fix.common.read(fix.pilot.PLAN)['cases']
        old, old_meta = fix.pilot.build(old_case)
        old_lines = old.decode('ascii').splitlines()
        for case in fix.plan_cases():
            bench, meta = fix.build(case)
            rows = bench.decode('ascii').splitlines()
            self.assertEqual(len(rows), len(old_lines))
            approved = {'V_RHI', 'V_RLO'}|set(case['correction']['capacitance_F'])
            changed = [(a, b) for a, b in zip(old_lines, rows, strict=True) if a != b]
            self.assertTrue(changed)
            self.assertTrue(all(a.split()[0] == b.split()[0] and a.split()[0] in approved
                                for a, b in changed))
            wave = copy.deepcopy(meta['wave'])
            wave['nominal_reference_span_V'] = old_meta['wave']['nominal_reference_span_V']
            wave['nominal_low_to_main_unit_weight'] = old_meta['wave']['nominal_low_to_main_unit_weight']
            self.assertEqual(wave, old_meta['wave'])

    def test_physical_correction_conserves_main_bank_and_preserves_low_and_dummy(self):
        cases = fix.plan_cases()
        if len(cases) == 1:
            self.skipTest('Only the reference diagnostic is configured')
        original, = fix.common.read(fix.pilot.PLAN)['cases']
        parent, _ = fix.pilot.build(original)
        bench, meta = fix.build(cases[1])
        def caps(source):
            return {match[1]: float(match[2]) for line in source.decode('ascii').splitlines()
                    if (match := re.fullmatch(r'(C\S+) \([^\n]+\) capacitor c=(\S+)', line))
                    and fix.CAP_INSTANCE.fullmatch(match[1])}
        old, new = caps(parent), caps(bench)
        for name, value in new.items():
            if fix.CAP_INSTANCE.fullmatch(name):
                self.assertEqual(value, new[name[:-1]+('n' if name.endswith('p') else 'p')])
        for side in ('p', 'n'):
            self.assertAlmostEqual(sum(new['Cunit'+str(bit)+side]/fix.native.UNIT
                                       for bit in (6, 5, 4, 3)), 15., places=8)
            for bit in ('0', '1', '2', 'd'):
                for kind in ('Cunit', 'Ctop', 'Cbott'):
                    name = kind+bit+side
                    self.assertEqual(new[name], old[name])
            for bit in ('6', '5', '4', '3'):
                count = new['Cunit'+bit+side]/fix.native.UNIT
                self.assertAlmostEqual(new['Ctop'+bit+side]/fix.native.UNIT_SHUNT, count, places=8)
                self.assertAlmostEqual(new['Cbott'+bit+side]/fix.native.UNIT_SHUNT, count, places=8)
            bridge = new['Cbridge'+side]
            low = bridge+new['Cbridge_low'+side]+sum(new[kind+bit+side]
                      for kind in ('Cunit', 'Ctop') for bit in ('0', '1', '2', 'd'))
            self.assertAlmostEqual(meta['wave']['nominal_low_to_main_unit_weight'], bridge/low, places=12)

    def test_arbitrary_circuit_and_input_changes_are_rejected(self):
        case = copy.deepcopy(fix.plan_cases()[0])
        case['input_cm_V'] += .01
        with self.assertRaises((ValueError, AssertionError, RuntimeError)):
            fix.build(case)
        case = copy.deepcopy(fix.plan_cases()[0])
        case['correction']['capacitance_F'] = {'Cunrelatedp': 1e-15, 'Cunrelatedn': 1e-15}
        with self.assertRaises((ValueError, AssertionError, RuntimeError)):
            fix.build(case)

    def test_approval_binds_every_case_and_deck(self):
        verified = [(case, fix.build(case)[1]) for case in fix.plan_cases()]
        with patch.object(fix.common, 'sha', return_value='a'*64):
            approval = fix.expected_approval(Path('/campaign'), verified)
        self.assertEqual(approval['design_source_sha256'], 'a'*64)
        self.assertEqual(approval['case_ids'], [case['case_id'] for case, _ in verified])
        self.assertEqual(approval['deck_sha256_by_case'],
                         {case['case_id']: meta['portable_sha256'] for case, meta in verified})
        self.assertTrue(approval['approved'])

    def test_gate_boundaries_and_incomplete_or_inconsistent_results(self):
        def result(peak, total, valid=True, cm=4):
            return dict(valid=valid, final_cm_change_mV=[-cm, -cm],
                        comparator=dict(max_abs_code_error=peak, sum_abs_code_error=total),
                        registered=dict(max_abs_code_error=peak, sum_abs_code_error=total))
        for row, expected in (
            (result(1, 12), 'STOP_TARGET'),
            (result(2, 8), 'STOP_CONVERGED'),
            (result(5, 23), 'ALLOW_INDEX1'),
            (result(5, 24), 'STOP_REVIEW'),
            (result(6, 23), 'STOP_REVIEW'),
            (result(1, 1, valid=False), 'STOP_REVIEW'),
            (result(1, 1, cm=10.00001), 'STOP_REVIEW'),
        ):
            self.assertEqual(fix.gate_recommendation(row)['recommendation'], expected)

    def test_gate_refuses_missing_evidence_and_does_not_collect(self):
        directory = fix.ROOT.parent/'__nonexistent_sar7_gate_evidence__'
        self.assertFalse(directory.exists())
        with patch.object(fix.base, 'collect') as collect:
            with self.assertRaises((ValueError, AssertionError, RuntimeError, OSError)):
                fix.measured_gate(directory, fix.plan_cases())
            collect.assert_not_called()

    def test_index1_refused_for_every_stop_recommendation(self):
        for reason in ('STOP_TARGET', 'STOP_CONVERGED', 'STOP_REVIEW'):
            with patch.object(fix, 'measured_gate', return_value={'recommendation': reason}):
                with self.assertRaises((ValueError, AssertionError, RuntimeError)):
                    fix.require_index1_gate(Path('/campaign'), fix.plan_cases())
