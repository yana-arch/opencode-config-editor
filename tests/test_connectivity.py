import pytest

from conftest import app


# --------------------------------------------------------------------------
# HC-3: {env:} / {file:} config variables
# --------------------------------------------------------------------------


def test_resolve_env_placeholder(monkeypatch):
    monkeypatch.setenv("OCCE_TEST_KEY", "sk-real")
    assert app.resolve_config_placeholders("{env:OCCE_TEST_KEY}") == "sk-real"


def test_resolve_unset_env_is_empty(monkeypatch):
    monkeypatch.delenv("OCCE_TEST_MISSING", raising=False)
    assert app.resolve_config_placeholders("{env:OCCE_TEST_MISSING}") == ""


def test_resolve_file_relative_to_config_dir(tmp_path):
    (tmp_path / "key.txt").write_text("sk-from-file\n")
    got = app.resolve_config_placeholders("{file:key.txt}", tmp_path)
    assert got == "sk-from-file"


def test_resolve_file_absolute(tmp_path):
    target = tmp_path / "abs.txt"
    target.write_text("sk-abs")
    assert app.resolve_config_placeholders("{file:%s}" % target) == "sk-abs"


def test_resolve_missing_file_is_empty(tmp_path):
    assert app.resolve_config_placeholders("{file:nope.txt}", tmp_path) == ""


def test_resolve_embedded_placeholder(monkeypatch):
    monkeypatch.setenv("OCCE_TEST_HOST", "https://api.example.com")
    got = app.resolve_config_placeholders("{env:OCCE_TEST_HOST}/v1")
    assert got == "https://api.example.com/v1"


def test_resolve_leaves_plain_string_alone():
    assert app.resolve_config_placeholders("sk-plain") == "sk-plain"


# --------------------------------------------------------------------------
# HC-5: SDK-style version segment must not be doubled
# --------------------------------------------------------------------------


def _ok_opener(seen):
    def opener(url, headers, timeout):
        seen.append(url)
        return b'{"data": [{"id": "m1"}]}'
    return opener


def test_anthropic_sdk_style_base_url_is_not_doubled():
    seen = []
    res = app.test_provider_connection(
        "https://api.anthropic.com/v1", "k", "anthropic", opener=_ok_opener(seen))
    assert res.success is True
    assert seen == ["https://api.anthropic.com/v1/models"]


def test_anthropic_host_root_base_url():
    seen = []
    app.test_provider_connection(
        "https://api.anthropic.com", "k", "anthropic", opener=_ok_opener(seen))
    assert seen == ["https://api.anthropic.com/v1/models"]


def test_gemini_sdk_style_base_url_is_not_doubled():
    seen = []
    app.test_provider_connection(
        "https://generativelanguage.googleapis.com/v1beta", "AIza-x", "gemini",
        opener=_ok_opener(seen))
    assert seen[0].split("?")[0] == "https://generativelanguage.googleapis.com/v1beta/models"


def test_gemini_host_root_base_url():
    seen = []
    app.test_provider_connection(
        "https://generativelanguage.googleapis.com", "AIza-x", "gemini",
        opener=_ok_opener(seen))
    assert seen[0].split("?")[0] == "https://generativelanguage.googleapis.com/v1beta/models"


def test_openai_existing_v1_not_doubled():
    seen = []
    app.test_provider_connection(
        "https://api.openai.com/v1", "k", "openai", opener=_ok_opener(seen))
    assert seen == ["https://api.openai.com/v1/models"]


# --------------------------------------------------------------------------
# HC-6: no secret in the 404 message
# --------------------------------------------------------------------------


def _raise404(url, headers, timeout):
    raise app.urllib.error.HTTPError(url, 404, "Not Found", {}, None)


def test_gemini_key_redacted_in_404_message():
    res = app.test_provider_connection(
        "https://generativelanguage.googleapis.com", "AIza-SECRET", "gemini",
        opener=_raise404)
    assert "AIza-SECRET" not in res.message
    assert "AIza-SECRET" not in res.raw_error
    assert "404" in res.message


def test_space_in_gemini_base_url_does_not_leak_key():
    """urllib echoes the request line back; the key must not survive."""
    res = app.test_provider_connection(
        "https://generativelanguage.googleapis.com/v1 beta", "AIza-LEAK-1", "gemini")
    assert res.success is False
    assert "AIza-LEAK-1" not in res.message
    assert "AIza-LEAK-1" not in res.raw_error


def test_newline_in_key_does_not_leak():
    """A multi-line {file:} credential must not be echoed into the log."""
    key = "sk-line1\nsk-line2"
    res = app.test_provider_connection("https://api.openai.com/v1", key, "openai")
    assert res.success is False
    assert key not in res.message
    assert "sk-line1" not in res.raw_error
    assert "sk-line2" not in res.raw_error


def test_sanitize_secret_masks_url_query_and_literal_key():
    out = app._sanitize_secret("boom https://h/v1?key=abc123 and sk-raw", "sk-raw")
    assert "abc123" not in out
    assert "sk-raw" not in out


def test_query_token_redacted_in_404_message():
    res = app._redact_url_secrets("https://h/v1/models?key=abc123&x=1")
    assert "abc123" not in res
    assert "x=1" in res


# --------------------------------------------------------------------------
# HC-4 / HC-8: provider target resolution
# --------------------------------------------------------------------------


def test_builtin_provider_without_npm_gets_default_endpoint():
    adapter, base, key, err = app.resolve_provider_target(
        "anthropic", {"options": {"apiKey": "sk-ant"}})
    assert (adapter, base, key, err) == (
        "anthropic", "https://api.anthropic.com", "sk-ant", "")


def test_builtin_google_provider_uses_gemini_adapter():
    adapter, base, _, _ = app.resolve_provider_target(
        "google", {"options": {"apiKey": "AIza"}})
    assert (adapter, base) == ("gemini", "https://generativelanguage.googleapis.com")


def test_explicit_base_url_wins_over_builtin_default():
    _, base, _, _ = app.resolve_provider_target(
        "anthropic", {"options": {"baseURL": "https://proxy.test", "apiKey": "k"}})
    assert base == "https://proxy.test"


def test_google_vertex_package_not_routed_to_gemini():
    adapter, base, _, _ = app.resolve_provider_target(
        "vertex", {"npm": "@ai-sdk/google-vertex", "options": {"apiKey": "SECRET"}})
    # Not tested against AI Studio; only its own baseURL would be used.
    assert base == ""
    assert adapter == "openai"


def test_google_vertex_package_with_own_base_url_is_used():
    _, base, _, _ = app.resolve_provider_target(
        "vertex", {"npm": "@ai-sdk/google-vertex",
                   "options": {"baseURL": "https://us-central1-aiplatform.googleapis.com"}})
    assert base == "https://us-central1-aiplatform.googleapis.com"


def test_unknown_package_is_not_given_a_vendor_default():
    _, base, _, _ = app.resolve_provider_target(
        "azure", {"npm": "@ai-sdk/azure", "options": {"apiKey": "S"}})
    assert base == ""


def test_known_package_maps_to_adapter():
    assert app.resolve_provider_target(
        "a", {"npm": "@ai-sdk/anthropic", "options": {}})[0] == "anthropic"
    assert app.resolve_provider_target(
        "a", {"npm": "@ai-sdk/google", "options": {}})[0] == "gemini"
    assert app.resolve_provider_target(
        "a", {"npm": "@ai-sdk/openai-compatible", "options": {}})[0] == "openai"


def test_resolve_provider_target_expands_placeholders(monkeypatch, tmp_path):
    monkeypatch.setenv("OCCE_TEST_URL", "https://env.test")
    (tmp_path / "k.txt").write_text("sk-file")
    _, base, key, _ = app.resolve_provider_target(
        "p", {"options": {"baseURL": "{env:OCCE_TEST_URL}", "apiKey": "{file:k.txt}"}},
        tmp_path)
    assert base == "https://env.test"
    assert key == "sk-file"


@pytest.mark.parametrize("npm", [["@ai-sdk/openai"], {"package": "x"}, 7])
def test_resolve_provider_target_tolerates_non_string_npm(npm):
    adapter, base, key, err = app.resolve_provider_target(
        "p", {"npm": npm, "options": {"baseURL": "https://proxy.test", "apiKey": "k"}})
    assert (adapter, base, key, err) == ("openai", "https://proxy.test", "k", "")


# --------------------------------------------------------------------------
# Existing coverage
# --------------------------------------------------------------------------


def test_test_provider_connection_empty_url():
    res = app.test_provider_connection(base_url="")
    assert res.success is False
    assert "empty" in res.message.lower()


def test_test_provider_connection_success():
    def mock_opener(url, headers, timeout):
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-key"
        return b'{"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]}'

    res = app.test_provider_connection(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        adapter="openai",
        opener=mock_opener,
    )
    assert res.success is True
    assert res.status_code == 200
    assert res.model_count == 2
    assert "gpt-4o" in res.models
    assert "gpt-4o-mini" in res.models
    assert "✓ Connected" in res.summary()


def test_test_provider_connection_anthropic():
    def mock_opener(url, headers, timeout):
        assert headers.get("x-api-key") == "sk-ant-test"
        return b'{"data": [{"id": "claude-3-5-sonnet-20241022"}]}'

    res = app.test_provider_connection(
        base_url="https://api.anthropic.com",
        api_key="sk-ant-test",
        adapter="anthropic",
        opener=mock_opener,
    )
    assert res.success is True
    assert res.model_count == 1
    assert "claude-3-5-sonnet-20241022" in res.models