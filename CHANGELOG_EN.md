# Changelog

**English** | [Bản Tiếng Việt](./CHANGELOG.md)

---
[← Back to README](README_EN.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/en/2.0.0/).


## [4.4.1] - 2026-08-24

### Added
- **Restored + Fetch from API button**: Re-added the toolbar button to create brand-new providers from API (supporting the full catalog normalization flow).
- **Aliases support in Model Catalog**: Models can now be matched via aliases defined in the catalog.

### Changed
- **Enhanced Model Catalog Matching**: Smarter fuzzy matching that automatically strips prefixes (google/, zh-...) and suffixes (-thinking, -vision, date-codes...) for better accuracy.
- **Separate Fetch entry points**: The Fetch button inside the Models dialog is for updates; the toolbar button is for adding new providers.

## [4.4.0] - 2026-08-23

Second agent supported: **openclaude** (layered settings.json), via a new adapter layer.

### Added

- **Fetch from API persists endpoint + syncs existing providers**:
  - Automatically saves `options.baseURL` (required by opencode docs) and `options.apiKey`
    (with an opt-in checkbox in the dialog) into the provider config.
  - Selects the right `npm` package by adapter and host (`@ai-sdk/openai-compatible` for
    gateways like OpenRouter/LiteLLM, `@ai-sdk/anthropic`, `@ai-sdk/google`...).
  - Works safely for existing providers: a **Status** column marks rows `new`/`existing`,
    configured specs are **never overwritten** by API listings (add-only by default), and
    an opt-in **Sync** checkbox removes models the API no longer lists after confirmation.
- **openclaude adapter** — `build.py` now emits **two standalone files** from the same
  source: `opencode-config-editor.py` (defaults to opencode) and
  `openclaude-config-editor.py` (defaults to openclaude). Switch at runtime with
  `--adapter=openclaude` or the `CONFIG_EDITOR_ADAPTER` environment variable.
- **Layered config**: user → project → local (later wins), plus a **read-only policy
  layer** `managed-settings.json` (+ `managed-settings.d/*.json` drop-ins) with the
  highest precedence. Text fields show inherited values as grey placeholders.
- **8 openclaude tabs**: Settings, Agent Models, MCP, Plugins, Hooks, Permissions,
  Env & Limits, Raw (per layer).
- **All four MCP scopes**: `user` → `~/.openclaude.json`, `project` → `.mcp.json`,
  `local` → `projects[<path>].mcpServers`, `policy` → `managed-mcp.json` (read-only).
  Edit stdio/http transport, command/url, args, env and headers.
- **Plugins/marketplaces**: `enabledPlugins`, `extraKnownMarketplaces`
  (github/git/url/file/directory/npm with ref, autoUpdate), cached-marketplace listing.
- **Structured hooks**: one row per hook entry (event · matcher · type ·
  command/url/prompt · timeout); untouched events round-trip byte-for-byte.
- **Provider profiles**: `providerProfiles` with masked apiKey, active-provider picker
  (`activeProviderProfileId`), fallback chain, agent routing.
- **Secret masking for MCP env/headers** — they usually carry API keys; masked by
  default, click 👁 to reveal.
- **Unsaved-work guard**: switching config layers with pending edits prompts
  Save / Discard / Cancel (also covers the Raw tab buffer).
- **`permissions` editor**: four rule lists (`allow`/`deny`/`ask`/
  `additionalDirectories`), `defaultMode` (including the undocumented
  `manual`/`delegate`/`dontAsk` modes), and the `disableBypassPermissionsMode`/
  `disableAutoMode` flags; unknown sub-keys are preserved.
- **`env` and `modelLimits` editors**: env values are masked; modelLimits edits
  per-model `contextWindow`/`maxOutputTokens` while preserving unknown sub-keys.
- **Live checking in the Raw tab**: shape errors (red) plus unknown-key and official
  `claude-code-settings.json` schema warnings (amber), per layer — `~/.openclaude.json`
  is exempt from unknown-key warnings since it is mostly app state. Warnings never
  block a save.
- **Corrupt-JSON write guard**: a file that exists but fails to parse is never
  overwritten with `{}` — the save is refused and points at the Raw tab.

### Changed

- **Shared adapter layer** (`core/adapter.py`): `AdapterSpec` + registry for targets,
  tabs, known keys and session hooks (initial_load / refresh / save). opencode now goes
  through the same layer with no behavior change.
- `BaseTab` gained shared helpers: `_set_text`, `cell_text`, `remove_current`,
  `preserve`/`preserved` — consolidating duplicated tab code.
- `atomic_write_json()` extracted into `core/config.py` and shared by `ConfigFile.save`
  and the layered writer; the temp file is cleaned up on failure.
- The openclaude key vocabulary is derived from `SettingsSchema` in the openclaude
  v0.28.0 binary and the official `claude-code-settings.json` schema (159 keys).

### Fixed

- App state in `~/.openclaude.json` (`numStartups`, `tipsHistory`, `projects`, …) is no
  longer clobbered when saving providers/MCP.
- `MaskedLineEdit` no longer swallows text typed while masked, and the 👁 toggle no
  longer overwrites in-progress edits.
- Hooks: newly added rows are no longer lost to value-based row matching; deleting every
  original entry and adding a new one no longer drops the whole event.
- Removed a leftover duplicate MCP editor in the Agent Models tab (it could clobber
  servers edited in the dedicated MCP tab).
- Editing cells of existing table rows now marks the document dirty — such changes could
  previously be skipped on save.
- Duplicate provider names are now reported in the status bar instead of dropped silently.
- A form save while the Raw tab holds unsaved text now says the Raw edits were NOT saved.
- Added `skipFullAccessModePermissionPrompt` to the known-key set (it is real in the
  binary) — the editor's own output was previously flagged as an unknown key.

## [4.3.1] - 2026-08-20

### Changed

- Split the large modules into 21 small domain-focused files (settings, config,
  parsing, catalog, provider fetch, common/models/catalog widgets, 10 individual
  tabs, main window, main). No behavior change — code moved verbatim, build
  concatenates as before, 75 tests pass.

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
