# SAR7 1.75 GS/s strong-decode pilot (2026-11-16)

One case, `sar7_15_tt_175gs_strong_decode` (job 761524), rebuilt from the native-decode R2 package (761433). OAI21/NOR3 decode stacks and the decoder-only inverter paralleled 2–3× with native CDF units; TG, CDAC, comparator, CML, and references unchanged. Non-uniform slots, b0 read 552 ps, formal registered read 565 ps.

- `package/`: Codex source (no decks, ZIPs or models).
- `results/sar7_strong_decode_summary.json`: summary with paths masked (original SHA 73dafa11235da6c63048536e447cd3bda60dba23155b03a399d86c725a84ac03).
- `prompts/`: the reply sent to Codex.

Result: STOP. At 565 ps the registered code is readable for 12/12 conversions, but 7/12 are wrong (max 3 LSB). The comparator code is readable for 0/12 conversions, with 26/84 bits unresolved (12/12 of the b2 bits). Gate crossings are about 3 ps faster and held settles earlier than in 761433. Internal x/y regenerate fully, but the buffered q is slowed by the larger decoder input load: the median high-side q at the b2 read is 0.59 V, versus 0.89 V in 761433. CM gates pass (552 ps: −4.0 mV; 565 ps: −9.2/+5.4 mV).
