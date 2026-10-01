"""Regressions in MainWindow itself: the Tools-menu MCP hub, the Raw-vs-form
tab sync, the custom-catalog manager guard, health-check config_path plumbing
and the fetched-provider baseURL policy.

Each test locks a behaviour a user would otherwise lose silently: an overwrite
that silently replaces an existing server, a raw-only key dropped by a later
form edit, a catalog reloaded on every menu visit, a {file:key.txt} reference
resolved against the wrong directory, or a listing URL persisted as if it were
an API base.
"""
import copy
import json

import pytest

from tests.conftest import HAS_QT, app

pytestmark = pytest.mark.skipif(not HAS_QT, reason="PySide6 not available")


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SETTINGS_FILE", tmp_path / "settings.ini")
    w = app.MainWindow(tmp_path)
    yield w
    w.dirty_oc = False
    w.dirty_tui = False
    w.close()


@pytest.fixture
def oc_win(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SETTINGS_FILE", tmp_path / "settings.ini")
    monkeypatch.setenv("OPENCLAUDE_CONFIG_DIR", str(tmp_path / "cfghome"))
    w = app.MainWindow(tmp_path / "proj", adapter=app.get_adapter("openclaude"))
    yield w
    w.close()


@pytest.fixture
def quiet(monkeypatch):
    """No modal popups: every dialog reports the given answers."""
    monkeypatch.setattr(app.QMessageBox, "information",
                        staticmethod(lambda *a, **k: app.QMessageBox.Ok))
    monkeypatch.setattr(app.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: app.QMessageBox.Ok))


def _hub(monkeypatch, key, cfg, accept=True):
    """Make the hub dialog 'install' `key`; return the target_modes seen."""
    seen = []

    def exec_(self):
        seen.append(self.target_mode)
        if not accept:
            return app.QDialog.Rejected
        self.result_server_key = key
        self.result_server_config = cfg
        return app.QDialog.Accepted

    monkeypatch.setattr(app.MCPTemplateHubDialog, "exec", exec_)
    return seen


def _answer(monkeypatch, answer):
    """QMessageBox.question (the _confirm helper) returns Yes or No."""
    def question(*a, **k):
        return (app.QMessageBox.Yes if answer else app.QMessageBox.No)
    monkeypatch.setattr(app.QMessageBox, "question", staticmethod(question))


# --- F3: the Tools-menu hub asks before replacing an existing server ---------

def test_menu_mcp_hub_prompts_before_overwriting(win, monkeypatch, quiet):
    win.cfg_oc.data = {"mcp": {"github": {"type": "local", "command": ["docker"]}}}
    win.refresh_tabs()
    _hub(monkeypatch, "github", {"type": "local", "command": ["npx", "new"]})
    asked = []
    _answer(monkeypatch, False)
    monkeypatch.setattr(app.QMessageBox, "question",
                        staticmethod(lambda *a, **k: (asked.append(a[1:3]),
                                                      app.QMessageBox.No)[1]))

    win._show_mcp_hub()

    assert asked, "the hub must ask before replacing an existing server"
    assert ("Overwrite Server", "Server 'github' already exists. Overwrite?") == asked[0]
    assert win.cfg_oc.data["mcp"]["github"] == {"type": "local", "command": ["docker"]}




def test_menu_mcp_hub_accept_installs_and_undo_restores(win, monkeypatch, quiet):
    win.cfg_oc.data = {"mcp": {"github": {"type": "local", "command": ["docker"]}}}
    win.refresh_tabs()
    _hub(monkeypatch, "github", {"type": "local", "command": ["npx", "new"]})
    _answer(monkeypatch, True)

    win._show_mcp_hub()
    assert win.cfg_oc.data["mcp"]["github"] == {"type": "local", "command": ["npx", "new"]}

    win.tabs.setCurrentIndex(0)          # never the tui tab: undo hits opencode
    win._undo()
    assert win.cfg_oc.data["mcp"]["github"] == {"type": "local", "command": ["docker"]}


# --- F4: the same menu entry installs into the openclaude MCP tab -----------

def test_menu_mcp_hub_installs_into_openclaude_tab(oc_win, monkeypatch, quiet):
    seen = _hub(monkeypatch, "ctx7", {"type": "stdio", "command": "npx ctx7"})

    oc_win._show_mcp_hub()

    assert seen == ["openclaude"]
    assert "ctx7" in oc_win._agent_mcp_tab._collect_scope_table()
    # and nowhere in the opencode tab, which this adapter has not built
    assert getattr(oc_win, "tab_mcp", None) is None


# --- CAT-06: a loaded catalog is not thrown away by the manager dialog ------

def test_manage_custom_catalog_keeps_loaded_catalog(win, monkeypatch, quiet, tmp_path):
    cat = tmp_path / "cat.json"
    cat.write_text(json.dumps(
        {"anthropic": {"id": "anthropic", "models": {
            "claude-x": {"id": "anthropic/claude-x", "name": "Claude X"}}}}),
        encoding="utf-8")
    win.model_catalog.load(cat)
    assert win.model_catalog.loaded()

    calls = {"ensure": 0, "exec": 0}

    def fake_exec(self):
        calls["exec"] += 1
        return app.QDialog.Accepted

    monkeypatch.setattr(app.CustomCatalogManagerDialog, "exec", fake_exec)
    monkeypatch.setattr(win, "_ensure_catalog",
                        lambda: (calls.__setitem__("ensure", calls["ensure"] + 1), True)[1])

    win._manage_custom_catalog()

    assert calls["exec"] == 1
    assert calls["ensure"] == 0, "an already-loaded catalog must not be reloaded"
    assert win.model_catalog.loaded()
    assert "anthropic" in win.model_catalog.by_provider


# --- OC-08: Raw edits and form edits both survive a save -------------------

OC_BASE = {
    "$schema": "https://opencode.ai/config.json",
    "provider": {"acme": {"npm": "@ai-sdk/openai-compatible", "name": "Acme",
                          "options": {"baseURL": "https://a/v1", "apiKey": "sk-A"}}},
    "agent": {"existing": {"description": "d", "model": "m"}},
    "plugin": ["p1"],
    "customRawKey": {"deep": [1, 2, 3]},
}


def _oc_win(win, data=None):
    win.cfg_oc.data = copy.deepcopy(data if data is not None else OC_BASE)
    win.refresh_tabs()
    return win


def _tab_index(win, widget):
    for i in range(win.tabs.count()):
        if win.tabs.widget(i) is widget:
            return i
    raise AssertionError("tab not found")


def _goto(win, widget):
    win.tabs.setCurrentIndex(_tab_index(win, widget))


def test_raw_only_key_survives_collect(win):
    """A key no form tab owns must not vanish when the Raw text is saved."""
    _oc_win(win)
    _goto(win, win.tab_raw)
    win.tab_raw.editor.setPlainText(json.dumps(
        {**OC_BASE, "customRawKey": {"deep": [9]}}, indent=2))
    win.tab_raw._modified = True
    _goto(win, win.tab_agents)          # leaving Raw folds the text in

    data = win._collect_oc()

    assert data["customRawKey"] == {"deep": [9]}
    assert data["provider"]["acme"]["options"]["apiKey"] == "sk-A"
    assert data["plugin"] == ["p1"]


def test_raw_edit_then_form_edit_both_survive(win):
    """Neither editor may overwrite the other on the way to the save."""
    _oc_win(win)
    _goto(win, win.tab_raw)
    win.tab_raw.editor.setPlainText(json.dumps(
        {**OC_BASE, "agent": {"existing": {"description": "d", "model": "m"},
                              "raw-agent": {"description": "from raw"}},
         "customRawKey": {"deep": [42]}}, indent=2))
    win.tab_raw._modified = True
    _goto(win, win.tab_agents)

    assert win.tab_agents._agents()["raw-agent"]["description"] == "from raw"

    win.cfg_oc.data["agent"]["form-agent"] = {"description": "from form", "model": "m"}
    win.tab_agents.refresh()

    data = win._collect_oc()

    assert data["customRawKey"] == {"deep": [42]}
    assert data["agent"]["raw-agent"]["description"] == "from raw"
    assert "form-agent" in data["agent"]
    assert "existing" in data["agent"]


def test_form_edit_then_raw_edit_both_survive(win):
    """The Raw editor must show the form edit, not a stale document."""
    _oc_win(win)
    win.cfg_oc.data.setdefault("agent", {})["only-form"] = {"description": "d"}
    win.tab_agents.refresh()
    _goto(win, win.tab_raw)
    raw_text = win.tab_raw.editor.toPlainText()
    assert '"only-form"' in raw_text

    win.tab_raw.editor.setPlainText(raw_text.replace('"only-form"', '"only-form-edited"'))
    win.tab_raw._modified = True

    data = win._collect_oc()

    assert "only-form-edited" in data["agent"]
    assert "only-form" not in data["agent"]
    assert data["customRawKey"] == OC_BASE["customRawKey"]


def test_invalid_raw_json_keeps_previous_data(win):
    """Unparseable raw text must not blank the config on the next save."""
    _oc_win(win)
    _goto(win, win.tab_raw)
    win.tab_raw.editor.setPlainText("{ not json")
    win.tab_raw._modified = True
    _goto(win, win.tab_agents)

    data = win._collect_oc()

    assert data["provider"]["acme"]["options"]["apiKey"] == "sk-A"
    assert data["customRawKey"] == OC_BASE["customRawKey"]


# --- health check: {file:key.txt} resolves next to the edited config --------



@pytest.fixture
def cfg_on_disk(tmp_path):
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps(
        {"provider": {"acme": {"options": {"apiKey": "{file:key.txt}"}}}}), encoding="utf-8")
    (tmp_path / "key.txt").write_text("sk-from-file", encoding="utf-8")
    return path




def test_menu_health_check_uses_config_path(win, cfg_on_disk, quiet, monkeypatch):
    seen = []
    real = app.ProviderHealthCheckDialog

    class Capturing(real):
        def __init__(self, parent=None, providers=None, auto_run=False, config_path=None):
            seen.append((providers, config_path))
            super().__init__(parent, providers=providers, auto_run=False,
                             config_path=config_path)

        def exec(self):
            return app.QDialog.Rejected

    monkeypatch.setattr(app, "ProviderHealthCheckDialog", Capturing)

    win.cfg_oc.path = cfg_on_disk
    win.cfg_oc.load()
    win.refresh_tabs()
    win._show_health_check()

    providers, config_path = seen[-1]
    assert config_path == str(cfg_on_disk)
    assert "acme" in providers
    # the reference the dialog would ping now resolves next to the config file
    assert app.resolve_config_placeholders(
        providers["acme"]["options"]["apiKey"],
        config_dir=cfg_on_disk.parent) == "sk-from-file"


def test_providers_tab_health_check_uses_config_path(win, cfg_on_disk, quiet,
                                                      monkeypatch):
    seen = []
    real = app.ProviderHealthCheckDialog

    class Capturing(real):
        def __init__(self, parent=None, providers=None, auto_run=False, config_path=None):
            seen.append((providers, config_path))
            super().__init__(parent, providers=providers, auto_run=False,
                             config_path=config_path)

        def exec(self):
            return app.QDialog.Rejected

    monkeypatch.setattr(app, "ProviderHealthCheckDialog", Capturing)

    win.cfg_oc.path = cfg_on_disk
    win.cfg_oc.load()
    win.refresh_tabs()
    win.tab_providers._health_check_providers()

    assert seen[-1][1] == str(cfg_on_disk)


# --- fetched provider: a listing URL is not an API base ---------------------

def _prepare_fetch(win, monkeypatch, url, fmt):
    """Stub the fetch dialog so the models are already 'fetched'."""
    monkeypatch.setattr(win.model_catalog, "loaded", lambda: False)

    def exec_(self):
        self.fetched_models = {"m1": {"id": "m1"}}
        self._populate(self.fetched_models)
        return app.QDialog.Accepted

    monkeypatch.setattr(app.FetchProviderModelsDialog, "exec", exec_)

    real_init = app.FetchProviderModelsDialog.__init__

    def init(self, *a, **k):
        real_init(self, *a, **k)
        self.url_edit.setText(url)
        self.format_combo.setCurrentIndex(self.format_combo.findData(fmt))
        self.key_edit.setText("newprov")
        self.apikey_edit.setText("")
        self.save_apikey_check.setChecked(False)
        self.sync_check.setChecked(False)

    monkeypatch.setattr(app.FetchProviderModelsDialog, "__init__", init)


def test_fetch_new_provider_stores_no_base_url_for_catalog_format(win, monkeypatch, quiet):
    """models.dev is a listing URL: persisting it as options.baseURL breaks
    every later request, so nothing is written for list/catalog formats."""
    win.cfg_oc.data = {}
    win.refresh_tabs()
    _prepare_fetch(win, monkeypatch, "https://models.dev/api.json", "models_dev")

    win.tab_providers._fetch_new_provider()

    prov = win.cfg_oc.data["provider"]["newprov"]
    assert prov["models"] == {"m1": {"id": "m1"}}
    assert not prov.get("options", {}).get("baseURL")


def test_fetch_new_provider_keeps_base_url_for_api_format(win, monkeypatch, quiet):
    win.cfg_oc.data = {}
    win.refresh_tabs()
    _prepare_fetch(win, monkeypatch, "https://api.example.com/v1", "openai")

    win.tab_providers._fetch_new_provider()

    prov = win.cfg_oc.data["provider"]["newprov"]
    assert prov["options"]["baseURL"] == "https://api.example.com/v1"
