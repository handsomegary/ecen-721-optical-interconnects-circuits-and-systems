# SAR7 q-buffer retained-waveform causal audit (2026-11-16)

Zero-solver audit of retained PSF from job 761549 (qbuffer) and 761524 (strong decode), each parsed once by collector job 761591 (1 CPU, 0:44).
Sources were re-hashed on Olympus after the audit and are unchanged.

- `package/`: Codex audit package (no decks).
- `results/sar7_qbuffer_audit_compact.json`: edges, sign runs and command runs only (SHA b0c87e35…0978). Dense samples stay off-repo.
- `prompts/`: Claude's result report.

Finding: in both wrong bits (conv7 b3, conv8 b2) the previous bit's accepted reference was stable 16-20 ps before compare, while the current trial step's bottom plate and held/sense crossed zero 1.5-15 ps after the compare clock.
