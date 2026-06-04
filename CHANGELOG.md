# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] — 2026-06-03

### Changed
- **Upstream ARS**: bumped from v3.9.4.2 to **v3.10.0** — 13 commands (`ars-mark-read`, `ars-reviewer`, `ars-unmark-read` added), 40 agents across 5 features (deep-research, academic-paper, academic-paper-reviewer, academic-pipeline, experiment-agent)
- **README**: upstream project section now lists pinned versions (ARS v3.10.0, experiment-agent v1.1.0)

### Fixed
- **Codex duplicate MCP entry**: when a user already had `paper-search-mcp` configured inline in `~/.codex/config.toml` (without AAT markers) and ran `aat install --replace-mcp`, the installer appended a new managed block instead of replacing the existing section, causing `duplicate key` TOML parse errors. The `merge_codex_config` function now detects inline `[mcp_servers.paper-search-mcp]` TOML sections and replaces them with the managed block via new helper `_replace_inline_codex_config`.
- **Doctor output**: `managed_ars_exists` field now correctly reflects whether the managed ARS source directory exists on disk, respecting the current `MANAGED_ARS_VERSION`.

### Verified
- Full install/uninstall/reinstall cycle tested — idempotent across two consecutive `aat install` runs, no duplicate entries created
- Paper Search MCP verified across all agents: Claude Code, OpenCode, Codex, Cursor, VS Code (13 tools: search/download/read for arxiv, pubmed, biorxiv, medrxiv, google scholar)
- Skill symlink chain verified for all agents: `~/.{agent}/skills/academic-research-suite` → `~/.agents/skills/academic-research-suite` → managed ARS source
- ARS architecture decision: ARS_REF remains manually pinned per CLI release (no auto-update) to avoid silent breakage from upstream structural changes

## [0.1.2] — 2026-05-28

### Added
- Developer testing section in README
- TUI with theme support

## [0.1.1] — 2026-05-28

### Changed
- Version bump

## [0.1.0] — 2026-05-28

### Added
- Initial release of Academic Agent Toolkit
- Skill adapter installation for Claude Code, OpenCode, Cursor, Copilot, Codex, Zed
- Paper Search MCP configuration across all supported agents
- `aat install`, `aat doctor`, `aat verify`, `aat setup-keys`, `aat uninstall` commands
