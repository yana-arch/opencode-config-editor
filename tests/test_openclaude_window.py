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
    assert oc_win.tabs.count() == 3            # Settings + Agent Models + Raw
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


def test_mcp_servers_roundtrip_preserves_keys(oc_win, tmp_path):
    tab = oc_win._agent_models_tab
    tab._add_mcp_row(
        {"name": "fs", "type": "command",
         "command": "npx -y @modelcontextprotocol/server-filesystem /tmp",
         "env": {"X": "1"}},
        name="fs",
    )
    oc_win._save()
    saved = json.loads((tmp_path / "cfghome.json").read_text())
    srv = saved["mcpServers"]["fs"]
    assert srv["command"] == "npx -y @modelcontextprotocol/server-filesystem /tmp"
    assert srv["type"] == "command"
    assert srv["env"] == {"X": "1"}     # unknown sub-key preserved
