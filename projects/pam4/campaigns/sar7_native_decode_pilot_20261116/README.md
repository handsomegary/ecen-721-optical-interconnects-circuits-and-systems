# SAR7 1.75 GS/s native OAI21+NOR3 reference decode with retimed slots (2026-11-16)

One case, `sar7_14_tt_175gs_native_decode` (job 761433). Native decoder + symmetric dummy loads; D/A waits b6..b0 = 42/40/24/17/13/10/8 ps; readouts at 554 and 557 ps.

- `package/`: Codex source (no decks, ZIPs or models).
- `results/sar7_native_decode_summary.json`: summary (paths masked; original SHA c2f46592839597c54d61ee843da089f86fcc9771aadc7cec0d01ed15f4bfbab6).
- `results/native_registered_bits_548_565ps.json` + `scripts/native_regbits.py`: Claude's read-only sampling of registered bit pairs and conv at 548–565 ps.
- `prompts/`: reply sent to Codex.

Result: STOP. Both readouts screen_pass=false. Registered readable 4/12 because b0=0 registers are still flipping after the 550 ps trial release (rail by ~560 ps); comparator 10/12 readable, 5 wrong, max 6 LSB; b4–b1 held settles 22–41 ps after launch, longer than the 24/17/13/10 ps windows.
