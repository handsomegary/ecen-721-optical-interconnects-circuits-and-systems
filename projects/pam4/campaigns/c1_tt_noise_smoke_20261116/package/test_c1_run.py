"""Exercise the staged pilot gate and idempotent solve paths without Spectre."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import c1_run as runner


class C1RunTests(TestCase):
    def test_pair_requires_valid_pilot_before_staging(self):
        cases = [dict(case_id='pilot'),dict(case_id='pair')]
        with TemporaryDirectory() as work, patch.object(runner,'read_report',side_effect=ValueError('pilot unavailable')), \
                patch.object(runner,'stage') as stage:
            with self.assertRaisesRegex(ValueError,'pilot unavailable'):
                runner.run(Path(work),1,cases,{},{},None,'test')
            stage.assert_not_called()

    def test_existing_solver_run_only_collects(self):
        cases = [dict(case_id='pilot')]
        with TemporaryDirectory() as work:
            directory = Path(work)
            (directory/'run_status.json').touch()
            with patch.object(runner.common,'checked_root',return_value=directory), \
                    patch.object(runner,'stage',return_value=directory), \
                    patch.object(runner,'collect',return_value={'collected':True}) as collect, \
                    patch.object(runner.common,'run_classic') as solver:
                self.assertEqual(runner.run(directory,0,cases,{},{},None,'test'),{'collected':True})
                solver.assert_not_called()
                collect.assert_called_once_with(directory,cases[0],{},{},'test')
