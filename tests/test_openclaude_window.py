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
    assert [oc_win.tabs.tabText(i) for i in range(oc_win.tabs.count())] == [
        "Settings", "Agent Models", "MCP", "Plugins", "Hooks",
        "Permissions", "Env & Limits", "Raw (per layer)"]
    assert oc_win.oc_layered is not None       # initial_load hook ran
    assert oc_win.oc_layer == "project"


def test_openclaude_agent_models_save_with_masked_key(oc_win, tmp_path):
    models_tab = oc_win._agent_tabs[1]
    models_tab._add_model_row({"name": "gpt", "provider": "openai",
                               "baseUrl": "https://api.openai.com/v1", "model": "gpt-4o",
                               "apiKey": "sk-secret-123"})
    models_tab._add_route_row("build", "gpt")
    models_tab.fallback_edit.setText("gpt, backup")
    oc_win._save()

    # Providers are written to the global ~/.openclaude.json as providerProfiles
    # (here config dir is tmp/cfghome, so its sibling file is tmp/cfghome.json).
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    prof = next(p for p in saved["providerProfiles"] if p["name"] == "gpt")
    assert prof == {"id": prof["id"], "name": "gpt", "provider": "openai",
                    "baseUrl": "https://api.openai.com/v1", "model": "gpt-4o",
                    "apiKey": "sk-secret-123"}
    assert prof["id"].startswith("provider_")     # id auto-assigned for new profiles
    assert saved["agentRouting"] == {"build": "gpt"}
    assert saved["providerFallbackChain"] == ["gpt", "backup"]


def test_openclaude_provider_profile_unknown_fields_preserved(oc_win, tmp_path):
    """Existing fields like authHeader/authScheme must survive load -> save."""
    models_tab = oc_win._agent_tabs[1]
    models_tab._add_model_row({"id": "provider_abc123", "name": "Gcli",
                               "provider": "custom",
                               "baseUrl": "https://gcli.example/v1beta",
                               "model": "gemini-3-flash-preview",
                               "apiKey": "kkk", "authHeader": "X-Goog-Api-Key",
                               "authScheme": "raw"})
    models_tab._cell(0, 3)  # touch nothing; just save
    oc_win._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    prof = next(p for p in saved["providerProfiles"] if p["name"] == "Gcli")
    assert prof["id"] == "provider_abc123"        # original id kept, not regenerated
    assert prof["authHeader"] == "X-Goog-Api-Key"
    assert prof["authScheme"] == "raw"
    # editing a field works
    assert prof["baseUrl"] == "https://gcli.example/v1beta"


def test_openclaude_global_providers_separate_from_settings_layer(oc_win, tmp_path):
    """providerProfiles go to the global file; scalar settings go to the layer."""
    oc_win._agent_settings_tab.model_edit.setText("sonnet")
    oc_win._agent_models_tab._add_model_row({"name": "z", "provider": "custom",
                                             "baseUrl": "https://api.z.ai/v1",
                                             "model": "glm-5.2", "apiKey": "zk"})
    oc_win._save()

    layer = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    glob = json.loads((tmp_path / "cfghome.json").read_text())
    assert layer["model"] == "sonnet"
    assert "providerProfiles" not in layer        # providers NOT in the settings layer
    names = [p["name"] for p in glob.get("providerProfiles", [])]
    assert "z" in names                           # providers in the global file
    assert "model" not in glob                    # scalar setting NOT in global


def test_openclaude_api_key_field_is_masked(oc_win):
    models_tab = oc_win._agent_tabs[1]
    models_tab._add_model_row({"name": "k", "baseUrl": "u", "model": "m",
                               "apiKey": "sk-topsecret"})
    widget = models_tab.models_table.cellWidget(0, 4)
    assert widget.is_secret                       # masked by MaskedLineEdit
    assert widget.value() == "sk-topsecret"       # real value still retrievable
    assert "sk-topsecret" not in widget.edit.text()  # display is masked


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


# --- regressions from the user-review pass ---

def _seed_global(tmp_path, data):
    (tmp_path / "cfghome").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cfghome.json").write_text(json.dumps(data), encoding="utf-8")


def test_untouched_global_not_rewritten_on_settings_save(oc_win, tmp_path):
    """Saving only the Settings tab must not touch the global file (app-state
    keys like numStartups/tipsHistory must be left byte-for-byte alone)."""
    gpath = tmp_path / "cfghome.json"
    gpath.write_text(json.dumps({"numStartups": 112, "tipsHistory": {"x": 1}}), encoding="utf-8")
    before = gpath.read_text(encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.refresh_tabs()
    oc_win._agent_settings_tab.model_edit.setText("sonnet")
    oc_win._save()
    assert gpath.read_text(encoding="utf-8") == before   # global untouched


def test_provider_profiles_non_dict_entries_preserved(oc_win, tmp_path):
    gpath = tmp_path / "cfghome.json"
    gpath.write_text(json.dumps({"providerProfiles": [
        {"id": "provider_ok", "name": "Good", "model": "m"},
        "weird-string-entry",
        123,
    ]}), encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.refresh_tabs()
    oc_win._agent_models_tab._dirty = True   # force a global write
    oc_win._save()
    saved = json.loads(gpath.read_text())
    assert "weird-string-entry" in saved["providerProfiles"]
    assert 123 in saved["providerProfiles"]
    assert any(isinstance(p, dict) and p["name"] == "Good" for p in saved["providerProfiles"])


def test_settings_layer_preserves_unmanaged_keys(oc_win, tmp_path):
    """env/permissions/hooks in a settings layer survive a Settings-tab save
    even though no form field edits them."""
    proj = tmp_path / "proj" / ".openclaude"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "settings.json").write_text(json.dumps({
        "env": {"A": "1"}, "permissions": {"edit": "allow"}, "model": "old",
    }), encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.refresh_tabs()
    oc_win._agent_settings_tab.model_edit.setText("new-model")
    oc_win._save()
    saved = json.loads((proj / "settings.json").read_text())
    assert saved["model"] == "new-model"
    assert saved["env"] == {"A": "1"}
    assert saved["permissions"] == {"edit": "allow"}


def test_effort_level_not_baked_from_inherited(oc_win, tmp_path):
    """A layer without effortLevel must not gain it from the effective merge."""
    cfg = tmp_path / "cfghome"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "settings.json").write_text(json.dumps({"effortLevel": "high"}), encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.oc_layer = "project"
    oc_win.refresh_tabs()
    oc_win._agent_settings_tab.model_edit.setText("x")  # edit something else
    oc_win._save()
    proj = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert "effortLevel" not in proj      # inherited 'high' NOT written to project


def test_active_provider_profile_roundtrip(oc_win, tmp_path):
    """The Active provider picker reads/writes activeProviderProfileId without
    clobbering the profiles list."""
    gpath = tmp_path / "cfghome.json"
    gpath.write_text(json.dumps({
        "activeProviderProfileId": "p2",
        "providerProfiles": [
            {"id": "p1", "name": "First", "model": "m1"},
            {"id": "p2", "name": "Second", "model": "m2"},
        ],
    }), encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.refresh_tabs()
    tab = oc_win._agent_models_tab
    assert tab.active_combo.currentData() == "p2"       # loaded correctly
    tab.active_combo.setCurrentIndex(tab.active_combo.findData("p1"))
    oc_win._save()
    saved = json.loads(gpath.read_text())
    assert saved["activeProviderProfileId"] == "p1"
    assert len(saved["providerProfiles"]) == 2


def test_settings_statusline_roundtrip(oc_win, tmp_path):
    st = oc_win._agent_settings_tab
    st.statusline_chk.setChecked(True)
    st.statusline_cmd.setText("echo hi")
    oc_win._save()
    proj = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert proj["statusLine"] == {"type": "command", "command": "echo hi"}
    # boolean form (no command)
    st.statusline_cmd.setText("")
    oc_win._save()
    proj = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert proj["statusLine"] is True
    # disabling removes the key that was previously present
    st.statusline_chk.setChecked(False)
    oc_win._save()
    proj = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert "statusLine" not in proj


def test_settings_skip_permission_roundtrip(oc_win, tmp_path):
    st = oc_win._agent_settings_tab
    st.skip_dangerous_chk.setChecked(True)
    oc_win._save()
    proj = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert proj["skipDangerousModePermissionPrompt"] is True
    # unchecking a pre-existing key writes false (not leaving it true)
    st.skip_dangerous_chk.setChecked(False)
    oc_win._save()
    proj = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert proj["skipDangerousModePermissionPrompt"] is False


def test_mcp_tab_user_scope_roundtrip(oc_win, tmp_path):
    """user-scope MCP servers go to the global ~/.openclaude.json."""
    tab = oc_win._agent_mcp_tab
    assert tab.scope_combo.currentData() == "user"
    tab._add_row("srv1", {"type": "stdio", "command": "npx -y srv", "env": {"A": "1"}})
    oc_win._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    assert saved["mcpServers"] == {"srv1": {"type": "stdio", "command": "npx -y srv",
                                            "env": {"A": "1"}}}


def test_mcp_tab_project_scope_writes_mcpjson(oc_win, tmp_path):
    """project-scope edits write <proj>/.mcp.json, not the global file."""
    tab = oc_win._agent_mcp_tab
    tab._on_scope_change()  # no-op safety; switch explicitly:
    idx = tab.scope_combo.findData("project")
    tab.scope_combo.setCurrentIndex(idx)
    tab._shown_scope = "project"
    tab._add_row("psrv", {"type": "http", "url": "https://mcp.example/v1"})
    oc_win._save()
    mcp = json.loads((tmp_path / "proj" / ".mcp.json").read_text())
    assert mcp == {"mcpServers": {"psrv": {"type": "http", "url": "https://mcp.example/v1"}}}
    gpath = tmp_path / "cfghome.json"
    if gpath.exists():      # project edits alone must not create/rewrite global
        assert "mcpServers" not in json.loads(gpath.read_text())


def test_mcp_tab_local_scope_keeps_project_state(oc_win, tmp_path):
    """local-scope MCP goes to projects[file dict].mcpServers and preserves
    sibling project state like hasTrustDialogAccepted + app-state keys."""
    key = str((tmp_path / "proj").resolve()).replace("\\", "/")
    (tmp_path / "cfghome.json").write_text(json.dumps({
        "numStartups": 9,
        "projects": {key: {"hasTrustDialogAccepted": True}},
    }), encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.refresh_tabs()
    tab = oc_win._agent_mcp_tab
    idx = tab.scope_combo.findData("local")
    tab.scope_combo.setCurrentIndex(idx)
    tab._shown_scope = "local"
    tab._add_row("lsrv", {"command": "run-me"})
    oc_win._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    assert saved["numStartups"] == 9
    entry = saved["projects"][key]
    assert entry["hasTrustDialogAccepted"] is True
    # the table infers an explicit stdio transport when none was given
    assert entry["mcpServers"] == {"lsrv": {"type": "stdio", "command": "run-me"}}


def test_mcp_tab_managed_policy_displayed_readonly(oc_win, tmp_path):
    """managed-mcp.json servers are shown as a read-only policy hint."""
    mdir = tmp_path / "managed"
    mdir.mkdir(parents=True)
    (mdir / "managed-mcp.json").write_text(
        json.dumps({"mcpServers": {"locked": {"command": "x"}}}), encoding="utf-8")
    cf = app.LayeredConfigFile(tmp_path / "proj", config_dir=tmp_path / "cfghome",
                               managed_dir=mdir)
    cf.load()
    monkey = oc_win.oc_layered
    oc_win.oc_layered = cf  # swap in the layered model with the policy layer
    try:
        oc_win.refresh_tabs()
        label = oc_win._agent_mcp_tab.managed_label.text()
        assert "locked" in label and "read-only" in label
    finally:
        oc_win.oc_layered = monkey


def test_plugins_tab_roundtrip(oc_win, tmp_path):
    """enabledPlugins/extraKnownMarketplaces round-trip into the layer."""
    plugins_tab = oc_win._agent_plugins_tab
    # enabledPlugins row: bool value
    plugins_tab.plugins_table.setRowCount(0)
    r = plugins_tab.plugins_table.rowCount()
    plugins_tab._add_plugin_row("formatter@claude-plugins-official")
    plugins_tab.plugins_table.item(r, 1).setText("true")
    # marketplace row: github source with ref + autoUpdate
    plugins_tab.market_table.setRowCount(0)
    plugins_tab._add_market_row("team-market", {
        "source": {"source": "github", "repo": "acme/plugins"},
        "autoUpdate": True,
    })
    mr = plugins_tab.market_table.rowCount() - 1
    plugins_tab.market_table.item(mr, 3).setText("v1.2.0")
    oc_win._save()
    layer = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert layer["enabledPlugins"] == {"formatter@claude-plugins-official": True}
    mk = layer["extraKnownMarketplaces"]["team-market"]
    assert mk["source"]["source"] == "github"
    assert mk["source"]["repo"] == "acme/plugins"
    assert mk["source"]["ref"] == "v1.2.0"
    assert mk["autoUpdate"] is True


def test_plugins_tab_marketplace_value_field_mapping(oc_win, tmp_path):
    """url/file/directory/npm sources map to the right schema field."""
    plugins_tab = oc_win._agent_plugins_tab
    plugins_tab.market_table.setRowCount(0)
    plugins_tab._add_market_row("u", {"source": {"source": "url", "url": "https://x/market.json"}})
    oc_win._save()
    layer = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    src = layer["extraKnownMarketplaces"]["u"]["source"]
    assert src == {"source": "url", "url": "https://x/market.json"}


def test_settings_tab_mcp_gating_roundtrip(oc_win, tmp_path):
    st = oc_win._agent_settings_tab
    st.enable_all_mcp_chk.setChecked(True)
    st.enabled_mcpjson_edit.setText("a, b")
    oc_win._save()
    layer = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert layer["enableAllProjectMcpServers"] is True
    assert layer["enabledMcpjsonServers"] == ["a", "b"]


def test_mcp_header_secret_is_masked_and_roundtrips(oc_win, tmp_path):
    """Headers/env often carry API keys: display must be masked while the real
    value still saves verbatim."""
    tab = oc_win._agent_mcp_tab
    secret = "ctx7sk-supersecret-1234"
    tab._add_row("context7", {"type": "http", "url": "https://mcp.context7.com/mcp",
                              "headers": {"CONTEXT7_API_KEY": secret}})
    w = tab.mcp_table.cellWidget(0, 5)
    assert secret not in w.edit.text()          # masked on screen
    assert w.value() == "CONTEXT7_API_KEY=" + secret
    oc_win._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    assert saved["mcpServers"]["context7"]["headers"] == {"CONTEXT7_API_KEY": secret}


def test_mcp_project_scope_preserves_args_and_extras(oc_win, tmp_path):
    """Real-world shape: stdio server with args, plus non-mcpServers top-level
    keys in .mcp.json (allowedTools, mcpContextUris) must survive a save."""
    (tmp_path / "proj").mkdir(parents=True, exist_ok=True)
    (tmp_path / "proj" / ".mcp.json").write_text(json.dumps({
        "allowedTools": [],
        "mcpContextUris": [],
        "mcpServers": {
            "pandalight": {"type": "stdio",
                           "command": "/opt/lightpanda",
                           "args": ["mcp"],
                           "env": {}},
        },
    }), encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.refresh_tabs()
    tab = oc_win._agent_mcp_tab
    idx = tab.scope_combo.findData("project")
    tab.scope_combo.setCurrentIndex(idx)
    tab._shown_scope = "project"
    # touch nothing — just save; fidelity must be byte-equal for untouched rows
    oc_win._save()
    saved = json.loads((tmp_path / "proj" / ".mcp.json").read_text())
    assert saved["allowedTools"] == []
    assert saved["mcpContextUris"] == []
    srv = saved["mcpServers"]["pandalight"]
    assert srv == {"type": "stdio", "command": "/opt/lightpanda",
                   "args": ["mcp"], "env": {}}


def test_mcp_args_editable(oc_win, tmp_path):
    """args column: new servers get typed args; loaded servers keep theirs
    verbatim until the cell is edited."""
    tab = oc_win._agent_mcp_tab
    # 1) typing args on a fresh row
    tab._add_row("pandalight", {"command": "/opt/lightpanda"})
    r = tab.mcp_table.rowCount() - 1
    tab.mcp_table.item(r, 3).setText("mcp, --port 8945")
    oc_win._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    assert saved["mcpServers"]["pandalight"]["args"] == ["mcp", "--port 8945"]
    assert "env" not in saved["mcpServers"]["pandalight"]

    # 2) loaded server with args: untouched cell keeps original verbatim
    (tmp_path / "proj" / ".openclaude" / "settings.json").write_text("{}", encoding="utf-8")
    gpath = tmp_path / "cfghome.json"
    gpath.write_text(json.dumps({"mcpServers": {
        "keep": {"type": "stdio", "command": "x", "args": ["--flag", "a,b"]}}}),
        encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.refresh_tabs()
    oc_win._save()
    kept = json.loads(gpath.read_text())["mcpServers"]["keep"]
    assert kept["args"] == ["--flag", "a,b"]     # comma inside arg survives

    # 3) editing args rewrites them
    row = next(r2 for r2 in range(tab.mcp_table.rowCount())
               if tab.mcp_table.item(r2, 0).text() == "keep")
    tab.mcp_table.item(row, 3).setText("--other")
    oc_win._save()
    edited = json.loads(gpath.read_text())["mcpServers"]["keep"]
    assert edited["args"] == ["--other"]


def test_mcp_viewing_scopes_does_not_create_files(oc_win, tmp_path):
    """Merely switching scopes must not mark them dirty: a save right after
    browsing must not conjure .mcp.json or touch an absent global file."""
    tab = oc_win._agent_mcp_tab
    for scope in ("project", "local", "user"):
        idx = tab.scope_combo.findData(scope)
        tab.scope_combo.setCurrentIndex(idx)
        tab._shown_scope = scope
    oc_win._save()
    assert not (tmp_path / "proj" / ".mcp.json").exists()


HOOKS_SAMPLE = {
    "SessionStart": [
        {"hooks": [{"type": "command",
                    "command": "/opt/token.py"}]},
        {"matcher": "*",
         "hooks": [{"type": "command", "command": "/bin/orca-hook.sh",
                    "timeout": 10, "asynchronous": True}]},
    ],
    "PreToolUse": [
        {"matcher": "Bash",
         "hooks": [{"type": "command", "command": "guard.sh", "timeout": 5}]},
    ],
    "Stop": [
        {"hooks": [{"type": "command", "command": "/opt/token.py"}]},
    ],
}


def _seed_user_layer(oc_win, tmp_path, extra=None):
    cfg = tmp_path / "cfghome"
    cfg.mkdir(parents=True, exist_ok=True)
    data = {"model": "claude-opus-4.8", "hooks": json.loads(json.dumps(HOOKS_SAMPLE))}
    if extra:
        data.update(extra)
    (cfg / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.oc_layer = "user"
    oc_win.refresh_tabs()
    return json.loads((cfg / "settings.json").read_text())


def _save_user_layer(oc_win, tmp_path):
    oc_win._save()
    return json.loads((tmp_path / "cfghome" / "settings.json").read_text())


def test_hooks_tab_untouched_roundtrip_verbatim(oc_win, tmp_path):
    """Loading a realistic hooks config and saving without edits must keep
    hooks byte-identical (unknown entry keys like `asynchronous` survive)."""
    before = _seed_user_layer(oc_win, tmp_path)
    after = _save_user_layer(oc_win, tmp_path)
    assert after["hooks"] == before["hooks"]
    assert after["model"] == "claude-opus-4.8"


def test_hooks_tab_rows_loaded(oc_win, tmp_path):
    _seed_user_layer(oc_win, tmp_path)
    tab = oc_win._agent_hooks_tab
    rows = [(tab._cell(r, 0), tab._cell(r, 1), tab._cell(r, 2),
             tab._cell(r, 4)) for r in range(tab.hooks_table.rowCount())]
    assert rows == [
        ("SessionStart", "", "command", ""),
        ("SessionStart", "*", "command", "10"),
        ("PreToolUse", "Bash", "command", "5"),
        ("Stop", "", "command", ""),
    ]


def test_hooks_tab_edit_patches_only_touched(oc_win, tmp_path):
    """Editing one entry's command must not disturb sibling entries/events."""
    _seed_user_layer(oc_win, tmp_path)
    tab = oc_win._agent_hooks_tab
    row = next(r for r in range(tab.hooks_table.rowCount())
               if tab._cell(r, 0) == "Stop")
    tab.hooks_table.item(row, 3).setText("/new/hook.py")
    after = _save_user_layer(oc_win, tmp_path)
    assert after["hooks"]["Stop"] == [
        {"hooks": [{"type": "command", "command": "/new/hook.py"}]}]
    # untouched events byte-identical to the sample
    assert after["hooks"]["SessionStart"] == HOOKS_SAMPLE["SessionStart"]
    assert after["hooks"]["PreToolUse"] == HOOKS_SAMPLE["PreToolUse"]


def test_hooks_tab_timeout_edit(oc_win, tmp_path):
    _seed_user_layer(oc_win, tmp_path)
    tab = oc_win._agent_hooks_tab
    row = next(r for r in range(tab.hooks_table.rowCount())
               if tab._cell(r, 0) == "PreToolUse")
    tab.hooks_table.item(row, 4).setText("30")
    after = _save_user_layer(oc_win, tmp_path)
    grp = after["hooks"]["PreToolUse"][0]
    assert grp["matcher"] == "Bash"
    assert grp["hooks"][0]["timeout"] == 30
    assert grp["hooks"][0]["command"] == "guard.sh"     # untouched field kept


def test_hooks_tab_add_and_delete(oc_win, tmp_path):
    _seed_user_layer(oc_win, tmp_path)
    tab = oc_win._agent_hooks_tab
    # add a hook under a NEW event
    tab._add_row("Notification", "*", "command", "notify.sh", "15")
    after = _save_user_layer(oc_win, tmp_path)
    assert after["hooks"]["Notification"] == [
        {"matcher": "*", "hooks": [{"type": "command", "command": "notify.sh",
                                    "timeout": 15}]}]
    # delete the PreToolUse entry -> event dropped entirely
    row = next(r for r in range(tab.hooks_table.rowCount())
               if tab._cell(r, 0) == "PreToolUse")
    tab.hooks_table.selectRow(row)
    tab._remove_hook_row()
    after = _save_user_layer(oc_win, tmp_path)
    assert "PreToolUse" not in after["hooks"]
    assert "SessionStart" in after["hooks"]


def test_hooks_tab_no_hooks_section_stays_absent(oc_win, tmp_path):
    """A layer without hooks gains no empty hooks key from a casual visit."""
    st = oc_win._agent_settings_tab
    st.model_edit.setText("sonnet")     # unrelated edit on project layer
    oc_win._save()
    proj = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert "hooks" not in proj


def test_hooks_tab_layer_switcher_reveals_user_hooks(oc_win, tmp_path):
    """Hooks live in the USER layer; the tab must default to the project view
    with an empty table plus a hint, and reveal rows after switching layers."""
    _seed_user_layer(oc_win, tmp_path)          # seeds cfghome/settings.json (user)
    oc_win.oc_layered.load()
    oc_win.oc_layer = "project"                 # fresh-launch default
    oc_win.refresh_tabs()
    tab = oc_win._agent_hooks_tab
    assert tab.hooks_table.rowCount() == 0      # nothing in project layer
    assert "user (" in tab.empty_hint.text()    # hint points at the user layer
    # switching the combo must load the user-layer hooks
    idx = tab.layer_combo.findData("user")
    tab.layer_combo.setCurrentIndex(idx)
    assert oc_win.oc_layer == "user"
    assert tab.hooks_table.rowCount() == 4
    assert tab.empty_hint.text() == ""


def test_plugins_tab_layer_hint(oc_win, tmp_path):
    cfg = tmp_path / "cfghome"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "settings.json").write_text(json.dumps(
        {"enabledPlugins": {"fmt@official": True}}), encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.oc_layer = "project"
    oc_win.refresh_tabs()
    tab = oc_win._agent_plugins_tab
    assert tab.plugins_table.rowCount() == 0
    assert "user (plugins)" in tab.empty_hint.text()


def test_hooks_new_row_under_existing_event_survives(oc_win, tmp_path):
    """Fresh rows (no gi/ei) must not collide or vanish (id-based slotting)."""
    _seed_user_layer(oc_win, tmp_path)
    tab = oc_win._agent_hooks_tab
    tab._add_row("Stop", "*", "command", "a.sh", "5")
    tab._add_row("Stop", "", "command", "b.sh", "")
    after = _save_user_layer(oc_win, tmp_path)
    stop = after["hooks"]["Stop"]
    assert stop[0] == HOOKS_SAMPLE["Stop"][0]            # original group intact
    assert {"matcher": "*", "hooks": [{"type": "command", "command": "a.sh",
                                       "timeout": 5}]} in stop
    assert {"hooks": [{"type": "command", "command": "b.sh"}]} in stop


def test_hooks_replace_all_entries_with_new(oc_win, tmp_path):
    """Deleting every original entry of an event then adding a fresh one must
    keep the event (pending placement happens before the empty-slot bail)."""
    _seed_user_layer(oc_win, tmp_path)
    tab = oc_win._agent_hooks_tab
    for r in range(tab.hooks_table.rowCount() - 1, -1, -1):
        if tab._cell(r, 0) == "SessionStart":
            tab.hooks_table.selectRow(r)
            tab._remove_hook_row()
    tab._add_row("SessionStart", "", "command", "/new-start.sh", "")
    after = _save_user_layer(oc_win, tmp_path)
    assert after["hooks"]["SessionStart"] == [
        {"hooks": [{"type": "command", "command": "/new-start.sh"}]}]
    assert after["hooks"]["Stop"] == HOOKS_SAMPLE["Stop"]


def test_masked_env_cell_typed_input_kept_and_dirty(oc_win, tmp_path):
    """Typing into a masked env cell (never revealed) must keep the typed text
    and mark the scope dirty so the global file actually gets written."""
    tab = oc_win._agent_mcp_tab
    tab._add_row("srv", {"command": "x"})
    w = tab.mcp_table.cellWidget(0, 4)
    w.edit.setText("API_KEY=typed-not-revealed")
    oc_win._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    assert saved["mcpServers"]["srv"]["env"] == {"API_KEY": "typed-not-revealed"}


def test_legacy_agent_models_no_camelcase_mirrors(oc_win, tmp_path):
    models_tab = oc_win._agent_models_tab
    # mimic how refresh() materializes a legacy agentModels row: snake keys in
    # the stash, camelCase values in the visible cells
    models_tab._add_model_row({"name": "leg", "_legacy_agentModels": True,
                               "base_url": "https://l.example/v1",
                               "api_key": "kkk", "model": "m1",
                               "provider": "",
                               "baseUrl": "https://l.example/v1",
                               "apiKey": "kkk"})
    oc_win._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    spec = saved["agentModels"]["leg"]
    assert spec == {"base_url": "https://l.example/v1", "api_key": "kkk",
                    "model": "m1"}


def test_effort_level_exotic_value_roundtrips(oc_win, tmp_path):
    st = oc_win._agent_settings_tab
    st.effort_combo.blockSignals(True)
    st.effort_combo.addItem("(current) turbo", "turbo")
    st.effort_combo.setCurrentIndex(st.effort_combo.count() - 1)
    st.effort_combo.blockSignals(False)
    oc_win._save()
    proj = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert proj["effortLevel"] == "turbo"


def test_marketplace_unknown_source_type_verbatim(oc_win, tmp_path):
    """A marketplace source type we don't model must not be coerced to github."""
    cfg = tmp_path / "cfghome"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "settings.json").write_text(json.dumps(
        {"extraKnownMarketplaces": {
            "weird": {"source": {"source": "settings", "name": "weird"}}}}),
        encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.oc_layer = "user"
    oc_win.refresh_tabs()
    oc_win._save()
    saved = json.loads((cfg / "settings.json").read_text())
    assert saved["extraKnownMarketplaces"]["weird"] == \
        {"source": {"source": "settings", "name": "weird"}}


def test_corrupt_layer_json_blocks_form_save(oc_win, tmp_path, monkeypatch):
    """A layer that fails to parse must never be overwritten by the form path."""
    cfg = tmp_path / "proj" / ".openclaude"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "settings.json").write_text("{not json!!", encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.oc_layer = "project"
    oc_win.refresh_tabs()
    oc_win._agent_settings_tab.model_edit.setText("should-not-persist")
    oc_win._save()
    assert (cfg / "settings.json").read_text() == "{not json!!"


def test_layer_switch_prompts_before_discarding(oc_win, tmp_path, monkeypatch):
    """Switching edit layers with unsaved form edits must ask first."""
    answers = []
    monkeypatch.setattr(app, "_confirm_unsaved",
                        lambda win, action="": answers.append(action) or "cancel")
    st = oc_win._agent_settings_tab
    st.model_edit.setText("unsaved-model")           # marks oc_form_dirty
    assert oc_win.oc_form_dirty is True
    hooks_tab = oc_win._agent_hooks_tab
    idx = hooks_tab.layer_combo.findData("user")
    hooks_tab.layer_combo.setCurrentIndex(idx)       # triggers prompt
    assert answers and "user" in answers[-1]
    assert oc_win.oc_layer == "project"              # cancelled -> unchanged
    assert st.model_edit.text() == "unsaved-model"   # edits preserved

    # discard path: layer switches and flag clears via refresh
    monkeypatch.setattr(app, "_confirm_unsaved",
                        lambda win, action="": "discard")
    hooks_tab.layer_combo.setCurrentIndex(idx)
    assert oc_win.oc_layer == "user"

    # save-first path persists the pending edit to the ORIGINAL layer
    monkeypatch.setattr(app, "_confirm_unsaved",
                        lambda win, action="": "save")
    oc_win.oc_layered.load()
    oc_win.oc_layer = "project"
    oc_win.refresh_tabs()
    oc_win._agent_settings_tab.model_edit.setText("saved-on-switch")
    plugins_tab = oc_win._agent_plugins_tab
    idx_p = plugins_tab.layer_combo.findData("user")
    plugins_tab.layer_combo.setCurrentIndex(idx_p)
    layer = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert layer["model"] == "saved-on-switch"


def test_permissions_tab_roundtrip(oc_win, tmp_path):
    cfg = tmp_path / "cfghome"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "settings.json").write_text(json.dumps({"permissions": {
        "allow": ["Bash(ls)", "Read"],
        "deny": ["Bash(rm -rf /)"],
        "defaultMode": "acceptEdits",
        "additionalDirectories": ["~/projects"],
        "someFutureKey": {"keep": True},
    }}), encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.oc_layer = "user"
    oc_win.refresh_tabs()
    tab = oc_win._agent_perms_tab
    assert tab.editors["allow"].toPlainText() == "Bash(ls)\nRead"
    assert tab.mode_combo.currentData() == "acceptEdits"

    tab.editors["ask"].setPlainText("WebFetch(domain:example.com)")
    tab.no_bypass_chk.setChecked(True)
    oc_win._save()
    perms = json.loads((cfg / "settings.json").read_text())["permissions"]
    assert perms["ask"] == ["WebFetch(domain:example.com)"]
    assert perms["allow"] == ["Bash(ls)", "Read"]
    assert perms["disableBypassPermissionsMode"] is True
    assert perms["someFutureKey"] == {"keep": True}


def test_permissions_tab_absent_stays_absent(oc_win, tmp_path):
    oc_win._agent_settings_tab.model_edit.setText("sonnet")
    oc_win._save()
    proj = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert "permissions" not in proj


def test_env_and_model_limits_roundtrip(oc_win, tmp_path):
    cfg = tmp_path / "cfghome"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "settings.json").write_text(json.dumps({
        "env": {"ANTHROPIC_API_KEY": "sk-secret-env"},
        "modelLimits": {
            "假流式-gemini-2.5-pro-search": {"contextWindow": 1048576,
                                             "maxOutputTokens": 65536,
                                             "vendorNote": "keep me"},
        },
    }), encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.oc_layer = "user"
    oc_win.refresh_tabs()
    tab = oc_win._agent_envlim_tab

    w = tab.env_table.cellWidget(0, 1)
    assert "sk-secret-env" not in w.edit.text()      # masked on screen
    assert w.value() == "sk-secret-env"
    assert tab.cell_text(tab.limits_table, 0, 1) == "1048576"

    tab._add_env_row("OPENAI_BASE_URL", "https://api.example/v1")
    tab.limits_table.item(0, 0).setText("假流式-gemini-2.5-pro-search")
    tab._add_limit_row("new-model", {})
    r = tab.limits_table.rowCount() - 1
    tab.limits_table.item(r, 1).setText("200000")
    tab.limits_table.item(r, 2).setText("8192")
    oc_win._save()

    saved = json.loads((cfg / "settings.json").read_text())
    assert saved["env"] == {"ANTHROPIC_API_KEY": "sk-secret-env",
                            "OPENAI_BASE_URL": "https://api.example/v1"}
    cjk = saved["modelLimits"]["假流式-gemini-2.5-pro-search"]
    assert cjk["contextWindow"] == 1048576
    assert cjk["vendorNote"] == "keep me"
    assert saved["modelLimits"]["new-model"] == {"contextWindow": 200000,
                                                 "maxOutputTokens": 8192}


def test_duplicate_provider_name_warns(oc_win, tmp_path):
    tab = oc_win._agent_models_tab
    tab._add_model_row({"name": "dup", "model": "m1"})
    tab._add_model_row({"name": "dup", "model": "m2"})
    oc_win._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    names = [p["name"] for p in saved["providerProfiles"]]
    assert names == ["dup"]                       # first row wins
    assert "duplicate provider name" in oc_win.status_bar.currentMessage().lower()


def test_raw_pending_edits_warned_on_form_save(oc_win, tmp_path):
    raw = oc_win._agent_raw_tab
    raw.editor.setPlainText('{"model": "typed-in-raw"}')   # marks _modified
    oc_win.tabs.setCurrentIndex(0)                          # form tab active
    oc_win._agent_settings_tab.model_edit.setText("from-form")
    oc_win._save()
    assert "Raw edits" in oc_win.status_bar.currentMessage()
    layer = json.loads((tmp_path / "proj" / ".openclaude" / "settings.json").read_text())
    assert layer["model"] == "from-form"


def test_raw_tab_reports_json_errors_and_warnings(oc_win, tmp_path):
    raw = oc_win._agent_raw_tab
    raw.editor.setPlainText("{broken")
    raw._validate()
    assert raw.status_label.text().startswith("JSON error:")

    raw.editor.setPlainText('{"model": "opus", "totallyMadeUp": 1}')
    raw._validate()
    assert "totallyMadeUp" in raw.status_label.text()

    raw.editor.setPlainText('{"hooks": []}')
    raw._validate()
    assert raw.status_label.text().startswith("error:")

    raw.editor.setPlainText('{"model": "opus"}')
    raw._validate()
    assert raw.status_label.text() == "Valid JSON"


# --- MaskedLineEdit.textChanged relay (arg-less signal fed by a str signal) ---

def test_masked_line_edit_relays_text_changed(qapp):
    """QLineEdit.textChanged carries a str; MaskedLineEdit.textChanged is
    declared arg-less. Connecting emit directly made PySide6 raise
    'textChanged() only accepts 0 argument(s), 1 given!' and swallow the
    signal, so downstream dirty-tracking never fired."""
    w = app.MaskedLineEdit("sk-old", field_name="apiKey")
    fired = []
    w.textChanged.connect(lambda: fired.append(1))
    w.edit.setText("sk-new")
    assert fired, "downstream slot never ran — textChanged was swallowed"
    assert w.value() == "sk-new"


def test_provider_apikey_edit_marks_dirty_and_saves(oc_win, tmp_path):
    """Updating ONLY a provider's apiKey must flip the Agent Models dirty flag,
    otherwise the save hook skips the global rewrite and the new key is lost."""
    gpath = tmp_path / "cfghome.json"
    gpath.write_text(json.dumps({"providerProfiles": [
        {"id": "provider_aaa", "name": "myprov", "provider": "custom",
         "baseUrl": "https://x/v1", "model": "m1", "apiKey": "sk-OLDKEY"}]}),
        encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.refresh_tabs()

    tab = oc_win._agent_models_tab
    assert tab._dirty is False                     # loading is not an edit
    widget = tab.models_table.cellWidget(0, 4)
    widget.edit.setText("sk-NEWKEY")               # user types a new key

    assert tab._dirty is True                      # gates the global write
    assert oc_win.oc_form_dirty is True            # gates the layer-switch prompt
    oc_win._save()
    saved = json.loads(gpath.read_text())
    assert saved["providerProfiles"][0]["apiKey"] == "sk-NEWKEY"


def test_masked_env_cell_edit_marks_scope_dirty(oc_win, tmp_path):
    """Editing an MCP env/headers cell must mark its scope dirty on its own."""
    gpath = tmp_path / "cfghome.json"
    gpath.write_text(json.dumps({"mcpServers": {
        "srv": {"command": "node", "env": {"TOKEN": "old"}}}}), encoding="utf-8")
    oc_win.oc_layered.load()
    oc_win.refresh_tabs()

    tab = oc_win._agent_mcp_tab
    assert tab.global_dirty() is False
    tab.mcp_table.cellWidget(0, 4).edit.setText("TOKEN=new")
    assert tab.global_dirty() is True
    oc_win._save()
    saved = json.loads(gpath.read_text())
    assert saved["mcpServers"]["srv"]["env"] == {"TOKEN": "new"}



def test_form_save_asks_before_stripping_comments(oc_win, tmp_path, monkeypatch):
    """F4: saving a settings layer that had comments must confirm first."""
    settings = tmp_path / "cfghome" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    original = '{\n  // my note\n  "model": "opus"\n}\n'
    settings.write_text(original, encoding="utf-8")

    oc_win.oc_layer = "user"
    oc_win.oc_layered.load()
    oc_win.refresh_tabs()

    asked = []

    def _decline(win, path):
        asked.append(str(path))
        return False

    monkeypatch.setattr(app, "_confirm_strip_comments", _decline)
    oc_win._save()

    assert asked == [str(settings)]
    # Declined -> the commented file is untouched.
    assert settings.read_text(encoding="utf-8") == original

    # Accepting does save (and does strip, as the dialog warned).
    monkeypatch.setattr(app, "_confirm_strip_comments", lambda w, p: True)
    oc_win._save()
    assert json.loads(settings.read_text(encoding="utf-8")) == {"model": "opus"}
    assert "//" not in settings.read_text(encoding="utf-8")
