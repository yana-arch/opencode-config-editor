"""OpenclaudeMcpTab: hub installs, conflict prompting, and URL transports.

Two data-loss/validation shapes are locked here. Installing a template whose
name already exists used to append a row that silently replaced the existing
server (its env, args and headers with it) on the next save. And a server
addressed by a URL - `sse` as well as `http` - was collected back as
`command`, which no openclaude schema member accepts.
"""
import json

import pytest

from tests.conftest import HAS_QT, app

pytestmark = pytest.mark.skipif(not HAS_QT, reason="PySide6 not available")


@pytest.fixture
def oc_win(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SETTINGS_FILE", tmp_path / "settings.ini")
    monkeypatch.setenv("OPENCLAUDE_CONFIG_DIR", str(tmp_path / "cfghome"))
    w = app.MainWindow(tmp_path / "proj", adapter=app.get_adapter("openclaude"))
    yield w
    w.close()


def _hub(monkeypatch, key, cfg):
    def exec_(self):
        self.result_server_key = key
        self.result_server_config = cfg
        return app.QDialog.Accepted

    monkeypatch.setattr(app.MCPTemplateHubDialog, "exec", exec_)


def _answer(monkeypatch, answer):
    def question(*a, **k):
        return app.QMessageBox.Yes if answer else app.QMessageBox.No
    monkeypatch.setattr(app.QMessageBox, "question", staticmethod(question))


# --- F5: the tab's own hub button asks before replacing a server ------------

def test_hub_asks_before_overwriting_existing_server(oc_win, monkeypatch):
    tab = oc_win._agent_mcp_tab
    tab._add_row("github", {"type": "stdio", "command": "docker",
                            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_ORIGINAL"}})
    _hub(monkeypatch, "github", {"type": "stdio", "command": "npx",
                                 "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_NEW"}})
    asked = []
    monkeypatch.setattr(
        app.QMessageBox, "question",
        staticmethod(lambda *a, **k: (asked.append(a[1:3]), app.QMessageBox.No)[1]))

    tab._open_mcp_hub()

    assert ("Overwrite Server", "Server 'github' already exists. Overwrite?") == asked[0]
    assert tab.mcp_table.rowCount() == 1
    assert tab._collect_scope_table()["github"]["env"] == {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_ORIGINAL"}


def test_hub_cancel_keeps_row_count_and_env(oc_win, monkeypatch):
    tab = oc_win._agent_mcp_tab
    tab._add_row("github", {"type": "stdio", "command": "docker",
                            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_ORIGINAL"}})
    _hub(monkeypatch, "github", {"type": "stdio", "command": "npx",
                                 "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_NEW"}})
    _answer(monkeypatch, False)

    tab._open_mcp_hub()

    assert tab.mcp_table.rowCount() == 1
    servers = tab._collect_scope_table()
    assert servers["github"]["command"] == "docker"
    assert servers["github"]["env"] == {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_ORIGINAL"}


def test_hub_accept_overwrites(oc_win, monkeypatch):
    tab = oc_win._agent_mcp_tab
    tab._add_row("github", {"type": "stdio", "command": "docker",
                            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_ORIGINAL"}})
    _hub(monkeypatch, "github", {"type": "stdio", "command": "npx",
                                 "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_NEW"}})
    _answer(monkeypatch, True)

    tab._open_mcp_hub()

    servers = tab._collect_scope_table()
    assert servers["github"]["command"] == "npx"
    assert servers["github"]["env"] == {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_NEW"}


def test_hub_new_name_does_not_prompt(oc_win, monkeypatch):
    tab = oc_win._agent_mcp_tab
    tab._add_row("github", {"type": "stdio", "command": "docker"})
    _hub(monkeypatch, "ctx7", {"type": "stdio", "command": "npx ctx7"})

    def boom(*a, **k):
        raise AssertionError("a new server name must not prompt")

    monkeypatch.setattr(app.QMessageBox, "question", staticmethod(boom))

    tab._open_mcp_hub()

    assert set(tab._collect_scope_table()) == {"github", "ctx7"}


# --- F6: a URL transport round-trips as url, not command -------------------

def test_sse_server_roundtrips_as_url(oc_win, tmp_path):
    tab = oc_win._agent_mcp_tab
    tab._add_row("remote", {"type": "sse", "url": "https://mcp.internal/sse"})

    assert tab._collect_scope_table()["remote"] == {
        "type": "sse", "url": "https://mcp.internal/sse"}

    oc_win._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    assert saved["mcpServers"]["remote"] == {"type": "sse",
                                             "url": "https://mcp.internal/sse"}


def test_sse_transport_offered_in_combo(oc_win):
    tab = oc_win._agent_mcp_tab
    tab._add_row("remote", {"type": "sse", "url": "https://mcp.internal/sse"})
    combo = tab.mcp_table.cellWidget(0, 1)
    assert [combo.itemData(i) for i in range(combo.count())].count("sse") == 1
    assert tab._transport(0) == "sse"


def test_http_and_stdio_transports_unchanged(oc_win):
    tab = oc_win._agent_mcp_tab
    tab._add_row("h", {"type": "http", "url": "https://mcp.example/v1"})
    tab._add_row("s", {"type": "stdio", "command": "npx -y srv", "args": ["a", "b"]})

    servers = tab._collect_scope_table()
    assert servers["h"] == {"type": "http", "url": "https://mcp.example/v1"}
    assert servers["s"] == {"type": "stdio", "command": "npx -y srv", "args": ["a", "b"]}
