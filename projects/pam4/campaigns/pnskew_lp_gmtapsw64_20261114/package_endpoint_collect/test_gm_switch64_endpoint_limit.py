from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch, sentinel

from comp_measure import collect_r5
import gm_switch64_metrics as metrics
import olympus_common as common


class EndpointFileBoundTests(unittest.TestCase):
    def test_native_path_passes_the_same_bound_through_both_readers(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            raw = root / 'raw' / 'codeSwitch.tran.tran'
            raw.parent.mkdir()
            raw.write_bytes(b'VALUE\nEND\n')
            info = SimpleNamespace(st_size=metrics.MAX_BYTES + 1, st_dev=1, st_ino=2, st_mtime_ns=3)
            digest = common.sha(raw)
            row = {'path': 'raw/codeSwitch.tran.tran', 'bytes': info.st_size, 'device': info.st_dev,
                   'inode': info.st_ino, 'mtime_ns': info.st_mtime_ns, 'sha256': digest}
            status = self.status(raw_inventory=[row])
            with (patch.object(common, 'owned_file', return_value=(raw, info)),
                  patch.object(collect_r5, 'ensure_end', wraps=collect_r5.ensure_end) as ensure_end,
                  patch.object(metrics, 'parse_selected', return_value=SimpleNamespace(sha256=digest)) as parse):
                with self.assertRaisesRegex(ValueError, 'outside supported size'):
                    metrics.native_transient(root, status)
                ensure_end.assert_not_called()
                parse.assert_not_called()
                metrics.native_transient(root, status, max_bytes=metrics.ENDPOINT_RETRY_FILE_BYTES)
                ensure_end.assert_called_once_with(raw, max_bytes=metrics.ENDPOINT_RETRY_FILE_BYTES)
                parse.assert_called_once_with(raw, metrics.SWEEP_TRACES, max_bytes=metrics.ENDPOINT_RETRY_FILE_BYTES)

    def test_extended_bound_rejects_other_cases_or_incomplete_solver_proof(self):
        for change in ({'case_id': 'gmsw_083_ss_hold_m60_m60_latep'},
                       {'max_solver_file_bytes': metrics.MAX_BYTES},
                       {'status': 'spectre_failed_or_source_changed'}, {'exit_code': 1}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'completed SWITCH64 endpoint'):
                metrics.native_transient(sentinel.root, self.status(**change), max_bytes=metrics.ENDPOINT_RETRY_FILE_BYTES)

    @staticmethod
    def status(**changes):
        status = dict(case_id=metrics.ENDPOINT_RETRY_CASE_IDS[84], status='spectre_completed',
                      exit_code=0, max_solver_file_bytes=metrics.ENDPOINT_RETRY_FILE_BYTES)
        return dict(status, **changes)
