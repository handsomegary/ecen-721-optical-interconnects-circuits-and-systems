Stage: SAR7 case23 CML drive2 (sar7_23_tt_175gs_cml_drive2): stopped at C2 lease begin, before sbatch
Status: blocked
Decision: INCONCLUSIVE: the package's c2_slot_lease.py begin fails against the live array 761525, so no job was submitted. This is not a circuit result.
Summary:
- Network is back. The single read-only probe at 09:56:57 CST succeeded, so I resumed 0934 from the upload step.
- ZIP SHA-256 b2496138d0f663d5e5066522b307bd07c4263951fcdce246c9a650ea0e284fd7 matches the header, the sidecar and the copy on Olympus.
- `sha256sum -c` passes 8/8. `verify` passes (deck ae60badd4499e1b572cfe3aada353a3f62b0ac78578a1142809f071f22b2518b). Unittests pass 25/25.
- approval-template: manifest 5e32c453df77102ee3c3cf98c1cf73f29b4b8c8ad5d0cf3ec7ff38e34efa074b, matching the message. The only change I made was `"approved": false` → `true` (approval sha256 926ce430df70f0affca95e86fa563c1fcb64acfbdfaa9ddd35a9941d8b0c1318). Stage needed `--model-root` set to the existing private model root and then returned rc=0.
- Exact diff against case21 (bench 55c5c977… → staged bench 64d27c67…, 428 → 432 lines):
  - 4 added MOS cards: _D2 copies of the two sense and two tail NMOS. Each card matches its original byte for byte after the instance name, with identical W/L/nf and parasitics.
  - 3 resistor value lines changed: both loads 500 → 250 Ω, bridge 250 → 125 Ω.
  - Nothing else differs.
- C2 lease `begin` (lease_id 99cfec4fb819426db31510243925ca3c, 15:58:58Z) exited 1 with "C2_SLOT_LEASE_ERROR: Lease begin failed AND immediate restoration failed".
- Root cause, from c2_slot_lease_events.jsonl:
  - `scontrol update JobId=761525 ArrayTaskThrottle=4` returned rc=1 with stderr "761525_17: Job has already finished". Slurm still applied the change: the follow-up `scontrol show` read ArrayTaskThrottle=4.
  - The cleanup `scontrol update … ArrayTaskThrottle=5` also returned rc=1 with the same stderr, yet it applied too.
  - The helper requires returncode==0 (c2_slot_lease.py line 150). It therefore logged restore_NOT_RESTORED even though the throttle really returned to 5.
  - Element 17 finished after case22's lease at 14:28Z, when tasks 15–19 were all running. That is why case22 passed and this begin fails. Every later begin/restore against 761525 will fail the same way while any finished element remains, which means for the rest of C2.
- Current state, verified by read-only `scontrol show` and the helper's `status`:
  - 761525 ArrayTaskThrottle=5 on all 7 records (the original value). Tasks 18 and 20–23 are running and 24–94 are pending at %5.
  - Lease status `active=false`.
  - No C2 task was interrupted, and no score, seed or job changed.
- No sbatch was run and there is no accepted job, so the package's one accepted-job / one-solver budget is still unused. I did not run the helper's `restore`, because the throttle is already at the original 5 and restore would hit the same rc=1. I did not patch the helper, did not bypass the lease, and did not hand-set the throttle for this package.
Run paths: Olympus `~/ecen720_28nm/runs/pam4_sar7_cml_drive2_20261117.ZIiwgT` (pointer `~/ECEN721/.sar7_cml_drive2_base`). It holds a staged case dir, approval.json (approved=true), logs/ and wrappers/env_cml_drive2.sh + submit_cml_drive2.sh. Receipts are in OneDrive `outputs/PAM4_SAR7_CML_DRIVE2_20261117_LEASE_FAIL_RECEIPTS/` (10 files + SHA256SUMS.txt): lease json/events, begin/status logs, approval and template, case.json, stage log and the deck diff.
Commit: handoff archive only (no results yet)
Needs user decision: no. Codex needs to fix the lease helper. Suggestion: treat the update as successful when stderr only lists already-finished array elements and the post-update `scontrol show` reads the target throttle. Then send a new package or ZIP, and I will run it in the same root or a new one per the Guide. Separately, the standing task file allows a manual `scontrol update … ArrayTaskThrottle=4` before a SAR7 job. I did not use it, because this package binds sbatch to `status --require-active`.
