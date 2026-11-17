from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import gm_switch64 as design


class EndpointRetrySummary(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.original, self.retry = base/'original', base/'retry'
        self.original.mkdir()
        self.retry.mkdir()
        self.cases = design.common.read(design.PLAN)['cases']
        self.indices = (84,86)

    def write_case(self, index, bound=None):
        case = self.cases[index]
        case_id = case['case_id']
        prior, retry = self.original/case_id, self.retry/case_id
        for path in (prior,retry):
            path.mkdir()
            for filename in ('bench.scs','parent_diff.txt','la5_foundry_corners.scs'):
                (path/filename).write_text(filename,encoding='ascii')
            sources = {item.name:design.common.sha(item) for item in path.iterdir()}
            design.common.write_new(path/'case.json',dict(case,staged_source_sha256=sources))
        intent = dict(format='pam4_gmdrive_run_v1', case_id=case_id,
                      input_deck_sha256_before=sources['bench.scs'],
                      case_sha256=design.common.sha(retry/'case.json'),
                      plan_sha256=design.common.sha(design.PLAN), solver_mode='classic',
                      simulator_build=design.common.BUILD,cpus_allocated=1,requested_threads=1,
                      SPECTRE_DEFAULTS='-E',max_solver_file_bytes=bound or 640*1024**2,
                      solver_hostname='olympus',started_utc='2026-11-14T20:00:00+00:00',slurm_job_id='758001',
                      actual_argv=['/cadence/bin/spectre','-64','+mt=1','bench.scs','-format','psfascii',
                                   '-raw','raw','+log','spectre.log','+lqtimeout','30'])
        design.common.write_new(prior/'run_status.json',dict(intent,max_solver_file_bytes=512*1024**2,
                               status='spectre_failed_or_source_changed',exit_code=1,
                               input_deck_sha256_after=sources['bench.scs']))
        design.common.write_new(retry/'execution_intent.json',intent)
        (retry/'.study_owned').write_text('758001\n',encoding='ascii')
        log = 'Spectre completes with 0 errors, 0 warnings.\n'
        (retry/'spectre.log').write_text(log,encoding='ascii')
        tran = dict(path='raw/codeSwitch.tran.tran', bytes=560*1024**2, sha256='a'*64)
        status = dict(intent,**{key:value for key,value in design.common.classic_log(log).items()
                               if key not in intent},status='spectre_completed',exit_code=0,
                      input_deck_sha256_after=sources['bench.scs'],
                      spectre_log_sha256=design.common.sha(retry/'spectre.log'),raw_inventory=[tran])
        design.common.write_new(retry/'run_status.json',status)
        design.common.write_new(retry/'measurements.json',dict(case_id=case_id,format=design.metrics.FORMAT,
            tran_sha256=tran['sha256'],measurement_complete=True,bench_sha256=sources['bench.scs'],
            run_status_sha256=design.common.sha(retry/'run_status.json')))
        design.common.write_new(retry/'completion.json',dict(measurement_complete=True,
            measurement_sha256=design.common.sha(retry/'measurements.json')))

    def summary(self, all_reads):
        real_read_case = design.gm_summary.read_case
        def read_case(root,case,plan):
            all_reads[case['case_id']] = root
            if case['case_id'] in [self.cases[i]['case_id'] for i in self.indices]:
                return real_read_case(root,case,plan)
            return {'case_id':case['case_id']}
        with patch.object(design.gm_summary,'read_case',side_effect=read_case), \
             patch.object(design.dense,'summarize',return_value={'verified_nominal_dense_steps':True,
                                                                 'missing_cases':[],'invalid_cases':{}}), \
             patch.object(design.metrics,'compare',return_value={'settled':True,'recovery_s_after_event':2.6e-9}):
            return design.summarize(self.original,self.retry)

    def test_two_retries_complete_all_87_cases_and_21_transitions(self):
        for index in self.indices:
            self.write_case(index)
        reads = {}
        summary = self.summary(reads)
        retried = {self.cases[i]['case_id'] for i in self.indices}
        self.assertEqual({case for case,root in reads.items() if root == self.retry},retried)
        self.assertEqual(set(summary['endpoint_retry']['case_evidence']),retried)
        self.assertEqual(summary['total_measured_case_count'],87)
        self.assertEqual(summary['dynamic_measured_case_count'],39)
        self.assertEqual(len(summary['transitions']),21)
        self.assertTrue(summary['ready_to_design_C0'])

    def test_bad_cap_or_missing_retry_cannot_pass(self):
        self.write_case(84,bound=512*1024**2)
        summary = self.summary({})
        self.assertIn('640 MiB',summary['invalid_dynamic_cases'][self.cases[84]['case_id']])
        self.assertIn(self.cases[86]['case_id'],summary['missing_dynamic_cases'])
        self.assertFalse(summary['ready_to_design_C0'])

    def test_changed_sources_and_extra_cases_are_rejected(self):
        self.write_case(84)
        (self.original/self.cases[84]['case_id']/'bench.scs').write_text('altered',encoding='ascii')
        summary = self.summary({})
        self.assertIn('staged source differs',summary['invalid_dynamic_cases'][self.cases[84]['case_id']])
        (self.retry/self.cases[83]['case_id']).mkdir()
        with self.assertRaisesRegex(ValueError,'only the two approved'):
            self.summary({})
