"""Tests for provider model fetching (adapters, URL/header building, SSRF guard).

No real network calls are made — fetch_provider_models accepts an injected
`opener` callable that returns canned bytes.
"""
import json

import pytest

from conftest import app


def _spec(**kw):
    return app.ProviderFetchSpec(
        base_url=kw.pop("base_url", "https://api.example.com/v1"),
        **kw,
    )


# ---------------------------------------------------------------------------
# parse_fetched_models — per adapter
# ---------------------------------------------------------------------------

def test_parse_openai_models():
    data = {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]}
    out = app.parse_fetched_models(data, _spec(adapter="openai"))
    assert set(out) == {"gpt-4o", "gpt-4o-mini"}
    # id == name for openai preset, so no name stored
    assert out["gpt-4o"] == {}


def test_parse_anthropic_models_with_display_name():
    data = {"data": [{"id": "claude-sonnet-4", "display_name": "Claude Sonnet 4"}]}
    out = app.parse_fetched_models(data, _spec(adapter="anthropic"))
    assert out["claude-sonnet-4"]["name"] == "Claude Sonnet 4"


def test_parse_gemini_strips_models_prefix():
    data = {"models": [{"name": "models/gemini-1.5-pro", "displayName": "Gemini 1.5 Pro"}]}
    out = app.parse_fetched_models(data, _spec(adapter="gemini"))
    assert "gemini-1.5-pro" in out
    assert out["gemini-1.5-pro"]["name"] == "Gemini 1.5 Pro"


def test_parse_models_dev_dump():
    data = {
        "openai": {"models": {"gpt-4o": {"name": "GPT-4o"}}},
        "anthropic": {"models": {"claude-x": {"name": "Claude X"}}},
    }
    out = app.parse_fetched_models(data, _spec(adapter="models_dev"))
    assert set(out) == {"gpt-4o", "claude-x"}


def test_parse_generic_custom_path():
    data = {"result": {"items": [{"model_id": "m1", "label": "M1"}]}}
    spec = _spec(adapter="generic", items_path="result.items",
                 id_field="model_id", name_field="label")
    out = app.parse_fetched_models(data, spec)
    assert out["m1"]["name"] == "M1"


def test_parse_generic_top_level_array():
    data = [{"id": "a"}, {"id": "b"}]
    spec = _spec(adapter="generic", items_path="")
    out = app.parse_fetched_models(data, spec)
    assert set(out) == {"a", "b"}


def test_parse_bad_path_raises():
    with pytest.raises(app.FetchError):
        app.parse_fetched_models({"nope": 1}, _spec(adapter="generic", items_path="data"))


def test_parse_empty_models_raises():
    with pytest.raises(app.FetchError):
        app.parse_fetched_models({"data": []}, _spec(adapter="openai"))


def test_parse_skips_items_without_id():
    data = {"data": [{"id": "ok"}, {"foo": "bar"}, {"id": ""}]}
    out = app.parse_fetched_models(data, _spec(adapter="openai"))
    assert set(out) == {"ok"}


# ---------------------------------------------------------------------------
# URL + header building
# ---------------------------------------------------------------------------

def test_build_url_appends_suffix():
    url = app._build_fetch_url(_spec(base_url="https://api.x.com", adapter="openai"))
    assert url == "https://api.x.com/models"


def test_build_url_no_double_suffix():
    url = app._build_fetch_url(_spec(base_url="https://api.x.com/models", adapter="openai"))
    assert url == "https://api.x.com/models"


def test_build_url_gemini_appends_query_key():
    url = app._build_fetch_url(
        _spec(base_url="https://generativelanguage.googleapis.com",
              adapter="gemini", api_key="SECRET"))
    assert "/v1beta/models" in url
    assert "key=SECRET" in url


def test_headers_bearer():
    h = app._build_fetch_headers(_spec(adapter="openai", api_key="abc"))
    assert h["Authorization"] == "Bearer abc"


def test_headers_anthropic():
    h = app._build_fetch_headers(_spec(adapter="anthropic", api_key="abc"))
    assert h["x-api-key"] == "abc"
    assert "anthropic-version" in h


def test_headers_extra_merge():
    h = app._build_fetch_headers(
        _spec(adapter="openai", api_key="abc", extra_headers={"X-Org": "acme"}))
    assert h["X-Org"] == "acme"


# ---------------------------------------------------------------------------
# SSRF guard
# ---------------------------------------------------------------------------

def test_validate_rejects_non_http():
    with pytest.raises(app.FetchError):
        app._validate_fetch_url("ftp://x.com/models", allow_local=False)


def test_validate_blocks_localhost():
    with pytest.raises(app.FetchError):
        app._validate_fetch_url("http://localhost:11434/api/tags", allow_local=False)


def test_validate_blocks_private_ip():
    with pytest.raises(app.FetchError):
        app._validate_fetch_url("http://192.168.1.10/models", allow_local=False)


def test_validate_allows_local_when_flagged():
    # Should not raise.
    app._validate_fetch_url("http://localhost:11434/api/tags", allow_local=True)


def test_validate_allows_public_https():
    app._validate_fetch_url("https://api.openai.com/v1/models", allow_local=False)


# ---------------------------------------------------------------------------
# fetch_provider_models end-to-end with injected opener (no network)
# ---------------------------------------------------------------------------

def test_fetch_with_injected_opener():
    captured = {}

    def fake_opener(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return json.dumps({"data": [{"id": "gpt-4o"}]}).encode("utf-8")

    spec = _spec(base_url="https://api.openai.com/v1", adapter="openai", api_key="k")
    out = app.fetch_provider_models(spec, opener=fake_opener)
    assert "gpt-4o" in out
    assert captured["url"] == "https://api.openai.com/v1/models"
    assert captured["headers"]["Authorization"] == "Bearer k"


def test_fetch_invalid_json_raises():
    def fake_opener(url, headers, timeout):
        return b"not json"
    with pytest.raises(app.FetchError):
        app.fetch_provider_models(_spec(adapter="openai"), opener=fake_opener)


def test_fetch_blocks_local_before_opener():
    called = {"n": 0}

    def fake_opener(url, headers, timeout):
        called["n"] += 1
        return b"{}"

    spec = _spec(base_url="http://127.0.0.1:1234", adapter="openai")
    with pytest.raises(app.FetchError):
        app.fetch_provider_models(spec, opener=fake_opener)
    assert called["n"] == 0  # guard fired before any fetch


# --- apply_fetched_provider: persisting endpoint config after a fetch ---

def test_apply_fetched_provider_persists_url_and_key():
    providers = {}
    prov, summary = app.apply_fetched_provider(
        providers, "openrouter", {"openai/gpt-4o": {"name": "GPT-4o"}},
        base_url="https://openrouter.ai/api/v1",
        api_key="the" + "-key", save_api_key=True,
        npm="@ai-sdk/openai-compatible")
    assert prov["npm"] == "@ai-sdk/openai-compatible"
    assert prov["name"] == "openrouter"
    opts = prov["options"]
    assert opts["baseURL"] == "https://openrouter.ai/api/v1"
    assert opts["apiKey"] == "the" + "-key"
    assert prov["models"] == {"openai/gpt-4o": {"name": "GPT-4o"}}
    assert summary == {"added": ["openai/gpt-4o"], "kept": [], "removed": []}


def test_apply_fetched_provider_unchecked_key_not_written():
    providers = {}
    prov, _ = app.apply_fetched_provider(
        providers, "p", {"m": {}},
        base_url="https://x/v1", api_key="the" + "-key", save_api_key=False)
    assert prov["options"] == {"baseURL": "https://x/v1"}


def test_apply_fetched_provider_keeps_existing_provider_fields():
    providers = {"p": {"npm": "@my/custom", "name": "Pretty",
                       "options": {"apiKey": "old" + "-key", "headers": {"X": "1"}},
                       "models": {"old-model": {"name": "Old"}}}}
    prov, summary = app.apply_fetched_provider(
        providers, "p", {"new-model": {}},
        base_url="https://new/v1", api_key="", save_api_key=True)
    assert prov["npm"] == "@my/custom"           # existing npm kept
    assert prov["name"] == "Pretty"
    assert prov["options"]["baseURL"] == "https://new/v1"
    assert prov["options"]["apiKey"] == "old" + "-key"   # empty field never wipes
    assert prov["options"]["headers"] == {"X": "1"}
    assert set(prov["models"]) == {"old-model", "new-model"}
    assert prov["models"]["old-model"] == {"name": "Old"}  # not overwritten
    assert summary == {"added": ["new-model"], "kept": [], "removed": []}


def test_apply_fetched_provider_repairs_bad_options():
    providers = {"p": {"options": "oops", "models": []}}
    prov, _ = app.apply_fetched_provider(providers, "p", {"m": {}},
                                         base_url="https://x/v1")
    assert prov["options"] == {"baseURL": "https://x/v1"}
    assert prov["models"] == {"m": {}}


def test_apply_fetched_provider_summary_counts_and_never_overwrites_specs():
    providers = {"p": {"models": {"kept-model": {"name": "UserEdited",
                                                 "limit": {"context": 999}}}}}
    fetched = {"kept-model": {"name": "FromAPI"}, "fresh": {"name": "Fresh"}}
    prov, summary = app.apply_fetched_provider(providers, "p", fetched)
    # existing spec survives untouched (API listings carry id/name only)
    assert prov["models"]["kept-model"] == {"name": "UserEdited",
                                            "limit": {"context": 999}}
    assert prov["models"]["fresh"] == {"name": "Fresh"}
    assert summary == {"added": ["fresh"], "kept": ["kept-model"], "removed": []}


def test_apply_fetched_provider_remove_missing_syncs_list():
    providers = {"p": {"models": {"alive": {}, "gone-a": {}, "gone-b": {}}}}
    prov, summary = app.apply_fetched_provider(
        providers, "p", {"alive": {}, "brand-new": {}}, remove_missing=True)
    assert set(prov["models"]) == {"alive", "brand-new"}
    assert summary == {"added": ["brand-new"], "kept": ["alive"],
                       "removed": ["gone-a", "gone-b"]}


def test_apply_fetched_provider_default_never_removes():
    providers = {"p": {"models": {"custom-alias": {"name": "Mine"}}}}
    prov, summary = app.apply_fetched_provider(providers, "p", {"other": {}})
    assert "custom-alias" in prov["models"]     # add-only by default
    assert summary["removed"] == []


def test_stale_configured_models():
    existing = {"a": {}, "b": {}, "c": {}}
    assert app.stale_configured_models(existing, ["a", "c", "d"]) == ["b"]
    assert app.stale_configured_models(existing, []) == ["a", "b", "c"]
    assert app.stale_configured_models("not-a-dict", ["a"]) == []


def test_npm_for_fetch_maps_by_adapter_and_host():
    assert app.npm_for_fetch("anthropic", "https://api.anthropic.com") == "@ai-sdk/anthropic"
    assert app.npm_for_fetch("gemini", "https://generativelanguage.googleapis.com") == "@ai-sdk/google"
    assert app.npm_for_fetch("openai", "https://api.openai.com/v1") == "@ai-sdk/openai"
    # an OpenAI-format gateway is NOT openai.com -> openai-compatible
    assert app.npm_for_fetch("openai", "https://openrouter.ai/api/v1") == "@ai-sdk/openai-compatible"
    assert app.npm_for_fetch("openai", "http://localhost:11434/v1") == "@ai-sdk/openai-compatible"
    assert app.npm_for_fetch("generic", "https://anything") == "@ai-sdk/openai-compatible"
    assert app.npm_for_fetch("models_dev", "") == "@ai-sdk/openai-compatible"
