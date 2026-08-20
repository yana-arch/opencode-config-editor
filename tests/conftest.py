"""Pytest setup: import the built app module without launching the GUI.

The built `opencode-config-editor.py` concatenates all src/ files and only
starts the Qt event loop under `if __name__ == "__main__"`, so importing it
as a module is safe (no QApplication is created).
"""
import importlib.util
from pathlib import Path

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