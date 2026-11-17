# SAR7 native r5 CML sense with 250 ohm source bridge, single case (TT) — 2026-11-15

- Package: `ECEN721_PAM4_SAR7_CML_RDEG_20261115.zip` (SHA256 938e179f33863ddec49894ba0a44f27b5249cf4efad3dfbfe4ac1bd9248e43dc); source in `package/` (no decks).
- Case `sar7_07_tt_r5_cml_rdeg`: the 760254 CML sense bench plus the historical r5 `B0_RDEG` 250 ohm resistor between the two source nodes. Diff vs the 760254 bench: exactly one line. Job 760348 (1 CPU, 3:39, solver 188.8 s, raw 87.8 MB).
- 760132 (ideal sense) / 760254 (CML, no bridge) -> 760348:
  - projected sense gain: 1 / 0.0335 -> 0.588
  - sign agreement: 80/84 (760254) -> 83/84
  - unresolved bits: 0 / 3 -> 0
  - wrong codes: 10 / 11 -> 10 of 12
  - sum |dcode|: 15 / 197 -> 23; max |dcode|: 3 / 24 -> 5 (760234 ref-trim, direct load: 8 / 2)
  - final CDAC CM change: -4.3 / -4.0 -> -4.0/-3.9 mV
- Residual code errors have the same signs as in 760132 and are about 1.5–1.7x larger, consistent with the un-trimmed Vref and gain < 1 (inference, not simulated).
- Decision: STOP (gain and isolation restored; max 5 LSB exceeds the ~1–2 LSB target; next direction is Codex's).
- `results/`: `sar7_cml_rdeg_summary.json` (SHA256 ab2cdaaa… on Olympus, home path masked). `prompts/`: Claude's report.
