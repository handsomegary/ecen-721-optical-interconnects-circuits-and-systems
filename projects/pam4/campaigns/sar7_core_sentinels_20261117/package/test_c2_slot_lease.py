#!/usr/bin/env python3
"""Mock-only lease tests: no real Slurm query, update, submission or solver."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import shutil
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("tested_c2_slot_lease", HERE / "c2_slot_lease.py")
lease = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lease)
OWNER = dict(name="tester", uid=1234)


def records(throttle, owner="tester", uid=1234, array="761525"):
    # Real show-job can return one allocated record plus the pending master/range.
    return (f"JobId=761526 ArrayJobId={array} ArrayTaskId=1 UserId={owner}({uid}) JobState=RUNNING\n"
            f"JobId={array} ArrayJobId={array} ArrayTaskId=2-40%{throttle} UserId={owner}({uid}) JobState=PENDING\n")


class FakeSlurm:
    def __init__(self, throttle=5):
        self.throttle = throttle
        self.calls = []
        self.fail_update = None
        self.wrong_after_update = None
        self.owner = "tester"
        self.uid = 1234
        self.array = "761525"

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        assert kwargs == dict(capture_output=True, text=True, timeout=10, check=False)
        if argv == ["scontrol", "--oneliner", "show", "job", "761525"]:
            return SimpleNamespace(returncode=0, stdout=records(self.throttle, self.owner, self.uid, self.array), stderr="")
        if argv[:3] == ["scontrol", "update", "JobId=761525"] and argv[3] in ("ArrayTaskThrottle=4", "ArrayTaskThrottle=5"):
            value = int(argv[3].split("=")[1])
            if self.fail_update == value:
                return SimpleNamespace(returncode=9, stdout="", stderr="mock update refused")
            self.throttle = self.wrong_after_update if self.wrong_after_update is not None else value
            self.wrong_after_update = None
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError("Unexpected command: " + repr(argv))


class LeaseTests(unittest.TestCase):
    def setUp(self):
        # mkdir with inherited permissions also works in Windows AppContainer tests;
        # Python3.14 TemporaryDirectory's private ACL excludes that sandbox SID.
        self.temp = HERE / ("test_lease_" + uuid.uuid4().hex)
        self.temp.mkdir()
        self.addCleanup(shutil.rmtree, self.temp)
        self.root = self.temp / "pam4_sar7_core_sentinels_mock"
        self.root.mkdir()
        self.approval = self.root / "approval.json"
        self.approval.write_text('{"approved":true}\n', encoding="utf-8")
        self.binding = dict(root=str(self.root.resolve()), package_manifest_sha256="a" * 64,
                            authorization_sha256="b" * 64, authorization_source_sha256=lease.AUTH_SOURCE_SHA256,
                            approval=str(self.approval.resolve()), approval_sha256=lease.sha(self.approval), owner=OWNER.copy())
        self.slurm = FakeSlurm()
        self.subject = lease.Lease(self.root, self.approval, runner=self.slurm,
                                   binding=lambda root, approval: self.binding.copy())

    def events(self):
        return [json.loads(line) for line in self.subject.log_path.read_text(encoding="utf-8").splitlines()]

    def test_multi_record_pending_range_and_explicit_agree(self):
        result = lease.parse_array_status(records(5), OWNER)
        self.assertEqual(result["throttle"], 5)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(lease.parse_array_status(records(4).replace("JobState=PENDING", "ArrayTaskThrottle=4 JobState=PENDING"), OWNER)["throttle"], 4)
        self.assertEqual(lease.parse_array_status("JobId=761525 UserId=tester(1234) ArrayTaskThrottle=5\n", OWNER)["throttle"], 5)

    def test_reject_unknown_conflicting_and_wrong_identity(self):
        samples = [records(5).replace("%5", ""), records(5).replace("JobState=PENDING", "ArrayTaskThrottle=4 JobState=PENDING"),
                   records(5, array="999"), records(5, owner="other"), records(5, uid=999),
                   records(5).replace("%5", "%5%4"), records(5) + "JobId=999 UserId=tester(1234)\n",
                   records(5).replace("%5", "%0"), records(5).replace("JobState=PENDING", "JobId=1 JobState=PENDING")]
        for output in samples:
            with self.subTest(output=output), self.assertRaises(lease.LeaseError):
                lease.parse_array_status(output, OWNER)

    def test_begin_intent_is_immutable_before_mutation_and_commands_are_exact(self):
        original = self.slurm.__call__
        def runner(argv, **kwargs):
            if argv[1] == "update":
                self.assertEqual(self.subject.read_lease()["temporary_throttle"], 4)
                self.assertEqual(self.events()[-1]["event"], "begin_intent")
            return original(argv, **kwargs)
        self.subject.runner = runner
        result = self.subject.begin()
        self.assertEqual(result["event"], "begin_verified")
        self.assertEqual(self.slurm.throttle, 4)
        self.assertEqual(self.subject.hash_path.read_text().strip(), lease.sha(self.subject.path))
        self.assertEqual([call[1] for call in self.slurm.calls], ["--oneliner", "update", "--oneliner"])
        self.assertTrue(all(event["array_job_id"] == "761525" for event in self.events()))
        before = self.subject.path.read_bytes()
        with self.assertRaises(lease.LeaseError):
            self.subject.begin()
        self.assertEqual(self.subject.path.read_bytes(), before)

    def test_begin_never_changes_preexisting4_or_external_value(self):
        for current in (4, 3, 6):
            self.slurm.throttle = current
            with self.subTest(current=current), self.assertRaises(lease.LeaseError):
                self.subject.begin()
            self.assertFalse(self.subject.path.exists())
        self.assertTrue(all(call[1] == "--oneliner" for call in self.slurm.calls))

    def test_failed_begin_immediately_cleans_up_owned4(self):
        calls = 0
        def runner(argv, **kwargs):
            nonlocal calls
            result = self.slurm(argv, **kwargs)
            if argv[1] == "--oneliner":
                calls += 1
                if calls == 2:
                    return SimpleNamespace(returncode=7, stdout="", stderr="mock verification failure")
            return result
        self.subject.runner = runner
        with self.assertRaisesRegex(lease.LeaseError, "restoration completed"):
            self.subject.begin()
        self.assertEqual(self.slurm.throttle, 5)
        self.assertEqual([c[3] for c in self.slurm.calls if c[1] == "update"], ["ArrayTaskThrottle=4", "ArrayTaskThrottle=5"])
        self.assertEqual(self.events()[-1]["outcome"], "restored_or_already5")

    def test_failed_begin_does_not_override_external_value(self):
        self.slurm.wrong_after_update = 3
        with self.assertRaisesRegex(lease.LeaseError, "restoration failed"):
            self.subject.begin()
        self.assertEqual(self.slurm.throttle, 3)
        self.assertEqual([c[3] for c in self.slurm.calls if c[1] == "update"], ["ArrayTaskThrottle=4"])
        self.assertEqual(self.events()[-1]["outcome"], "NOT_RESTORED")

    def test_restore_verified_and_idempotent_does_not_rewrite_intent(self):
        self.subject.begin()
        before = self.subject.path.read_bytes()
        self.assertEqual(self.subject.restore()["outcome"], "restored5")
        count = len(self.slurm.calls)
        self.assertEqual(self.subject.restore()["outcome"], "already5_no_update")
        self.assertEqual(len(self.slurm.calls) - count, 1)
        self.assertEqual(self.subject.path.read_bytes(), before)
        self.assertEqual(self.slurm.throttle, 5)

    def test_restore_refuses_tampered_or_different_owner_packet(self):
        self.subject.begin()
        self.subject.path.write_bytes(self.subject.path.read_bytes() + b" ")
        count = len(self.slurm.calls)
        with self.assertRaisesRegex(lease.LeaseError, "digest differs"):
            self.subject.restore()
        self.assertEqual(len(self.slurm.calls), count)
        self.subject.hash_path.write_text(lease.sha(self.subject.path) + "\n")
        self.subject.binding["owner"] = dict(name="other", uid=999)
        with self.assertRaisesRegex(lease.LeaseError, "another packet"):
            self.subject.restore()
        self.assertEqual(len(self.slurm.calls), count)

    def test_restore_external_value_and_fresh_owner_never_overridden(self):
        self.subject.begin()
        self.slurm.throttle = 6
        count = len(self.slurm.calls)
        with self.assertRaisesRegex(lease.LeaseError, "no override"):
            self.subject.restore()
        self.assertEqual(len(self.slurm.calls) - count, 1)
        self.slurm.throttle = 4
        self.slurm.owner = "other"
        with self.assertRaisesRegex(lease.LeaseError, "owner"):
            self.subject.restore()
        self.assertEqual(self.slurm.throttle, 4)

    def test_status_fresh_read_only_and_require_active(self):
        self.subject.begin()
        count = len(self.slurm.calls)
        self.assertTrue(self.subject.status(True)["active"])
        self.slurm.throttle = 5
        self.assertFalse(self.subject.status()["active"])
        with self.assertRaisesRegex(lease.LeaseError, "not active"):
            self.subject.status(True)
        self.assertTrue(all(call[1] == "--oneliner" for call in self.slurm.calls[count:]))

    def test_update_failure_is_recorded_and_does_not_submit_anything(self):
        self.slurm.fail_update = 4
        with self.assertRaisesRegex(lease.LeaseError, "restoration completed"):
            self.subject.begin()
        commands = [event for event in self.events() if event["event"] == "command"]
        self.assertTrue(any(event["returncode"] == 9 and event["stderr"] == "mock update refused" for event in commands))
        self.assertEqual(self.slurm.throttle, 5)

    def test_restore_failure_is_visible_and_can_be_retried_without_new_lease(self):
        self.subject.begin()
        original = self.subject.path.read_bytes()
        self.slurm.fail_update = 5
        with self.assertRaisesRegex(lease.LeaseError, "nonzero"):
            self.subject.restore()
        self.assertEqual(self.events()[-1]["event"], "restore_NOT_RESTORED")
        self.assertEqual(self.slurm.throttle, 4)
        self.slurm.fail_update = None
        self.assertEqual(self.subject.restore()["outcome"], "restored5")
        self.assertEqual(self.subject.path.read_bytes(), original)

    def test_packet_binding_requires_full_approval_and_fresh_authorization_before_slurm(self):
        package = self.root / "fakepackage"
        package.mkdir()
        (package / "SHA256SUMS.txt").write_text("mockmanifest\n")
        auth = dict(source_note_sha256=lease.AUTH_SOURCE_SHA256, starts_utc="2026-11-17T13:55:00Z", no_expiry=True)
        (package / "AUTHORIZATION.json").write_text(json.dumps(auth))
        core = SimpleNamespace(verify=lambda: ("case", {"portable_sha256": "d" * 64}),
                               approval_record=lambda root, meta, approved: {"approved": approved})
        with patch.object(lease, "__file__", str(package / "c2_slot_lease.py")), patch.object(lease.importlib, "import_module", return_value=core), patch.object(lease, "owner_identity", return_value=OWNER):
            result = lease.packet_binding(self.root, self.approval)
            self.assertEqual(result["authorization_source_sha256"], lease.AUTH_SOURCE_SHA256)
            self.approval.write_text('{"approved":false}')
            with self.assertRaisesRegex(lease.LeaseError, "Approval"):
                lease.packet_binding(self.root, self.approval)
            self.approval.write_text('{"approved":true}')
            auth["source_note_sha256"] = "0" * 64
            (package / "AUTHORIZATION.json").write_text(json.dumps(auth))
            with self.assertRaisesRegex(lease.LeaseError, "authorization"):
                lease.packet_binding(self.root, self.approval)
        self.assertEqual(self.slurm.calls, [])

    def test_batch_trap_resources_and_own_payload_lf(self):
        batch = (HERE / "sar7_core_sentinels.sbatch").read_text(encoding="utf-8")
        for token in ("#SBATCH --cpus-per-task=1", "#SBATCH --mem=6G", "#SBATCH --time=00:12:00", "#SBATCH --no-requeue", "#SBATCH --signal=B:TERM@60", "trap restore_c2_on_exit EXIT", "trap 'exit 143' TERM", "original_rc=$?", "restore_rc=$?", 'exit "$original_rc"', "status --require-active"):
            self.assertIn(token, batch)
        self.assertNotIn("exec /usr/bin", batch)
        self.assertNotIn("c2_slot_lease.py\" begin", batch)
        self.assertNotIn("scontrol ", batch)
        for name in ("c2_slot_lease.py", "sar7_core_sentinels.sbatch", "test_c2_slot_lease.py"):
            self.assertNotIn(b"\r", (HERE / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
