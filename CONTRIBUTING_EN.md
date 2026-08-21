# Contributing Guidelines

**English** | [Bản Tiếng Việt](./CONTRIBUTING.md)

---
[← Back to README](README_EN.md)

Thank you for your interest in contributing to **opencode-config-editor**!

## Source Code Structure

The source code is divided into modules within the `src/` directory, which are then 
bundled into a single file by `build.py`. **Important**: Only modify code inside 
`src/` — the file `opencode-config-editor.py` is the build output and will be 
overwritten. The concatenation order is the explicit `ORDER` list in `build.py`.

```
src/core/                  # generic, agent-agnostic
  header.py                # Imports, constants, key lists
  settings.py              # SettingsManager, ThemeManager, UndoManager
  config.py                # ConfigFile, Validator, section(), layered-config helpers
  parsing.py               # import/parse/merge helpers
  catalog.py               # ModelCatalog, ModelFormat, matching/fallback
  provider_fetch.py        # provider model-list fetching
  adapter.py               # AdapterSpec + registry (the multi-agent seam)
  widgets_common.py        # shared widgets/dialogs
  base_tab.py              # BaseTab: touched-tracking + value helpers
  widgets_models.py        # model editing dialogs
  widgets_catalog.py       # catalog dialogs
src/adapters/opencode/     # opencode + tui specifics
  tab_*.py                 # the 10 editor tabs
  adapter.py               # registers the opencode AdapterSpec
src/app/                   # window + entrypoint
  main_window.py           # MainWindow (adapter-driven)
  main.py                  # entry point
```

## Adding a New Agent CLI (adapter)

The editor is multi-agent via `core/adapter.py`. To support another CLI:

1. Create `src/adapters/<agent>/` with tab classes inheriting `BaseTab`
   (implement `refresh()`/load and `collect(self, data)`).
2. Add `src/adapters/<agent>/adapter.py` that calls `register_adapter(AdapterSpec(...))`
   with the agent's `kinds`, `known_keys`, `raw_files`, `targets_fn`, `make_tabs_fn`
   and `capabilities`.
3. Add the new files to `ORDER` in `build.py` (after `core/*`, before `app/*`).
4. Select it via the adapter registry in `app/main.py` (`--adapter`/env).

No changes to `core/` are required. The parametrized contract test in
`tests/test_adapter.py` automatically covers any registered adapter.

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

1. Create a new tab class (inheriting from `BaseTab`) in the relevant adapter,
   e.g. `src/adapters/opencode/tab_yourfeature.py`.
2. Implement `refresh()`/load logic and the `collect(self, data)` method.
3. Add it to that adapter's `make_tabs_fn` in `adapters/<agent>/adapter.py`
   (append `(tab, "Title", kind)`); for opencode.json tabs also append to
   `win._oc_tabs`.
4. Add the new file to `ORDER` in `build.py`.

## Reporting Bugs

When reporting a bug, please include:

- Python and PySide6 versions (`python3 -c "import PySide6; print(PySide6.__version__)"`).
- Operating system and desktop environment.
- Steps to reproduce the issue and any error messages.
- A sample configuration file (with sensitive data removed).

## Security Note

Please do not commit sensitive information (API keys, tokens) in sample configs or code.
