# Changelog

**English** | [Bản Tiếng Việt](./CHANGELOG.md)

---
[← Back to README](README_EN.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/en/2.0.0/).

## [4.3.0] - 2026-08-20

Streamlined bulk match review + **Reference provider fallback** for unmatched models.

### Added

- **Reference provider** in Fetch from API: pick a provider whose formats are used
  as a fallback for models not found in the catalog.
- **4-level fallback**: exact id within the reference provider → normalized id
  (strips version/date suffixes like `-2024-08-13`, `-v2`, `-latest`) within the
  reference provider → normalized across the catalog → longest shared prefix
  within the reference provider.
- Fallback rows show status `fallback:<provider>` (blue), fill-missing only.
- **Manual Map…**: `unknown` rows get a button opening a searchable Catalog Model
  Picker to map to any catalog model, status `mapped` (purple).
- **Mappings persist** (`unknown → catalog id`) in QSettings; future fetches remember.
- **"Apply fallback"** checkbox toggles all fallback rows at once.

### Changed

- Post-fetch matching and the Models Manager now funnel into **one review dialog**
  (previously each ambiguous model required its own confirmation).
- Provider combos default to the best-ranked match (same provider name first,
  then the most complete data via `_sort_matches`); ambiguous rows are pre-checked.

## [4.2.0] - 2026-08-20

**Fetch Models from provider API** feature: add a new provider by fetching its model list directly from the API.

### Added

- **"Fetch from API"** button in the Providers tab: enter provider key + Base URL + API key,
  pick an API format and fetch the model list.
- Five API formats supported: **OpenAI-compatible** (`/models`), **Anthropic/Claude**
  (`/v1/models`), **Google Gemini** (`/v1beta/models`), **models.dev** (api.json),
  and **Generic JSON** (custom array path + id/name fields).
- Fetching runs in a **QThread** so the UI never blocks; results listed with checkboxes.
- **Auto-match after fetch**: fetched models (id/name only) are automatically matched
  against the models.dev catalog to fill context/output/cost/modalities; ambiguous ids
  prompt for provider selection.
- Security: SSRF guard against localhost/private IPs (unless "Allow local URL" is set),
  API key sent as a header only and never stored in the config, request timeout.

## [4.1.0] - 2026-08-20

**Model Format Match & Apply** feature: normalize and match models against the models.dev catalog.

### Added

- **Browse Model Catalog**: browse the full catalog (190+ providers, 6800+ models) with
  context/output tier, modality and capability filters; view normalized format details;
  export CSV/JSON.
- **Match & Format Models from Catalog**: match each configured model id against the catalog,
  locate its provider, and fill in the normalized format (context, output, modalities, cost,
  capability flags) either fill-missing or overwrite.
- **Per-model / per-provider matching** right inside the Models Manager (per-row "Match"
  button and "Match from Catalog").
- **Visual old → new diff preview** before applying: field-by-field with add/change/delete
  colors, provider dropdown for models that match multiple providers, overwrite checkbox.
- **Catalog tier settings** to configure context/output thresholds for filtering.
- Bundled models.dev catalog (`models/models.dev.catalog.json`) auto-loaded when opening dialogs.
- **Test suite** (`tests/`, 32 tests) for the core matching/normalization logic plus a fast
  model-lookup index; wired into `build.py` and CI.

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
