"""Tests for ModelCatalog indexing used by find_model()."""
import pytest

from conftest import app


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