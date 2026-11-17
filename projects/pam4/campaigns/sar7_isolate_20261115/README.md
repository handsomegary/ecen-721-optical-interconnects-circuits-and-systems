# SAR7 comparator-input isolation diagnostic (TT, 60 ps + 60 ps) — 2026-11-15

- Package: `ECEN721_PAM4_SAR7_SENSE_ISOLATION_20261115.zip` (SHA256 43ecd1547d01571f844c2ed925cb686d7f705d1e5de959a0ae51d698df8d0393); source in `package/` (no decks).
- Change vs. `sar7_relaxed_20261115` (job 760091): adds ideal unity VCVS `EISO_P`/`EISO_N` and moves the seven `XCMP` inputs from `mp mn` to `isop ison` (16 diff lines). Removes total comparator input load (static + kickback, not separable). Diagnostic only, not a 1.75 GS/s spec pass.
- Baseline audit of 760091 PSF (`results/sar7_760091_rail_audit.json`): all 6 unreadable registered codes are bit 0 only; comparator q0 at rail at read and end_s, output pair stuck at ~0.322/0.768 V at end_s. Null codes are exactly those with b0 = 0 (same in 760132).
- Olympus job 760132, COMPLETED in 3:34; solver 184.8 s; raw 82.6 MB kept on Olympus.
- Result: 0/84 unresolved; 10/12 wrong (unchanged), but sum |Δcode| 30 → 15, max |Δ| 7 → 3; final CDAC CM change −110 mV → −4.3 mV; full-scale residue ~±10 → ~±5 LSB; max sampling error 1.687 LSB; 5/12 registered null.
- Decision: STOP; comparator loading explains part of the error; remaining CDAC transfer/weight error and the b0 = 0 output path are for Codex to decide.
- `results/`: summary, rail audit and measurements JSON (home path masked). `prompts/`: Claude's report.
