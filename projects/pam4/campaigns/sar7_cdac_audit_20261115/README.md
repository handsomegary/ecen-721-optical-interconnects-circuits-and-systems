# SAR7 retained-raw CDAC weight and b0 readout audit — 2026-11-15

- Package: `ECEN721_PAM4_SAR7_CDAC_AUDIT_20261115.zip` (SHA256 f41bba0b672f6b59fa5e99981927eabeeea2786d97f63cc1dd2726cdddc5a24f); source in `package/`.
- Read-only audit of retained PSF from jobs 760091 (direct sense, `sar7_relaxed_20261115`) and 760132 (ideal isolation, `sar7_isolate_20261115`). Zero new simulations; collector job 760174 (1 CPU, 33 s).
- Weight fit (actual bit states and voltages; expected codes not used), 84 points each, leave-one-conversion-out RMSE 0.748 / 0.887 LSB.
  - 760091: offset 53.74 LSB, gain 0.9887, weights b6..b0 = 52.57, 27.65, 13.84, 6.85, 3.37, 1.87, 1.01 LSB, span 107.16 vs 127.
  - 760132: offset 59.75 LSB, gain 0.9899, weights = 58.77, 30.77, 15.37, 7.32, 3.77, 2.04, 1.12 LSB, span 119.16 vs 127.
- b0 readout (thresholds 0.18 / 0.72 V): b0 = 0 outputs are ~0.322 / 0.768 V at `end_s` but ~0.077 / 0.837 V at `end_s + 3.5 ps`, before conv falls; rail reached 12.5 ps after the last trial release (b0 = 1: ~0.25 ps). Read point too early, path works. Frozen scores unchanged.
- Decision: STOP; remaining wrong codes are explained by static CDAC span/weight and offset; next direction is Codex's.
- `results/`: `sar7_cdac_weight_audit.json` (SHA256 e7d7e006…, home path masked). `prompts/`: Claude's report.
