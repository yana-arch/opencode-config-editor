"""Plugins tab: staged removal, enabled-wins precedence, filter-safe collect."""
import pytest

from tests.conftest import app, HAS_QT

pytestmark = pytest.mark.skipif(not HAS_QT, reason="PySide6 not available")


class FakeApp:
    """Minimal stand-in for MainWindow as seen by PluginsTab."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.dirty = False
        self.snapshots = 0

    def mark_dirty(self, *a, **k):
        self.dirty = True

    def snapshot_state(self):
        self.snapshots += 1


class FakeCfg:
    def __init__(self, path, plugins=None):
        self.path = path
        self.data = {"plugin": list(plugins or [])}


def _tab(qapp, tmp_path, plugins=(), store=None, cfg_path=None):
    cfg = FakeCfg(cfg_path or (tmp_path / "opencode.json"), plugins)
    fake = FakeApp(cfg)
    tab = app.PluginsTab(fake)
    if store is not None:
        tab.state_store = store
    tab.refresh()
    return tab, fake


def _remove(tab, fake, name):
    row = tab._find_plugin_row(name)
    assert row >= 0
    tab.table.selectRow(row)


def test_remove_is_staged_until_save(qapp, tmp_path, monkeypatch):
    """F3: Remove must not touch the store; only collect() (Save) does."""
    store = app.PluginStateStore()
    store.path = tmp_path / "plugin-state.json"
    store._data = {}
    cfg_file = tmp_path / "opencode.json"

    tab, _ = _tab(qapp, tmp_path, plugins=["keep", ["gone", {"lang": "vi"}]],
                  store=store, cfg_path=cfg_file)
    tab.cbs["gone"].setChecked(False)
    tab.collect(tab.app.cfg.data)          # Save persists the disable

    assert store.get_entries(cfg_file) == {"gone": ["gone", {"lang": "vi"}]}

    monkeypatch.setattr(app, "_confirm", lambda *a, **k: True)
    row = tab._find_plugin_row("gone")
    tab.table.selectRow(row)
    tab._remove_selected()

    # Still in the store: Undo/Reload can restore it.
    assert store.get_entries(cfg_file) == {"gone": ["gone", {"lang": "vi"}]}
    assert "gone" in tab._removed

    # Reload (refresh) restores the row from the store.
    tab.refresh()
    assert "gone" in tab._entries

    # Save persists the removal.
    tab._removed.add("gone")
    tab.collect(tab.app.cfg.data)
    assert store.get_entries(cfg_file) == {}


def test_collect_with_active_filter_keeps_hidden_plugins(qapp, tmp_path):
    """(b) A search filter must not make Save drop the filtered-out rows."""
    store = app.PluginStateStore()
    store.path = tmp_path / "plugin-state.json"
    store._data = {}
    cfg_file = tmp_path / "opencode.json"

    tab, _ = _tab(qapp, tmp_path, plugins=["alpha", "beta", "gamma"],
                  store=store, cfg_path=cfg_file)

    tab._filter_plugins("alpha")
    assert tab.table.rowCount() == 1          # only the match is shown

    tab.collect(tab.app.cfg.data)
    assert sorted(tab.app.cfg.data["plugin"]) == ["alpha", "beta", "gamma"]


def test_enabled_plugin_wins_over_stale_store_entry(qapp, tmp_path):
    """A plugin present in plugin[] is never shown as disabled, even if a
    migrated/legacy store entry says otherwise."""
    store = app.PluginStateStore()
    store.path = tmp_path / "plugin-state.json"
    store._data = {}
    cfg_file = tmp_path / "opencode.json"
    store.set_entry(cfg_file, "beta", ["beta", {"lang": "en"}])

    tab, _ = _tab(qapp, tmp_path, plugins=["alpha", "beta"],
                  store=store, cfg_path=cfg_file)

    assert tab.cbs["beta"].isChecked() is True
    assert tab.cbs["alpha"].isChecked() is True


def test_filter_repopulating_keeps_unchecked_state(qapp, tmp_path):
    store = app.PluginStateStore()
    store.path = tmp_path / "plugin-state.json"
    store._data = {}
    cfg_file = tmp_path / "opencode.json"

    tab, _ = _tab(qapp, tmp_path, plugins=["alpha", "beta"],
                  store=store, cfg_path=cfg_file)
    tab.cbs["beta"].setChecked(False)
    tab._filter_plugins("alpha")
    tab._filter_plugins("")

    assert tab.cbs["beta"].isChecked() is False
    assert tab.cbs["alpha"].isChecked() is True
