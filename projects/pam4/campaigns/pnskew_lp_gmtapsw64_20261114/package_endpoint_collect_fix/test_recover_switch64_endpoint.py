"""Check endpoint recovery admission, publication, and safe retries."""

from contextlib import nullcontext
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from pvt import model_preflight
from recover_bias import payload
import recover_switch64_endpoint as recovery


# Transcribed from the Olympus feedback. Only the first eight hex digits of
# each retry waveform SHA were supplied, so the fixture keeps them as prefixes.
OLYMPUS_ENDPOINTS = {
    84: dict(prior_task='757710', retry_task='757730', retry_bytes=576370217,
             retry_sha_prefix='fea911b3', prior_wall_s=297),
    86: dict(prior_task='757597', retry_task='757729', retry_bytes=560309741,
             retry_sha_prefix='10c96868', prior_wall_s=296),
}
OLYMPUS_PRIOR_STATUS = 'spectre_evidence_incomplete'
OLYMPUS_PRIOR_EXIT = 0
PRIOR_FATAL_LOG = b'ERROR (USIMUWI-20006): not enough virtual memory\nFATAL: simulation terminated\n'


class EndpointCollectOnly(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        self.original, self.retry = root/'original', root/'retry'
        self.original.mkdir()
        self.retry.mkdir()
        self.cases = recovery.common.read(recovery.switch.PLAN)['cases']
        self.prepare_case(84)
        self.addCleanup(patch.stopall)
        patch.object(recovery.common, 'owned_file', side_effect=lambda _, path: (path, path.stat())).start()
        patch.object(recovery, 'lock_case', side_effect=lambda _: nullcontext()).start()

    def prepare_case(self, index):
        observed = OLYMPUS_ENDPOINTS[index]
        self.case = self.cases[index]
        self.name = self.case['case_id']
        self.original_case, self.retry_case = self.original/self.name, self.retry/self.name
        model = '/ecen720_28nm/private_models/r7_vm_shrink'
        m = model_preflight
        portable = (m.REFERENCE/m.CORNER_FILE).read_bytes()
        process = self.case['process']
        proof = dict(schema='PAM4_PRIVATE_VM_KIT_PREFLIGHT_V1', model_root=model, process=process,
                     root_section='top_'+process, active_shrink_sections=m.verify_wrapper(portable, process),
                     kit_fingerprints={name: {'bytes': size, 'sha256': digest}
                                       for name, (size, digest) in m.KIT_PINS.items()},
                     active_static_mos_scale=.9, static_identity_verified=True,
                     model_files_written=False, model_bodies_exported=False, simulation_started=False)
        with patch.object(m, 'verify_private_kit', return_value=proof):
            recovery.switch.stage(self.case, self.original_case, model)
            recovery.switch.stage(self.case, self.retry_case, model)
        bench = recovery.common.sha(self.retry_case/'bench.scs')
        self.intent = dict(format='pam4_gmdrive_run_v1', case_id=self.name,
                           case_sha256=recovery.common.sha(self.retry_case/'case.json'),
                           plan_sha256=recovery.PLAN_SHA, input_deck_sha256_before=bench,
                           solver_mode='classic', simulator_build=recovery.common.BUILD,
                           cpus_allocated=1, requested_threads=1, SPECTRE_DEFAULTS='-E',
                           max_solver_file_bytes=recovery.metrics.ENDPOINT_RETRY_FILE_BYTES,
                           slurm_job_id=observed['retry_task'], solver_hostname='node',
                           started_utc='2026-11-15T01:00:00Z',
                           actual_argv=['/cadence/bin/spectre', *recovery.ARGUMENTS])
        self.prior = dict(self.intent, max_solver_file_bytes=536870912,
                          status=OLYMPUS_PRIOR_STATUS, exit_code=OLYMPUS_PRIOR_EXIT,
                          input_deck_sha256_after=bench, slurm_job_id=observed['prior_task'],
                          spectre_wall_seconds=observed['prior_wall_s'])
        (self.original_case/'run_status.json').write_bytes(payload(self.prior))
        (self.original_case/'spectre.log').write_bytes(PRIOR_FATAL_LOG)
        self.write('execution_intent.json', self.intent)
        (self.retry_case/'.study_owned').write_text(observed['retry_task']+'\n', encoding='ascii')
        (self.retry_case/'runner_stdout.log').write_bytes(b'Raw exceeds 512 MiB collector bound\n')
        log = 'scalefactor = 0.900\nSpectre completes with 0 errors, 3 warnings.\n'
        (self.retry_case/'spectre.log').write_bytes(log.encode('ascii'))
        self.size = observed['retry_bytes']
        self.assertEqual(self.size, recovery.RETRY_TRAN_BYTES[index])
        synthetic_sha = hashlib.sha256(f'fixture-only endpoint {index}'.encode('ascii')).hexdigest()
        self.row = dict(path=recovery.TRAN_PATH, bytes=self.size, sha256=synthetic_sha,
                        inode=2, mtime_ns=3, device=4)
        self.live = dict(self.row, device=5)
        self.status = dict(self.intent, status='spectre_completed', exit_code=0,
                           input_deck_sha256_after=bench, raw_inventory=[self.row],
                           spectre_log_sha256=recovery.common.sha(self.retry_case/'spectre.log'),
                           **{k:v for k,v in recovery.common.classic_log(log).items() if k not in self.intent})
        self.write('run_status.json', self.status)

    def write(self, name, document):
        (self.retry_case/name).write_bytes(payload(document))

    def collect(self):
        return recovery.recover(self.original, self.retry, self.case, self.size, 'b'*64, 'c'*64)

    def test_scope_and_original_approval(self):
        approval = dict(approved=True, platform='Olympus', plan_sha256=recovery.PLAN_SHA,
                        design_source_sha256=recovery.RETRY_MANIFEST_SHA, stages=['switch'],
                        case_ids=list(recovery.metrics.ENDPOINT_RETRY_CASE_IDS.values()), retire_new_raw=False)
        recovery.verify_approval(approval)
        for altered in (dict(design_source_sha256='0'*64), dict(case_ids=[self.name]),
                        dict(stages=['hold','switch']), dict(retire_new_raw=True)):
            with self.subTest(altered=altered), self.assertRaisesRegex(ValueError, 'original Olympus approval'):
                recovery.verify_approval(dict(approval, **altered))

    def test_mismatched_endpoint_inputs_and_wrong_size_fail_before_collection(self):
        with patch.object(recovery.metrics, 'native_transient') as read:
            self.size -= 1
            with self.assertRaisesRegex(ValueError, 'PSF path or size differs'):
                self.collect()
            self.size += 1
            (self.original_case/'bench.scs').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'original failed case'):
                self.collect()
            read.assert_not_called()

    def test_prior_zero_exit_requires_failure_evidence(self):
        (self.original_case/'spectre.log').write_bytes(b'Spectre completes with 0 errors.\n')
        with patch.object(recovery.metrics, 'native_transient') as read:
            with self.assertRaisesRegex(ValueError, 'original failed case'):
                self.collect()
            read.assert_not_called()

    def test_prior_completed_status_is_rejected_even_with_failure_log(self):
        (self.original_case/'run_status.json').write_bytes(payload(dict(self.prior, status='spectre_completed')))
        with patch.object(recovery.metrics, 'native_transient') as read:
            with self.assertRaisesRegex(ValueError, 'original failed case'):
                self.collect()
            read.assert_not_called()

    def test_commit_is_compatible_with_summary_and_second_call_is_idempotent(self):
        def simulated_link(source, target):
            with Path(target).open('xb') as stream:
                stream.write(Path(source).read_bytes())

        for index, observed in OLYMPUS_ENDPOINTS.items():
            with self.subTest(index=index):
                if index != 84:
                    self.prepare_case(index)
                measured = dict(case_id=self.name, format=recovery.metrics.FORMAT, tran_sha256=self.row['sha256'])
                before = {path: recovery.common.sha(path)
                          for directory in (self.original_case, self.retry_case) for path in directory.iterdir()}
                with (patch.object(recovery.common, 'raw_inventory', return_value=[self.live]) as inventory,
                      patch.object(recovery.metrics, 'native_transient') as read,
                      patch.object(recovery.metrics, 'measurement', return_value=measured),
                      patch('recover_bias.os.link', side_effect=simulated_link)):
                    self.assertEqual(self.collect(), 'recovered')
                    self.assertEqual(read.call_args.kwargs['max_bytes'], 640*1024**2)
                    self.assertEqual(read.call_args.args[1]['raw_inventory'], [self.live])
                    self.assertEqual(self.collect(), 'already_recovered')
                    self.assertEqual(read.call_count, 1)
                    self.assertEqual(inventory.call_count, 2)
                proof = recovery.common.read(self.retry_case/'recovery.json')
                self.assertEqual(proof['reported_slurm_array_job_id'], '757729')
                self.assertEqual(proof['slurm_job_id'], observed['retry_task'])
                self.assertEqual(recovery.common.read(self.original_case/'run_status.json')['slurm_job_id'],
                                 observed['prior_task'])
                self.assertTrue(all(recovery.common.sha(path) == sha for path, sha in before.items()))

        summary = recovery.switch.summarize(self.original, self.retry)
        for index, observed in OLYMPUS_ENDPOINTS.items():
            case_id = self.cases[index]['case_id']
            row = summary['endpoint_retry']['case_evidence'][case_id]
            self.assertEqual(row['slurm_job_id'], observed['retry_task'])
            self.assertEqual(row['transient_psf_bytes'], observed['retry_bytes'])
            self.assertNotIn(case_id, summary['invalid_dynamic_cases'])

    def test_source_inventory_change_refuses_to_publish(self):
        measured = dict(case_id=self.name, format=recovery.metrics.FORMAT, tran_sha256=self.row['sha256'])
        with (patch.object(recovery.common, 'raw_inventory', side_effect=[[self.live], [dict(self.live, device=6)]]),
              patch.object(recovery.metrics, 'native_transient'),
              patch.object(recovery.metrics, 'measurement', return_value=measured),
              patch.object(recovery, 'publish') as publish):
            with self.assertRaisesRegex(ValueError, 'Source changed'):
                self.collect()
            publish.assert_not_called()
