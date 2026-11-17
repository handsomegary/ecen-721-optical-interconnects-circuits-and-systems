"""Check the re-score handoff with original run records and a stubbed scorer."""

from contextlib import ExitStack, nullcontext
import os
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import c0_rescore as driver


COLLECTOR_SHA = 'c'*64
common = driver.common
runner = driver.original


def copy_exclusive(source, target):
    with Path(source).open('rb') as src, Path(target).open('xb') as dst:
        copyfileobj(src, dst)


def previous_metrics(raw_errors, adc_errors):
    def ffe(errors):
        return {'symbol_errors':errors, 'sample_count':240, 'SER':errors/240,
                'gray_bit_errors':errors, 'prediction_RMSE_in_target_symbol_units':2.55}

    return {'raw_held_FFE_before_ADC':ffe(raw_errors), 'ideal7bit_ADC_then_FFE':ffe(adc_errors),
            'ADC_validation_input_count':256, 'FFE_validation_output_count':240,
            'validation_fitting_performed':False}


class C0Recovery(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(TemporaryDirectory(prefix='c0-aligned-test-'))).resolve()
        self.cases = common.read(runner.PLAN)['cases']
        if os.name == 'nt':
            stack.enter_context(patch.object(os, 'getuid', return_value=self.root.stat().st_uid, create=True))
            stack.enter_context(patch.object(driver.original, 'lock_case', return_value=nullcontext()))
            stack.enter_context(patch.object(os, 'link', side_effect=copy_exclusive))
        stack.enter_context(patch.object(common, 'environment', side_effect=AssertionError('solver environment used')))
        stack.enter_context(patch.object(common, 'run_classic', side_effect=AssertionError('solver called')))

    def staged_completed(self, index, job):
        case = self.cases[index]
        directory = self.root/case['case_id']
        directory.mkdir()
        deck, record = runner.staged_record(case, {'model_root':'/fixture/private-models'})
        (directory/'bench.scs').write_bytes(deck)
        common.write_new(directory/'case.json', record)
        (directory/'.study_owned').write_text(job+'\n', encoding='ascii')
        (directory/'runner_stdout.log').write_bytes(b'')
        (directory/'spectre.log').write_bytes(b'scalefactor = 0.900\nSpectre completes with 0 errors, 3 warnings.\n')
        (directory/'raw').mkdir()
        (directory/runner.review.RAW_NAME).write_bytes(b'fixture retained bytes\n')
        bench_sha = common.sha(directory/'bench.scs')
        intent = dict(format='pam4_c0_run_v1', case_id=case['case_id'], case_sha256=common.sha(directory/'case.json'),
            plan_sha256=driver.PLAN_SHA, design_source_sha256=driver.ORIGINAL_MANIFEST_SHA,
            input_deck_sha256_before=bench_sha, solver_mode='classic', simulator_build=common.BUILD,
            cpus_allocated=1, requested_threads=1, SPECTRE_DEFAULTS='-E',
            max_solver_file_bytes=common.DEFAULT_SOLVER_FILE_BYTES, actual_argv=['/fixture/spectre', *runner.ARGUMENTS],
            slurm_job_id=job, solver_hostname='fixture', started_utc='2026-11-15T20:00:00+00:00')
        common.write_new(directory/'execution_intent.json', intent)
        proof = common.classic_log((directory/'spectre.log').read_text(encoding='ascii'))
        common.write_new(directory/'run_status.json', dict(intent, **proof,
            status='spectre_completed', exit_code=0, input_deck_sha256_after=bench_sha,
            spectre_log_sha256=common.sha(directory/'spectre.log'), raw_inventory=common.raw_inventory(directory),
            spectre_wall_seconds=2373, child_peak_rss_KiB_after_solver=283000))
        if index == 0:
            status, hashes = runner.execution_evidence(case, directory)
            prior = {'case':case, 'measurement_complete':True, 'frozen_sha256':runner.review.FROZEN_SHA,
                     'bench_sha256':bench_sha, 'run_status_sha256':hashes['run_status.json'],
                     'tran_sha256':status['raw_inventory'][0]['sha256'],
                     'metrics':{'primary':{'metrics':previous_metrics(173,174)},
                                'secondary':{'metrics':previous_metrics(175,175)}}}
            receipt = dict(case_id=case['case_id'], source_files_sha256=hashes,
                           original_plan_sha256=driver.PLAN_SHA, collector_manifest_sha256=driver.ORIGINAL_MANIFEST_SHA)
            runner.publish(directory, prior, receipt)
        return directory

    def score_stub(self, directory, calibration):
        case, = [row for row in self.cases if row['case_id'] == directory.name]
        status_sha = common.sha(directory/'run_status.json')
        tran_sha = common.sha(directory/runner.review.RAW_NAME)
        if calibration is None:
            calibration = dict(baseline_tran_sha256=tran_sha, baseline_run_status_sha256=status_sha,
                selections={point:dict(lag=3, last_training_read_s=10e-9)
                            for point in ('primary', 'secondary')})
        return dict(case=case, calibration=calibration, frozen_sha256=runner.review.FROZEN_SHA,
                    run_status_sha256=status_sha, tran_sha256=tran_sha,
                    scoring=dict(payload_tx_indices=[1152,1408], ffe_center_tx_indices=[1160,1400],
                                 phase_optimized=False),
                    metrics={'primary':dict(metrics=previous_metrics(20,20), lag=3, first_read_s=10.52e-9),
                             'secondary':dict(metrics=previous_metrics(25,25), lag=3, first_read_s=10.53e-9)})

    def test_case0_recovery_preserves_original_and_freezes_calibration_across_summary(self):
        import c0_align

        directory = self.staged_completed(0, driver.CASE0_TASK)
        original_files = {path:common.sha(path) for path in directory.rglob('*') if path.is_file()}
        with patch.object(c0_align, 'measure', side_effect=self.score_stub) as measure:
            baseline = driver.collect(self.cases, 0, self.root, COLLECTOR_SHA)
            self.assertEqual(baseline['prior_symbol_errors']['primary']['raw_held_FFE_before_ADC'],173)
            self.assertEqual(baseline['prior_symbol_errors']['primary']['ideal7bit_ADC_then_FFE'],174)
            self.assertEqual(baseline['prior_symbol_errors']['secondary']['ideal7bit_ADC_then_FFE'],175)
            self.assertTrue(baseline['prior_result_matches_feedback'])
            self.assertEqual(driver.collect(self.cases, 0, self.root, COLLECTOR_SHA),baseline)
            self.assertEqual(measure.call_count, 1)
            for index in range(1, 5):
                self.staged_completed(index, str(757901+index))
                score = driver.collect(self.cases, index, self.root, COLLECTOR_SHA)
                self.assertEqual(score['calibration_sha256'], baseline['calibration_sha256'])
                self.assertEqual(measure.call_args.args[1], baseline['calibration'])
        self.assertTrue(all(common.sha(path) == digest for path, digest in original_files.items()))
        summary = driver.summarize(self.cases, self.root, COLLECTOR_SHA)
        self.assertEqual(summary['completed_cases'],5)
        self.assertEqual(summary['resources'][directory.name]['slurm_task_id'],'757899')
        self.assertEqual(summary['calibration_sha256'],baseline['calibration_sha256'])

    def test_wrong_task_or_changed_raw_rejected_before_scoring(self):
        import c0_align

        directory = self.staged_completed(0, '757898')
        with patch.object(c0_align, 'measure', side_effect=AssertionError('invalid run was scored')):
            with self.assertRaisesRegex(ValueError, '757899'):
                driver.collect(self.cases, 0, self.root, COLLECTOR_SHA)
            with patch.object(driver, 'CASE0_TASK', '757898'):
                (directory/runner.review.RAW_NAME).write_bytes(b'changed waveform')
                with self.assertRaisesRegex(ValueError, 'Retained raw differs'):
                    driver.collect(self.cases, 0, self.root, COLLECTOR_SHA)
        self.assertFalse((directory/driver.MEASUREMENT).exists())


if __name__ == '__main__':
    unittest.main()
