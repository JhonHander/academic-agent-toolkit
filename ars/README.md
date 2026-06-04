# ARS Source

This folder documents the source strategy used by the toolkit.

The packaged CLI does not write symlinks inside this repository or inside an installed wheel. Instead, `aat install` materializes each target skill directory directly in the user's agent config path and creates an `ars` symlink there.

Source selection order:

- use `--ars-source /path/to/ars` when provided
- reuse the last saved source from `~/.config/academic-agent-toolkit/config.json` when valid
- adopt a valid existing source from known agent skill locations
- bootstrap the supported upstream ARS release plus the companion Experiment Agent release into `~/.local/share/academic-agent-toolkit/ars/` when no local source exists

This keeps AAT plug-and-play for new users while preserving existing installations for advanced users.
