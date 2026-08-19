# Changelog

**English** | [Bản Tiếng Việt](./CHANGELOG.md)

---
[← Back to README](README_EN.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/en/2.0.0/).

## [4.0.0] - 2026-08-19

Major rewrite, transitioning from a single-file script to a modular architecture with a build system.

### Added

- Modular architecture in `src/` (00_header to 05_main) and `build.py` script.
- 10 Specialized tabs: General, Runtime, Agents, Commands, Providers, MCP Servers, Plugins, Permissions, TUI, Raw JSON.
- Advanced Model Management: Bulk edit, model catalog with preview and filtering.
- Import/Export functionality for providers, MCP servers, and plugins with conflict resolution.
- Schema Validation (`jsonschema`) with detailed error reporting and basic fallback.
- Undo/Redo support for all operations (100 steps limit).
- Global search/filter across all tabs.
- Bulk enable/disable for plugins and MCP servers.
- System dark/light theme detection and font size adjustment.
- Automatic backups before saving and manual Export feature.
- Raw JSON tab with syntax highlighting and debounced validation.
- `install.sh` script (creates `opencode-editor` command and `.desktop` shortcut).

### Changed

- Reorganized entire codebase into modules for better maintainability.

## [3.0.0] - Prior to 2026-08-19

Intermediate version (stored in `.archives/opencode-config-editor.v3.py`).

## [2.0.0] - Prior to 2026-08-19

Intermediate version (stored in `.archives/opencode-config-editor.v2a.py`).

## [1.0.0] - Prior to 2026-08-19

Initial versions (stored in `.archives/opencode-config-editor.v1a.py` and `.archives/opencode-config-editor.v1b.py`).

> **Note**: Exact release dates for versions 1.x through 3.x were not recorded in 
> the git history (which contains only the v4.0.0 commit). These entries are 
> synthesized from files in `.archives/`.
