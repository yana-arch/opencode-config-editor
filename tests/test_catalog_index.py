"""Tests for ModelCatalog indexing used by find_model()."""
import pytest

from conftest import app


@pytest.fixture(autouse=True)
def _isolated_catalog_files(tmp_path, monkeypatch):
    """Keep every test in this module away from the developer's real
    custom_models.json / pattern_rules.json (CAT-17)."""
    monkeypatch.setattr(app, "CUSTOM_MODELS_FILE", tmp_path / "custom_models.json")
    monkeypatch.setattr(app, "PATTERN_RULES_FILE", tmp_path / "pattern_rules.json")


def _catalog():
    return app.ModelCatalog()


def test_index_built_on_ingest():
    cat = _catalog()
    cat.load_text(
        json_dump({"p1": {"models": {"a": {"name": "A"}}},
                   "p2": {"models": {"a": {"name": "A2"}, "b": {"name": "B"}}}}))
    assert sorted(cat._model_index["a"]) == ["p1", "p2"]
    assert cat._model_index["b"] == ["p2"]


def test_find_model_uses_index_multi_provider():
    cat = _catalog()
    cat.load_text(
        json_dump({"p1": {"models": {"x": {"name": "X"}}},
                   "p2": {"models": {"x": {"name": "X2"}}}}))
    matches = cat.find_model("x")
    assert sorted(m.provider for m in matches) == ["p1", "p2"]
    assert {m.context for m in matches} == {None}


def test_find_model_returns_empty_for_unknown():
    cat = _catalog()
    cat.load_text(json_dump({"p1": {"models": {"a": {}}}}))
    assert cat.find_model("ghost") == []


def test_index_reset_on_reload():
    cat = _catalog()
    cat.load_text(json_dump({"p1": {"models": {"a": {}}}}))
    cat.load_text(json_dump({"p2": {"models": {"b": {}}}}))
    assert "a" not in cat._model_index
    assert cat._model_index.get("b") == ["p2"]


def json_dump(data):
    import json
    return json.dumps(data)


def test_real_bundled_catalog_index_and_lookup():
    """Smoke-test find_model against the real bundled models.dev catalog."""
    cat = _catalog()
    bundled = __import__("conftest").ROOT / "models" / "models.dev.catalog.json"
    if not bundled.exists():
        pytest.skip("bundled catalog not present")
    cat.load(bundled)
    assert cat._model_index, "index should be populated"
    # A model id known to appear across many providers.
    matches = cat.find_model("glm-5.2")
    assert matches, "glm-5.2 should exist in the catalog"
    providers = {m.provider for m in matches}
    assert "zhipuai" in providers
    # With normalization, we might match variations, so we check if the normalized ID matches
    assert all(app._normalize_model_id(m.model_id) == app._normalize_model_id("glm-5.2") for m in matches)
    # Unknown id returns empty without error.
    assert cat.find_model("definitely-not-a-real-model-xyz") == []


def test_custom_models_management(tmp_path, monkeypatch):
    custom_file = tmp_path / "custom_models.json"
    monkeypatch.setattr(app, "CUSTOM_MODELS_FILE", custom_file)

    cat = _catalog()
    cat.load_text(json_dump({"openai": {"models": {"gpt-4o": {"name": "GPT-4o"}}}}))

    # Add custom model
    spec = {
        "name": "GLM 5.3 Flash",
        "provider": "zhipu",
        "limit": {"context": 128000, "output": 8192},
        "attachment": True,
        "reasoning": True,
    }
    assert cat.save_custom_model("glm-5.3-flash", spec, provider="zhipu") is True

    # Find custom model
    matches = cat.find_model("glm-5.3-flash")
    assert len(matches) == 1
    assert matches[0].model_id == "glm-5.3-flash"
    assert matches[0].name == "GLM 5.3 Flash"
    assert matches[0].provider == "zhipu"
    assert matches[0].context == 128000
    assert matches[0].reasoning is True

    # Delete custom model
    assert cat.delete_custom_model("glm-5.3-flash") is True
    assert cat.find_model("glm-5.3-flash") == []


def test_find_model_prefers_the_exact_entry(tmp_path, monkeypatch):
    """An id present in the catalog must resolve to itself, not to a sibling."""
    monkeypatch.setattr(app, "CUSTOM_MODELS_FILE", tmp_path / "custom_models.json")
    monkeypatch.setattr(app, "PATTERN_RULES_FILE", tmp_path / "pattern_rules.json")
    cat = app.ModelCatalog()
    cat.load_text(json_dump({
        "acme": {"models": {
            "openai/gpt-4o-2024-05-13": {"name": "Dated", "limit": {"context": 1}},
            "openai/gpt-4o-2024-11-20": {"name": "Newer", "limit": {"context": 2}},
            "openai/gpt-4o-preview": {"name": "Preview", "limit": {"context": 3}},
            "openai/gpt-4o-chat": {"name": "Chat", "limit": {"context": 4}},
        }}
    }))
    matches = cat.find_model("openai/gpt-4o-2024-05-13")
    assert [(m.provider, m.model_id, m.context) for m in matches] == [
        ("acme", "openai/gpt-4o-2024-05-13", 1),
    ]


def test_apply_writes_the_exact_entry_not_a_sibling(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "CUSTOM_MODELS_FILE", tmp_path / "custom_models.json")
    monkeypatch.setattr(app, "PATTERN_RULES_FILE", tmp_path / "pattern_rules.json")
    cat = app.ModelCatalog()
    cat.load_text(json_dump({
        "acme": {"models": {
            "openai/gpt-4o-2024-05-13": {"name": "Dated", "limit": {"context": 128000}},
            "openai/gpt-4o-preview": {"name": "Preview", "limit": {"context": 64000}},
        }}
    }))
    providers = {"router": {"models": {"openai/gpt-4o-2024-05-13": {}}}}
    app.apply_catalog_to_config(cat, providers)
    written = providers["router"]["models"]["openai/gpt-4o-2024-05-13"]
    assert written["name"] == "Dated"
    assert written["limit"]["context"] == 128000


def test_find_model_ordering_is_deterministic(tmp_path, monkeypatch):
    """Sibling matches come back in a stable, reproducible order."""
    monkeypatch.setattr(app, "CUSTOM_MODELS_FILE", tmp_path / "custom_models.json")
    monkeypatch.setattr(app, "PATTERN_RULES_FILE", tmp_path / "pattern_rules.json")
    cat = app.ModelCatalog()
    # Every id below normalizes to "gpt-4o", so all of them land in one bucket.
    siblings = ["gpt-4o", "gpt-4o-2024-04-09", "gpt-4o-preview", "gpt-4o-chat"]
    cat.load_text(json_dump({
        "acme": {"models": {mid: {"limit": {"context": i}}
                             for i, mid in enumerate(siblings)}}
    }))
    # "gpt-4o-preview-0409" normalizes to "gpt-4o", joining the bucket.
    first = [(m.provider, m.model_id) for m in cat.find_model("gpt-4o-preview-0409")]
    assert first, "the normalized bucket must produce matches"
    for _ in range(5):
        assert [(m.provider, m.model_id)
                for m in cat.find_model("gpt-4o-preview-0409")] == first
    assert first == [("acme", mid) for mid in siblings]


def test_pattern_rules_matching(tmp_path, monkeypatch):
    rules_file = tmp_path / "pattern_rules.json"
    monkeypatch.setattr(app, "PATTERN_RULES_FILE", rules_file)

    cat = _catalog()
    cat.load_text(json_dump({
        "zhipu": {
            "models": {
                "glm-4-flash": {
                    "name": "GLM 4 Flash",
                    "limit": {"context": 128000, "output": 4096},
                    "tool_call": True,
                }
            }
        },
        "openai": {
            "models": {
                "gpt-4o": {
                    "name": "GPT-4o",
                    "limit": {"context": 128000, "output": 4096},
                }
            }
        }
    }))

    rules = [
        {
            "pattern": "glm-*",
            "reference_provider": "zhipu",
            "reference_model": "glm-4-flash",
            "description": "Auto match GLM models",
        },
        {
            "pattern": "regex:^my-proxy/.*",
            "reference_provider": "openai",
            "reference_model": "gpt-4o",
        }
    ]
    assert cat.save_pattern_rules(rules) is True

    # Test wildcard pattern match
    matches = cat.find_model("glm-6.0-ultra")
    assert len(matches) == 1
    assert matches[0].model_id == "glm-6.0-ultra"
    assert matches[0].name == "GLM 6.0 Ultra"
    assert matches[0].provider == "zhipu"
    assert matches[0].tools is True

    # Test regex pattern match
    matches = cat.find_model("my-proxy/custom-agent")
    assert len(matches) == 1
    assert matches[0].model_id == "my-proxy/custom-agent"
    assert matches[0].name == "Custom Agent"
    assert matches[0].provider == "openai"

def test_loaded_is_false_for_custom_models_only(tmp_path, monkeypatch):
    """Custom models overlay a base catalog; they must not stand in for it."""
    custom = tmp_path / "custom_models.json"
    monkeypatch.setattr(app, "CUSTOM_MODELS_FILE", custom)
    custom.write_text(json_dump({"mine": {"provider": "zz", "limit": {"context": 5}}}))
    cat = app.ModelCatalog()
    assert cat.loaded() is False
    assert len(cat.find_model("mine")) == 1


def test_bundled_catalog_loads_despite_custom_models(tmp_path, monkeypatch):
    """The cached/bundled catalog still loads and keeps custom models (CAT-07)."""
    custom = tmp_path / "custom_models.json"
    monkeypatch.setattr(app, "CUSTOM_MODELS_FILE", custom)
    custom.write_text(json_dump({"mine-internal-1": {"provider": "zz"}}))
    cache = tmp_path / "catalog_cache.json"
    cache.write_text(json_dump({"zz": {"models": {"base-model": {"limit": {"context": 9}}}}}))
    monkeypatch.setattr(app, "CATALOG_CACHE", cache)

    cat = app.ModelCatalog()
    assert app.try_load_bundled_catalog(cat) is True
    assert cat.find_model("base-model"), "base catalog entries must still match"
    assert len(cat.find_model("mine-internal-1")) == 1, "custom models overlay it"


def test_self_matching_pattern_rule_does_not_recurse(tmp_path, monkeypatch):
    """A rule whose reference matches its own pattern must be skipped (CAT-08)."""
    monkeypatch.setattr(app, "PATTERN_RULES_FILE", tmp_path / "pattern_rules.json")
    cat = app.ModelCatalog()
    cat.load_text(json_dump({
        "zhipuai": {"models": {"glm-4-flash": {"limit": {"context": 128000}}}},
        "openai": {"models": {"gpt-4o": {}}},
    }))
    assert cat.save_pattern_rules([{
        "pattern": "glm-*",
        "reference_provider": "zhipuai",
        "reference_model": "glm-5.3-flash",
    }]) is True

    # The reference id matches the rule's own pattern: no RecursionError, and
    # the unresolvable reference leaves the id unmatched.
    assert cat.find_model("glm-5.3-flash") == []
    # An id the rule cannot resolve at all is still unmatched rather than crashing.
    assert cat.find_model("glm-6.0-ultra") == []


def test_unparseable_custom_models_file_is_never_rewritten(tmp_path, monkeypatch):
    """A broken custom_models.json must survive every write attempt (CAT-10)."""
    custom = tmp_path / "custom_models.json"
    monkeypatch.setattr(app, "CUSTOM_MODELS_FILE", custom)
    broken = '{ "kept": { "name": "Kept", },'
    custom.write_text(broken)
    before = custom.read_bytes()

    cat = app.ModelCatalog()
    with pytest.raises(ValueError):
        cat.get_all_custom_models()
    assert cat.save_custom_model("new-one", {"name": "New"}, provider="custom") is False
    assert cat.delete_custom_model("kept") is False
    assert custom.read_bytes() == before


def test_delete_clears_indexes_without_base_catalog(tmp_path, monkeypatch):
    """With no base catalog a deleted model disappears from every index (CAT-15)."""
    custom = tmp_path / "custom_models.json"
    monkeypatch.setattr(app, "CUSTOM_MODELS_FILE", custom)
    custom.write_text(json_dump({
        "gone": {"provider": "zz", "limit": {"context": 1}},
        "kept": {"provider": "zz"},
    }))
    cat = app.ModelCatalog()
    assert cat.find_model("gone")
    assert cat.delete_custom_model("gone") is True
    assert cat.find_model("gone") == []
    assert "gone" not in cat.flat
    assert "gone" not in cat.by_provider.get("zz", {})


def test_custom_models_mix_grouped_and_flat_entries(tmp_path, monkeypatch):
    """Grouped and flat custom entries coexist; bad values are skipped (CAT-12)."""
    custom = tmp_path / "custom_models.json"
    monkeypatch.setattr(app, "CUSTOM_MODELS_FILE", custom)
    custom.write_text(json_dump({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "zhipu": {"models": {"glm-x": {"limit": {"context": 3}}}},
        "flat-one": {"provider": "custom", "limit": {"context": 4}},
    }))
    cat = app.ModelCatalog()
    assert [m.model_id for m in cat.find_model("glm-x")] == ["glm-x"]
    assert [m.model_id for m in cat.find_model("flat-one")] == ["flat-one"]
    # A later save must not drop the grouped entries.
    assert cat.save_custom_model("another", {"limit": {"context": 5}}) is True
    assert [m.model_id for m in cat.find_model("glm-x")] == ["glm-x"]


def test_fetch_online_rejects_wrong_shape_and_keeps_cache(tmp_path, monkeypatch):
    """A 200 response with the wrong shape must not replace the cache (CAT-05)."""
    import http.server
    import threading
    import socketserver

    bodies = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            payload = bodies[self.path].encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass

    cache = tmp_path / "catalog_cache.json"
    monkeypatch.setattr(app, "CATALOG_CACHE", cache)
    cache.write_text(json_dump({"zz": {"models": {"kept-model": {"limit": {"context": 7}}}}}))
    bytes_before = cache.read_bytes()

    srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        cat = app.ModelCatalog()
        cat.load(cache)

        bodies["/openai-models"] = json_dump({"object": "list", "data": [{"id": "x"}]})
        ok, msg, _ = cat.fetch_online(base + "/openai-models")
        assert ok is False
        assert "invalid" in msg.lower()
        assert cache.read_bytes() == bytes_before
        assert cat.find_model("kept-model"), "in-memory catalog untouched"

        bodies["/good"] = json_dump({"zz": {"models": {"new-model": {"limit": {"context": 9}}}}})
        ok, _, _ = cat.fetch_online(base + "/good")
        assert ok is True
        assert cat.find_model("new-model")
    finally:
        srv.shutdown()
        srv.server_close()
