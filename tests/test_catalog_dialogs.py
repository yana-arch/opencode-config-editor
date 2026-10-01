import json

import pytest
from conftest import HAS_QT, app

pytestmark = pytest.mark.skipif(not HAS_QT, reason="PySide6 not available")


def test_add_custom_model_dialog_opens_and_accepts(qapp):
    # Regression: the dialog used QGridLayout without importing it (NameError on open).
    dlg = app.EditCustomModelDialog(None)
    dlg.id_edit.setText("glm-x")
    dlg._accept()
    assert dlg.result() == app.QDialog.Accepted
    assert dlg.result_model_id == "glm-x"


@pytest.fixture(autouse=True)
def _isolated_catalog_files(tmp_path, monkeypatch):
    """Never touch the developer's real catalog files from a UI test (CAT-17)."""
    monkeypatch.setattr(app, "CUSTOM_MODELS_FILE", tmp_path / "custom_models.json")
    monkeypatch.setattr(app, "PATTERN_RULES_FILE", tmp_path / "pattern_rules.json")


def _stored_spec():
    return {
        "name": "GLM 5.3 Flash",
        "provider": "zhipu",
        "limit": {"context": 128000, "output": 8192, "input": 4000},
        "cost": {"input": 0.0001, "output": 0.0002},
        "aliases": ["glm-5.3"],
        "attachment": False,
        "tool_call": True,
        "modalities": {"input": ["text", "image", "video"], "output": ["text"]},
    }


def test_unedited_custom_model_edit_preserves_hidden_fields(qapp):
    # Regression: the edit dialog rebuilt the spec from its widgets, silently
    # deleting cost/aliases/limit.input and flipping absent flags to true.
    stored = _stored_spec()
    dlg = app.EditCustomModelDialog(None, "glm-5.3-flash", dict(stored), "zhipu")
    dlg._accept()
    got = dlg.result_spec
    assert dlg.result() == app.QDialog.Accepted
    assert got["cost"] == stored["cost"]
    assert got["aliases"] == stored["aliases"]
    assert got["limit"] == stored["limit"]
    assert got["modalities"]["input"] == ["text", "image", "video"]
    assert got["attachment"] is False
    assert got["tool_call"] is True
    assert "temperature" not in got


def test_custom_model_edit_applies_widget_edits(qapp):
    stored = _stored_spec()
    dlg = app.EditCustomModelDialog(None, "glm-5.3-flash", dict(stored), "zhipu")
    dlg.name_edit.setText("Renamed")
    dlg.reas_cb.setChecked(True)
    dlg.mod_out_image.setChecked(True)
    dlg._accept()
    got = dlg.result_spec
    assert got["name"] == "Renamed"
    assert got["reasoning"] is True
    assert got["modalities"]["output"] == ["text", "image"]
    # Untouched hidden fields still survive.
    assert got["cost"] == stored["cost"]


def test_custom_model_edit_survives_null_limits(qapp):
    dlg = app.EditCustomModelDialog(
        None, "x", {"limit": {"context": None, "output": None}}, "custom")
    dlg._accept()
    assert dlg.result() == app.QDialog.Accepted


class _FakeImportDialog:
    result_data = {}

    def exec(self=None):
        return app.QDialog.Accepted


def test_import_rejects_non_model_entries(qapp, tmp_path, monkeypatch):
    # Regression: importing {"$schema": "..."} wrote it to custom_models.json
    # and then crashed the table refresh.
    custom = tmp_path / "custom_models.json"
    monkeypatch.setattr(app, "CUSTOM_MODELS_FILE", custom)
    custom.write_text('{"existing": {"limit": {"context": 1}}}')

    cat = app.ModelCatalog()
    dlg = app.CustomCatalogManagerDialog(None, cat)
    monkeypatch.setattr(app, "JsonImportDialog", lambda *a, **k: _FakeImportDialog)
    warnings = []
    monkeypatch.setattr(app.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warnings.append(a[2] if len(a) > 2 else "")))
    monkeypatch.setattr(app.QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))

    _FakeImportDialog.result_data = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "imported-model": {"limit": {"context": 5}},
    }
    dlg._import_custom_models()
    assert "$schema" not in custom.read_text()
    assert warnings, "the user must be told the import was rejected"

    # A well-formed import still merges.
    warnings.clear()
    _FakeImportDialog.result_data = {"imported-model": {"limit": {"context": 5}}}
    dlg._import_custom_models()
    saved = json.loads(custom.read_text())
    assert "imported-model" in saved and "existing" in saved
    assert dlg.custom_table.rowCount() == 2
    dlg.deleteLater()


def test_online_sync_runs_off_the_gui_thread(qapp, tmp_path, monkeypatch):
    # Regression: fetch_online ran on the GUI thread, freezing the window.
    import threading
    import time

    started = threading.Event()
    release = threading.Event()

    class _SlowCatalog(app.ModelCatalog):
        def fetch_online(self, url=None):
            started.set()
            release.wait(10)
            return True, "updated", 3

    cat = _SlowCatalog()
    dlg = app.CustomCatalogManagerDialog(None, cat)
    messages = []
    monkeypatch.setattr(app.QMessageBox, "information",
                        staticmethod(lambda *a, **k: messages.append(a[2] if len(a) > 2 else "")))
    monkeypatch.setattr(app.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: messages.append("WARN")))

    ticks = []
    timer = app.QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()

    try:
        dlg._sync_online()
        deadline = time.time() + 10
        while not started.is_set() and time.time() < deadline:
            qapp.processEvents()
        assert started.is_set(), "fetch_online never ran"
        # Keep pumping the loop while the worker is still busy: had the
        # download run on the GUI thread, processEvents() could not run at all.
        deadline = time.time() + 1.0
        while not release.is_set() and time.time() < deadline:
            qapp.processEvents()
        assert len(ticks) > 3, f"event loop stalled during sync ({len(ticks)} ticks)"

        release.set()
        deadline = time.time() + 10
        while not messages and time.time() < deadline:
            qapp.processEvents()
        assert messages == ["updated"]
        assert dlg.sync_btn.isEnabled()
    finally:
        release.set()
        timer.stop()
        dlg.deleteLater()


# ---------------------------------------------------------------------------
# FetchProviderModelsDialog
# ---------------------------------------------------------------------------

def test_fetch_dialog_infers_format_before_prefilled_key(qapp):
    # Regression: the OpenAI default URL was applied first, so an Anthropic
    # key got sent to api.openai.com.
    providers = {"anthropic": {
        "npm": "@ai-sdk/anthropic",
        "options": {"baseURL": "https://api.anthropic.com"},
    }}
    dlg = app.FetchProviderModelsDialog(None, "anthropic", None, providers)
    assert dlg._current_adapter() == "anthropic"
    assert dlg.url_edit.text() == "https://api.anthropic.com"


def test_fetch_dialog_gemini_default_has_v1beta(qapp):
    dlg = app.FetchProviderModelsDialog(None, "x", None, {"x": {"npm": "@ai-sdk/google"}})
    assert dlg._current_adapter() == "gemini"
    assert dlg.url_edit.text() == "https://generativelanguage.googleapis.com/v1beta"


def test_fetch_dialog_keeps_placeholder_key_verbatim(qapp, monkeypatch):
    # Regression: a stored "{env:OPENAI_API_KEY}" was expanded in the field, so
    # Save wrote the secret itself instead of the reference.
    providers = {"openai": {"options": {"apiKey": "{env:OPENAI_API_KEY}"}}}
    dlg = app.FetchProviderModelsDialog(None, "openai", None, providers)
    assert dlg.apikey_edit.text() == "{env:OPENAI_API_KEY}"
    assert dlg.save_apikey_check.isChecked() is False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-resolved")
    assert dlg._build_spec().api_key == "sk-resolved"


def test_fetch_dialog_plain_key_is_saved_by_default(qapp):
    providers = {"openai": {"options": {"apiKey": "sk-plain"}}}
    dlg = app.FetchProviderModelsDialog(None, "openai", None, providers)
    assert dlg.save_apikey_check.isChecked() is True


def test_fetch_dialog_lock_key_is_read_only_but_usable(qapp):
    providers = {"openai": {"options": {"apiKey": "sk-plain"}}}
    dlg = app.FetchProviderModelsDialog(None, "openai", None, providers, lock_key=True)
    assert dlg.apikey_edit.isReadOnly() is True
    assert dlg.apikey_edit.isEnabled() is True
    assert dlg.apikey_edit.text() == "sk-plain"


def test_fetch_dialog_api_base_url_per_format(qapp):
    providers = {"openai": {"options": {"baseURL": "https://api.openai.com/v1"}}}
    dlg = app.FetchProviderModelsDialog(None, "openai", None, providers)
    assert dlg.api_base_url() == "https://api.openai.com/v1"
    for adapter in ("models_dev", "generic"):
        dlg.format_combo.setCurrentIndex(dlg.format_combo.findData(adapter))
        assert dlg.api_base_url() == "", adapter


def test_fetch_dialog_invalidates_after_fetch_on_change(qapp):
    providers = {"openai": {"options": {"baseURL": "https://api.openai.com/v1",
                                         "apiKey": "sk-plain"}}}
    dlg = app.FetchProviderModelsDialog(None, "openai", None, providers)
    dlg._on_fetched({"a": {"name": "A"}})
    ok_btn = dlg.buttons.button(app.QDialogButtonBox.Ok)
    assert ok_btn.isEnabled()
    dlg.url_edit.setText("https://other.example/v1")
    assert not ok_btn.isEnabled()
    assert dlg.fetched_models == {}
    assert dlg.table.rowCount() == 0


def test_fetch_dialog_ignores_result_after_close(qapp):
    providers = {"openai": {"options": {"apiKey": "sk-plain"}}}
    dlg = app.FetchProviderModelsDialog(None, "openai", None, providers)
    dlg._closed = True
    dlg._on_fetched({"late": {"name": "Late"}})
    assert dlg.fetched_models == {}
