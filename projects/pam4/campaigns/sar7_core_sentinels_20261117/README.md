# SAR7 case22 fixed-input core sentinels (2026-11-17)

One TT diagnostic case (`sar7_22_tt_core_sentinels`) built from the exact case20 circuit. Only the 7 comparator input pairs were moved to 2 stiff PWL sources (`diag_p/n`), and those 2 nodes were added to the save list. All other physical and timing content is unchanged. The run holds 12 frames: 6 targets (±48.8 µV, ±1 LSB = 0.78125 mV, ±5 mV), each preceded by an opposite-polarity 5 mV precondition, at VCM 0.8346 V. That is 84 comparator decisions in total. This is an input characterization of the existing core. It is not a SAR ADC result, and no ADC score applies.

- Job 761764 (6:00, solver 327 s). Controls valid: 56/56 strong (5 mV) decisions correct and stable by 44 ps. Reset and input are correct in 84/84.
- ±1 LSB: raw is correct by 44 ps in 14/14 (median stable delays: internal 37.6 ps, raw 39.3 ps). The 2 decisions missing at the original read are on the MSB core, which reads at 37 ps.
- ±48.8 µV: 13/14 correct by 60 ps (median raw 49.7 ps). One decision (b0 core, −48.8 µV) resolved with the wrong sign.
- Internal to raw takes about 2 ps. qmid and qdecode trail raw by 6 to 9 ps.
- Reading: with a fixed input, the core resolves 1 LSB inside 44 ps. The case21 missing decision therefore points more to the input moving during regeneration than to the core's small-signal ability.

`results/` holds a compact extract. The full summary and all receipts stay on the cluster and in the private results folder. `package/` is the Codex source and `prompts/` the executor reply.
