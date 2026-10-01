"""Pytest setup: import the built app module without launching the GUI.

The built `opencode-config-editor.py` concatenates all src/ files and only
starts the Qt event loop under `if __name__ == "__main__"`, so importing it
as a module is safe (no QApplication is created).
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

# Force (not setdefault): a desktop session exports QT_QPA_PLATFORM=wayland/xcb,
# and then every test dialog would pop up on the user's real screen.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = Path(__file__).resolve().parent.parent
BUILT = ROOT / "opencode-config-editor.py"


_MODULE = "opencode_config_editor"


def _load():
    # pytest imports this file as `conftest`; test modules that write
    # `from tests.conftest import app` import it again as `tests.conftest`.
    # Both must get ONE module object, or the autouse isolation fixtures patch
    # a different instance than those tests use (which then writes into the
    # developer's real ~/.config).
    mod = sys.modules.get(_MODULE)
    if mod is not None:
        return mod
    if not BUILT.exists():
        raise RuntimeError(
            "opencode-config-editor.py not found. Run `python3 build.py` first."
        )
    spec = importlib.util.spec_from_file_location(_MODULE, BUILT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(_MODULE, None)
        raise
    return mod


app = _load()
HAS_QT = bool(getattr(app, "HAS_QT", False))


@pytest.fixture(scope="session")
def qapp():
    """One shared QApplication for all UI-touching tests (offscreen)."""
    if not HAS_QT:
        pytest.skip("PySide6 not available - skipping Qt tests")
    instance = app.QApplication.instance()
    if instance is None:
        instance = app.QApplication([])
    return instance


@pytest.fixture(autouse=True)
def _isolated_provider_trash(tmp_path, monkeypatch):
    """Never touch the real ~/.config/opencode-config-editor/deleted-providers.json."""
    monkeypatch.setattr(app, "PROVIDER_TRASH_FILE", tmp_path / "deleted-providers.json")


@pytest.fixture(autouse=True)
def _isolate_user_dirs(tmp_path, monkeypatch):
    """Keep tests off the developer's real config, cache, and schema files."""
    home = tmp_path / "_home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    for var in ("XDG_CONFIG_HOME", "OPENCLAUDE_CONFIG_DIR", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(var, raising=False)
    appdir = home / ".config" / app.APP_NAME
    monkeypatch.setattr(app, "USER_CONFIG_DIR", appdir)
    for name in ("PLUGIN_STATE_CACHE", "CUSTOM_MODELS_FILE", "PATTERN_RULES_FILE",
                 "CATALOG_CACHE", "SETTINGS_FILE", "SCHEMA_CACHE", "TUI_SCHEMA_CACHE",
                 "OPENCLAUDE_SCHEMA_CACHE"):
        monkeypatch.setattr(app, name, appdir / getattr(app, name).name)
