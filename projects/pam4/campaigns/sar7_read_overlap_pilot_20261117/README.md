# SAR7 1.75 GS/s read-aligned trial overlap pilot (2026-11-17)

Single case `sar7_18_tt_175gs_read_overlap`: exact qbuffer circuit (job 761549) with only the 12 trial/clock
pulse cards retimed (next trial edge starts at previous read; guard 3→0.5 ps; b0 eval 54→46 ps; b3 wait +7, b2 wait +16).

- Job 761649 (Olympus), solver completed; collector failed (KeyError 'trial6'), summary pending a fixed collect-only.
- Decision: INCONCLUSIVE. See `prompts/` for the full report.
- `package/` = Codex source (no decks/ZIPs).
