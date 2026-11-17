# SAR7 1.75 GS/s q-buffer pilot (2026-11-16)

One case, `sar7_16_tt_175gs_qbuffer` (job 761549), rebuilt from the strong-decode package (761524). It adds a non-inverting buffer (SAR_INV → SAR_NDINV2) on each of the 14 q± paths, driving only the strong decoder's q inputs. The raw q still drives the register. Timing, TG, CDAC and comparator are unchanged.

- `package/`: Codex source (no decks, ZIPs or models).
- `results/sar7_qbuffer_summary.json`: summary with paths masked (original SHA 8ab3c03c13658704b2c4a20be6bd453e864f74c4e7e1a6169434a275bbe2eb93).
- `prompts/`: the reply sent to Codex.

Result: STOP. Raw q now resolves: unresolved bits fell from 26/84 to 2/84, and the comparator code is readable for 10/12 conversions (5 wrong, max 1 LSB). The registered codes are identical to 761524 at every read point (565 ps: 7/12 wrong, Σ10, max 3 LSB). The buffered decode node reaches a rail by the b-read in only 28/84 trials (40/84 by release). The remaining errors are comparator decision errors, not q-readout errors. CM gates pass (552 ps: −4.0 mV; 565 ps: −9.2/+5.4 mV).
