# opencode-config-editor

**English** | [Bản Tiếng Việt](./README.md)

Graphical User Interface (GUI) for coding-agent configuration files. Two agents are supported:

- **[opencode](https://opencode.ai)** — `opencode.json` and `tui.json`
- **[openclaude](https://openclaude.gitlawb.com)** — layered `settings.json` (user → project →
  local) plus `~/.openclaude.json` and `.mcp.json`

This application provides a visual way to manage your settings, instead of manual JSON editing,
featuring schema validation, import/export, and advanced model management.

![Version](https://img.shields.io/badge/version-4.3.1-blue)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![GUI](https://img.shields.io/badge/GUI-PySide6-green)

## Features

**Shared by both agents**
- **Schema Validation**: Real-time validation with detailed error reporting (uses `jsonschema`
  if available, with a built-in fallback).
- **Secret masking**: API keys, tokens and auth headers render as `sk-****e`; click 👁 to reveal.
  Real values never reach the UI while masked.
- **Data safety**: keys the forms don't model are preserved verbatim on save; files are written
  atomically (temp + replace); a file whose JSON fails to parse is never overwritten.
- **Unsaved-work guard**: switching config layers with pending edits prompts Save/Discard/Cancel.
- **Polished UI**: Dark/Light theme support (system detection), adjustable font size, and
  standard keyboard shortcuts.
- **Raw JSON Tab**: Direct editor with syntax highlighting and debounced validation.

**opencode only**
- **10 Specialized Tabs**: General, Runtime, Agents, Commands, Providers, MCP Servers, Plugins, Permissions, TUI, Raw JSON.
- **Advanced Model Management**: Add/Edit/Remove models, bulk editing, and a model catalog with preview and filtering.
- **Import/Export**: Easily import/export providers, MCP servers, and plugins with conflict resolution.
- **Undo/Redo**: Full history support for all operations (100 steps limit).
- **Bulk Operations**: Enable/disable plugins and MCP servers in batches.

**openclaude only** — see the [openclaude section](#openclaude)
- **8 tabs**: Settings, Agent Models, MCP, Plugins, Hooks, Permissions, Env & Limits,
  Raw (per layer).
- **Layered editing** with inherited-value hints and a read-only enterprise policy layer.
- **All four MCP scopes**, **plugins/marketplaces**, and structured **hooks** editing.

## Requirements

- Python 3.8+
- [PySide6](https://pypi.org/project/PySide6/) (Required)
- `jsonschema` (Optional — for full schema validation)

## Installation

### Option 1: Auto-download release from GitHub (Recommended)

`install.sh` downloads the latest GitHub release, moves it to `/opt/opencode-editor/`,
and creates the `opencode-editor` command plus a desktop menu shortcut:

```bash
curl -fsSL https://raw.githubusercontent.com/yana-arch/opencode-config-editor/master/install.sh | sudo bash
```

Or download the script first, then run it in **remote** mode:

```bash
curl -fsSL -o install.sh https://raw.githubusercontent.com/yana-arch/opencode-config-editor/master/install.sh
sudo bash install.sh --remote
```

### Option 2: Install from a local file

If you already have the `opencode-config-editor.py` file (e.g. built manually or downloaded
separately), install it directly without re-downloading:

```bash
python3 build.py
sudo bash install.sh --local opencode-config-editor.py
```

After installation (remote or local), launch the app with:

```bash
opencode-editor
```

or find "OpenCode Config Editor" in your application menu.

**Customization:**

```bash
# Install from a different repo
REPO=<owner/repo> sudo bash install.sh --remote

# Install a specific version (default: latest)
VERSION=4.0.1 sudo bash install.sh --remote

# Skip dependency installation
NO_DEPS=1 sudo bash install.sh --remote
```

**Full help:** `bash install.sh --help`

### Option 3: Build from source manually

```bash
pip install PySide6
python3 build.py
python3 opencode-config-editor.py
```

## Usage

1. Launch the app. Use the **Mode** selector in the toolbar:
   - **Global**: Edits `~/.config/opencode/opencode.json` and `tui.json`.
   - **Local project…**: Select a project folder to edit `.opencode/opencode.json` and `.opencode/tui.json`.
2. Edit settings in the appropriate tabs. Changes are marked "dirty" and can be saved with `Ctrl+S`.
3. Use the **Raw JSON** tab for keys that don't have a specific UI yet.
4. Save, Export, or Reload via the **File** menu.

### Keyboard Shortcuts

| Action | Shortcut |
| --- | --- |
| Open Folder/File | `Ctrl+O` |
| Save | `Ctrl+S` |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` |
| Cut / Copy / Paste | `Ctrl+X` / `Ctrl+C` / `Ctrl+V` |
| Toggle Theme | `Ctrl+T` |
| Zoom In / Out | `Ctrl++` / `Ctrl+-` |

## openclaude

`build.py` emits **two** standalone files from the same source; they differ only in the
default adapter:

| File | Default agent |
| --- | --- |
| `opencode-config-editor.py` | opencode |
| `openclaude-config-editor.py` | openclaude |

The adapter can also be switched at runtime without rebuilding:

```bash
python3 opencode-config-editor.py --adapter=openclaude
CONFIG_EDITOR_ADAPTER=openclaude python3 opencode-config-editor.py
```

### openclaude config files

| File | Layer | Contents |
| --- | --- | --- |
| `<managed>/managed-settings.json` | policy (read-only) | Enterprise policy, **highest precedence**. Includes `managed-settings.d/*.json` drop-ins and `managed-mcp.json`. Paths: `/etc/claude-code` (Linux), `/Library/Application Support/ClaudeCode` (macOS), `C:\Program Files\ClaudeCode` (Windows). |
| `~/.openclaude/settings.json` | user | Machine-wide defaults |
| `.openclaude/settings.json` | project | Committed to the repo |
| `.openclaude/settings.local.json` | local | Per-machine overrides, usually gitignored |
| `~/.openclaude.json` | global | `providerProfiles`, `activeProviderProfileId`, `mcpServers` (user scope), plus app state (`numStartups`, `projects`, …) which is **never clobbered**. |
| `<project>/.mcp.json` | project-mcp | Project-scope MCP servers |

Merge order: user → project → local, then **policy overrides everything**.
The config directory can be redirected with `OPENCLAUDE_CONFIG_DIR` (or legacy
`CLAUDE_CONFIG_DIR`).

### openclaude tabs

- **Settings** — pick the layer to edit; `model`, `agent`, `effortLevel`, `advisorModel`,
  `statusLine`, the skip-permission-prompt flags, and MCP gating
  (`enableAllProjectMcpServers`, `enabled/disabledMcpjsonServers`). Text fields show the
  **inherited** value as a grey placeholder so you can tell which layer a value came from.
- **Agent Models** — `providerProfiles` (apiKey masked), active-provider picker, fallback
  chain, agent routing.
- **MCP** — all four scopes: `user` → global file, `project` → `.mcp.json`, `local` →
  `projects[file dict].mcpServers`, `policy` → read-only. Edit transport (stdio/http),
  command/url, **args**, env and headers (env/headers are masked since they usually carry
  API keys).
- **Plugins** — `enabledPlugins`, `extraKnownMarketplaces`
  (github/git/url/file/directory/npm with ref and autoUpdate), plus a read-only listing of
  cached marketplaces.
- **Hooks** — one row per hook entry: event · matcher · type · command/url/prompt · timeout.
  Edits are surgical: untouched events round-trip **byte-for-byte**.
- **Permissions** — `permissions`: four rule lists (`allow`/`deny`/`ask`/
  `additionalDirectories`, one rule per line such as `Bash(ls)`), `defaultMode`, and the
  `disableBypassPermissionsMode`/`disableAutoMode` flags. Unknown sub-keys are preserved.
- **Env & Limits** — `env` (values masked, they usually hold API keys) and `modelLimits`
  (per-model `contextWindow`/`maxOutputTokens`; unknown sub-keys preserved).
- **Raw (per layer)** — direct JSON editing for every layer, including `.mcp.json`, with
  live checking: JSON and shape errors in red, unknown keys and schema findings in amber.

> **Tip**: when a tab looks empty it tells you which layer actually holds the config
> (e.g. *"No hooks in the 'project' layer. Hooks found in: user (6 entries)"*) — switch
> **Edit layer** at the top of the tab.

## Project Structure

```
.
├── src/
│   ├── core/                 # Generic, agent-agnostic
│   │   ├── header.py         # Imports, constants, opencode keys
│   │   ├── settings.py       # QSettings, theme, undo
│   │   ├── config.py         # ConfigFile, layered merge, atomic write
│   │   ├── adapter.py        # AdapterSpec + registry
│   │   ├── base_tab.py       # Shared helpers for every form tab
│   │   └── widgets_*.py      # Shared widgets/dialogs (incl. MaskedLineEdit)
│   ├── adapters/
│   │   ├── opencode/         # 10 tabs + opencode adapter registration
│   │   └── openclaude/       # constants, layered config, 6 tabs, adapter
│   └── app/                  # Main window + entry point
├── tests/                    # pytest suite (run automatically by build.py)
├── build.py                  # Bundles src/ into two standalone files
├── install.sh                # Script to download release from GitHub and install
├── .github/workflows/        # GitHub Actions: automated build + release
├── opencode-config-editor.py     # Built executable (opencode adapter)
├── openclaude-config-editor.py   # Built executable (openclaude adapter)
└── .archives/                # Legacy versions (v1 to v4)
```

## Build & Release (CI/CD)

GitHub Actions automatically builds the file and creates a **GitHub Release** when you push a tag:

```bash
git tag v4.0.0
git push origin v4.0.0
```

- Workflow: `.github/workflows/build-release.yml`
- Runs `python3 build.py`, packages the `opencode-config-editor-<version>.py` asset
  along with `CHANGELOG.md` / `CHANGELOG_EN.md`.
- Can also be triggered manually from the **Actions** tab → *Build & Release* → *Run workflow*
  (in that case the asset is attached as an artifact, not a release).

> **Note**: The workflow uses `github.repository` automatically, so no extra config is needed.
> The default download source for `install.sh` is `yana-arch/opencode-config-editor`; if you fork,
> set the `REPO` variable when running it to point to your repo.

## Schema Validation

- **opencode**: schemas are fetched from `https://opencode.ai/config.json` and
  `https://opencode.ai/tui.json` (cached in `~/.cache/opencode-config-editor/`).
- **openclaude**: a 159-key vocabulary derived from `SettingsSchema` in the openclaude v0.28.0
  binary, plus the official `https://json.schemastore.org/claude-code-settings.json` schema
  (cached in `~/.cache/openclaude-config-editor/`). The Raw tab reports shape errors (red) and
  unknown-key/schema warnings (amber) per layer; `~/.openclaude.json` is exempt from
  unknown-key warnings because it is mostly app state.

If `jsonschema` is not installed, it falls back to a basic validation engine based on known
keys. Either way unknown keys are **never dropped** — they are only reported as warnings.

## License

See [LICENSE](LICENSE).

---
**Related Documentation:**
- [Changelog](CHANGELOG_EN.md)
- [Contributing Guidelines](CONTRIBUTING_EN.md)
