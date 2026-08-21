"""Round-trip safety net: load a realistic config into the tabs and collect it
back with no data loss. Guards refactors of tab load/collect and the adapter
wiring against silently dropping or mangling config sections.
"""
import copy

import pytest

from tests.conftest import HAS_QT, app

pytestmark = pytest.mark.skipif(not HAS_QT, reason="PySide6 not available - GUI round-trip")


OPENCODE_FIXTURE = {
    "$schema": "https://opencode.ai/config.json",
    "model": "anthropic/claude-sonnet-4",
    "small_model": "anthropic/claude-haiku",
    "theme": "opencode",
    "provider": {
        "openai": {
            "models": {
                "gpt-4o": {"name": "GPT-4o", "limit": {"context": 128000, "output": 16384}},
            },
        },
    },
    "mcp": {
        "my-server": {"type": "local", "command": ["node", "server.js"]},
    },
    "agent": {
        "build": {"model": "anthropic/claude-sonnet-4", "prompt": "You build."},
    },
    "permission": {"edit": "allow", "bash": "ask"},
    "plugin": ["my-plugin@1.0.0"],
    "instructions": ["CONTEXT.md"],
}

TUI_FIXTURE = {
    "$schema": "https://opencode.ai/tui.json",
    "theme": "tokyonight",
    "mouse": True,
    "scroll_speed": 2.0,
}


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SETTINGS_FILE", tmp_path / "settings.ini")
    w = app.MainWindow(tmp_path)
    yield w
    w.close()


def _assert_contains(result, expected, path=""):
    """Assert `result` deep-contains `expected` (no data loss / no mangling).

    Tabs may add empty/default fields on collect (e.g. ProvidersTab writes an
    empty `npm: ""`), so we assert every value the fixture *specifies* survives
    unchanged, tolerating additive keys.
    """
    if isinstance(expected, dict):
        assert isinstance(result, dict), f"{path}: expected dict, got {type(result)}"
        for k, v in expected.items():
            assert k in result, f"lost key: {path}/{k}"
            _assert_contains(result[k], v, f"{path}/{k}")
    else:
        assert result == expected, f"mangled value at {path}: {result!r} != {expected!r}"


def test_opencode_roundtrip_preserves_all_sections(win):
    win.cfg_oc.data = copy.deepcopy(OPENCODE_FIXTURE)
    win.refresh_tabs()
    result = win._collect_oc()
    _assert_contains(result, OPENCODE_FIXTURE)


def test_tui_roundtrip_preserves_all_sections(win):
    win.cfg_tui.data = copy.deepcopy(TUI_FIXTURE)
    win.refresh_tabs()
    result = win._collect_tui()
    _assert_contains(result, TUI_FIXTURE)


def test_empty_opencode_roundtrip_adds_only_empty_containers(win):
    win.cfg_oc.data = {}
    win.refresh_tabs()
    result = win._collect_oc()
    # Tabs may seed empty containers, but never non-empty data from nothing.
    for k, v in result.items():
        assert v in ({}, [], "", None), f"unexpected data synthesized: {k}={v!r}"


def test_unknown_keys_preserved(win):
    """Keys no tab knows about must pass through untouched."""
    win.cfg_oc.data = {"someExperimentalKey": {"nested": [1, 2, 3]}}
    win.refresh_tabs()
    result = win._collect_oc()
    assert result.get("someExperimentalKey") == {"nested": [1, 2, 3]}
