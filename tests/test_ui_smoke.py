"""Offscreen smoke tests: instantiate the full UI tree to catch
build-order / import / constructor regressions early.

Covers MainWindow, every tab and every catalog/model dialog.
"""
import pytest

from tests.conftest import HAS_QT, ROOT, app

pytestmark = pytest.mark.skipif(not HAS_QT, reason="PySide6 not available - skipping GUI smoke tests")


@pytest.fixture
def catalog():
    cat = app.ModelCatalog()
    bundled = ROOT / "models" / "models.dev.catalog.json"
    if bundled.exists():
        cat.load(bundled)
        assert cat.loaded()
    return cat


class FakeApp:
    """Minimal stand-in for MainWindow used by tab constructors."""

    def __init__(self, catalog):
        self.model_catalog = catalog
        self.cfg = None
        self.dirty_oc = False

    def snapshot_state(self, *a):
        pass

    def mark_dirty(self, *a):
        pass

    def _ensure_catalog(self):
        return True


def test_main_window_constructs(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SETTINGS_FILE", tmp_path / "settings.ini")
    win = app.MainWindow(tmp_path)
    assert win.windowTitle().startswith(app.APP_NAME)
    win.close()


def test_all_tabs_construct(qapp, catalog):
    fake = FakeApp(catalog)
    for cls in (app.ProvidersTab, app.McpTab, app.PluginsTab, app.PermissionTab,
                app.RuntimeTab, app.AgentsTab, app.CommandsTab, app.TuiTab,
                app.GeneralTab, app.RawJsonTab):
        tab = cls(fake)
        assert tab is not None, cls.__name__


def test_catalog_dialogs_construct(qapp, catalog, tmp_path):
    if not catalog.formats():
        pytest.skip("bundled catalog not available")
    prov_key, models = next(iter(catalog.formats().items()))
    fmt = next(iter(models.values()))
    spec = app.build_spec_from_format(fmt)

    d1 = app.FetchProviderModelsDialog(None, catalog=catalog)
    d2 = app.MatchFormatPreviewDialog(
        None, [("m", {}, spec, "matched")], {}, catalog=catalog)
    d3 = app.CatalogModelPickerDialog(None, catalog)
    d4 = app.ModelCatalogDialog(None, catalog)
    d5 = app.ApplyCatalogDialog(None, catalog, {"provider": {prov_key: {"models": {}}}})
    for d in (d1, d2, d3, d4, d5):
        assert d is not None


def test_match_preview_status_sorting(qapp, catalog):
    entries = [
        ("a", {}, {"limit": {"context": 1}}, "unknown"),
        ("b", {}, {"limit": {"context": 2}}, "matched"),
    ]
    d = app.MatchFormatPreviewDialog(None, entries, {}, catalog=catalog)
    assert d is not None


def test_section_helper_used_by_providers_tab(qapp, catalog):
    fake = FakeApp(catalog)
    tab = app.ProvidersTab(fake)
    tab._update_table()  # must not raise with cfg=None


def test_fetch_dialog_marks_existing_models(qapp):
    providers = {"myp": {"models": {"m-old": {}}}}
    dlg = app.FetchProviderModelsDialog(None, providers=providers)
    dlg.key_edit.setText("myp")
    dlg.fetched_models = {"m-old": {"name": "Old"}, "m-new": {"name": "New"}}
    dlg._populate(dlg.fetched_models)
    statuses = {dlg.table.item(r, 1).text(): dlg.table.item(r, 3).text()
                for r in range(dlg.table.rowCount())}
    assert statuses == {"m-old": "existing", "m-new": "new"}
    assert dlg.sync_check.isHidden() is False      # offered when providers given
    dlg.key_edit.setText("other")                  # re-evaluates on key change
    assert {dlg.table.item(r, 3).text() for r in range(dlg.table.rowCount())} == {"new"}


def test_fetch_dialog_sync_hidden_without_providers(qapp):
    dlg = app.FetchProviderModelsDialog(None)
    assert dlg.sync_check.isHidden() is True


def test_fetch_dialog_prefills_existing_provider_endpoint(qapp):
    providers = {"myp": {"options": {"baseURL": "https://gw.example/v1",
                                     "apiKey": "stored" + "-key"}}}
    dlg = app.FetchProviderModelsDialog(None, provider_key="myp", providers=providers)
    assert dlg.url_edit.text() == "https://gw.example/v1"
    assert dlg.apikey_edit.text() == "stored" + "-key"
    # a brand-new key stays untouched by defaults
    dlg2 = app.FetchProviderModelsDialog(None, provider_key="fresh", providers=providers)
    assert dlg2.url_edit.text().startswith("https://api.openai.com")
    assert dlg2.apikey_edit.text() == ""


def test_providers_tab_add_from_api_creates_new_provider(qapp, catalog, monkeypatch):
    """The toolbar 'Fetch from API' entry must still be able to add a brand-new
    provider (the flow that was lost when fetch moved into the Models dialog)."""
    class Cfg:
        def __init__(self):
            self.data = {}

    fake = FakeApp(catalog)
    fake.cfg = Cfg()
    fake.status_bar = type("S", (), {"showMessage": lambda s, *a, **k: None})()
    tab = app.ProvidersTab(fake)

    assert hasattr(tab, "_fetch_new_provider")

    # Stub the fetch dialog: user picks key "brand-new" and two models, accepts.
    class StubDialog:
        def __init__(self, *a, **kw):
            self.key_edit = type("E", (), {"text": lambda s: "brand-new"})()
            self.url_edit = type("E", (), {"text": lambda s: "https://api.x.test/v1"})()
            self.apikey_edit = type("E", (), {"text": lambda s: ""})()
            self.save_apikey_check = type("C", (), {"isChecked": lambda s: False})()
            self.sync_check = type("C", (), {"isChecked": lambda s: False})()
            self.selected_models = {"m-a": {"name": "A"}, "m-b": {"name": "B"}}
            self.fetched_models = dict(self.selected_models)
            self.reference_provider = None
        def _current_adapter(self):
            return "openai"
        def exec(self):
            return app.QDialog.Accepted

    monkeypatch.setattr(app, "FetchProviderModelsDialog", StubDialog)
    # No catalog matches for these ids -> skip the review dialog quietly.
    monkeypatch.setattr(app.QMessageBox, "information", lambda *a, **k: None)

    tab._fetch_new_provider()

    providers = app.section(fake.cfg.data, "provider")
    assert "brand-new" in providers
    assert set(providers["brand-new"]["models"]) == {"m-a", "m-b"}


def test_new_feature_dialogs_construct(qapp):
    # Health check dialog
    health_dlg = app.ProviderHealthCheckDialog(None, providers={"openai": {"npm": "@ai-sdk/openai"}}, auto_run=False)
    assert health_dlg is not None
    health_dlg.close()

    # MCP Hub dialog
    hub_oc = app.MCPTemplateHubDialog(None, target_mode="opencode")
    assert hub_oc is not None
    hub_oc.close()

    hub_cl = app.MCPTemplateHubDialog(None, target_mode="openclaude")
    assert hub_cl is not None
    hub_cl.close()

    # Cross config converter dialog
    conv_dlg = app.CrossConfigConverterDialog(None)
    assert conv_dlg is not None
    conv_dlg.close()


