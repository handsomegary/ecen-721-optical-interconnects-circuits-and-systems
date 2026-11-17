# SAR7 760348 retained-raw final audit (zero new simulation) — 2026-11-15

- Package: `ECEN721_PAM4_SAR7_CML_RDEG_AUDIT_20261115.zip` (SHA256 83bf3ae00747c95cbe9badabff9282e300a1f378afc23b802c844f7abe217039); source in `package/`.
- Read-only collector job 760362 (1 CPU, 0:20, zero solver, no new raw) over the retained PSF of job 760348 (`sar7_07_tt_r5_cml_rdeg`); original ZIP SHA measured (938e179f…43dc).
- CDAC fit (84 pre-compare states, identified): sample gain 0.990, offset 57.12 LSB, weights b6..b0 = 56.13 / 29.41 / 14.70 / 7.00 / 3.60 / 2.02 / 1.05 LSB, span 113.9 vs 127 LSB, LOO RMSE 0.86 LSB.
- Sense affine: slope 0.588 V/V, output intercept 82 uV, output RMSE 225 uV; sense-stage zero crossing -0.18 LSB (not comparator offset); sign agreement 83/84 overall, 82/82 for |held| >= 0.25 LSB.
- Original scores unchanged: 10/12 wrong, sum |dcode| 23, max 5 LSB; 0.926 GS/s diagnostic only.
- Decision: STOP (final audit; residual code errors trace to CDAC span compression, not the sense stage; no tuning or new simulation).
- `results/`: `sar7_cml_rdeg_final_audit.json` (SHA256 bc8c4e64…f9c4). `prompts/`: Claude's report (includes corrected full SHAs for the 2042 report's mistyped abbreviations).
