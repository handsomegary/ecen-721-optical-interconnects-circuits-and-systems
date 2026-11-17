# SAR7 case20 b2 local-drive pilot (2026-11-17)

One physical TT case (`sar7_20_tt_175gs_b2_local_drive`) built from the exact case19 circuit. Only the b2 real and dummy local control cells changed: the OAI/NOR and their complementary inverters were doubled in drive, and the second qbuffer inverter went from INV2 to INV4 (p and n). That is 10 instance swaps and 3 new cells. TG switches, the CDAC, the 14 first-stage qbuffer INV1s and every other bit cell are unchanged. The MSB EVAL went from 39 to 37 ps and the 2 ps went to b0 EVAL (46 to 48 ps).

- Job 761688 (6:07, solver 324 s). Screen at 565 ps: FAIL.
- Registered 12/12 readable, 7 wrong, max 1 LSB. Comparator 11/12.
- Unresolved bits went from 2 to 1. conv7 b0 now resolves (margin 1.75 ps). conv8 b1 is still unresolved.
- conv8 b2 accepts Z 2.25 ps earlier than in case19, but Z still arrives 4.07 ps after the next b1 compare (case19: 6.32 ps).
- The larger second qbuffer stage delays every b2 qmid/qdecode by about 1.9 to 3.6 ps. The accepted O path shows no bubble.
- All 12 MSBs resolve in 37 ps (min margin 4.00 ps). b5 is unchanged.
- The hypothesis that 2x local drive is enough is rejected.

`results/` holds a compact extract of the 3.4 MB summary (the full file stays on the cluster and in the private results folder). `package/` is the Codex source and `prompts/` the executor reply.
