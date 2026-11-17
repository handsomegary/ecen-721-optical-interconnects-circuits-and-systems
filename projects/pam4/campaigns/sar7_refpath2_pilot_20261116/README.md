# SAR7 1.75 GS/s reference-path 2× pilot (2026-11-17)

One case, `sar7_17_tt_175gs_refpath2` (job 761632), rebuilt from the q-buffer bench (761549). This is one coordinated 2× scale: the 28 functional XRef and 28 matched dummy loads use SAR_REFTG2, the strong OAI/NOR replicas are doubled, and the decoder INV and second q-buffer stage go from 2 to 4. That is 126 instance swaps plus 4 local cells. Timing, CDAC, comparator, register and reference voltages are unchanged.

- `package/`: Codex source (no decks, ZIPs or models).
- `results/sar7_refpath2_summary.json`: the summary with paths masked (original SHA 06de75d36d492b3e7d166e124094e73aa8a94a8be2e497d33f01b354b334b611).
- `prompts/`: the reply sent to Codex.

Result: STOP, and worse than 761549. At 565 ps the registered codes have 8/12 wrong (Σ58, max 32 LSB), and the comparator code is readable for only 5/12. 7/84 bits are unresolved, 4 of them MSBs (761549 had 2/84). Median decode-to-rail delay rose from 40.4 ps to 47.0 ps. Peak reference-source current rose from 217 µA to 455 µA. The two original problem codes did not change (85→88, 42→44). The CM gates still pass (552 ps: −3.3 mV; 565 ps: −9.5/+7.8 mV).
