# SAR7 CDAC round 2 — retained-evidence audit of 760874 (2026-11-16)

Read-only collector over the retained PSF of case `sar7_09_tt_cml_main_ratio` (job 760874, campaign `sar7_cdac_fix_20261116`). Zero new solver jobs.

- Olympus run root: `~/ecen720_28nm/runs/pam4_sar7_cdac_round2_audit_20261116.c85nB5` (collector job 761255, 1 CPU / 6 GiB, 0:21).
- Package ZIP SHA-256 `7f72ce581b3d8a5aa50b26564271fca3cba7ff71031eda4a07ffc5ef5611a598`.
- Full analysis JSON (`0e9e0915…`) and byte-exact source copies stay on Olympus / OneDrive; `results/` holds only an aggregate summary without trial time series.
- Finding: actual control words match the old prefix assumption 84/84; #8 sample error −0.19 LSB; all 5 decision/sign disagreements are "negative input, decided 1" (one-sided), with the #8 b2 latch flipping between 30 and 50 ps after compare. Descriptive CDAC fit span 126.9 LSB, leave-one-out RMSE 1.01 LSB.
- Reply: `prompts/20261116T1545_sar7_cdac_round2_audit_result.md`.
