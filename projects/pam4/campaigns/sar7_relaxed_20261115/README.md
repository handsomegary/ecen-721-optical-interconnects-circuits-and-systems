# SAR7 relaxed-timing diagnostic (TT, 60 ps DAC wait + 60 ps compare) — 2026-11-15

- Package: `ECEN721_PAM4_SAR7_RELAXED_PILOT_20261115.zip` (SHA256 55ec7f5dd3b8cb9a0befbb910407e03ca2d29bd4f4151d97a3ffc153c870de64); source in `package/` (no decks).
- Change vs. `sar7_slice_20261115`: period 571.4 → 1080 ps (0.926 GS/s, low-speed diagnostic only); 22 timing pulses, 2 PWL time axes and tran stop changed (25 lines). Same circuit, 12 codes, 0.756855 V CM, 100 mVppd, 1 Ω, TT private kit.
- Olympus job 760091, COMPLETED in 3:22; solver 185.5 s; raw 82.6 MB kept on Olympus.
- Result: 0/84 unresolved comparator bits; 10/12 wrong codes (same as 760002); 6/12 registered output codes unreadable (not at rail); logic_smoke_pass=false. Max resolve 54.3 ps, max sampling error 1.373 LSB, final CDAC CM −112.5 to −109.1 mV.
- Diagnosis: decisions follow the residue (80/84; the 4 exceptions are within ~0.3 LSB of zero). The SAR loop converges to < ~1 LSB final residue while codes are off by −6..+7, which points to a static CDAC weight/gain error. Full scale is short by ~10 LSB. Decision: STOP; next step is Codex's.
- `results/`: summary and measurements JSON (home path masked). `prompts/`: Claude's report.
