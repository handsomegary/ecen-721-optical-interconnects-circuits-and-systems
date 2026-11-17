# 224 Gb/s PAM4 receiver front-end checkpoint — 2026-11-06

## Scope

This checkpoint covers the 224 Gb/s PAM4 receiver front end. The repository contains circuit inputs, case metadata, historic source snapshots, and Olympus preparation, simulation, and measurement helpers. See [the main README](README.md) for setup and dependencies.

The repository does not contain a PDK, foundry model files or coefficients, native-card data, OA databases, fixed detector coefficients, raw waveforms, or credentials. The historical code is a source reference, not proof that every old workflow can run without its original project data. The available VM and Olympus installations and their separate project data remain necessary for some workflows. Do not restart an old queue or retry a failed simulation automatically.

The [historical checkpoint snapshots](projects/pam4/reference/historical_checkpoints/) retain prior results and decisions. The r5 handoff there was last updated on 2026-10-29 and must be read alongside this later checkpoint. Historical local tools and source paths were sanitized and may require adaptation. [Local cleanup part 1](LOCAL_CLEANUP_RECEIPT_20261106.json) and [part 2](LOCAL_CLEANUP_PART2_20261106.json) record 194 verified local copies and caches removed after their backups were confirmed. Those receipts cover logical file sizes only.

## PAM4 independent comparison

The fixed four-case r7 comparison completed with all four simulator exit codes zero. It compared the r5 baseline secondary sampler, 10 fF and TG width 1 µm per side, with 25 fF and TG width 2 µm per side. Each case used 2,048 scored inputs and 2,032 complete FFE outputs per branch, with previously trained detectors held fixed and no validation fitting. See [the independent validation summary](projects/pam4/reference/independent_validation_summary.json) for seeds, hashes, cases, and details.

For this one fresh-data noisy comparison, secondary ideal 7-bit quantization plus FFE produced 235/2,032 symbol errors for the baseline and 210/2,032 for the 25 fF / 2 µm candidate. That is a 1.23 percentage point lower observed symbol error rate; it is not an independent-bit BER certification or proof of a robust improvement across conditions. The unquantized-FFE error counts were 218 and 190. Numerical quantization and FFE, ideal clocks, and reset comparators do not establish a complete physical 7-bit 112-GS/s ADC.

## Olympus execution evidence

On 2026-11-06 the documented Olympus work included a full 21.986 ns noiseless PAM4 candidate transient, and a full noisy baseline APS timing benchmark. Job 738307 (candidate transient) and job 738438 (4-CPU APS noisy baseline) were recorded as completed with exit 0:0. These are historical execution records, not a claim that current remote files remain in place or that the full ADC was validated. Execution and benchmark notes are maintained separately in the Olympus Cadence notes repository.

## Planned r8 diagnostic, not a completed result

The 2026-10-29 fixed two-case secondary-load isolation diagnostic was planned but not launched in the recorded preflight. It is a noiseless mechanism experiment, not a new detector fit, new holdout, or validated design improvement. Any future work needs a fresh review of its authorization, storage, input hashes, active jobs, and current environment; no job is started by this checkpoint.

## Retained environments and deletion boundary

Per the user's 2026-11-06 instruction, any subsequent cleanup is limited to local Windows copies of explicitly identified project artifacts. The VMware project and Olympus data are retained. Preserve shared infrastructure, SSH keys, other courses and projects, and the separate Olympus notes repository. An independently verifiable remote commit must exist before deleting any local source or result. Raw waveform availability and independent reproducibility depend on the retained VM/Olympus data and authorized external PDK.

Read-only inspection on 2026-11-06 found the VM Project 6 OA library still contained CTLE r3 and sampler r2 schematic and symbol views. Five OA files in the existing local PAM4 transfer package matched their retained VM counterparts by SHA-256. No Project 6 layout view directory or completed DRC/LVS/PEX evidence was found in the inspected project; this is not a claim that no earlier exploratory work ever existed. OA libraries are not included in this Git repository; do not mistake source generators or the transfer package for a finished physical layout.

The local PAM4 transfer ZIP (SHA-256 `7c900477f5ec1b105a3af48b7136f1bb1bcce4144ac6d34149c0e77d863a4f7b`, 665,911 bytes) was subsequently removed after the five OA files and four simulation input netlists in it were individually matched against retained VM files. The shared packaging and notes folders were not deleted. Olympus was not modified or inspected during this cleanup.
