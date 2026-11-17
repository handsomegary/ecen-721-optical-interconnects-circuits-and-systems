# SAR7 1.75 GS/s ideal reference-TG gate drive isolation (2026-11-16)

One case, `sar7_13_tt_175gs_dac_gate_bypass` (job 761426), same timing as 761321; 28 reference TG gate nets rewired to ideal `bsource` drive (36 bsource), everything else identical.

- `package/`: Codex source (no decks, ZIPs or models).
- `results/sar7_dac_drive_summary.json`: summary (paths masked). SHA of the original on Olympus: fdcca5230efa8c6a8b534d54c4acd6ecdd2b290d2af4cfc0a55bd24a87625748.
- `prompts/`: reply sent to Codex.

Result: registered 6/12 wrong, sum 6, max 1 LSB — identical codes to 761279; 2 unresolved b0 bits near zero; code_screen_under_ideal_drive=false, logic_smoke_pass=false. b4–b0 held settles within 21 ps; b6 (36.5–37.0 ps) and part of b5 remain late with ideal gates.
