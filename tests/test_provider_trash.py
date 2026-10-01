"""Soft-deleted providers live in the editor's own trash file
(PROVIDER_TRASH_FILE, isolated per test by conftest), never inside the agent
config: opencode silently strips unknown provider keys and still loads them."""
import copy
import json
import os

import pytest

from tests.conftest import app


def _store(tmp_path):
    return app.ProviderTrashStore(tmp_path / "deleted-providers.json")


# --- ProviderTrashStore ---------------------------------------------------

def test_store_put_entries_discard_prune(tmp_path):
    store = _store(tmp_path)
    assert store.prune("/cfg/a.json", {"x"}) == 0
    assert not store.path.exists()             # no-op prune never creates the file

    store.put("/cfg/a.json", "p1", {"npm": "x", "options": {"apiKey": "sk"}})
    store.put("/cfg/a.json", "p2", {"npm": "y"})
    store.put("/cfg/b.json", "p1", {"npm": "other"})
    assert store.entries("/cfg/a.json") == {"p1": {"npm": "x", "options": {"apiKey": "sk"}},
                                            "p2": {"npm": "y"}}
    assert store.entries("/cfg/b.json") == {"p1": {"npm": "other"}}   # buckets per config file
    assert store.entries("/cfg/none.json") == {}

    store.discard("/cfg/a.json", "p2")
    store.discard("/cfg/a.json", "missing")    # no-op
    assert store.entries("/cfg/a.json") == {"p1": {"npm": "x", "options": {"apiKey": "sk"}}}

    assert store.prune("/cfg/a.json", {"p1", "unrelated"}) == 1
    assert store.entries("/cfg/a.json") == {}
    assert json.loads(store.path.read_text()) == {"/cfg/b.json": {"p1": {"npm": "other"}}}


@pytest.mark.parametrize("raw", [b"{not json", b"\xff\xfe\x00", b"[1, 2]"])
def test_store_never_overwrites_a_corrupt_file(tmp_path, raw):
    store = _store(tmp_path)
    store.path.write_bytes(raw)
    assert store.entries("/cfg/a.json") == {}
    for mutate in (lambda: store.put("/cfg/a.json", "k", {}),
                   lambda: store.discard("/cfg/a.json", "k"),
                   lambda: store.prune("/cfg/a.json", {"k"})):
        with pytest.raises(OSError):
            mutate()
    assert store.path.read_bytes() == raw


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test_store_file_is_private(tmp_path):
    store = _store(tmp_path)
    store.put("/cfg/a.json", "k", {"options": {"apiKey": "sk-secret"}})
    assert store.path.stat().st_mode & 0o777 == 0o600


# --- opencode Providers tab -----------------------------------------------

PROVIDERS = {
    "a": {"npm": "@ai-sdk/openai", "name": "Alpha", "options": {"apiKey": "sk-a"}},
    "b": {"npm": "@ai-sdk/anthropic"},
    "c": {"options": {"apiKey": "sk-c"}},          # no npm/name on purpose
}


@pytest.fixture
def providers_tab(qapp, tmp_path, monkeypatch):
    """ProvidersTab on a real ConfigFile + UndoManager, with MainWindow's
    snapshot/mark_dirty protocol."""
    monkeypatch.setattr(app, "USER_CONFIG_DIR", tmp_path / "appdata")  # backups
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps({"provider": copy.deepcopy(PROVIDERS)}), encoding="utf-8")
    cfg = app.ConfigFile(path, "opencode")
    assert cfg.load()

    class Win:
        def __init__(self):
            self.cfg = cfg
            self.undo = app.UndoManager()
            self.dirty = False
            self._snap = False

        def snapshot_state(self, *a):
            self.undo.push(copy.deepcopy(self.cfg.data))
            self._snap = True

        def mark_dirty(self, *a):
            if not self._snap:
                self.undo.push(copy.deepcopy(self.cfg.data))
                self._snap = True
            self.dirty = True

        def undo_once(self):
            self.cfg.data = self.undo.undo(self.cfg.data)
            self._snap = False

    warnings = []
    monkeypatch.setattr(app.QMessageBox, "warning", lambda *a, **k: warnings.append(a))
    monkeypatch.setattr(app.QMessageBox, "critical", lambda *a, **k: warnings.append(a))
    monkeypatch.setattr(app, "_confirm", lambda *a, **k: True)
    win = Win()
    tab = app.ProvidersTab(win)
    tab.refresh()
    tab.win, tab.cfg, tab.path, tab.warnings = win, cfg, path, warnings
    return tab


def _keys(tab):
    return [tab.table.item(r, 0).text() for r in range(tab.table.rowCount())]


def _click(tab, row, text):
    btn = next(b for b in tab.table.cellWidget(row, 4).findChildren(app.QPushButton)
               if b.text() == text)
    btn.click()


def _collect(tab):
    data = dict(tab.cfg.data)          # MainWindow._collect_oc: shallow root copy
    tab.collect(data)
    return data


def _trash_of(path):
    return app.ProviderTrashStore().entries(path)


def test_remove_moves_provider_to_trash(providers_tab):
    tab = providers_tab
    _click(tab, 0, "Remove")
    assert "a" not in tab.cfg.data["provider"]
    assert "a" not in _collect(tab)["provider"]
    assert tab.win.dirty
    assert _trash_of(tab.path) == {"a": PROVIDERS["a"]}
    assert _keys(tab) == ["b", "c"]                 # hidden until "Show deleted"
    assert tab.status_label.text() == "2 providers · 1 deleted"

    tab.show_trash_chk.setChecked(True)
    assert _keys(tab) == ["b", "c", "a"]            # deleted rows go below live rows
    assert [r[0] for r in tab.rows] == ["b", "c"]   # and are never collected
    item = tab.table.item(2, 0)
    assert not item.flags() & app.Qt.ItemIsEditable
    buttons = {b.text() for b in tab.table.cellWidget(2, 4).findChildren(app.QPushButton)}
    assert buttons == {"Restore", "Delete permanently"}
    # Live rows keep the theme's text color (no hard-coded foreground).
    assert tab.table.item(0, 0).data(app.Qt.ForegroundRole) is None


def test_remove_keeps_uncommitted_inline_edit(providers_tab):
    tab = providers_tab
    tab.rows[0][1].edit.setText("@ai-sdk/edited")    # editingFinished not fired yet
    _click(tab, 0, "Remove")
    assert _trash_of(tab.path)["a"]["npm"] == "@ai-sdk/edited"


def test_undo_restore_and_save_prunes_trash(providers_tab):
    tab = providers_tab
    tab.show_trash_chk.setChecked(True)
    _click(tab, 0, "Remove")
    tab.win.undo_once()
    tab.refresh()
    assert "a" in tab.cfg.data["provider"]
    assert _keys(tab) == ["a", "b", "c"]            # undone: no longer listed as deleted

    _click(tab, 0, "Remove")
    assert _keys(tab) == ["b", "c", "a"]
    _click(tab, 2, "Restore")
    assert tab.cfg.data["provider"]["a"] == PROVIDERS["a"]
    assert _keys(tab) == ["a", "b", "c"]
    assert "a" in _trash_of(tab.path)               # kept until a successful save

    ok, msg = tab.cfg.save(_collect(tab))
    assert ok, msg
    saved = json.loads(tab.path.read_text())
    assert saved["provider"] == PROVIDERS
    assert "_deleted" not in tab.path.read_text()
    assert _trash_of(tab.path) == {}


def test_delete_permanently_asks_then_drops_trash_entry(providers_tab, monkeypatch):
    tab = providers_tab
    tab.show_trash_chk.setChecked(True)
    _click(tab, 0, "Remove")
    tab.win.dirty = False
    monkeypatch.setattr(app, "_confirm", lambda *a, **k: False)
    _click(tab, 2, "Delete permanently")
    assert "a" in _trash_of(tab.path)               # declined
    monkeypatch.setattr(app, "_confirm", lambda *a, **k: True)
    _click(tab, 2, "Delete permanently")
    assert _trash_of(tab.path) == {}
    assert _keys(tab) == ["b", "c"]
    assert not tab.win.dirty                        # the config itself is unchanged


def test_remove_aborts_cleanly_when_trash_unwritable(providers_tab):
    tab = providers_tab
    trash_file = app.PROVIDER_TRASH_FILE
    trash_file.write_text("{corrupt", encoding="utf-8")
    _click(tab, 0, "Remove")
    assert tab.warnings                              # error shown
    assert tab.cfg.data["provider"] == PROVIDERS     # nothing removed
    assert not tab.win.dirty and not tab.win.undo.can_undo()
    assert trash_file.read_text() == "{corrupt"


def test_rename_via_key_cell_renames_in_place(providers_tab):
    tab = providers_tab
    tab.table.item(0, 0).setText("renamed")
    assert set(tab.cfg.data["provider"]) == {"renamed", "b", "c"}
    assert tab.cfg.data["provider"]["renamed"] == PROVIDERS["a"]
    assert set(_collect(tab)["provider"]) == {"renamed", "b", "c"}   # no duplicate
    assert tab.win.dirty
    _click(tab, 0, "Remove")                        # row buttons follow the new key
    assert set(_trash_of(tab.path)) == {"renamed"}


def test_rename_collision_is_refused_even_when_hidden_by_search(providers_tab):
    tab = providers_tab
    tab.search_edit.setText("anthropic")
    assert _keys(tab) == ["b"]                      # "a" is filtered out of view
    tab.table.item(0, 0).setText("a")
    tab.table.item(0, 0).setText("   ")
    assert _keys(tab) == ["b"]                      # both reverted
    assert len(tab.warnings) == 2
    assert tab.cfg.data["provider"] == PROVIDERS
    assert not tab.win.dirty


def test_cleared_npm_is_dropped_not_written_empty(providers_tab):
    tab = providers_tab
    edit = tab.rows[1][1]                           # provider "b"
    edit.edit.setText("")
    edit.edit.editingFinished.emit()
    providers = _collect(tab)["provider"]
    assert "npm" not in providers["b"]
    assert providers["c"] == PROVIDERS["c"]         # never gains "npm": ""


def test_inline_edit_survives_table_rebuilds(providers_tab):
    tab = providers_tab
    edit = tab.rows[0][1]                           # provider "a"
    edit.edit.setText("@ai-sdk/new")
    edit.edit.editingFinished.emit()
    tab.search_edit.setText("zzz")
    tab.search_edit.setText("")
    tab.show_trash_chk.setChecked(True)
    assert tab.rows[0][1].value() == "@ai-sdk/new"
    assert _collect(tab)["provider"]["a"]["npm"] == "@ai-sdk/new"
    assert tab.win.dirty


def test_collect_applies_edit_still_in_focused_cell(providers_tab):
    tab = providers_tab
    tab.rows[0][2].edit.setText("Renamed display")  # e.g. Save shortcut, no focus-out
    assert _collect(tab)["provider"]["a"]["name"] == "Renamed display"


def test_collect_never_resurrects_provider_removed_in_raw(providers_tab):
    tab = providers_tab
    data = {"provider": {"b": dict(PROVIDERS["b"])}}   # Raw JSON dropped "a" and "c"
    tab.collect(data)
    assert data == {"provider": {"b": PROVIDERS["b"]}}


def test_search_tolerates_non_object_provider(providers_tab):
    tab = providers_tab
    tab.cfg.data["provider"]["x"] = None
    tab.refresh()
    tab.search_edit.setText("x")
    assert _keys(tab) == ["x"]
    tab.search_edit.setText("anthropic")
    assert _keys(tab) == ["b"]


# --- openclaude Agent Models tab ------------------------------------------

GLOBAL = {
    "numStartups": 3,
    "activeProviderProfileId": "p2",
    "providerProfiles": [
        {"id": "p1", "name": "One", "provider": "openai", "model": "m1", "apiKey": "sk-one"},
        {"id": "p2", "name": "Two", "provider": "custom", "baseUrl": "https://two.example/v1",
         "model": "m2", "apiKey": "sk-two", "authScheme": "raw"},
    ],
    "agentModels": {"leg": {"base_url": "https://leg.example", "model": "m-leg",
                            "api_key": "sk-leg", "extra": 1}},
}


@pytest.fixture
def ocl(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SETTINGS_FILE", tmp_path / "settings.ini")
    monkeypatch.setenv("OPENCLAUDE_CONFIG_DIR", str(tmp_path / "cfghome"))
    monkeypatch.setattr(app, "_confirm", lambda *a, **k: True)
    (tmp_path / "cfghome.json").write_text(json.dumps(GLOBAL), encoding="utf-8")
    w = app.MainWindow(tmp_path / "proj", adapter=app.get_adapter("openclaude"))
    yield w
    w.close()


def _models_tab(win):
    return win._agent_models_tab


def _global_trash(win):
    return app.ProviderTrashStore().entries(win.oc_layered.global_file)


def _row_names(tab):
    return [tab.models_table.item(r, 0).text() for r in range(tab.models_table.rowCount())]


def _select_rows(tab, rows):
    from PySide6.QtCore import QItemSelectionModel
    sel = tab.models_table.selectionModel()
    sel.clearSelection()
    for r in rows:
        sel.select(tab.models_table.model().index(r, 0),
                   QItemSelectionModel.Select | QItemSelectionModel.Rows)


def test_openclaude_remove_trashes_profile_by_id(ocl):
    tab = _models_tab(ocl)
    assert _row_names(tab) == ["One", "Two", "leg"]
    tab.models_table.item(1, 3).setText("m2-edited")   # unsaved edit goes to the trash
    tab.models_table.selectRow(1)
    tab._remove_model_row()
    assert _global_trash(ocl) == {"p2": {
        "id": "p2", "name": "Two", "provider": "custom", "baseUrl": "https://two.example/v1",
        "model": "m2-edited", "apiKey": "sk-two", "authScheme": "raw"}}
    data = {}
    tab.collect(data)
    assert [p["id"] for p in data["providerProfiles"]] == ["p1"]
    assert tab._dirty


def test_openclaude_show_deleted_rows_are_display_only(ocl, tmp_path):
    tab = _models_tab(ocl)
    tab.models_table.selectRow(1)
    tab._remove_model_row()
    ocl._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    assert [p["id"] for p in saved["providerProfiles"]] == ["p1"]
    combo = [tab.active_combo.itemData(i) for i in range(tab.active_combo.count())]
    assert combo == ["", "p1"]

    tab.models_table.item(0, 3).setText("m1-unsaved")    # live edit must survive toggles
    tab._dirty = False
    ocl.oc_form_dirty = False
    tab.show_trash_chk.setChecked(True)
    assert not tab._dirty and not ocl.oc_form_dirty      # toggling is not an edit
    assert _row_names(tab) == ["One", "leg", "Two"]
    assert not tab.models_table.item(2, 0).flags() & app.Qt.ItemIsEditable
    assert not tab.models_table.cellWidget(2, 4).isEnabled()
    data = {}
    tab.collect(data)
    assert [p["id"] for p in data["providerProfiles"]] == ["p1"]
    assert data["providerProfiles"][0]["model"] == "m1-unsaved"

    tab.show_trash_chk.setChecked(False)
    assert _row_names(tab) == ["One", "leg"]
    assert tab.models_table.item(0, 3).text() == "m1-unsaved"


def test_openclaude_restore_then_save_prunes_trash(ocl, tmp_path):
    tab = _models_tab(ocl)
    tab.models_table.selectRow(1)
    tab._remove_model_row()
    tab.show_trash_chk.setChecked(True)
    tab.models_table.selectRow(2)
    tab._restore_trash_rows()
    assert _row_names(tab) == ["One", "leg", "Two"]
    assert "p2" in _global_trash(ocl)                    # kept until a successful save
    ocl._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    assert [p["id"] for p in saved["providerProfiles"]] == ["p1", "p2"]
    assert saved["providerProfiles"][1] == GLOBAL["providerProfiles"][1]
    assert _global_trash(ocl) == {}


def test_openclaude_save_global_prunes_present_profiles(tmp_path):
    cf = app.LayeredConfigFile(tmp_path / "proj", config_dir=tmp_path / "cfghome")
    store = app.ProviderTrashStore()
    for key in ("p1", "agentModels:leg", "gone"):
        store.put(cf.global_file, key, {"name": key})
    ok, msg = cf.save_global({"providerProfiles": [{"id": "p1", "name": "One"}, "junk"],
                              "agentModels": {"leg": {}}})
    assert ok, msg
    assert store.entries(cf.global_file) == {"gone": {"name": "gone"}}


def test_openclaude_removing_all_profiles_clears_active_id(ocl, tmp_path):
    tab = _models_tab(ocl)
    _select_rows(tab, [0, 1])
    tab._remove_model_row()
    assert _row_names(tab) == ["leg"]
    ocl._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    assert saved["providerProfiles"] == []
    assert "activeProviderProfileId" not in saved        # no dangling id
    assert set(_global_trash(ocl)) == {"p1", "p2"}


def test_openclaude_legacy_agent_model_remove_restore_roundtrip(ocl, tmp_path):
    tab = _models_tab(ocl)
    tab.models_table.selectRow(2)
    tab._remove_model_row()
    assert set(_global_trash(ocl)) == {"agentModels:leg"}
    tab.show_trash_chk.setChecked(True)
    tab.models_table.selectRow(2)
    tab._restore_trash_rows()
    ocl._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    assert saved["agentModels"] == GLOBAL["agentModels"]
    assert _global_trash(ocl) == {}


def test_openclaude_profile_without_id_gets_stable_trash_key(ocl, tmp_path):
    tab = _models_tab(ocl)
    tab._add_model_row({"name": "New", "model": "m-new"})
    tab.models_table.selectRow(3)
    tab._remove_model_row()
    (key, entry), = _global_trash(ocl).items()
    assert key.startswith("provider_") and entry["id"] == key
    tab.show_trash_chk.setChecked(True)
    tab.models_table.selectRow(3)
    tab._restore_trash_rows()
    ocl._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    assert {"id": key, "name": "New", "model": "m-new"} in saved["providerProfiles"]
    assert _global_trash(ocl) == {}
