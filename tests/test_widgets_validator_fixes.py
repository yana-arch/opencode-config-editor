"""Regression tests for MW-15 (MaskedLineEdit), MW-16 and MW-19 (Validator)."""
import json
import os
import time

import pytest

from conftest import HAS_QT, app


# --- MW-16: a non-object 'mcp' is a hard error, not a crash ---

@pytest.mark.parametrize("bad", [[], "x", None, 5, True])
def test_validate_rejects_non_object_mcp(bad):
    """MW-16: validate() must return the hard error instead of raising on 'mcp': []."""
    ok, hard, _ = app.Validator().validate({"mcp": bad}, "opencode")
    assert ok is False
    assert any("'mcp' must be an object" in e for e in hard)


def test_validate_still_checks_mcp_entries():
    """The early return must not skip per-entry checks for a valid object."""
    ok, hard, _ = app.Validator().validate({"mcp": {"fs": {"type": "bogus"}}}, "opencode")
    assert ok is False
    assert any("must be 'local' or 'remote'" in e for e in hard)
    assert app.Validator().validate({"mcp": {"fs": {"type": "local", "command": ["npx"]}}}, "opencode")[0]


# --- MW-19: disk cache expiry, non-schema bodies, per-kind state ---

class _Resp:
    def __init__(self, body):
        self._body = body

    def read(self):
        return json.dumps(self._body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _schema(props):
    return {"type": "object", "properties": {k: {"type": "string"} for k in props}}


@pytest.fixture(autouse=True)
def _schema_support(monkeypatch):
    """schema_from() short-circuits without jsonschema; force it on for these tests."""
    monkeypatch.setattr(app, "HAVE_JSONSCHEMA", True)


def test_stale_disk_cache_is_refreshed(tmp_path, monkeypatch):
    """MW-19: a cache older than 24h must trigger a fetch (it used to never expire)."""
    cache = tmp_path / "schema.json"
    cache.write_text(json.dumps(_schema(["model"])))
    old = time.time() - 30 * 86400
    os.utime(cache, (old, old))

    calls = []

    def fake_urlopen(req, timeout=10):
        calls.append(req)
        return _Resp(_schema(["theme"]))

    monkeypatch.setattr(app.urllib.request, "urlopen", fake_urlopen)
    got = app.Validator().schema_from("http://x/s.json", cache, "opencode")

    assert len(calls) == 1

    assert "theme" in got["properties"]
    assert "theme" in json.loads(cache.read_text())["properties"]


def test_fresh_disk_cache_avoids_the_network(tmp_path, monkeypatch):
    cache = tmp_path / "schema.json"
    cache.write_text(json.dumps(_schema(["model"])))

    def boom(*a, **k):
        raise AssertionError("must not fetch while the cache is fresh")

    monkeypatch.setattr(app.urllib.request, "urlopen", boom)
    got = app.Validator().schema_from("http://x/s.json", cache, "opencode")
    assert "model" in got["properties"]


def test_non_schema_response_is_not_cached(tmp_path, monkeypatch):
    """MW-19: a 200 body that is not a JSON Schema must not be cached."""
    cache = tmp_path / "schema.json"
    monkeypatch.setattr(app.urllib.request, "urlopen",
                        lambda req, timeout=10: _Resp({"message": "rate limited"}))

    assert app.Validator().schema_from("http://x/s.json", cache, "opencode") is None
    assert not cache.exists()


def test_ref_root_schema_is_accepted_and_cached(tmp_path, monkeypatch):
    cache = tmp_path / "schema.json"
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
              "$ref": "#/$defs/Root", "$defs": {"Root": {"type": "object"}}}
    monkeypatch.setattr(app.urllib.request, "urlopen",
                        lambda req, timeout=10: _Resp(schema))
    got = app.Validator().schema_from("http://x/s.json", cache, "opencode")
    assert got == schema
    assert json.loads(cache.read_text()) == schema


def test_failed_fetch_still_serves_the_stale_cache(tmp_path, monkeypatch):
    """A fetch failure must not silently disable validation when a cache exists."""
    cache = tmp_path / "schema.json"
    cache.write_text(json.dumps(_schema(["model"])))
    old = time.time() - 30 * 86400
    os.utime(cache, (old, old))

    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(app.urllib.request, "urlopen", boom)
    got = app.Validator().schema_from("http://x/s.json", cache, "opencode")
    assert got is not None and "model" in got["properties"]


def test_failed_fetch_backoff_keeps_serving_stale_cache(tmp_path, monkeypatch):
    cache = tmp_path / "schema.json"
    cache.write_text(json.dumps(_schema(["model"])))
    old = time.time() - 30 * 86400
    os.utime(cache, (old, old))
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise OSError("offline")

    monkeypatch.setattr(app.urllib.request, "urlopen", boom)
    validator = app.Validator()
    assert validator.schema_from("http://x/s.json", cache, "opencode") is not None
    assert validator.schema_from("http://x/s.json", cache, "opencode") is not None
    assert len(calls) == 1


def test_fetch_failure_is_scoped_to_one_kind(tmp_path, monkeypatch):
    """MW-19: a failed tui fetch must not suppress a valid opencode schema."""
    cache = tmp_path / "s.json"
    cache.write_text(json.dumps(_schema(["model"])))
    v = app.Validator()

    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(app.urllib.request, "urlopen", boom)
    assert v.schema_from("http://x/s.json", cache, "tui") is not None
    assert v.schema_from("http://x/s.json", cache, "opencode") is not None


@pytest.mark.skipif(not HAS_QT, reason="PySide6 not available")
class TestMaskedLineEdit:
    @staticmethod
    def _edit(value, field_name="apiKey"):
        return app.MaskedLineEdit(value, field_name=field_name)

    def test_hide_after_reveal_remasks(self, qapp):
        """MW-15(a): toggling the eye off must re-mask; the secret must not stay visible."""
        e = self._edit("sk-live-1234567890abcdef")
        assert "*" in e.edit.text()
        e.toggle_btn.setChecked(True)
        assert e.edit.text() == "sk-live-1234567890abcdef"
        e.toggle_btn.setChecked(False)
        assert "*" in e.edit.text(), "secret still shown after hiding"
        assert e.value() == "sk-live-1234567890abcdef"

    def test_editing_while_masked_saves_the_new_secret(self, qapp):
        """MW-15(b): a masked edit must not save literal asterisks."""
        e = self._edit("sk-old-value-1234")
        e.edit.setText("sk-new-value-5678")
        assert "*" not in e.value()
        assert e.value() == "sk-new-value-5678"

    def test_untouched_masked_field_yields_the_real_value(self, qapp):
        e = self._edit("sk-live-1234567890abcdef")
        assert e.value() == "sk-live-1234567890abcdef"
        assert "*" in e.edit.text()  # still displayed masked

    def test_revealed_edit_then_hide_keeps_the_edit(self, qapp):
        e = self._edit("sk-old-value-1234")
        e.toggle_btn.setChecked(True)
        e.edit.setText("sk-new-value-5678")
        e.toggle_btn.setChecked(False)
        assert e.value() == "sk-new-value-5678"
        assert "*" in e.edit.text()

    def test_non_secret_field_is_unaffected(self, qapp):
        e = self._edit("plain-value", field_name="username")
        assert e.toggle_btn is None
        assert e.value() == "plain-value"
        e.edit.setText("typed")
        assert e.value() == "typed"