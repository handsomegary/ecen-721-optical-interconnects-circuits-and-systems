# SAR7 case18 read-overlap — collect-only summary fix (2026-11-17)

Re-collects the completed case18 run (job 761649) with a fixed selected-signal parser (trial0–6 nodes added). No new solver, no new raw, source untouched (receipt: before==after, parse count 1).

- Collector job 761658 (0:24). Two earlier submissions (761656, 761657) exited at argument checks (output-root misconfiguration by the executor) before reading any source.
- Result: 565 ps screen FAIL. Registered 12/12 readable, 7 wrong (max 1 LSB). Comparator 10/12, with 4 unresolved bits (conv7/8 b2, b1). CM gates pass.
- 72-boundary diagnostic: 2 prior-latch unresolved boundaries (conv8 b2→b1, b1→b0), 0 opposite-rail.
- Max resolve delay 44.82 ps at conv8 b0. Minimum b0 margin 1.18 ps. Minimum overall sampled margin 0.07 ps (conv6 b2).

`results/`: compact extract of the 3.4 MB summary (full file kept on the cluster) plus the collector receipt. `package/`: Codex collector source. `prompts/`: executor reply.
