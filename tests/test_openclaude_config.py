"""Tests for the openclaude layered config model (no Qt required)."""
import json

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
    assert cf2.effective()["model"] == "haiku"


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
    assert kinds == ["user", "project", "local", "global"]
    from pathlib import Path
    for _label, path, _kind in targets:
        assert isinstance(path, Path)


def test_settings_keys_defined():
    assert "agentModels" in app.OPENCLAUDE_SETTINGS_KEYS
    assert "theme" in app.OPENCLAUDE_GLOBAL_KEYS
    assert "api_key" in app.OPENCLAUDE_SECRET_FIELDS
