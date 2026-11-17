Stage: SAR7 case23 CML drive2 (lease helper fix package) sar7_23_tt_175gs_cml_drive2
Status: done
Decision: STOP — 565 screen fail (reg 7 wrong, max 2 LSB > gate 1; conv8 b1 still unresolved; resolve delay 45.0 -> 47.0 ps, so sense is not effective earlier). Reject the 2x CML scaling branch per the stop rules.
Summary: one job 761986 accepted and COMPLETED 6:26 (solver 332.1 s). Codes are no better than case21: sum|err| 7 -> 8, max 1 -> 2. CML draws 0.484 mW mean over 78–565 ps. Lease begin rc0; restore hit the exact rc1 finished-element case (761525_33), which was verified_with_finished_element_warnings -> restore_verified 5.
Run paths: ~/ecen720_28nm/runs/pam4_sar7_cml_drive2_lease_fix_20261117.IuKPg7 (summary sar7_cml_drive2_summary.json); OneDrive outputs/PAM4_SAR7_CML_DRIVE2_LEASE_FIX_20261117_RESULTS/ (26 files + SHA256SUMS, 26/26 OK)
Commit: see below (handoff + results)
Needs user decision: no

## Handled message
- inbox `20261117T1053_sar7_cml_drive2_lease_fix.md`. ZIP `ECEN721_PAM4_SAR7_CML_DRIVE2_LEASE_FIX_20261117.zip` SHA `0a588fddb57a781a1d230c5c1962559c159ac2ffc93821b14c6ec194e8742df6` matched (local copy, sidecar, and Olympus).
- New root `pam4_sar7_cml_drive2_lease_fix_20261117.IuKPg7` (canonical mktemp). The old 0934 root ZIiwgT was not touched: its approval, lease and receipts are all still in place.
- `sha256sum -c` passed 8/8; manifest SHA `f98875b1…2381`; LF only. `verify` returned deck `ae60badd…518b`. unittest 29/29 OK.
- The approval-template's only change is approved=true. It binds the new root, manifest f98875b1 and deck ae60badd. approval.json SHA is `d82ecb28…f6d5`.
- Stage used the existing private model root. The staged bench.scs SHA `64d27c67…bd63` is byte-identical to the 0934 staged bench. The diff against case21 is exactly 4 added MOS replicas plus 3 R changes (500→250, 500→250, 250→125), and this diff file is byte-identical to the 0934 one.
- Pre-check: sacct showed no other case23 or SAR7 job accepted since 13:00Z, and all 7 records of 761525 showed throttle 5.

## Lease and job (receipts in OneDrive)
- lease_id `e3c02f93e61a4852b9a368e67b642070`. Begin at 21:28:18Z: show, update ArrayTaskThrottle=4 returned rc0 with empty stderr, then a fresh show returned begin_verified. prior_throttle was 5.
- `status --require-active` returned rc0 (active=true). After that, sbatch was run once: job **761986**, Submit 2026-11-17T15:28:22 CST (21:28:22Z, after 13:55Z).
- The job waited (QOSMaxCpuPerUserLimit) until a C2 slot freed. It started 16:02:03 and ended 16:08:29, COMPLETED 0:0, 1 CPU, on n02-hera. In-job status at 22:02:08Z was active, throttle 4.
- Restore at 22:08:29Z: update ArrayTaskThrottle=5 returned **rc1, stdout empty, stderr exactly `761525_33: Job has already finished\n`**. The fresh show confirmed every record at 5, giving `verified_with_finished_element_warnings` and then `restore_verified` (outcome restored5). That is the exact case the fix was written for. The raw rc and stderr are kept in c2_slot_lease_events.jsonl.
- A separate scontrol check afterwards showed 6 records, all ArrayTaskThrottle=5; 761525 is running 5-wide again. C2 was not cancelled or resubmitted. The accepted-job and solver budget (1 each) is now used up.

## Results (case23 vs parent case21 job 761700)
| gate (565) | case21 | case23 |
|---|---|---|
| registered available / wrong / sum\|err\| / max | 12 / 7 / 7 / 1 | 12 / 7 / 8 / **2** |
| comparator available / wrong / sum / max | 11 / 6 / 6 / 1 | 11 / 6 / 7 / 2 |
| unresolved raw bits | 1 (conv8 b1) | 1 (conv8 b1) |
| cmp/reg agreement | false | false |
| screen_pass / logic_smoke | false / false | false / false |
| physical_read_window_valid, active-last-read CM pass | true | true |
| final DAC ΔCM 565 (mV) | −9.17 / +5.39 | −8.73 / +5.30 |
| last-compare trigger ΔCM (mV) | −4.23 / −3.66 | −3.96 / −3.40 |
| max \|sample error\| (LSB) | 1.673 | 1.578 |
| max observed resolve delay | 45.0 ps | 47.0 ps |
| min sampled margin | 1.21 ps | 0.96 ps |

Readouts at 563 and 554 give the same comparator numbers. At 563 the registered result is 12/7/8/2; at 554 it is 12/8/10/2. At 557, registered has 6 available and 6 missing.

Codes (expected | c21 cmp, reg565 | c23 cmp, reg565):
conv0 64|64,64|64,64 · conv1 0|0,0|0,0 · conv2 127|127,127|127,127 · conv3 31|31,31|31,31 · **conv4 96|95,95|97,97** · conv5 63|64,64|64,64 · conv6 65|64,64|64,64 · **conv7 85|86,86|87,87** · **conv8 42|None,43|None,41** · conv9 1|0,0|0,0 · conv10 126|127,127|127,127 · conv11 64|64,64|64,64

Bit changes vs case21 (all other bits match):
- conv4: the b5 decision flips from 0 to 1 (sampled margin 1.21 → 1.46 ps). Because the prefix changed, b4 to b1 all go from 1 to 0. The code goes from −1 to +1; the error size is the same.
- conv7: b0 goes from 0 to 1 (margin 3.0 → 6.75 ps), so the error grows from +1 to +2.
- conv8: b1 is still unresolved (None). The register reads 41 instead of 43 (−1 instead of +1).
- Overlap diagnostic: 72/72 boundaries assessed; 0 unresolved and 0 opposite-rail; minimum prior internal |x−y| is 0.623 V.

CML power and current (new absolute values, active window 78–565 ps, 12 frames):
- Mean supply power is 0.4844 mW (frame range 0.4843–0.4849). Mean draw current is 0.538 mA; the peak is 0.654 mA. Energy per frame is 0.236 pJ.
- Sense CM spans 0.818–0.841 V.
- The current computed analytically as (1.8−sensep−sensen)/250 matches the source current to within 5.4e-19 A.
- This is close to the predicted 2× of the original ~0.235 mW. The old case21 RAW has been retired, so no measured old-vs-new window ratio is claimed.

## Reading (against the package stop rules)
- The 565 screen fails because max code error is 2, above the 1 LSB gate. sum|err| also rises (7 → 8) and the conv8 b1 unresolved bit remains.
- The largest observed resolve delay did not shrink (45 → 47 ps); the minimum sampled margin also dropped (1.21 → 0.96 ps). The per-bit trajectories therefore give no evidence that sense becomes valid earlier.
- The sample error improves slightly (1.673 → 1.578 LSB) and CM stays inside the gate. However, conv4 and conv7 moved in the wrong direction, consistent with the added input load and kickback warned about in the package.
- Under the stop rule ("未達標而sense未更早有效…拒絕這個縮放方案"), this 2× CML scaling branch is rejected. There is no automatic 4×, no bias/VCM/clock change and no case24. Codex reviews next.

## Data
- RAW is kept (per the package: still under diagnosis, nothing deleted): `sar7_23_tt_175gs_cml_drive2/raw`, 118,289,421 B (tran 118,288,663 B). case22 RAW is also kept.
- Full summary SHA `6139242337932516bf32d938f7ed19fe176cbc1b116869641c66e461ce835bae` (3,764,276 B); measurements `ecba3123…02ca`; tran `04d0f9ce…e9c9`.
- OneDrive results contain the summary, measurements, run_status, execution_intent, case.json, spectre/runner logs, submission_proof, slurm out, sacct, approval, the lease json/sha/events, every log (verify, unittest, stage, diff, lease begin/status, sbatch), the RAW inventory and a pointer to the old failed 0934 root. All have checksums, and 26/26 verified after the copy.
