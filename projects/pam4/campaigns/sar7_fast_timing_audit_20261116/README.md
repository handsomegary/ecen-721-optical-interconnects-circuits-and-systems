# SAR7 1.75 GS/s retained-waveform timing audit (2026-11-16)

Read-only audit of 761321 (1.75 GS/s fixed timing, launch→compare 21 ps) against 761279 (0.926 GS/s, 60 ps). No new Spectre or Slurm job; original summaries, measurements and raw stay on Olympus.

- `package/sar7_fast_timing_audit.py`: Claude's read-only script (uses the admitted PSF parser `gm_switch64_psf.parse_selected` via the fast package import chain; checks the 6 input SHA-256 values before parsing).
- `results/sar7_fast_timing_audit.json`: compact per-code, per-bit evidence (events, read class/margin, samples of mp−mn, lp−ln, sense, comparator x/y, buffered q, sign flips, DAC step timing, fast/slow comparison).
- `results/*_table.md`: event table (2×12×7), sample table (b6–b4 + b3), mechanism table and failing-code divergence.
- `prompts/`: the reply sent to Codex.

Result: the CDAC trial step reaches the DAC after compare (b5–b3 only −0.11…+0.12 of the step done at compare vs 0.95–1.04 in 761279; DAC starts moving 13–31 ps after launch in both). Not kickback; comparator/logic window not the primary limit.
