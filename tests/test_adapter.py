"""Adapter registry + contract tests.

Every registered AdapterSpec must satisfy a minimal contract so a new agent
CLI cannot be half-implemented. Also covers registry behavior and, when Qt is
available, that the active adapter drives MainWindow's tabs.
"""
import pytest

from tests.conftest import HAS_QT, app


def test_opencode_adapter_registered():
    assert "opencode" in app.list_adapters()
    spec = app.get_adapter("opencode")
    assert spec is not None
    assert spec is app.OPENCODE_ADAPTER


def test_default_adapter_is_first_registered():
    default = app.default_adapter()
    assert default is not None
    assert default.name in app.list_adapters()


def test_get_unknown_adapter_returns_none():
    assert app.get_adapter("does-not-exist") is None


@pytest.mark.parametrize("name", app.list_adapters())
def test_adapter_contract(name):
    """Contract every adapter must uphold."""
    spec = app.get_adapter(name)
    assert isinstance(spec.name, str) and spec.name
    assert isinstance(spec.app_title, str) and spec.app_title
    assert isinstance(spec.kinds, list) and spec.kinds

    # known_keys: each primary kind resolves to a non-empty set
    for kind in spec.kinds:
        keys = spec.known_keys_for(kind)
        assert isinstance(keys, set) and keys, f"{name}: empty known_keys for {kind}"

    # raw_files reference declared kinds
    for label, kind in spec.raw_files:
        assert isinstance(label, str) and label
        assert kind in spec.kinds

    # targets() returns (label, Path, kind) triples with known kinds
    from pathlib import Path
    targets = spec.targets(Path("/tmp/example-project"))
    assert isinstance(targets, list) and targets
    for label, path, kind in targets:
        assert isinstance(label, str) and label
        assert isinstance(path, Path)
        assert kind in spec.kinds

    # callables are wired
    assert callable(spec.targets_fn)
    assert callable(spec.make_tabs_fn)


def test_known_keys_fallback_to_primary_kind():
    spec = app.get_adapter("opencode")
    # an undeclared kind falls back to the primary kind's keys (opencode)
    assert spec.known_keys_for("totally-unknown") == spec.known_keys_for("opencode")


def test_validator_accepts_injected_known_keys():
    v = app.Validator()
    # inject a permissive key set - custom key must be accepted
    ok, errors, _ = v.validate({"customKey": {}}, "opencode",
                               known_keys={"customKey"})
    assert ok and not errors


@pytest.mark.skipif(not HAS_QT, reason="PySide6 not available")
def test_adapter_drives_main_window_tabs(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SETTINGS_FILE", tmp_path / "settings.ini")
    win = app.MainWindow(tmp_path)
    assert win.adapter is app.OPENCODE_ADAPTER
    # all 10 opencode tabs built via the adapter factory
    assert win.tabs.count() == 10
    assert hasattr(win, "tab_providers") and hasattr(win, "_oc_tabs")
    assert len(win._oc_tabs) == 8
    win.close()
