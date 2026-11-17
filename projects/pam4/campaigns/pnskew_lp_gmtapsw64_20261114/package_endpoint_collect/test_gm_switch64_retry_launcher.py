"""Verify the endpoint-only launcher without starting Spectre or Slurm."""

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import gm_switch64_retry as retry


class EndpointRetryLauncher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = retry.verify_plan()

    def setUp(self):
        self.case = self.cases[84]
        self.approval = {'case_ids':[case['case_id'] for case in self.cases.values()],
                         'stages':['switch'], 'retire_new_raw':False}
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()

    def test_only_frozen_endpoint_decks_are_in_runner_scope(self):
        self.assertEqual(set(self.cases), {84,86})
        for case in self.cases.values():
            self.assertEqual(case['stage'], 'switch')
            self.assertEqual(case['stop_s'], 14e-9)
            self.assertAlmostEqual(abs(case['skew_ps']), 4.464285714285714)

    def test_launcher_supplies_same_limit_to_solver_and_collector(self):
        (self.root/self.cases[86]['case_id']).mkdir()  # The other array task may be active.
        with (patch.object(retry.gm_drive, 'approved_case', return_value=True),
              patch.object(retry.common, 'checked_root', return_value=self.root),
              patch.object(retry.gm_drive, 'run') as launch):
            retry.run(self.case, self.root, Path('/private/models'), self.approval)
            launch.assert_called_once()
        kwargs = launch.call_args.kwargs
        self.assertEqual(kwargs['max_solver_file_bytes'], 640 * 1024**2)
        self.assertIs(kwargs['plan'], retry.switch.PLAN)
        self.assertIs(kwargs['stage_case'], retry.switch.stage)
        self.assertIs(kwargs['collect_case'].func, retry.metrics.collect)
        self.assertEqual(kwargs['collect_case'].keywords['max_bytes'], kwargs['max_solver_file_bytes'])

    def test_cannot_use_broad_approval_or_overwrite_prior_case(self):
        with (patch.object(retry.gm_drive, 'approved_case', return_value=True),
              patch.object(retry.common, 'checked_root', return_value=self.root),
              patch.object(retry.gm_drive, 'run') as launch):
            invalid_approvals = (
                dict(self.approval, case_ids=[*self.approval['case_ids'], 'another_case']),
                dict(self.approval, stages=['hold','switch']),
                dict(self.approval, retire_new_raw=True),
            )
            for approval in invalid_approvals:
                with self.assertRaisesRegex(ValueError, 'Approval must bind only'):
                    retry.run(self.case, self.root, Path('/private/models'), approval)
            original = self.root/'gmsw_083_existing_reference'
            original.mkdir()
            with self.assertRaisesRegex(ValueError, 'separate retry campaign'):
                retry.run(self.case, self.root, Path('/private/models'), self.approval)
            original.rmdir()
            (self.root/self.case['case_id']).mkdir()
            with self.assertRaisesRegex(ValueError, 'no prior attempt'):
                retry.run(self.case, self.root, Path('/private/models'), self.approval)
            launch.assert_not_called()

    def test_classic_file_limit_is_applied_and_recorded(self):
        for variant, bound in (('legacy', 512 * 1024**2), ('retry', 640 * 1024**2)):
            with self.subTest(variant=variant):
                case_dir = self.root/variant
                case_dir.mkdir()
                bench = case_dir/'bench.scs'
                bench.write_bytes(b'original reviewed deck\n')
                fake_resource = SimpleNamespace(RLIMIT_FSIZE=1, RUSAGE_CHILDREN=2,
                                                setrlimit=Mock(), getrusage=lambda _: SimpleNamespace(ru_maxrss=7))

                def simulated_subprocess(argv, *, preexec_fn, **kwargs):
                    self.assertEqual(argv[1:4], ['-64','+mt=1','bench.scs'])
                    preexec_fn()
                    (case_dir/'spectre.log').write_bytes(b'Spectre completes with 0 errors, 0 warnings.\n')
                    return SimpleNamespace(returncode=0)

                options = {} if variant == 'legacy' else {'max_solver_file_bytes':bound}
                with (patch.dict(sys.modules, {'resource':fake_resource}),
                      patch.dict(os.environ, {'SLURM_JOB_ID':'757598'}),
                      patch.object(retry.common.subprocess, 'run', side_effect=simulated_subprocess),
                      patch.object(retry.common, 'raw_inventory', return_value=[])):
                    status = retry.common.run_classic(case_dir, retry.common.sha(bench), {},
                                                      1200, '/opt/bin/spectre', {}, **options)
                fake_resource.setrlimit.assert_called_once_with(fake_resource.RLIMIT_FSIZE, (bound,bound))
                self.assertEqual(status['max_solver_file_bytes'], bound)
                self.assertEqual(retry.common.read(case_dir/'execution_intent.json')['max_solver_file_bytes'], bound)
                self.assertEqual(status['status'], 'spectre_completed')
                self.assertEqual(retry.common.read(case_dir/'run_status.json'), status)
