"""Tests for the opencode MCP tab and its headers dialog.

No network and no real user files: the fake app keeps everything in memory.
"""
import pytest

from conftest import app

pytestmark = pytest.mark.skipif(not app.HAS_QT, reason="PySide6 not available")


class FakeCatalog:
    def loaded(self):
        return False


class FakeApp:
    """Minimal stand-in for the main window (cfg.data + dirty tracking)."""

    def __init__(self, mcp=None):
        self.cfg = type("C", (), {"data": {"mcp": mcp or {}, "provider": {}}})()
        self.model_catalog = FakeCatalog()
        self.dirty = False
        self.snapshots = 0

    def mark_dirty(self):
        self.dirty = True

    def snapshot_state(self):
        self.snapshots += 1


@pytest.fixture
def mcp_tab(qapp):
    """Factory: build an McpTab over the given mcp dict."""
    made = []

    def build(mcp):
        a = FakeApp(mcp)
        tab = app.McpTab(a)
        tab.refresh()
        made.append((tab, a))
        return tab, a

    yield build
    for tab, _a in made:
        tab.deleteLater()


def _rows(tab):
    return [tab.table.item(r, 1).text() for r in range(tab.table.rowCount())]


def _row_of(tab, name):
    for r in range(tab.table.rowCount()):
        if tab.table.item(r, 1).text() == name:
            return r
    raise AssertionError(f"{name} not in {_rows(tab)}")


# ---------------------------------------------------------------------------
# F1: in-place cell edits must persist
# ---------------------------------------------------------------------------

def test_collect_persists_remote_url_edit(mcp_tab):
    tab, fake = mcp_tab({
        "remote-a": {"type": "remote", "url": "https://old.example/mcp",
                     "headers": {"A": "b"}, "oauth": {"x": 1}, "timeout": 5},
    })
    r = _row_of(tab, "remote-a")
    tab.table.item(r, 3).setText("https://NEW.example/mcp")
    tab.collect(fake.cfg.data)
    assert fake.cfg.data["mcp"]["remote-a"]["url"] == "https://NEW.example/mcp"
    assert fake.dirty is True


def test_collect_persists_local_command_edit(mcp_tab):
    tab, fake = mcp_tab({
        "local-b": {"type": "local", "command": ["uvx", "srv"],
                    "cwd": "/tmp", "environment": {"A": "B"}},
    })
    r = _row_of(tab, "local-b")
    tab.table.item(r, 3).setText("uvx other-server --flag")
    tab.collect(fake.cfg.data)
    assert fake.cfg.data["mcp"]["local-b"]["command"] == [
        "uvx", "other-server", "--flag"]


def test_collect_round_trips_quoted_argv(mcp_tab):
    """shlex keeps a quoted argument as one argv entry."""
    tab, fake = mcp_tab({
        "local-b": {"type": "local", "command": ["npx", "-y", "pkg"]},
    })
    r = _row_of(tab, "local-b")
    tab.table.item(r, 3).setText("npx -y pkg")
    tab.collect(fake.cfg.data)
    assert fake.cfg.data["mcp"]["local-b"]["command"] == ["npx", "-y", "pkg"]


def test_collect_keeps_unknown_subkeys(mcp_tab):
    tab, fake = mcp_tab({
        "remote-a": {"type": "remote", "url": "https://old/mcp",
                     "headers": {"A": "b"}, "oauth": {"x": 1}, "timeout": 5},
    })
    tab.collect(fake.cfg.data)
    entry = fake.cfg.data["mcp"]["remote-a"]
    assert entry["headers"] == {"A": "b"}
    assert entry["oauth"] == {"x": 1}
    assert entry["timeout"] == 5
    assert fake.dirty is False  # nothing changed


def test_collect_clears_url_when_cell_emptied(mcp_tab):
    tab, fake = mcp_tab({"r": {"type": "remote", "url": "https://x/mcp"}})
    r = _row_of(tab, "r")
    tab.table.item(r, 3).setText("")
    tab.collect(fake.cfg.data)
    assert fake.cfg.data["mcp"]["r"]["url"] == ""


def test_name_and_type_cells_are_read_only(mcp_tab):
    tab, _fake = mcp_tab({"r": {"type": "remote", "url": "https://x/mcp"}})
    r = _row_of(tab, "r")
    assert not (tab.table.item(r, 1).flags() & app.Qt.ItemIsEditable)
    assert not (tab.table.item(r, 2).flags() & app.Qt.ItemIsEditable)


def test_collect_survives_rebuild(mcp_tab):
    """The written-back value is what a later refresh shows."""
    tab, fake = mcp_tab({"r": {"type": "remote", "url": "https://old/mcp"}})
    r = _row_of(tab, "r")
    tab.table.item(r, 3).setText("https://new/mcp")
    tab.collect(fake.cfg.data)
    tab.refresh()
    assert tab.table.item(_row_of(tab, "r"), 3).text() == "https://new/mcp"


# ---------------------------------------------------------------------------
# F12: header values are masked in the UI but round-trip intact
# ---------------------------------------------------------------------------

def test_headers_dialog_masks_value_but_returns_it(qapp):
    dlg = app.MCPHeadersDialog(headers={"Authorization": "Bearer s3cret-value"})
    shown = dlg.table.item(0, 1).text()
    assert "s3cret-value" not in shown
    assert dlg.headers() == {"Authorization": "Bearer s3cret-value"}


def test_headers_dialog_returns_edited_value(qapp):
    dlg = app.MCPHeadersDialog(headers={"Authorization": "Bearer old"})
    dlg.table.item(0, 1).setText("Bearer new")
    assert dlg.headers() == {"Authorization": "Bearer new"}


# ---------------------------------------------------------------------------
# F13: headers only on type=remote entries
# ---------------------------------------------------------------------------

def test_edit_headers_refuses_toggle_entry(monkeypatch, mcp_tab):
    shown = []
    monkeypatch.setattr(
        app.QMessageBox, "information",
        lambda *a, **k: shown.append(a[1] if len(a) > 1 else ""))
    tab, fake = mcp_tab({"tog": {"enabled": False}})
    tab._edit_headers("tog")
    assert fake.cfg.data["mcp"]["tog"] == {"enabled": False}
    assert shown


def test_edit_headers_refuses_local_entry(monkeypatch, mcp_tab):
    monkeypatch.setattr(app.QMessageBox, "information", lambda *a, **k: None)
    tab, fake = mcp_tab({"loc": {"type": "local", "command": ["x"]}})
    tab._edit_headers("loc")
    assert "headers" not in fake.cfg.data["mcp"]["loc"]


# ---------------------------------------------------------------------------
# F14: non-dict entries are skipped
# ---------------------------------------------------------------------------

def test_enable_all_skips_non_dict_entries(mcp_tab):
    tab, fake = mcp_tab({"a": {"enabled": True}, "bad": "oops",
                         "c": {"enabled": True}})
    tab._set_all_enabled(False)
    assert fake.cfg.data["mcp"]["a"]["enabled"] is False
    assert fake.cfg.data["mcp"]["c"]["enabled"] is False
    assert fake.cfg.data["mcp"]["bad"] == "oops"
    assert fake.dirty is True


def test_search_skips_non_dict_entries(mcp_tab):
    """A search term that only occurs *inside* a non-dict entry matches nothing,
    and searching by that entry's name still lists it. The point is that
    _mcp_matches never dereferences a non-dict cfg."""
    tab, _fake = mcp_tab({"a": {"type": "remote", "url": "https://a"},
                          "bad": "oops", "c": {"type": "remote", "url": "https://c"}})

    tab.search_edit.setText("oops")
    assert _rows(tab) == [], "content of a non-dict entry is not searchable"

    tab.search_edit.setText("bad")
    assert _rows(tab) == ["bad"], "a name match still lists the entry"


def test_toggle_enabled_skips_non_dict_entry(mcp_tab):
    tab, fake = mcp_tab({"bad": "oops"})
    tab._toggle_enabled("bad")
    assert fake.cfg.data["mcp"]["bad"] == "oops"
    assert fake.dirty is False


# ---------------------------------------------------------------------------
# F15: the search filter survives a refresh
# ---------------------------------------------------------------------------

def test_filter_stays_applied_after_bulk_action(mcp_tab):
    tab, fake = mcp_tab({
        "github": {"type": "remote", "url": "https://g"},
        "gitlab": {"type": "remote", "url": "https://g"},
        "slack": {"type": "remote", "url": "https://s"},
    })
    tab.search_edit.setText("git")
    assert _rows(tab) == ["github", "gitlab"]
    tab._set_all_enabled(False)
    assert _rows(tab) == ["github", "gitlab"]


def test_refresh_keeps_filter_by_url_match(mcp_tab):
    tab, _fake = mcp_tab({
        "a": {"type": "remote", "url": "https://only-here/mcp"},
        "b": {"type": "remote", "url": "https://other"},
    })
    tab.search_edit.setText("only-here")
    assert _rows(tab) == ["a"]
    tab.refresh()
    assert _rows(tab) == ["a"]


def test_clearing_search_shows_everything(mcp_tab):
    tab, _fake = mcp_tab({"a": {"type": "remote", "url": "https://a"},
                          "b": {"type": "remote", "url": "https://b"}})
    tab.search_edit.setText("a")
    assert _rows(tab) == ["a"]
    tab.search_edit.setText("")
    assert _rows(tab) == ["a", "b"]
