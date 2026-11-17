"""Check endpoint recovery admission, publication, and safe retries."""

from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from pvt import model_preflight
from recover_bias import payload
import recover_switch64_endpoint as recovery


class EndpointCollectOnly(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        self.original, self.retry = root/'original', root/'retry'
        self.original.mkdir()
        self.retry.mkdir()
        self.case = recovery.common.read(recovery.switch.PLAN)['cases'][84]
        self.name = self.case['case_id']
        self.original_case, self.retry_case = self.original/self.name, self.retry/self.name
        model = '/ecen720_28nm/private_models/r7_vm_shrink'
        m = model_preflight
        portable = (m.REFERENCE/m.CORNER_FILE).read_bytes()
        proof = dict(schema='PAM4_PRIVATE_VM_KIT_PREFLIGHT_V1', model_root=model, process='ss',
                     root_section='ss', active_shrink_sections=m.verify_wrapper(portable, 'ss'),
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
                           slurm_job_id='757730', solver_hostname='node', started_utc='2026-11-15T01:00:00Z',
                           actual_argv=['/cadence/bin/spectre', *recovery.ARGUMENTS])
        prior = dict(self.intent, max_solver_file_bytes=recovery.common.DEFAULT_SOLVER_FILE_BYTES,
                     status='spectre_failed_or_source_changed', exit_code=1, input_deck_sha256_after=bench)
        (self.original_case/'run_status.json').write_bytes(payload(prior))
        self.write('execution_intent.json', self.intent)
        (self.retry_case/'.study_owned').write_bytes(b'757730\n')
        (self.retry_case/'runner_stdout.log').write_bytes(b'Raw exceeds 512 MiB collector bound\n')
        log = 'scalefactor = 0.900\nSpectre completes with 0 errors, 3 warnings.\n'
        (self.retry_case/'spectre.log').write_bytes(log.encode('ascii'))
        self.size = recovery.RETRY_TRAN_BYTES[84]
        self.row = dict(path=recovery.TRAN_PATH, bytes=self.size, sha256='a'*64,
                        inode=2, mtime_ns=3, device=4)
        self.live = dict(self.row, device=5)
        self.status = dict(self.intent, status='spectre_completed', exit_code=0,
                           input_deck_sha256_after=bench, raw_inventory=[self.row],
                           spectre_log_sha256=recovery.common.sha(self.retry_case/'spectre.log'),
                           **{k:v for k,v in recovery.common.classic_log(log).items() if k not in self.intent})
        self.write('run_status.json', self.status)
        self.addCleanup(patch.stopall)
        patch.object(recovery.common, 'owned_file', side_effect=lambda _, path: (path, path.stat())).start()
        patch.object(recovery, 'lock_case', side_effect=lambda _: nullcontext()).start()

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

    def test_commit_is_compatible_with_summary_and_second_call_is_idempotent(self):
        def simulated_link(source, target):
            with Path(target).open('xb') as stream:
                stream.write(Path(source).read_bytes())

        measured = dict(case_id=self.name, format=recovery.metrics.FORMAT, tran_sha256=self.row['sha256'])
        before = {path.name: recovery.common.sha(path) for path in self.retry_case.iterdir()}
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
        self.assertEqual(proof['slurm_job_id'], '757730')
        self.assertTrue(all(recovery.common.sha(self.retry_case/name) == sha for name, sha in before.items()))

    def test_source_inventory_change_refuses_to_publish(self):
        measured = dict(case_id=self.name, format=recovery.metrics.FORMAT, tran_sha256=self.row['sha256'])
        with (patch.object(recovery.common, 'raw_inventory', side_effect=[[self.live], [dict(self.live, device=6)]]),
              patch.object(recovery.metrics, 'native_transient'),
              patch.object(recovery.metrics, 'measurement', return_value=measured),
              patch.object(recovery, 'publish') as publish):
            with self.assertRaisesRegex(ValueError, 'Source changed'):
                self.collect()
            publish.assert_not_called()
