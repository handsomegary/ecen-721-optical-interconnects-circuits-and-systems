import hashlib
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import recover_switch64 as recovery
from recover_bias import payload


class TestSwitch64Recovery(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.case = recovery.common.read(recovery.PLAN)['cases'][48]
        self.case_dir = Path(self.temp.name).resolve()/self.case['case_id']
        self.case_dir.mkdir()
        self.size = recovery.SMOKE[48][1]
        self.row = dict(path=recovery.TRAN_PATH, bytes=self.size, sha256='a'*64,
                        mtime_ns=200, inode=100, device=4)
        self.live_row = dict(self.row, device=5)
        self.stored = self.make_staged_case()
        self.write('case.json', self.stored)
        log = b'scalefactor = 0.900\nSpectre completes with 0 errors, 3 warnings.\n'
        (self.case_dir/'spectre.log').write_bytes(log)
        (self.case_dir/'runner_stdout.log').write_bytes(b'collector wrapper failed\n')
        (self.case_dir/'.study_owned').write_bytes(b'757443\n')
        self.intent = dict(format='pam4_gmdrive_run_v1', case_id=self.case['case_id'],
                           case_sha256=self.sha('case.json'), plan_sha256=recovery.PLAN_SHA,
                           input_deck_sha256_before=self.sha('bench.scs'), solver_mode='classic',
                           simulator_build=recovery.common.BUILD, cpus_allocated=1, requested_threads=1,
                           SPECTRE_DEFAULTS='-E', max_solver_file_bytes=512*1024**2,
                           slurm_job_id='757443', solver_hostname='solver-node',
                           actual_argv=['/cadence/bin/spectre', *recovery.ARGUMENTS],
                           started_utc='2026-11-14T21:00:00+00:00')
        self.status = dict(self.intent, status='spectre_completed', exit_code=0,
                           **recovery.common.classic_log(log.decode()),
                           raw_inventory=[self.row], input_deck_sha256_after=self.sha('bench.scs'),
                           spectre_log_sha256=self.sha('spectre.log'))
        self.write('execution_intent.json', self.intent)
        self.write('run_status.json', self.status)
        self.addCleanup(patch.stopall)
        # Fixture files are plain local files. UID/NFS inode semantics are covered
        # by the real Olympus helpers and the explicit inventory tests here.
        patch.object(recovery.common, 'owned_file', side_effect=lambda _, path: (path, path.stat())).start()
        patch.object(recovery, 'lock_case', side_effect=lambda _: nullcontext()).start()

    def make_staged_case(self):
        model_root = '/ecen720_28nm/private_models/r7_vm_shrink'
        m = recovery.model_preflight
        portable = (m.REFERENCE/m.CORNER_FILE).read_bytes()
        (self.case_dir/m.CORNER_FILE).write_bytes(m.materialize_corner(portable, model_root))
        deck, rails, ac, dc, currents, diff = recovery.gm_switch64_rf.render(self.case, model_root)
        (self.case_dir/'bench.scs').write_bytes(deck.encode('ascii'))
        (self.case_dir/'parent_diff.txt').write_bytes(diff.encode('ascii'))
        proof = {
            'schema': 'PAM4_PRIVATE_VM_KIT_PREFLIGHT_V1', 'static_identity_verified': True,
            'active_static_mos_scale': .9, 'process': 'ss', 'root_section': 'ss',
            'active_shrink_sections': m.verify_wrapper(portable, 'ss'), 'model_root': model_root,
            'root_substitution_reversible': True, 'model_files_written': False,
            'model_bodies_exported': False, 'simulation_started': False,
            'portable_corner_wrapper_sha256': hashlib.sha256(portable).hexdigest(),
            'corner_wrapper_sha256': self.sha(m.CORNER_FILE),
            'kit_fingerprints': {name: {'bytes': size, 'sha256': digest}
                                 for name, (size, digest) in m.KIT_PINS.items()},
        }
        return dict(self.case, rail_voltages_V=rails, AC_traces=ac, DC_nodes=dc,
                    DC_currents=currents, model_preflight=proof,
                    staged_source_sha256={name: self.sha(name) for name in recovery.SOURCE_FILES})

    def sha(self, name):
        return recovery.common.sha(self.case_dir/name)

    def write(self, name, value):
        (self.case_dir/name).write_bytes(payload(value))

    def evidence(self):
        return recovery.historical_evidence(self.case_dir, self.case, self.size)[0]

    def test_original_approval_remains_the_authority(self):
        approval = dict(approved=True, platform='Olympus', case_ids=[self.case['case_id']],
                        stages=['hold'], plan_sha256=recovery.PLAN_SHA,
                        design_source_sha256=recovery.ORIGINAL_MANIFEST_SHA)
        recovery.verify_approval(approval, [self.case])
        for update in (dict(design_source_sha256='0'*64), dict(stages=['switch']), dict(case_ids=[])):
            with self.assertRaisesRegex(ValueError, 'original Olympus'):
                recovery.verify_approval(dict(approval, **update), [self.case])

    def test_only_device_can_change_across_hosts(self):
        pin = self.evidence()
        self.assertEqual(pin['slurm_job_id'], '757443')
        self.assertEqual(pin['reported_slurm_array_job_id'], '757441')
        with patch.object(recovery.common, 'raw_inventory', return_value=[self.live_row]):
            self.assertEqual(recovery.live_raw(self.case_dir, pin), [self.live_row])
        for altered in (dict(inode=101), dict(bytes=self.size-1), dict(sha256='b'*64)):
            with patch.object(recovery.common, 'raw_inventory', return_value=[dict(self.live_row, **altered)]):
                with self.assertRaisesRegex(ValueError, 'raw inventory differs'):
                    recovery.live_raw(self.case_dir, pin)

    def test_slurm_task_marker_must_match_historical_intent_and_status(self):
        self.write('execution_intent.json', dict(self.intent, slurm_job_id='757442'))
        self.write('run_status.json', dict(self.status, slurm_job_id='757442'))
        with self.assertRaisesRegex(ValueError, 'execution provenance differs'):
            self.evidence()

    def test_regeneration_catches_replaced_bench_with_rewritten_hashes(self):
        (self.case_dir/'bench.scs').write_bytes(b'different deck\n')
        self.stored['staged_source_sha256']['bench.scs'] = self.sha('bench.scs')
        self.write('case.json', self.stored)
        changes = dict(case_sha256=self.sha('case.json'), input_deck_sha256_before=self.sha('bench.scs'))
        self.write('execution_intent.json', dict(self.intent, **changes))
        changes['input_deck_sha256_after'] = self.sha('bench.scs')
        self.write('run_status.json', dict(self.status, **changes))
        with self.assertRaisesRegex(ValueError, 'Frozen generator'):
            self.evidence()

    def test_collection_reaches_summary_and_retries_allow_archived_raw(self):
        pin = self.evidence()
        measured = dict(case_id=self.case['case_id'], tran_sha256=self.row['sha256'])

        def publish(case_dir, report, receipt):
            self.assertEqual(case_dir, self.case_dir)
            self.write('measurements.json', report)
            self.write('recovery.json', dict(receipt, measurement_sha256=self.sha('measurements.json')))
            self.write('completion.json', dict(measurement_complete=True, mode='collect-only',
                       measurement_sha256=self.sha('measurements.json'),
                       recovery_sha256=self.sha('recovery.json')))
            return 'recovered'

        with (patch.object(recovery.common, 'raw_inventory', return_value=[self.live_row]) as inventory,
              patch.object(recovery.metrics, 'native_transient') as native,
              patch.object(recovery.metrics, 'measurement', return_value=measured),
              patch.object(recovery, 'publish', side_effect=publish)):
            status = recovery.recover(self.case_dir, self.case, self.size, pin, 'c'*64, 'd'*64)
            self.assertEqual(status, 'recovered')
            self.assertEqual(native.call_args.args[1]['raw_inventory'], [self.live_row])
            self.assertEqual(inventory.call_count, 2)
        with patch.object(recovery.common, 'raw_inventory', side_effect=FileNotFoundError('archived')):
            self.assertEqual(recovery.recover(self.case_dir, self.case, self.size, pin, 'c'*64, 'd'*64),
                             'already_recovered')
        self.write('recovery.json', {})
        with self.assertRaisesRegex(ValueError, 'Recovery provenance differs'):
            recovery.recover(self.case_dir, self.case, self.size, pin, 'c'*64, 'd'*64)

    def test_changed_post_collection_raw_stays_unpublished(self):
        pin = self.evidence()
        measured = dict(case_id=self.case['case_id'], tran_sha256=self.row['sha256'])
        later = dict(self.live_row, device=6)
        with (patch.object(recovery.common, 'raw_inventory', side_effect=[[self.live_row], [later]]),
              patch.object(recovery.metrics, 'native_transient'),
              patch.object(recovery.metrics, 'measurement', return_value=measured),
              patch.object(recovery, 'publish') as publish):
            with self.assertRaisesRegex(ValueError, 'Source changed'):
                recovery.recover(self.case_dir, self.case, self.size, pin, 'c'*64, 'd'*64)
            publish.assert_not_called()
