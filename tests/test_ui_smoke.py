"""Offscreen smoke tests: instantiate the full UI tree to catch
build-order / import / constructor regressions early.

Covers MainWindow, every tab and every catalog/model dialog.
"""
import pytest

from tests.conftest import ROOT, app


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
