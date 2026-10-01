"""Tests for the openclaude layered config model (no Qt required)."""
import json
from pathlib import Path

from tests.conftest import app


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_layers_merge_user_project_local(tmp_path):
    cfg_dir = tmp_path / "cfghome"
    _write(cfg_dir / "settings.json", {"model": "sonnet", "env": {"A": "1"}})
    proj = tmp_path / "proj"
    _write(proj / ".openclaude" / "settings.json", {"model": "gpt-4o", "env": {"B": "2"}})
    _write(proj / ".openclaude" / "settings.local.json", {"env": {"A": "override"}})

    cf = app.LayeredConfigFile(proj, config_dir=cfg_dir)
    assert cf.load()
    eff = cf.effective()
    assert eff["model"] == "gpt-4o"                       # project overrides user
    assert eff["env"] == {"A": "override", "B": "2"}      # deep-merged, local wins A


def test_missing_files_yield_empty_layers(tmp_path):
    cf = app.LayeredConfigFile(tmp_path / "proj", config_dir=tmp_path / "none")
    assert cf.load()
    assert cf.effective() == {}
    assert cf.layer("user") == {}


def test_corrupt_layer_is_ignored(tmp_path):
    cfg_dir = tmp_path / "cfghome"
    (cfg_dir).mkdir(parents=True)
    (cfg_dir / "settings.json").write_text("{broken", encoding="utf-8")
    cf = app.LayeredConfigFile(tmp_path / "proj", config_dir=cfg_dir)
    assert cf.load()
    assert cf.layer("user") == {}


def test_save_layer_roundtrip(tmp_path):
    cf = app.LayeredConfigFile(tmp_path / "proj", config_dir=tmp_path / "cfghome")
    cf.load()
    ok, msg = cf.save_layer("project", {"model": "haiku"})
    assert ok, msg
    cf2 = app.LayeredConfigFile(tmp_path / "proj", config_dir=tmp_path / "cfghome")
    cf2.load()
    assert cf2.layer("project") == {"model": "haiku"}


def test_successful_save_clears_jsonc_marker(tmp_path):
    cfg_dir = tmp_path / "cfghome"
    path = cfg_dir / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text('{\n  // comment\n  "model": "opus"\n}', encoding="utf-8")
    cf = app.LayeredConfigFile(tmp_path / "proj", config_dir=cfg_dir)
    cf.load()
    assert str(path) in cf.jsonc_files

    ok, msg = cf.save_layer("user", {"model": "opus"})

    assert ok, msg
    assert str(path) not in cf.jsonc_files
    assert "// comment" not in path.read_text(encoding="utf-8")


def test_save_unknown_layer_rejected(tmp_path):
    cf = app.LayeredConfigFile(tmp_path / "proj", config_dir=tmp_path / "cfghome")
    ok, msg = cf.save_layer("bogus", {})
    assert not ok and "Unknown layer" in msg


def test_config_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLAUDE_CONFIG_DIR", str(tmp_path / "envhome"))
    _write(tmp_path / "envhome" / "settings.json", {"model": "from-env"})
    cf = app.LayeredConfigFile(tmp_path / "proj")  # no explicit config_dir
    cf.load()
    assert cf.effective()["model"] == "from-env"


def test_targets_shape(tmp_path):
    targets = app._openclaude_targets(tmp_path / "proj", config_dir=tmp_path / "cfghome")
    kinds = [k for _, _, k in targets]
    assert kinds == ["user", "project", "local", "global", "project-mcp", "managed"]
    from pathlib import Path
    for _label, path, _kind in targets:
        assert isinstance(path, Path)


def test_settings_keys_defined():
    # Verified-real settings keys present.
    assert "model" in app.OPENCLAUDE_SETTINGS_KEYS
    assert "statusLine" in app.OPENCLAUDE_SETTINGS_KEYS
    assert "skipDangerousModePermissionPrompt" in app.OPENCLAUDE_SETTINGS_KEYS
    # Legacy/back-compat key still tolerated.
    assert "agentModels" in app.OPENCLAUDE_SETTINGS_KEYS
    # Global file real user-meaningful keys.
    assert "providerProfiles" in app.OPENCLAUDE_GLOBAL_KEYS
    assert "activeProviderProfileId" in app.OPENCLAUDE_GLOBAL_KEYS
    assert "api_key" in app.OPENCLAUDE_SECRET_FIELDS


def test_settings_keys_defined_extended():
    """Docs-confirmed openclaude keys must be present (regression for the
    earlier 'unverified' misclassification)."""
    for key in ("effortLevel", "smartRouting", "agentModels", "agentRouting",
                "providerFallbackChain", "advisorModel", "subscriptionType",
                "enabledPlugins", "extraKnownMarketplaces", "enableAllProjectMcpServers"):
        assert key in app.OPENCLAUDE_SETTINGS_KEYS
    # Docs: these live in the global ~/.openclaude.json.
    for key in ("theme", "verbose", "autoUpdates", "mcpServers"):
        assert key in app.OPENCLAUDE_GLOBAL_KEYS
    assert app.OPENCLAUDE_SETTINGS_SCHEMA_URL.startswith("https://")


def test_managed_layer_merge(tmp_path):
    """managed-settings.json (+ drop-ins) is read-only and wins over all layers."""
    mdir = tmp_path / "managed"
    mdir.mkdir()
    (mdir / "managed-settings.json").write_text(
        json.dumps({"model": "policy-model", "permissions": {"allow": ["Bash(ls)"]}}),
        encoding="utf-8")
    drop = mdir / "managed-settings.d"
    drop.mkdir()
    (drop / "10-extra.json").write_text(json.dumps({"env": {"B": "2"}}), encoding="utf-8")

    cfg = tmp_path / "cfghome"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "settings.json").write_text(json.dumps({"model": "user-model"}), encoding="utf-8")
    proj = tmp_path / "proj" / ".openclaude"
    proj.mkdir(parents=True)
    (proj / "settings.json").write_text(json.dumps({"model": "proj-model"}), encoding="utf-8")

    cf = app.LayeredConfigFile(tmp_path / "proj", config_dir=cfg, managed_dir=mdir)
    cf.load()
    eff = cf.effective()
    assert eff["model"] == "policy-model"          # policy overrides user layers
    assert eff["env"]["B"] == "2"                  # drop-in merged in
    assert eff["permissions"] == {"allow": ["Bash(ls)"]}
    # layers themselves untouched by managed
    assert cf.layer("project")["model"] == "proj-model"


def test_managed_mcp_and_project_mcp_load(tmp_path):
    mdir = tmp_path / "managed"
    mdir.mkdir(parents=True)
    (mdir / "managed-mcp.json").write_text(
        json.dumps({"mcpServers": {"locked": {"type": "stdio", "command": "x"}}}),
        encoding="utf-8")
    (tmp_path / "proj").mkdir(parents=True)
    (tmp_path / "proj" / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"proj-srv": {"type": "http", "url": "https://x/mcp"}}}),
        encoding="utf-8")

    cf = app.LayeredConfigFile(tmp_path / "proj", config_dir=tmp_path / "cfghome",
                               managed_dir=mdir)
    cf.load()
    assert cf.managed_mcp_servers() == {"locked": {"type": "stdio", "command": "x"}}
    assert cf.project_mcp == {"mcpServers": {"proj-srv": {"type": "http", "url": "https://x/mcp"}}}
    assert str(cf.project_mcp_file).endswith(".mcp.json")
    assert cf.managed_file.parent == mdir


def test_project_key_normalization(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    cf = app.LayeredConfigFile(proj, config_dir=tmp_path / "cfghome")
    assert cf.project_key() == str(proj.resolve()).replace("\\", "/")


def test_local_mcp_scope_roundtrip(tmp_path):
    """Local MCP servers live under global projects[file dict].mcpServers."""
    cfg = tmp_path / "cfghome"
    cfg.mkdir(parents=True)
    gpath = Path(str(cfg) + ".json")
    key = str((tmp_path / "proj").resolve()).replace("\\", "/")
    gpath.write_text(json.dumps({
        "numStartups": 5,
        "projects": {key: {"hasTrustDialogAccepted": True,
                           "mcpServers": {"local1": {"command": "run"}}}},
    }), encoding="utf-8")
    cf = app.LayeredConfigFile(tmp_path / "proj", config_dir=cfg)
    cf.load()
    assert cf.local_mcp() == {"local1": {"command": "run"}}
    # rewrite global preserving app-state + other project keys
    data = dict(cf.global_data)
    entry = dict(data["projects"][key])
    entry.pop("mcpServers")
    data["projects"][key] = entry
    ok, _ = cf.save_global(data)
    assert ok
    saved = json.loads(gpath.read_text())
    assert saved["numStartups"] == 5
    assert saved["projects"][key] == {"hasTrustDialogAccepted": True}


def test_save_project_mcp(tmp_path):
    cf = app.LayeredConfigFile(tmp_path / "proj", config_dir=tmp_path / "cfghome")
    cf.load()
    ok, _ = cf.save_project_mcp({"mcpServers": {"a": {"command": "c"}}})
    assert ok
    saved = json.loads((tmp_path / "proj" / ".mcp.json").read_text())
    assert saved == {"mcpServers": {"a": {"command": "c"}}}


def test_findings_unknown_key_warns_but_does_not_error():
    errors, warnings = app.openclaude_findings(
        {"model": "opus", "totallyMadeUp": 1}, "user")
    assert errors == []
    assert any("totallyMadeUp" in w for w in warnings)


def test_findings_container_shapes_are_errors():
    errors, _ = app.openclaude_findings({
        "hooks": [],
        "permissions": {"allow": "Bash(ls)"},
        "modelLimits": {"m": 5},
        "statusLine": 7,
    }, "project")
    joined = " | ".join(errors)
    assert "'hooks' must be an object." in joined
    assert "permissions.allow must be an array" in joined
    assert "modelLimits['m'] must be an object." in joined
    assert "'statusLine' must be an object or a boolean." in joined


def test_findings_hook_event_must_be_array():
    errors, _ = app.openclaude_findings(
        {"hooks": {"Stop": {"command": "x"}}}, "user")
    assert any("hooks['Stop']" in e for e in errors)


def test_findings_env_non_string_value_warns():
    errors, warnings = app.openclaude_findings({"env": {"PORT": 8080}}, "user")
    assert errors == []
    assert any("env['PORT']" in w for w in warnings)


def test_findings_global_layer_ignores_app_state():
    errors, warnings = app.openclaude_findings({
        "numStartups": 42,
        "tipsHistory": {"a": 1},
        "providerProfiles": [{"id": "p1", "name": "x"}, {"name": "no-id"}],
        "mcpServers": {"ok": {"type": "stdio", "command": "x", "args": ["a"]},
                       "odd": {"type": "grpc"}},
    }, "global")
    assert errors == []
    assert any("providerProfiles[1] has no 'id'" in w for w in warnings)
    assert any("grpc" in w for w in warnings)
    assert not any("numStartups" in w for w in warnings)


def test_findings_global_layer_shape_errors():
    errors, _ = app.openclaude_findings({
        "mcpServers": [], "providerProfiles": {},
    }, "global")
    joined = " | ".join(errors)
    assert "'mcpServers' must be an object." in joined
    assert "'providerProfiles' must be an array." in joined


def test_findings_project_mcp_unknown_key_warns():
    _, warnings = app.openclaude_findings({
        "mcpServers": {}, "allowedTools": [], "somethingElse": True,
    }, "project-mcp")
    assert any("somethingElse" in w for w in warnings)


def test_every_key_the_editor_writes_is_known():
    """The forms must never produce a key their own validator flags."""
    written = {
        "model", "effortLevel", "agent", "advisorModel", "statusLine",
        "enableAllProjectMcpServers", "enabledMcpjsonServers",
        "disabledMcpjsonServers", "skipDangerousModePermissionPrompt",
        "skipFullAccessModePermissionPrompt", "enabledPlugins",
        "extraKnownMarketplaces", "hooks", "permissions", "env", "modelLimits",
        "agentModels", "agentRouting",
    }
    assert written <= app.OPENCLAUDE_SETTINGS_KEYS
    assert {"providerProfiles", "activeProviderProfileId",
            "mcpServers"} <= app.OPENCLAUDE_GLOBAL_KEYS


class _FakeSchemaError:
    def __init__(self, message, path):
        self.message = message
        self.absolute_path = path


class _FakeDraft7Validator:
    def __init__(self, schema):
        self.schema = schema

    def iter_errors(self, data):
        if not isinstance(data.get("model", ""), str):
            yield _FakeSchemaError("5 is not of type 'string'", ["model"])


class _FakeJsonschema:
    Draft7Validator = _FakeDraft7Validator


class _StubValidator:
    """Stands in for core Validator; records what schema was asked for."""

    def __init__(self, schema):
        self._schema = schema
        self.asked = None

    def schema_from(self, url, cache_path, kind):
        self.asked = (url, cache_path, kind)
        return self._schema


def test_findings_reports_schema_warnings(monkeypatch):
    """The jsonschema branch is dead unless the dependency is installed, so
    drive it with a stub to keep it honest."""
    monkeypatch.setattr(app, "jsonschema", _FakeJsonschema, raising=False)
    validator = _StubValidator({"type": "object"})
    errors, warnings = app.openclaude_findings({"model": 5}, "user", validator)
    assert errors == []
    assert any("schema: 5 is not of type 'string'" in w and "path: model" in w
               for w in warnings)
    url, cache_path, kind = validator.asked
    assert url == app.OPENCLAUDE_SCHEMA_URL
    assert cache_path == app.OPENCLAUDE_SCHEMA_CACHE
    assert kind == "openclaude-settings"


def test_findings_survives_broken_schema_validator(monkeypatch):
    class _Boom:
        def __init__(self, schema):
            raise RuntimeError("schema is malformed")

    class _BoomModule:
        Draft7Validator = _Boom

    monkeypatch.setattr(app, "jsonschema", _BoomModule, raising=False)
    errors, warnings = app.openclaude_findings(
        {"model": "opus"}, "user", _StubValidator({"type": "object"}))
    assert errors == []
    assert any("schema error: schema is malformed" in w for w in warnings)


def test_findings_skips_schema_when_shape_already_broken():
    validator = _StubValidator({"type": "object"})
    errors, _ = app.openclaude_findings({"hooks": []}, "user", validator)
    assert errors
    assert validator.asked is None       # no fetch when the file is malformed


def test_schema_source_constants_are_openclaude_specific():
    assert app.OPENCLAUDE_SCHEMA_URL.endswith("claude-code-settings.json")
    assert app.OPENCLAUDE_SCHEMA_CACHE.name == "openclaude-settings-schema.json"
    # Unified config dir used for both
    assert "opencode-config-editor" in str(app.OPENCLAUDE_SCHEMA_CACHE)


def test_schema_from_is_offline_without_jsonschema():
    """No jsonschema -> no network call, just None."""
    if app.HAVE_JSONSCHEMA:
        return
    v = app.Validator()
    assert v.schema_from(app.OPENCLAUDE_SCHEMA_URL,
                         app.OPENCLAUDE_SCHEMA_CACHE, "openclaude-settings") is None
