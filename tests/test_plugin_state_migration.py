"""F2: migration of the v4.4.0 ~/.cache plugin-state files into ~/.config."""
import json

from tests.conftest import app


def _legacy(tmp_path, name, payload):
    d = tmp_path / ".cache" / app.APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(payload, encoding="utf-8")
    return p


def _fake_home(monkeypatch, tmp_path):
    monkeypatch.setattr(app.Path, "home", classmethod(lambda cls: tmp_path))


def test_legacy_cache_state_is_merged_and_renamed(tmp_path, monkeypatch):
    _fake_home(monkeypatch, tmp_path)
    new_path = tmp_path / ".config" / app.APP_NAME / "plugin-state.json"
    new_path.parent.mkdir(parents=True)
    new_path.write_text(json.dumps({"/cfg": {"fresh": "fresh"}}), encoding="utf-8")

    cfg_a, cfg_b = "/cfg", "/other"
    legacy = _legacy(tmp_path, "plugin-state.json", json.dumps({
        cfg_a: {"stale": ["stale", {"opt": 1}]},
        cfg_b: {"only-here": "only-here"},
    }))

    app._merge_legacy_plugin_state(new_path, "plugin-state.json")

    merged = json.loads(new_path.read_text())
    # New store wins for keys it already has; legacy-only keys are folded in.
    assert merged[cfg_a]["fresh"] == "fresh"
    assert merged[cfg_a]["stale"] == ["stale", {"opt": 1}]
    assert merged[cfg_b] == {"only-here": "only-here"}
    # Legacy file renamed, never deleted.
    assert not legacy.exists()
    assert legacy.with_name(legacy.name + ".migrated").exists()


def test_first_upgrade_migrates_when_new_store_is_absent(tmp_path, monkeypatch):
    _fake_home(monkeypatch, tmp_path)
    new_path = tmp_path / ".config" / app.APP_NAME / "plugin-state.json"
    legacy = _legacy(tmp_path, "plugin-state.json",
                     json.dumps({"/cfg": {"disabled": "disabled"}}))

    app._merge_legacy_plugin_state(new_path, "plugin-state.json")

    assert json.loads(new_path.read_text()) == {"/cfg": {"disabled": "disabled"}}
    assert not legacy.exists()
    assert legacy.with_name(legacy.name + ".migrated").exists()


def test_migration_is_idempotent(tmp_path, monkeypatch):
    _fake_home(monkeypatch, tmp_path)
    new_path = tmp_path / ".config" / app.APP_NAME / "tui-plugin-state.json"
    new_path.parent.mkdir(parents=True)
    new_path.write_text("{}", encoding="utf-8")
    legacy = _legacy(tmp_path, "tui-plugin-state.json", json.dumps({"/tui": {"p": "p"}}))

    app._merge_legacy_plugin_state(new_path, "tui-plugin-state.json")
    app._merge_legacy_plugin_state(new_path, "tui-plugin-state.json")

    assert json.loads(new_path.read_text()) == {"/tui": {"p": "p"}}
    assert legacy.with_name(legacy.name + ".migrated").exists()


def test_migration_survives_corrupt_legacy_file(tmp_path, monkeypatch):
    _fake_home(monkeypatch, tmp_path)
    new_path = tmp_path / ".config" / app.APP_NAME / "plugin-state.json"
    new_path.parent.mkdir(parents=True)
    new_path.write_text(json.dumps({"/cfg": {"keep": "keep"}}), encoding="utf-8")
    legacy = _legacy(tmp_path, "plugin-state.json", "{not json")

    app._merge_legacy_plugin_state(new_path, "plugin-state.json")

    # Store untouched and the legacy file still there for manual recovery.
    assert json.loads(new_path.read_text()) == {"/cfg": {"keep": "keep"}}
    assert legacy.exists()
