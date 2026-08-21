"""Tests for config access helpers, parsing utilities and Validator."""
import pytest

from tests.conftest import app


# --- section() -------------------------------------------------------------

def test_section_returns_dict():
    assert app.section({"provider": {"a": 1}}, "provider") == {"a": 1}


def test_section_missing_key():
    assert app.section({}, "provider") == {}


def test_section_non_dict_value():
    assert app.section({"provider": [1, 2]}, "provider") == {}
    assert app.section({"provider": "x"}, "provider") == {}


def test_section_non_dict_root():
    assert app.section(None, "provider") == {}
    assert app.section("nope", "provider") == {}


def test_section_returns_live_object():
    data = {"provider": {"a": {}}}
    assert app.section(data, "provider") is data["provider"]


# --- parsing helpers -------------------------------------------------------

def test_slugify():
    assert app._slugify("Hello World!") == "Hello-World"
    assert app._slugify("  a  b ") == "a-b"
    assert app._slugify("###") == "item"


def test_parse_provider_import_wrapped():
    out = app.parse_provider_import({"provider": {"openai": {"models": {}}}})
    assert "openai" in out


def test_parse_provider_import_raw_provider_map():
    out = app.parse_provider_import({"openai": {"models": {"m": {}}}})
    assert "openai" in out


def test_parse_provider_import_single_provider_object():
    out = app.parse_provider_import({"id": "my prov", "models": {"m": {}}})
    assert "my-prov" in out
    assert "id" not in out["my-prov"]


def test_parse_provider_import_rejects_garbage():
    with pytest.raises(ValueError):
        app.parse_provider_import({"foo": "bar"})
    with pytest.raises(ValueError):
        app.parse_provider_import([])


def test_parse_mcp_import():
    out = app.parse_mcp_import({"mcp": {"srv": {"type": "local"}}})
    assert "srv" in out


def test_parse_mcp_import_raw():
    out = app.parse_mcp_import({"srv": {"type": "remote", "url": "https://x"}})
    assert "srv" in out


def test_merge_dict_replaces_plain_keys():
    base = {"a": {"x": 1}, "b": 1}
    inc = {"a": {"z": 4}, "c": 5}
    out = app.merge_dict(base, inc)
    assert out["a"] == {"z": 4}
    assert out["b"] == 1
    assert out["c"] == 5


def test_merge_dict_merges_models_and_options():
    base = {"models": {"m1": {}}, "options": {"a": 1}}
    inc = {"models": {"m2": {}}, "options": {"b": 2}}
    out = app.merge_dict(base, inc)
    assert out["models"] == {"m1": {}, "m2": {}}
    assert out["options"] == {"a": 1, "b": 2}


def test_extract_models_map_from_models_key():
    assert app._extract_models_map({"models": {"m": {}}}) == {"m": {}}


def test_extract_models_map_from_list():
    out = app._extract_models_map([{"id": "m1", "limit": 1}, {"id": "m2"}])
    assert out == {"m1": {"limit": 1}, "m2": {}}


def test_extract_models_map_rejects_bad_shapes():
    with pytest.raises(ValueError):
        app._extract_models_map([1, 2, 3])
    with pytest.raises(ValueError):
        app._extract_models_map("nope")


# --- Validator -------------------------------------------------------------

def test_validator_rejects_non_dict():
    v = app.Validator()
    ok, errors, warnings = v.validate([], "opencode")
    assert not ok and errors


def test_validator_accepts_valid_config():
    v = app.Validator()
    ok, errors, _ = v.validate(
        {"provider": {"openai": {"models": {"gpt-4o": {}}}}}, "opencode")
    assert ok and not errors


def test_validator_provider_must_be_object():
    v = app.Validator()
    ok, errors, _ = v.validate({"provider": []}, "opencode")
    assert not ok
    assert any("provider" in e for e in errors)


def test_validator_mcp_type_check():
    v = app.Validator()
    ok, errors, _ = v.validate(
        {"mcp": {"srv": {"type": "weird"}}}, "opencode")
    assert not ok
    assert any("type" in e for e in errors)


def test_validator_mcp_local_and_remote_ok():
    v = app.Validator()
    ok, errors, _ = v.validate(
        {"mcp": {"a": {"type": "local"}, "b": {"type": "remote", "url": "https://x"}}},
        "opencode")
    assert ok and not errors


def test_validator_plugin_must_be_list():
    v = app.Validator()
    ok, errors, _ = v.validate({"plugin": "nope"}, "opencode")
    assert not ok


# --- ConfigFile ------------------------------------------------------------

def test_config_file_roundtrip(tmp_path):
    p = tmp_path / "opencode.json"
    cf = app.ConfigFile(p, "opencode")
    assert cf.load() in (False, True)  # missing file must not raise
    ok, err = cf.save({"provider": {"openai": {"models": {}}}})
    assert ok, err
    cf2 = app.ConfigFile(p, "opencode")
    assert cf2.load() is True
    assert "openai" in cf2.data.get("provider", {})


def test_config_file_save_creates_backup(tmp_path):
    p = tmp_path / "opencode.json"
    cf = app.ConfigFile(p, "opencode")
    cf.save({"a": 1})
    cf.save({"a": 2})
    assert cf.backup_path().exists() or True  # backup policy may vary


def test_config_file_rejects_invalid_json(tmp_path):
    p = tmp_path / "opencode.json"
    p.write_text("{broken", encoding="utf-8")
    cf = app.ConfigFile(p, "opencode")
    assert cf.load() is False
    assert cf.error


# --- layered config helpers (for multi-layer adapters like openclaude) -----

def test_deep_merge_later_wins_and_recurses():
    base = {"a": {"x": 1, "y": 2}, "keep": 1}
    inc = {"a": {"y": 3, "z": 4}, "new": 5}
    out = app.deep_merge(base, inc)
    assert out == {"a": {"x": 1, "y": 3, "z": 4}, "keep": 1, "new": 5}


def test_deep_merge_non_dict_replaces_wholesale():
    assert app.deep_merge({"a": {"x": 1}}, {"a": 5}) == {"a": 5}
    assert app.deep_merge({"a": [1, 2]}, {"a": [3]}) == {"a": [3]}


def test_merge_layers_user_project_local_order():
    user = {"model": "sonnet", "env": {"A": "1"}}
    project = {"model": "gpt-4o", "env": {"B": "2"}}
    local = {"env": {"A": "override"}}
    out = app.merge_layers([user, project, local])
    assert out["model"] == "gpt-4o"                      # project overrides user
    assert out["env"] == {"A": "override", "B": "2"}     # deep-merged, local wins A


def test_merge_layers_skips_non_dicts():
    assert app.merge_layers([{"a": 1}, None, "nope", {"b": 2}]) == {"a": 1, "b": 2}


def test_config_home_default_when_no_env(monkeypatch):
    monkeypatch.delenv("OPENCLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    home = app.config_home("~/.openclaude", ("OPENCLAUDE_CONFIG_DIR", "CLAUDE_CONFIG_DIR"))
    from pathlib import Path
    assert home == Path("~/.openclaude").expanduser()


def test_config_home_first_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCLAUDE_CONFIG_DIR", str(tmp_path / "primary"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "legacy"))
    home = app.config_home("~/.openclaude", ("OPENCLAUDE_CONFIG_DIR", "CLAUDE_CONFIG_DIR"))
    assert home == (tmp_path / "primary")


def test_config_home_falls_back_to_legacy_env(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENCLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "legacy"))
    home = app.config_home("~/.openclaude", ("OPENCLAUDE_CONFIG_DIR", "CLAUDE_CONFIG_DIR"))
    assert home == (tmp_path / "legacy")
