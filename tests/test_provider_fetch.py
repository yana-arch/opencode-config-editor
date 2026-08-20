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
