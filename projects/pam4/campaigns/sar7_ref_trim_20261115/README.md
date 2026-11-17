# SAR7 direct-load CDAC Vref trim single case — 2026-11-15

- Package: `ECEN721_PAM4_SAR7_REF_TRIM_20261115.zip` (SHA256 c2268736c1b92a96ce6c9e68adfd06383c61cc54800959f6304483a7cb75e17f); source in `package/`.
- Case `sar7_05_tt_ref_trim`: 760091 relaxed direct-load bench with only V_RHI/V_RLO changed (span x127/107.16 = 57.18 -> 67.77 mV, midpoint 0.45 V); scoring final read moved 1027 -> 1030 ps per cycle, per-bit compare times unchanged. Job 760234 (1 CPU, 3:24).
- vs 760091: wrong conversions 10 -> 7/12; sum |comparator code error| 30 -> 8; max 7 -> 2; registered null 6 -> 0; full-scale residue ~10.5 -> <=1.9 LSB; max sample error 1.37 -> 1.41 LSB; final CM drop unchanged (-112/-109 mV).
- Remaining +/-1-2 errors: sampling error (codes 1/126) and MSB midpoint offset (code 63, b6 pre-trial residue +2.89 LSB) plus sub-LSB low-bit decisions.
- Decision: STOP (gain trim confirmed; not acceptance; next direction is Codex's).
- `results/`: `sar7_ref_trim_summary.json` (SHA256 b70fdf21…, home path masked). `prompts/`: Claude's report.
