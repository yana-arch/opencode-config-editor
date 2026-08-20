"""Tests for SettingsManager (QSettings-backed, pointed at a temp file)."""
import pytest

from tests.conftest import app


@pytest.fixture
def settings(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SETTINGS_FILE", tmp_path / "settings.ini")
    return app.SettingsManager()


def test_get_set_roundtrip(settings):
    assert settings.get("missing/key", "dflt") == "dflt"
    settings.set("a/b", "value")
    assert settings.get("a/b") == "value"


def test_font_size(settings):
    settings.set_font_size(13)
    assert int(settings.get_font_size()) == 13


def test_theme(settings):
    settings.set_theme("dark")
    assert settings.get_theme() == "dark"


def test_context_tiers_default_and_roundtrip(settings):
    tiers = settings.get_context_tiers()
    assert isinstance(tiers, list) and tiers
    settings.set_context_tiers([40, 60, 90])
    assert settings.get_context_tiers() == [40, 60, 90]


def test_output_tiers_roundtrip(settings):
    settings.set_output_tiers([10, 20])
    assert settings.get_output_tiers() == [10, 20]


def test_reference_mappings_empty_default(settings):
    assert settings.get_reference_mappings() == {}


def test_reference_mappings_roundtrip(settings):
    settings.set_reference_mappings({"openai/gpt-4o": "openai/gpt-4o"})
    assert settings.get_reference_mappings() == {"openai/gpt-4o": "openai/gpt-4o"}


def test_add_reference_mapping(settings):
    settings.add_reference_mapping("openai", "gpt-4o-2024", "openai/gpt-4o")
    got = settings.get_reference_mappings()
    assert got == {"openai/gpt-4o-2024": "openai/gpt-4o"}


def test_recent_files(settings):
    settings.add_recent_file("/tmp/x/opencode.json")
    settings.add_recent_file("/tmp/y/opencode.json")
    recent = settings.get_recent_files()
    assert recent[0] == "/tmp/y/opencode.json"
    assert "/tmp/x/opencode.json" in recent
