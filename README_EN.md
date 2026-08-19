# opencode-config-editor

**English** | [Bản Tiếng Việt](./README.md)

Enhanced Graphical User Interface (GUI) for [opencode](https://opencode.ai) configuration files — 
`opencode.json` and `tui.json`. This application provides a visual way to manage your 
settings, instead of manual JSON editing, featuring schema validation, import/export, 
and advanced model management.

![Version](https://img.shields.io/badge/version-4.0.0-blue)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![GUI](https://img.shields.io/badge/GUI-PySide6-green)

## Features

- **Visual Editing** for `opencode.json` (global & project-local) and `tui.json`.
- **10 Specialized Tabs**: General, Runtime, Agents, Commands, Providers, MCP Servers, Plugins, Permissions, TUI, Raw JSON.
- **Advanced Model Management**: Add/Edit/Remove models, bulk editing, and a model catalog with preview and filtering.
- **Import/Export**: Easily import/export providers, MCP servers, and plugins with conflict resolution.
- **Schema Validation**: Real-time validation with detailed error reporting (uses `jsonschema` if available, with a built-in fallback).
- **Undo/Redo**: Full history support for all operations (100 steps limit).
- **Search & Filter**: Quickly find settings across all tabs.
- **Bulk Operations**: Enable/disable plugins and MCP servers in batches.
- **Automatic Backups**: Creates timestamped backups before saving and provides an Export feature.
- **Polished UI**: Dark/Light theme support (system detection), adjustable font size, and standard keyboard shortcuts.
- **Raw JSON Tab**: Direct editor with syntax highlighting and debounced validation for advanced users.

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

## Project Structure

```
.
├── src/                      # Modular source code
│   ├── 00_header.py          # Imports, constants, and key definitions
│   ├── 01_core.py            # Managers (Settings, Theme, Undo, Validator, Catalog...)
│   ├── 02_widgets.py         # Shared UI widgets and dialogs
│   ├── 03_tabs.py            # Implementations for all 10 tabs
│   ├── 04_main_window.py     # Main window logic (menus, toolbar, save/load)
│   └── 05_main.py            # Application entry point
├── build.py                  # Script to bundle src/ modules into one file
├── install.sh                # Script to download release from GitHub and install
├── .github/workflows/        # GitHub Actions: automated build + release
├── opencode-config-editor.py # Built executable (output of build.py)
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

The application fetches schemas from `https://opencode.ai/config.json` and 
`https://opencode.ai/tui.json` (cached in `~/.cache/opencode-config-editor/`). 
If `jsonschema` is not installed, it falls back to a basic validation engine 
based on known keys.

## License

See [LICENSE](LICENSE).

---
**Related Documentation:**
- [Changelog](CHANGELOG_EN.md)
- [Contributing Guidelines](CONTRIBUTING_EN.md)
