# SAR7 case19 compare-window pilot (2026-11-17)

One physical TT case (`sar7_19_tt_175gs_compare_window`) built from the exact case18 circuit. Only 12 pulse cards changed (trial/clk for b6–b1). The MSB wait went from 42 to 30 ps; the freed 12 ps went to b2 EVAL (38→47) and b1 EVAL (41→44). b0 and the read/reset timing did not change.

- Job 761674 (5:53, solver 309 s). Screen at 565 ps: FAIL.
- Registered 12/12 readable, 7 wrong, max 1 LSB. Comparator 10/12.
- Unresolved bits went from 4 to 2. conv7 b2, conv7 b1 and conv8 b2 now resolve. conv8 b1 is still unresolved. conv7 b0 is a new unresolved bit.
- All 12 MSBs resolve inside the 39 ps window (min margin 6.0 ps). Minimum b0 margin went from 1.18 to 3.57 ps.
- conv8 b2 accepts Z only after an O→transition→Z sequence that ends about 6 ps after the next compare. That is the likely cause of the conv8 b1 failure.
- 72-boundary diagnostic: 1 unassessable (conv8 b1→b0), 0 opposite-rail among the 71 assessable.

`results/` holds a compact extract of the 3.4 MB summary (full file stays on the cluster and in the private results folder). `package/` is the Codex source and `prompts/` the executor reply.
