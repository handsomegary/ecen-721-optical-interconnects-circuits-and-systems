# Project #6 PAM4 deskew C1 TT transient-noise smoke, seed 1001 (2026-11-16)

Five frozen cases (zero, P late 0/−60, N late 0/+60), Spectre classic +mt=1, noise 500 MHz–150 GHz, seed 1001; jobs 761319 and 761421 (array 1–4). Each side scores 2,032 FFE centers; clipping 0 in all cases.

- `package/`: Codex source (no decks or ZIP).
- `results/c1_noise_smoke_summary.json`: summary (original SHA ec30d9d95c29e3dcfb3cede5f0b83e48ae3e2354011a8fd841f1b8d6f4549fc9).
- `prompts/`: progress and final replies sent to Codex.

Paired deltas (comp − base errors): P late −60 primary −125 / secondary −173; N late +60 primary −278 / secondary −224. Secondary absolute SER is 34–45% in every case (noise enhancement suspected); compare pairs only.
