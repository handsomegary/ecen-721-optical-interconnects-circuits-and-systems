"""Offline regression for the shared runner's result/evidence boundaries."""
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile
import unittest

import olympus_common as common
import run_case
from native import readback_guard


class TestClassicEvidence(unittest.TestCase):
    def test_accepts_only_documented_thread_evidence(self):
        end = 'spectre completes with 0 errors, 0 warnings.\n'
        self.assertIsNone(common.classic_log(end)['explicit_effective_threads'])
        one = 'Multithreading Enabled: 1 thread in the system with 1 available processors.\n'
        self.assertEqual(common.classic_log(one+end)['explicit_effective_threads'],1)
        with self.assertRaisesRegex(ValueError,'thread count'):
            common.classic_log(one.replace('1 thread','4 threads')+end)

    def test_mode_or_failed_solver_blocks_collect(self):
        for text in ('Fast APS Enabled.\nspectre completes with 0 errors.',
                     'APS Enabled.\nspectre completes with 0 errors.',
                     'spectre completes with 1 errors.'):
            with self.assertRaises(ValueError):
                common.classic_log(text)

    def test_case_paths_are_leaf_names(self):
        self.assertEqual(run_case.case_name('quiet_delta_p125'),'quiet_delta_p125')
        for value in ('..','../foreign','foo/bar','C:\\bad'):
            with self.assertRaises(ValueError):
                run_case.case_name(value)

    def test_cross_case_measurement_and_raw_output_keeper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'bench.scs').write_bytes(b'bench\n')
            digest = common.sha(root/'bench.scs')
            common.write_new(root/'run_status.json',{'input_deck_sha256_after':digest})
            self.assertEqual(run_case.verify_compact(root,{'measurement_complete':True,'input_deck_sha256':digest}),[])
            with self.assertRaisesRegex(ValueError,'binding'):
                run_case.verify_compact(root,{'measurement_complete':True,'input_deck_sha256':'0'*64})
            with self.assertRaisesRegex(ValueError,'Unsafe'):
                run_case.verify_compact(root,{'measurement_complete':True,'input_deck_sha256':digest,
                                             'compact_outputs':{'raw/transfer':digest}})


class TestRawRetirement(unittest.TestCase):
    def setUp(self):
        self.pid = Mock()
        self.pid.name = '808'
        self.pid.stat.return_value.st_uid = 123
        self.fd_dir = self.pid.__truediv__.return_value if hasattr(self.pid, '__truediv__') else Mock()
        self.pid.__truediv__ = Mock(return_value=self.fd_dir)

    def fake_proc(self):
        proc = Mock()
        proc.iterdir.return_value = [self.pid]
        return patch.object(common, 'Path', return_value=proc)

    def test_denied_same_or_unknown_uid_scan_defers_retirement(self):
        self.fd_dir.iterdir.side_effect = PermissionError('fd directory denied')
        with self.fake_proc(), patch.object(common.os, 'getuid', return_value=123, create=True), \
                patch.object(common.os, 'getpid', return_value=999):
            with self.assertRaisesRegex(common.RawRetirementDeferred, 'fd directory denied'):
                common.require_raw_unused([{'device': 10, 'inode': 25}])
            self.pid.stat.side_effect = PermissionError('UID unknown')
            with self.assertRaisesRegex(common.RawRetirementDeferred, 'UID unknown'):
                common.require_raw_unused([{'device': 10, 'inode': 25}])

    def test_other_uid_is_skipped_but_open_raw_defers(self):
        self.pid.stat.return_value.st_uid = 124
        with self.fake_proc(), patch.object(common.os, 'getuid', return_value=123, create=True), \
                patch.object(common.os, 'getpid', return_value=999):
            common.require_raw_unused([{'device': 10, 'inode': 25}])
            self.fd_dir.iterdir.assert_not_called()
            self.pid.stat.return_value.st_uid = 123
            fd = Mock()
            fd.stat.return_value = SimpleNamespace(st_dev=10, st_ino=25)
            self.fd_dir.iterdir.return_value = [fd]
            with self.assertRaisesRegex(common.RawRetirementDeferred, 'files open'):
                common.require_raw_unused([{'device': 10, 'inode': 25}])

    def test_permission_denial_keeps_raw_and_does_not_invalidate_measurements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            job = 'study-test'
            (root/'.study_owned').write_text(job)
            for name in ('bench.scs', 'spectre.log', 'case.json', 'measurements.json'):
                (root/name).write_text('fixture')
            (root/'raw').mkdir()
            path = root/'raw'/'tran.tran'
            path.write_bytes(b'raw bytes')
            row = {'path': 'raw/tran.tran', 'bytes': len(b'raw bytes')}
            measurement_sha = common.sha(root/'measurements.json')
            common.write_new(root/'completion.json', {'measurement_complete': True, 'measurement_sha256': measurement_sha})
            common.write_new(root/'run_status.json', {'slurm_job_id': job, 'status': 'spectre_completed', 'raw_inventory': [row]})
            with patch.dict(common.os.environ, {'SLURM_JOB_ID': job}), \
                    patch.dict(sys.modules, {'fcntl': Mock()}), \
                    patch.object(common, 'raw_inventory', return_value=[row]), \
                    patch.object(common, 'owned_file', side_effect=lambda _, p: (p, p.stat())), \
                    patch.object(common, 'raw_in_use', side_effect=PermissionError('denied')):
                receipt = common.retire_case_raw(root, [])
            self.assertEqual(receipt['status'], 'deferred')
            self.assertEqual(receipt['removed'], [])
            self.assertEqual(receipt['remaining_raw_paths'], ['raw/tran.tran'])
            self.assertEqual(path.read_bytes(), b'raw bytes')
            self.assertEqual(common.sha(root/'measurements.json'), measurement_sha)
            self.assertTrue(common.read(root/'completion.json')['measurement_complete'])
            self.assertFalse((root/'raw_retirement.jsonl').exists())
            self.assertEqual(common.read(root/'raw_retirement.json'), receipt)

    def test_partial_readback_requires_the_exact_missing_paths(self):
        a, b = 'raw/tran.tran', 'raw/info'
        inv = {a: {}, b: {}}
        receipt = {'status': 'deferred', 'reason': 'inaccessible fd', 'removed': [{'path': a}],
                   'remaining_raw_paths': [b], 'VM_or_original_study_deletion': False}
        self.assertEqual(set(readback_guard.check_retirement_paths(receipt, [a], inv)), {a})
        with self.assertRaises(ValueError):
            readback_guard.check_retirement_paths(receipt, [a, b], inv)
        with self.assertRaises(ValueError):
            readback_guard.check_retirement_paths(dict(receipt, status='completed'), [a], inv)


if __name__=='__main__':
    unittest.main()
