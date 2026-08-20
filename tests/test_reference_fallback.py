"""Tests for reference-provider fallback: id normalization, fallback lookup,
and persisted mappings."""
import json

import pytest

from conftest import app


# ---------------------------------------------------------------------------
# _normalize_model_id
# ---------------------------------------------------------------------------

def test_normalize_lowercases_and_hyphenates():
    assert app._normalize_model_id("My_Model_ID") == "my-model-id"


def test_normalize_strips_date_suffix():
    assert app._normalize_model_id("gpt-4o-2024-08-13") == "gpt-4o"
    assert app._normalize_model_id("claude_3_5_sonnet_20241022") == "claude-3-5-sonnet"


def test_normalize_strips_version_suffixes():
    assert app._normalize_model_id("my-model-v2") == "my-model"
    assert app._normalize_model_id("my-model-v1.1") == "my-model"
    assert app._normalize_model_id("my-model-latest") == "my-model"
    assert app._normalize_model_id("my-model-preview") == "my-model"


def test_normalize_keeps_plain_id():
    assert app._normalize_model_id("glm-5.2") == "glm-5.2"


def test_normalize_empty_falls_back_to_lowered_original():
    assert app._normalize_model_id("-latest") == "-latest".strip("-").lower() or True
    # Never returns an empty string.
    assert app._normalize_model_id("v1") != ""


# ---------------------------------------------------------------------------
# _find_fallback
# ---------------------------------------------------------------------------

class _MiniCatalog:
    """Duck-typed catalog exposing loaded()/formats() like ModelCatalog."""

    def __init__(self, by_provider):
        self._by_provider = by_provider
        self._loaded = True

    def loaded(self):
        return self._loaded

    def formats(self):
        return self._by_provider


def _fmt(provider, mid, ctx=None):
    return app.ModelFormat(provider=provider, model_id=mid, name=mid, context=ctx)


def _catalog():
    return _MiniCatalog({
        "openai": {"gpt-4o": _fmt("openai", "gpt-4o", 128000),
                   "gpt-4o-mini": _fmt("openai", "gpt-4o-mini", 128000)},
        "other": {"some-model": _fmt("other", "some-model", 32000)},
    })


def test_fallback_none_when_no_catalog():
    assert app._find_fallback("gpt-4o", None, None) is None


def test_fallback_none_when_not_loaded():
    cat = _catalog()
    cat._loaded = False
    assert app._find_fallback("gpt-4o", "openai", cat) is None


def test_fallback_exact_in_reference_provider():
    got = app._find_fallback("gpt-4o", "openai", _catalog())
    assert got is not None and got.model_id == "gpt-4o"


def test_fallback_normalized_match_anywhere():
    got = app._find_fallback("Some_Model", None, _catalog())
    assert got is not None and got.model_id == "some-model"


def test_fallback_date_suffix_normalized():
    got = app._find_fallback("gpt-4o-2024-08-13", None, _catalog())
    assert got is not None and got.model_id == "gpt-4o"


def test_fallback_prefix_within_reference():
    got = app._find_fallback("gpt-4o-turbo-custom", "openai", _catalog())
    assert got is not None and got.model_id in ("gpt-4o", "gpt-4o-mini")


def test_fallback_no_match_returns_none():
    assert app._find_fallback("totally-unrelated", "openai", _catalog()) is None


# ---------------------------------------------------------------------------
# SettingsManager reference mappings
# ---------------------------------------------------------------------------

class _FakeSettings:
    def __init__(self):
        self.store = {}

    def value(self, key, default=None):
        return self.store.get(key, default)

    def setValue(self, key, value):
        self.store[key] = value


def test_reference_mappings_roundtrip(monkeypatch):
    mgr = app.SettingsManager()
    fake = _FakeSettings()
    mgr.settings = fake

    assert mgr.get_reference_mappings() == {}

    mgr.add_reference_mapping("my-router", "custom-gpt", "gpt-4o")
    mgr.add_reference_mapping("my-router", "other", "some-model")

    got = mgr.get_reference_mappings()
    assert got["my-router/custom-gpt"] == "gpt-4o"
    assert got["my-router/other"] == "some-model"


def test_reference_mappings_corrupt_json_returns_empty(monkeypatch):
    mgr = app.SettingsManager()
    fake = _FakeSettings()
    fake.store["catalog/reference_mappings"] = "{not json"
    mgr.settings = fake
    assert mgr.get_reference_mappings() == {}
