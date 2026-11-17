#!/usr/bin/env python3
"""Narrow, receipt-backed lease of ONE C2 array slot; never submits/cancels jobs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ARRAY_ID = "761525"
PRIOR = 5
TEMPORARY = 4
AUTH_SOURCE_SHA256 = "d9491abfb1429caf097c1c798d763d6529264fb3fa9cbbf2b82cd78b0d4183ea"
ROOT_PREFIX = "pam4_sar7_cml_drive2_"
LEASE_NAME = "c2_slot_lease.json"
SCHEMA = "pam4_sar7_cml_drive2_c2_slot_lease_v1"


class LeaseError(RuntimeError):
    pass


def need(condition, message):
    if not condition:
        raise LeaseError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def owner_identity():
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    if uid is not None:
        import pwd
        name = pwd.getpwuid(uid).pw_name
    else:
        name = getpass.getuser()
    return dict(name=name, uid=uid)


def write_new(path, value):
    data = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def packet_binding(root, approval):
    """Verify the ordinary approved packet before ANY Slurm query or update."""
    root, approval = Path(root).resolve(), Path(approval).resolve()
    need(root.is_dir() and root.name.startswith(ROOT_PREFIX), "Use the approved isolated cml-drive2 root")
    need(approval.parent == root, "Approval must be inside that exact root")
    package = Path(__file__).resolve().parent
    sys.path.insert(0, str(package))
    try:
        core = importlib.import_module("sar7_cml_drive2")
        _, meta = core.verify()
        expected = core.approval_record(root, meta, True)
        need(json.loads(approval.read_text(encoding="utf-8")) == expected,
             "Approval must bind approved=true, exact root, manifest and deck")
        authorization = package / "AUTHORIZATION.json"
        auth = json.loads(authorization.read_text(encoding="utf-8"))
        need(auth.get("source_note_sha256") == AUTH_SOURCE_SHA256,
             "Wrong renewed user authorization")
        need(auth.get("no_expiry") is True and auth.get("starts_utc") == "2026-11-17T13:55:00Z",
             "Wrong renewed authorization interval")
        return dict(root=str(root), package_manifest_sha256=sha(package / "SHA256SUMS.txt"),
                    authorization_sha256=sha(authorization), authorization_source_sha256=AUTH_SOURCE_SHA256,
                    approval=str(approval), approval_sha256=sha(approval), owner=owner_identity())
    finally:
        sys.path.pop(0)


def parse_array_status(output, expected_owner):
    """scontrol may return allocated tasks plus one pending range%throttle record."""
    records, throttles = [], []
    for line in output.splitlines():
        if not line.strip():
            continue
        pairs = re.findall(r"(?:^|\s)([A-Za-z][A-Za-z0-9_]*)=(\S*)", line)
        fields = dict(pairs)
        need(len(fields) == len(pairs), "Duplicate scontrol fields")
        need("JobId" in fields and "UserId" in fields, "Malformed scontrol job record")
        array = fields.get("ArrayJobId")
        need(array == ARRAY_ID or (array is None and fields["JobId"] == ARRAY_ID),
             "scontrol returned a different array")
        match = re.fullmatch(r"([^()\s]+)\((\d+)\)", fields["UserId"])
        need(match is not None and match.group(1) == expected_owner["name"], "C2 owner does not match current user")
        if expected_owner["uid"] is not None:
            need(int(match.group(2)) == expected_owner["uid"], "C2 UID does not match current user")
        if "ArrayTaskThrottle" in fields:
            need(fields["ArrayTaskThrottle"].isdigit(), "Invalid explicit C2 throttle")
            throttles.append(int(fields["ArrayTaskThrottle"]))
        task = fields.get("ArrayTaskId", "")
        if "%" in task:
            match = re.fullmatch(r"[^%\s]+%(\d+)", task)
            need(match is not None, "Ambiguous pending array throttle")
            throttles.append(int(match.group(1)))
        records.append(dict(job_id=fields["JobId"], array_job_id=array, array_task_id=task,
                            user_id=fields["UserId"], job_state=fields.get("JobState")))
    need(records and throttles and len(set(throttles)) == 1 and throttles[0] > 0,
         "No single explicit/pending-range C2 throttle; refusing to assume a value")
    return dict(array_job_id=ARRAY_ID, throttle=throttles[0], records=records)


def finished_element_warnings(returncode, stdout, stderr):
    """Only the exact own-array update warning is eligible for post-read verification."""
    line = re.escape(ARRAY_ID) + r"_[0-9]+: Job has already finished"
    return (type(returncode) is int and returncode == 1 and stdout == ""
            and isinstance(stderr, str)
            and re.fullmatch(line + r"(?:\n" + line + r")*\n?", stderr) is not None)


class Lease:
    def __init__(self, root, approval, runner=None, binding=None):
        self.root = Path(root).resolve()
        self.approval = Path(approval).resolve()
        self.binding = (binding or packet_binding)(self.root, self.approval)
        self.runner = runner or subprocess.run
        self.path = self.root / LEASE_NAME
        self.hash_path = self.root / (LEASE_NAME + ".sha256")
        self.log_path = self.root / "c2_slot_lease_events.jsonl"

    def event(self, kind, **payload):
        value = dict(time_utc=utc_now(), event=kind, array_job_id=ARRAY_ID, **payload)
        with self.log_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return value

    def _command_result(self, argv):
        allowed = (["scontrol", "--oneliner", "show", "job", ARRAY_ID],
                   ["scontrol", "update", "JobId=" + ARRAY_ID, "ArrayTaskThrottle=4"],
                   ["scontrol", "update", "JobId=" + ARRAY_ID, "ArrayTaskThrottle=5"])
        need(argv in allowed, "Command is outside this narrow lease")
        try:
            # Preserve CR/LF bytes: text=True would normalize CRLF before the strict warning check.
            captured = self.runner(argv, capture_output=True, text=False, timeout=10, check=False)
            decode = lambda value: value.decode("utf-8") if isinstance(value, bytes) else value
            result = subprocess.CompletedProcess(argv, captured.returncode,
                                                 decode(captured.stdout), decode(captured.stderr))
        except Exception as exc:
            self.event("command", argv=argv, returncode=None, stdout="", stderr=str(exc))
            raise LeaseError("scontrol failed; see immutable lease/event receipts") from exc
        self.event("command", argv=argv, returncode=result.returncode,
                   stdout=result.stdout, stderr=result.stderr)
        return result

    def command(self, argv):
        result = self._command_result(argv)
        need(result.returncode == 0, "scontrol returned nonzero; see lease/event receipts")
        return result.stdout

    def verified_update(self, target):
        need(target in (PRIOR, TEMPORARY), "Update is outside this narrow lease")
        argv = ["scontrol", "update", "JobId=" + ARRAY_ID, "ArrayTaskThrottle=" + str(target)]
        result = self._command_result(argv)
        warnings = finished_element_warnings(result.returncode, result.stdout, result.stderr)
        need(result.returncode == 0 or warnings, "scontrol returned nonzero; see lease/event receipts")
        # Even an eligible warning is not accepted until this separate strict read verifies every
        # returned owner/array record and the one unambiguous requested throttle.
        after = self.query()
        need(after["throttle"] == target, "C2 update target was not verified")
        if warnings:
            self.event("verified_with_finished_element_warnings", target_throttle=target,
                       returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
                       current=after)
        return after

    def query(self):
        return parse_array_status(self.command(["scontrol", "--oneliner", "show", "job", ARRAY_ID]),
                                  self.binding["owner"])

    def read_lease(self):
        need(self.path.is_file() and self.hash_path.is_file(), "No complete immutable C2 lease")
        expected = self.hash_path.read_text(encoding="ascii").strip()
        need(re.fullmatch(r"[0-9a-f]{64}", expected) is not None and sha(self.path) == expected,
             "C2 lease digest differs")
        value = json.loads(self.path.read_text(encoding="utf-8"))
        need(value.get("schema") == SCHEMA and value.get("binding") == self.binding,
             "C2 lease belongs to another packet, root, approval or owner")
        need(value.get("array_job_id") == ARRAY_ID and value.get("prior_throttle") == PRIOR
             and value.get("temporary_throttle") == TEMPORARY and isinstance(value.get("lease_id"), str),
             "C2 lease scope differs")
        return value

    def status(self, require_active=False):
        lease = self.read_lease()
        current = self.query()
        result = self.event("status", lease_id=lease["lease_id"], current=current,
                            active=current["throttle"] == TEMPORARY)
        need(not require_active or result["active"], "C2 lease is not active at throttle4; do not run SAR")
        return result

    def begin(self):
        need(not self.path.exists() and not self.hash_path.exists(), "Lease already exists; use status/restore, never re-begin")
        before = self.query()
        need(before["throttle"] == PRIOR, "C2 must currently be exactly5; no change made")
        lease = dict(schema=SCHEMA, lease_id=uuid.uuid4().hex, created_utc=utc_now(),
                     binding=self.binding, array_job_id=ARRAY_ID, prior_throttle=PRIOR,
                     temporary_throttle=TEMPORARY, observed_before=before)
        write_new(self.path, lease)
        # Durable ownership intent precedes the external mutation, including crash recovery.
        with self.hash_path.open("x", encoding="ascii", newline="\n") as stream:
            stream.write(sha(self.path) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.event("begin_intent", lease_id=lease["lease_id"], lease_sha256=sha(self.path))
        try:
            after = self.verified_update(TEMPORARY)
            return self.event("begin_verified", lease_id=lease["lease_id"], current=after)
        except Exception as exc:
            # No SAR job has been accepted yet. Undo only our matching 4, never an external value.
            try:
                restored = self.restore()
                self.event("begin_failed_cleanup", outcome="restored_or_already5", restore=restored)
            except Exception as restore_error:
                self.event("begin_failed_cleanup", outcome="NOT_RESTORED", error=str(restore_error))
                raise LeaseError("Lease begin failed AND immediate restoration failed; inspect receipts and restore manually") from exc
            raise LeaseError("Lease begin failed; immediate safe restoration completed; do not submit SAR") from exc

    def restore(self):
        lease = self.read_lease()
        current = self.query()
        if current["throttle"] == PRIOR:
            return self.event("restore_verified", lease_id=lease["lease_id"], outcome="already5_no_update", current=current)
        if current["throttle"] != TEMPORARY:
            self.event("restore_NOT_RESTORED", lease_id=lease["lease_id"], current=current,
                       reason="external_throttle_no_override")
            raise LeaseError("C2 throttle is neither owned4 nor restored5; NOT RESTORED, no override")
        try:
            after = self.verified_update(PRIOR)
        except Exception as exc:
            self.event("restore_NOT_RESTORED", lease_id=lease["lease_id"], reason="update_or_verification_failed", error=str(exc))
            raise
        return self.event("restore_verified", lease_id=lease["lease_id"], outcome="restored5", current=after)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("begin", "status", "restore"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--approval", required=True, type=Path)
    parser.add_argument("--require-active", action="store_true", help="status only: refuse unless verified owned throttle4")
    args = parser.parse_args()
    need(not args.require_active or args.mode == "status", "--require-active is status-only")
    lease = Lease(args.root, args.approval)
    result = lease.status(args.require_active) if args.mode == "status" else getattr(lease, args.mode)()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("C2_SLOT_LEASE_ERROR: " + str(exc), file=sys.stderr)
        sys.exit(1)
