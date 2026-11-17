# SAR7 comparator-timing pilot (TT, 42 ps) — 2026-11-15

- Package: `ECEN721_PAM4_SAR7_TIMING_PILOT_20261115.zip` (SHA256 8d4c53e7c176369ebec1041b5d205db5e1d47206793e62284f850b037defdea3); source in `package/` (no decks).
- Change vs. job 759069 (`sar7_slice_20261115`): the seven `V_clk` comparator pulses rise 17 ps earlier (compare window 25 → 42 ps; DAC trial settle 38 → 21 ps). Same 12 codes, 0.756855 V CM, 100 mVppd, 1.75 GS/s, TT private kit.
- Olympus job 760002, COMPLETED in 2:06; solver 114.8 s; raw 43.8 MB kept on Olympus.
- Result: 0/84 unresolved bits (was 73/84), but 10/12 wrong codes (was 5); logic_smoke_pass=false.
- Diagnosis: 83/84 decisions follow the pre-trial residue sign; all 7 trials whose residue flips sign during the trial follow the pre-trial sign → CDAC not settled at compare (21 ps). Two b0 errors come from ~1 LSB sampling error. Decision: STOP; next timing choice is Codex's.
- `results/`: `sar7_timing_summary.json`, `sar7_02_tt_earlycmp42_measurements.json` (home path masked). `prompts/`: Claude's report.
