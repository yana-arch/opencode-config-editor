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

### Option 1: System-wide Installation (Recommended)

```bash
# 1. Build the single-file executable from modules in src/
python3 build.py

# 2. Install (requires root privileges)
sudo bash install.sh
```

After installation, run the application using:

```bash
opencode-editor
```

Or find "OpenCode Config Editor" in your application menu (a `.desktop` entry is created automatically).

### Option 2: Run Without Installation

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
├── install.sh                # System installation script
├── opencode-config-editor.py # Built executable (output of build.py)
└── .archives/                # Legacy versions (v1 to v4)
```

## Build Process

```bash
python3 build.py
```

The `build.py` script combines files in `src/` following the order defined in `ORDER` 
into a single `opencode-config-editor.py` file for easy distribution.

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
