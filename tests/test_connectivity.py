import pytest
from conftest import app


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
