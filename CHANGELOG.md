# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] — 2026-06-03

### Changed
- Bumped bundled ARS from v3.9.4.2 to **v3.10.0** (13 commands, 40 agents across 5 features)

### Fixed
- **Codex duplicate MCP entry**: when a user already had `paper-search-mcp` configured inline in `~/.codex/config.toml` (without AAT markers) and ran `aat install --replace-mcp`, the installer appended a new block instead of replacing the existing section, causing `duplicate key` TOML parse errors. The installer now detects inline `[mcp_servers.paper-search-mcp]` sections and replaces them with the managed block.
- **Doctor output**: `managed_ars_exists` field now correctly reflects whether the managed ARS source directory exists on disk.

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
