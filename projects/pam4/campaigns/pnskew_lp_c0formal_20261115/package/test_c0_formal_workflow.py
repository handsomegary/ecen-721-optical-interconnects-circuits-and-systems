"""Exercise the three formal C0 stages with an offline solver stub."""

from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from shutil import copyfileobj
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import c0_formal as driver
import c0_formal_score as score


common = driver.common


def copy_exclusive(source, target):
    with Path(source).open('rb') as src, Path(target).open('xb') as dst:
        copyfileobj(src, dst)


class CampaignDate(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026,11,15,tzinfo=timezone.utc).astimezone(tz)


class FormalWorkflow(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(TemporaryDirectory(prefix='c0-formal-test-'))).resolve()
        package = self.root/'test-manifest.txt'
        package.write_text('local test fixture\n', encoding='ascii')
        stack.enter_context(patch.object(driver, 'MANIFEST', package))
        self.approval = self.root/'approval.json'
        common.write_new(self.approval, dict(approved=True, platform='Olympus', campaign=driver.SCHEMA,
                        design_source_sha256=common.sha(package)))
        if os.name == 'nt':
            stack.enter_context(patch.object(os, 'getuid', return_value=self.root.stat().st_uid, create=True))
            stack.enter_context(patch.object(driver.original, 'lock_case', return_value=nullcontext()))
            stack.enter_context(patch.object(os, 'link', side_effect=copy_exclusive))
            resource = SimpleNamespace(RLIMIT_FSIZE=1, RUSAGE_CHILDREN=2,
                                       getrusage=lambda _: SimpleNamespace(ru_maxrss=280000))
            stack.enter_context(patch.dict(sys.modules, resource=resource))
        stack.enter_context(patch.dict(os.environ, SLURM_JOB_ID='1000'))
        stack.enter_context(patch.object(driver, 'datetime', CampaignDate))
        stack.enter_context(patch.object(common, 'checked_root', side_effect=lambda root: root))
        stack.enter_context(patch.object(common, 'environment', return_value=('/fixture/spectre', {'SPECTRE_DEFAULTS':'-E'})))
        stack.enter_context(patch.object(driver.original.model_preflight, 'verify_private_kit',
                                         return_value={'model_root':'/fixture/private-models'}))
        self.child = stack.enter_context(patch.object(common.subprocess, 'run', side_effect=self.solve))
        stack.enter_context(patch.object(score, 'measure', side_effect=self.measure))
        self.functions = score.aligned.scoring_functions()
        self.frozen = score.review.pinned_r5()

    def solve(self, args, *, cwd, timeout, **_):
        self.assertEqual(args, ['/fixture/spectre', *driver.original.ARGUMENTS])
        self.assertEqual(timeout, driver.TIMEOUT_S)
        (cwd/'spectre.log').write_text('scalefactor = 0.900\nSpectre completes with 0 errors, 3 warnings.\n',
                                      encoding='ascii')
        (cwd/'raw').mkdir()
        (cwd/score.review.RAW_NAME).write_bytes(b'fixture retained bytes\n')
        return SimpleNamespace(returncode=0)

    def measure(self, directory, meta, calibration):
        symbols = driver.deck.symbols(meta['stimulus'])
        records = {}
        for plane, sign, extra_ui in (('primary', 1, .4), ('secondary', -1, 4.)):
            records[plane] = []
            for index, symbol in enumerate(symbols, start=3):
                time = driver.deck.T0 + (index+extra_ui)*score.review.UI
                records[plane].append((index, sign*.012*(symbol-1.5), time, time, index%8))
        report = score.score_records(meta, records, calibration, self.functions, self.frozen)
        report.update(run_status_sha256=common.sha(directory/'run_status.json'),
                      tran_sha256=common.sha(directory/score.review.RAW_NAME))
        metric = driver.metric(report)
        if calibration is None:
            metric['prediction_RMSE_in_target_symbol_units'] = {0:.21, -1:.24, 1:.18}[meta['phase']]
        elif meta['stimulus']=='training':
            # Profile a has an exact tie. Profile b chooses +60. Both see all three candidates.
            metric['prediction_RMSE_in_target_symbol_units'] = {
                'a':{0:.31,-60:.31,60:.33}, 'b':{0:.48,-60:.62,60:.26},
            }[meta['condition']][meta['code']]
        elif meta['condition']=='b':
            errors = 2 if meta['code']==60 else 15
            metric.update(symbol_errors=errors, gray_bit_errors=errors, SER=errors/496)
        return report

    def stage(self, stage, jobs=None):
        calibration, pins = driver.inputs(self.root, stage)
        return [driver.run(self.root, job, calibration, pins, self.root/'mock-model', self.approval)
                for job in (driver.jobs(self.root, stage) if jobs is None else jobs)]

    def test_training_selection_is_bound_to_shared_phase_and_fresh_payload(self):
        self.stage('phase')
        phase = driver.select_phase(self.root)
        self.assertEqual(phase['phase'], 1)
        code_jobs = driver.jobs(self.root, 'code')
        for profile in driver.PROFILES:
            self.assertEqual([code for condition,code,_,_ in code_jobs if condition==profile], list(driver.CODES))
        code_reports = self.stage('code')
        codes = driver.select_codes(self.root)
        self.assertEqual(codes['codes'], {'a':0, 'b':60})
        payload_jobs = driver.jobs(self.root, 'payload')
        self.assertEqual(payload_jobs, [('zero',0,1,'payload'), ('a',0,1,'payload'),
                                       ('b',0,1,'payload'), ('b',60,1,'payload')])
        self.stage('payload', payload_jobs[:-1])
        # A missing final run has no valid summary.
        with self.assertRaises((FileNotFoundError, ValueError)):
            driver.summarize(self.root)
        last, = self.stage('payload', payload_jobs[-1:])
        self.assertNotEqual(last['capture_window']['symbol_sha256'], code_reports[-1]['capture_window']['symbol_sha256'])
        self.assertEqual(last['capture_window']['tx_symbol_indices'], [128,640])
        stored_phase = json.loads((self.root/driver.PHASE_FILE).read_text(encoding='utf-8'))
        self.assertEqual(stored_phase['calibration'], phase['calibration'])
        self.assertEqual(codes['phase_sha256'], common.sha(self.root/driver.PHASE_FILE))
        summary = driver.summarize(self.root)
        self.assertEqual(summary['phase'], phase['phase'])
        self.assertEqual(summary['payload_symbol_sha256'], last['capture_window']['symbol_sha256'])
        self.assertTrue(summary['pairs']['a']['shared_payload_run'])
        self.assertEqual(summary['pairs']['a']['delta_SER'], {'primary':0, 'secondary':0})
        self.assertLess(summary['pairs']['b']['delta_SER']['primary'], 0)
        self.assertEqual(len(summary['resources']), 4)
        calibration, pins = driver.inputs(self.root, 'payload')
        self.assertEqual(phase['calibration'], calibration)
        self.assertEqual(summary['selection_files_sha256'], pins)
        self.assertEqual(driver.collect(self.root, payload_jobs[-1], calibration, pins), last)
        self.assertEqual(self.child.call_count, 13)


if __name__ == '__main__':
    unittest.main()
