# SAR7 case21 accepted-reference timing-gap pilot (2026-11-17)

One physical TT case (`sar7_21_tt_175gs_accept_gap`) built from the exact case20 circuit. Only 10 pulse sources changed (trial1-6, clk2-5). The MSB EVAL went from 37 to 35 ps and the b2 EVAL from 47 to 44 ps; the 5 ps went to the b1 WAIT (8 to 13 ps). So the gap from b2 release to b1 compare grew from 6.5 to 11.5 ps. b1 compare/read and all b0 timing are unchanged.

- Job 761700 (6:06, solver 323 s). Screen at 565 ps: FAIL.
- Registered 12/12 readable, 7 wrong, max 1 LSB. Comparator 11/12. All 84 comparator decisions match case20.
- All 7 b2 accepted-Z commands now settle before the next b1 compare (nominal margin 0.86 to 1.07 ps; case20 was about 4 ps late).
- conv8 b1 is still unresolved. At its compare the differential is only about +0.09 LSB held / -0.06 LSB sense. So a late Z alone does not explain the failure.
- The earlier b2 release opens new accepted-O bubbles in conv4, conv7 and conv10 (conv7: 8.5 ps transition, O back only 0.5 ps before the b1 compare). No b1 decision flipped.
- MSB minimum margin 2.00 ps, b2 minimum 1.93 ps, as predicted by the package.
- This timing branch stops here.

`results/` holds a compact extract of the 3.4 MB summary (the full file stays on the cluster and in the private results folder). `package/` is the Codex source and `prompts/` the executor reply.
