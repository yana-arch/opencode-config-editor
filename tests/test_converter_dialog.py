import json

import pytest

from conftest import HAS_QT, app

pytestmark = pytest.mark.skipif(not HAS_QT, reason="PySide6 not available")


class FakeOCConfig:
    def __init__(self, data):
        self.data = data


class FakeWindow:
    """Minimal stand-in for MainWindow: only the API the dialog calls."""

    def __init__(self, data=None):
        self.cfg = FakeOCConfig(data if data is not None else {})
        self.oc_layered = None
        self.refreshed = 0
        self.snapshots = []
        self.dirty = []

    def snapshot_state(self, kind="auto"):
        self.snapshots.append(kind)

    def mark_dirty(self, kind="auto"):
        self.dirty.append(kind)

    def refresh_tabs(self):
        self.refreshed += 1


@pytest.fixture
def silent_dialogs(qapp, monkeypatch):
    """Auto-accept confirm/info/warning boxes and remember which one fired."""
    seen = []
    monkeypatch.setattr(app.QMessageBox, "information",
                        staticmethod(lambda *a, **k: seen.append(a[1] if len(a) > 1 else "")))
    monkeypatch.setattr(app.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(a[1] if len(a) > 1 else "")))
    monkeypatch.setattr(app, "_confirm", lambda *a, **k: True)
    return seen


def _dialog(win):
    return app.CrossConfigConverterDialog(None, app_context=win)


def _select_target(dlg, data_value):
    idx = dlg.tgt_format_combo.findData(data_value)
    dlg.tgt_format_combo.setCurrentIndex(idx)


def test_apply_deep_merges_provider_entry(silent_dialogs):
    """CC-01: applying a provider entry keeps options/models the source omits."""
    win = FakeWindow({"provider": {"anthropic": {"npm": "@ai-sdk/anthropic",
                                               "options": {"apiKey": "sk-old"},
                                               "models": {"claude-x": {}}}}})
    dlg = _dialog(win)
    _select_target(dlg, "opencode")
    dlg.src_editor.setPlainText(json.dumps({"provider": {"anthropic": {"npm": "@ai-sdk/anthropic-v2"}}}))
    dlg._apply_to_active()

    entry = win.cfg.data["provider"]["anthropic"]
    assert entry["npm"] == "@ai-sdk/anthropic-v2"
    assert entry["options"]["apiKey"] == "sk-old"
    assert "claude-x" in entry["models"]



def test_mcp_only_apply_keeps_existing_plugins(silent_dialogs):
    """CC-02: an MCP-only conversion must not wipe the plugin list."""
    win = FakeWindow({"plugin": ["existing-plugin"]})
    dlg = _dialog(win)
    _select_target(dlg, "opencode")
    dlg.src_editor.setPlainText(json.dumps({"mcpServers": {"fs": {"command": "npx", "args": ["-y", "@mcp/fs"]}}}))
    dlg._apply_to_active()

    assert win.cfg.data["plugin"] == ["existing-plugin"]
    assert "fs" in win.cfg.data["mcp"]


def test_save_merges_into_existing_file_atomically(silent_dialogs, tmp_path, monkeypatch):
    """CC-05: unrelated keys of the target survive, and the write is atomic."""
    target = tmp_path / "openclaude.json"
    target.write_text(json.dumps({"numStartups": 7, "oauthAccount": {"a": 1},
                                  "mcpServers": {"memory": {"command": "old"}}}))
    monkeypatch.setattr(app.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))

    win = FakeWindow({})
    dlg = _dialog(win)
    _select_target(dlg, "openclaude_global")
    dlg.src_editor.setPlainText(json.dumps({"mcpServers": {"fs": {"command": "npx"}}}))
    dlg._save_to_file()

    saved = json.loads(target.read_text())
    assert saved["numStartups"] == 7
    assert saved["oauthAccount"] == {"a": 1}
    assert set(saved["mcpServers"]) == {"memory", "fs"}
    assert not list(tmp_path.glob("*.tmp"))


def test_save_and_apply_refuse_invalid_source(silent_dialogs, tmp_path, monkeypatch):
    """CC-06: a parse error clears the converted data instead of leaving it stale."""
    target = tmp_path / "out.json"
    monkeypatch.setattr(app.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))

    win = FakeWindow({"plugin": ["existing"]})
    dlg = _dialog(win)
    _select_target(dlg, "opencode")
    dlg.src_editor.setPlainText(json.dumps({"plugin": ["new"]}))
    dlg.src_editor.setPlainText('{"plugin": ["new"')

    dlg._save_to_file()
    assert not target.exists()
    dlg._apply_to_active()
    assert win.cfg.data["plugin"] == ["existing"]


def test_openclaude_source_and_apply_use_layered_config(silent_dialogs, tmp_path, monkeypatch):
    """CC-04: the active OpenClaude config is read from oc_layered and written back to it."""
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = tmp_path / "proj"
    (proj / ".openclaude").mkdir(parents=True)
    (proj / ".openclaude" / "settings.json").write_text(json.dumps({"env": {"E": "1"}}))

    win = FakeWindow({})
    win.cfg = None
    win.oc_layered = app.LayeredConfigFile(proj)
    win.oc_layered.load()
    global_file = win.oc_layered.global_file
    global_file.write_text(json.dumps({"numStartups": 3, "mcpServers": {"memory": {"command": "npx"}}}))
    win.oc_layered.load()

    dlg = _dialog(win)
    dlg.src_type_combo.setCurrentIndex(1)
    source = json.loads(dlg.src_editor.toPlainText())
    assert source["numStartups"] == 3
    assert "memory" in source["mcpServers"]
    assert source["env"] == {"E": "1"}

    _select_target(dlg, "openclaude_global")
    dlg.src_editor.setPlainText(json.dumps({"mcpServers": {"fs": {"command": "npx"}}}))
    dlg._apply_to_active()

    saved = json.loads(global_file.read_text())
    assert saved["numStartups"] == 3
    assert set(saved["mcpServers"]) == {"memory", "fs"}
    assert win.refreshed == 1


def test_omp_target_honours_component_checkboxes(silent_dialogs):
    """CC-11: unchecked components are not exported into the OMP bundle."""
    win = FakeWindow({})
    dlg = _dialog(win)
    _select_target(dlg, "omp")
    dlg.src_editor.setPlainText(json.dumps(
        {"provider": {"anthropic": {"options": {"apiKey": "sk-secret"}}}, "plugin": ["p"]}))
    for key, chk in dlg.comp_checks.items():
        chk.setChecked(key == "plugins")

    assert "providers" not in dlg.converted_data
    assert dlg.converted_data["plugins"] == ["p"]


def test_preview_reports_unmapped_source_keys(silent_dialogs):
    """CC-13: keys with no mapping are named in the preview instead of vanishing."""
    win = FakeWindow({})
    dlg = _dialog(win)
    _select_target(dlg, "opencode")
    dlg.src_editor.setPlainText(json.dumps(
        {"model": "anthropic/claude", "agent": {"a": {}}, "mcp": {"fs": {"type": "local", "command": ["npx"]}}}
    ))

    assert set(dlg.unmapped_keys) == {"model", "agent"}
    assert "model" in dlg.unmapped_label.text()
    assert not dlg.unmapped_label.isHidden()

def test_apply_cancel_keeps_unsaved_tui_theme_edit(qapp, monkeypatch, tmp_path):
    """A pending TUI edit lives only in the widget until Save. Cancelling the
    unsaved-changes prompt must keep it and merge nothing."""
    monkeypatch.setattr(app.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(app.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(app, "_confirm", lambda *a, **k: True)
    monkeypatch.setattr(app, "_confirm_unsaved", lambda *a, **k: "cancel")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(app, "PROVIDER_TRASH_FILE", tmp_path / "deleted-providers.json")

    win = app.MainWindow(tmp_path)
    win.tab_tui.theme_edit.set_value("typed-theme")
    win.dirty_tui = True

    dlg = app.CrossConfigConverterDialog(win, app_context=win)
    _select_target(dlg, "opencode")
    dlg.src_editor.setPlainText(json.dumps({"mcp": {"fs": {"type": "local", "command": ["npx"]}}}))
    dlg._apply_to_active()

    assert win.tab_tui.theme_edit.value() == "typed-theme"
    assert "mcp" not in (win.cfg.data or {})

