# Contributing Guidelines

**English** | [Bản Tiếng Việt](./CONTRIBUTING.md)

---
[← Back to README](README_EN.md)

Thank you for your interest in contributing to **opencode-config-editor**!

## Source Code Structure

The source code is divided into modules within the `src/` directory, which are then 
bundled into a single file by `build.py`. **Important**: Only modify code inside 
`src/` — the file `opencode-config-editor.py` is the build output and will be 
overwritten.

```
src/00_header.py    # Imports, constants, key lists
src/01_core.py      # Logic: Managers (Settings, Theme, Undo, Validator, Catalog...)
src/02_widgets.py   # Shared UI widgets and dialogs
src/03_tabs.py      # Implementation of all 10 editor tabs
src/04_main_window.py  # Main window assembly and app logic
src/05_main.py      # Application entry point
```

## Contribution Workflow

1. **Open an Issue** describing the bug or the feature you'd like to add.
2. **Fork** the repository and create a new branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Edit the code in `src/`. Please maintain the existing style (Python, 4-space indent, concise docstrings).
4. Build and test your changes:
   ```bash
   python3 build.py
   python3 opencode-config-editor.py
   ```
5. Update [CHANGELOG_EN.md](CHANGELOG_EN.md) (and [CHANGELOG.md](CHANGELOG.md) if possible) for significant changes.
6. Submit a **Pull Request** with a clear description of your changes.

## Coding Style

- Python 3.8+ following [PEP 8](https://peps.python.org/pep-0008/).
- Concise docstrings in English (matching existing code).
- Keep comments to a minimum; prefer self-documenting code.
- When adding UI features, update key lists in `00_header.py` if necessary.

## How to Add a New Tab

1. Create a new tab class (inheriting from `QWidget`) in `src/03_tabs.py`.
2. Implement `_refresh`/load logic and the `collect(self, data)` method.
3. Register the tab in `MainWindow._build_tabs()` within `src/04_main_window.py`.
4. If it's an `opencode.json` tab, add it to the `self._oc_tabs` list.

## Reporting Bugs

When reporting a bug, please include:

- Python and PySide6 versions (`python3 -c "import PySide6; print(PySide6.__version__)"`).
- Operating system and desktop environment.
- Steps to reproduce the issue and any error messages.
- A sample configuration file (with sensitive data removed).

## Security Note

Please do not commit sensitive information (API keys, tokens) in sample configs or code.
