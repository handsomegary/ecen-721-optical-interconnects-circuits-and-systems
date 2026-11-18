# Project #6 PAM4 deskew C2 TT paired multi-seed batch (2026-11-16 → 2026-11-18)

95 new Spectre classic +mt=1 cases (seeds 1002–1020 × zero, P late 0/−60, N late 0/+60), same frozen stimulus, FFE, window and ideal 7-bit scoring as C1; seed 1001 (C1) is descriptive only. Slurm array 761525 (0-94), all COMPLETED; clipping 0 in all 100 cases × 2 outputs.

- `package/`: Codex source (no decks or ZIP).
- `results/c2_tt_paired_summary.json`: summary (original SHA a164336ee415c5e7d0c10e60db7a4e719c4bd269de528255a909ac41f8c27ede; this copy has the home path masked as `~`).
- `prompts/`: final reply sent to Codex.

Fresh 19 seeds, errors before→after compensation (38,608 symbols per arm), all 19 seeds improved, exact one-sided paired sign test p = 1.9e−6 each:
- N late +60 (C0 selection): primary 7316→2042, secondary 16846→13168.
- P late −60 (fixed-code diagnostic): primary 4482→1811, secondary 15868→12939.

Secondary absolute SER remains 33–44%; the batch validates the paired direction only (TT, fixed stimulus, two skew endpoints), not absolute reference-paper performance.
