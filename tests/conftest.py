"""Pytest setup: import the built app module without launching the GUI.

The built `opencode-config-editor.py` concatenates all src/ files and only
starts the Qt event loop under `if __name__ == "__main__"`, so importing it
as a module is safe (no QApplication is created).
"""
import importlib.util
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
BUILT = ROOT / "opencode-config-editor.py"


def _load():
    if not BUILT.exists():
        raise RuntimeError(
            "opencode-config-editor.py not found. Run `python3 build.py` first."
        )
    spec = importlib.util.spec_from_file_location("opencode_config_editor", BUILT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
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
