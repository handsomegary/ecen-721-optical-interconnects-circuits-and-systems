# SAR7 native r5 CML sense-isolation single case (TT) — 2026-11-15

- Package: `ECEN721_PAM4_SAR7_CML_SENSE_20261115.zip` (SHA256 8a8d5556b3dd6370889fdfb43152231bf527744fdea4eca58cc1e5daf5bb26cb); source in `package/` (no decks).
- Case `sar7_06_tt_r5_cml_sense`: 760091 relaxed direct-load bench (un-trimmed Vref, as 760132) plus an r5 B0 CML sense arm (500 ohm loads, 4 native nmos_lvt, tail gate 0.5 V, 0.9 V supply, per-leg tails) driving the seven comparators with swapped inverted legs. Diff vs 760091: 8 elements + 7 comparator input pairs + 1 save. Job 760254 (1 CPU, 3:40).
- vs 760091 / 760132: wrong 10 / 10 -> 11/12; unresolved bits 0 / 0 -> 3; sum |dcode| 30 / 15 -> 197; max 7 / 3 -> 24; final CDAC CM change -112/-109 / -4.3 -> -4.0/-3.9 mV.
- Sense arm: projected gain 0.0335, sign agreement 80/84 (only b6 near zero), output CM 0.835 V, supply 260.7 uA. SAR converges to an input-referred threshold of about -14.5 mV (-18.6 LSB): codes +13..+24 high.
- Read-only note: historical r5 B0 also has `B0_RDEG` 250 ohm between the two source nodes; this package omits it, which likely explains the ~0.03 gain (not verified by simulation).
- Decision: STOP (CM isolation achieved, but gain/offset unusable; next direction is Codex's).
- `results/`: `sar7_cml_sense_summary.json` (SHA256 a9670002… on Olympus, home path masked). `prompts/`: Claude's report.
