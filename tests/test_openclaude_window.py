"""End-to-end test: MainWindow driven by the openclaude adapter (offscreen).

Proves the adapter seam works for a second, differently-shaped agent: layered
settings load -> edit -> save via the adapter session hooks, with opencode
untouched.
"""
import json

import pytest

from tests.conftest import HAS_QT, app

pytestmark = pytest.mark.skipif(not HAS_QT, reason="PySide6 not available")


@pytest.fixture
def oc_win(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SETTINGS_FILE", tmp_path / "settings.ini")
    # isolate config home so we never touch the real ~/.openclaude
    monkeypatch.setenv("OPENCLAUDE_CONFIG_DIR", str(tmp_path / "cfghome"))
    adapter = app.get_adapter("openclaude")
    w = app.MainWindow(tmp_path / "proj", adapter=adapter)
    yield w
    w.close()


def test_openclaude_window_builds_with_adapter(oc_win):
    assert oc_win.adapter.name == "openclaude"
    assert oc_win.tabs.count() == 2            # Settings + Raw
    assert oc_win.oc_layered is not None       # initial_load hook ran
    assert oc_win.oc_layer == "project"


def test_openclaude_settings_save_roundtrip(oc_win, tmp_path):
    settings_tab = oc_win._agent_tabs[0]
    settings_tab.model_edit.setText("anthropic/claude-sonnet-4")
    settings_tab.agent_edit.setText("build")
    oc_win._save()  # routes to adapter.save_fn

    saved = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert saved["model"] == "anthropic/claude-sonnet-4"
    assert saved["agent"] == "build"


def test_openclaude_layer_isolation(oc_win, tmp_path):
    # write to project layer
    st = oc_win._agent_tabs[0]
    st.model_edit.setText("project-model")
    oc_win._save()
    # switch to local layer, save a different model
    st.layer_combo.setCurrentIndex(st.layer_combo.findData("local"))
    assert oc_win.oc_layer == "local"
    st.model_edit.setText("local-model")
    oc_win._save()

    proj = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    local = json.loads((tmp_path / "proj" / ".openclaude" / "settings.local.json").read_text())
    assert proj["model"] == "project-model"
    assert local["model"] == "local-model"
    # effective view: local overrides project
    assert oc_win.oc_layered.effective()["model"] == "local-model"


def test_openclaude_does_not_register_opencode_tabs(oc_win):
    # opencode-specific attributes must not exist on an openclaude window
    assert not hasattr(oc_win, "tab_tui")
    assert not hasattr(oc_win, "_oc_tabs")


def test_opencode_still_default(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SETTINGS_FILE", tmp_path / "s.ini")
    w = app.MainWindow(tmp_path)
    assert w.adapter.name == "opencode"
    assert w.tabs.count() == 10
    w.close()
