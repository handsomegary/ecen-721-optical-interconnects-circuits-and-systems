# SAR7 case23 CML drive2, lease-fix package (2026-11-17)

This is the single physical TT case `sar7_23_tt_175gs_cml_drive2`, built on the case21 circuit and timing. The only change is in the CML input buffer that drives all 7 comparators. The 2 sense NMOS and 2 tail NMOS each get one complete replica, which doubles the device width. The 2 load resistors go from 500 Ω to 250 Ω and the bridge resistor from 250 Ω to 125 Ω. Nothing else changes: pulses, 12 center codes, gates and reads are all the same. This package replaced the 0934 package's C2 lease helper, which had refused a partially successful `scontrol` update caused by a finished array element. The core, sbatch, plan and deck are byte-identical to 0934.

- Job 761986: COMPLETED in 6:26 (solver 332 s). The lease begin was clean. The restore met the rc1 "Job has already finished" warning, then a fresh read verified throttle 5.
- 565 screen fails. Registered codes: 12 available, 7 wrong, sum|err| 8, max 2 (case21: 7 wrong, sum 7, max 1). conv8 b1 is still unresolved.
- conv4 flips from −1 to +1 LSB through a b5 flip; conv7 grows from +1 to +2 LSB.
- Max sample error improves (1.673 → 1.578 LSB). The largest resolve delay gets worse (45.0 → 47.0 ps). CM gates still pass.
- The CML draws a mean 0.484 mW over 78–565 ps, about twice the original estimate.
- Decision: STOP. The 2× CML impedance scaling branch is rejected.

`results/` holds a compact extract (per-bit timing snapshots removed). The full summary and all receipts stay on the cluster and in the private results folder. `package/` is the Codex source without decks, and `prompts/` holds the executor reply.
