# Public release notice

This is a de-identified public copy of an ECEN 721 (Texas A&M) PAM4 receiver project.

- Foundry PDK identifiers were replaced with generic placeholders: device names (e.g. `nmos_lvt`, `pmos_lvt`, `mom_cap`, `mim_cap`, `res_ppoly`), model files (`pdk_model*`, `pdk_toplevel.scs`), foundry kit codes (the process node is kept, e.g. `28nm`; kit codes become `28nm_pdk`), and corner sections (`tt`, `ss`, `ff`). Device sizes, topology and all design values are unchanged.
- Install paths, license paths, cluster node names and user names were replaced with `<PDK_ROOT>`, `<LICENSE_FILE>`, `<compute-node>`, `user`, `<owner>`, `<workspace>`.
- No foundry model files, model parameters, simulator decks with real PDK references, raw waveforms or credentials are included.
- Because of these substitutions, recorded SHA-256 values (SHA256SUMS.txt, *_sha256 fields) no longer match the files here, and the scripts need a real PDK mapping before they can run.
