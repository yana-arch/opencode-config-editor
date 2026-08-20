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
    assert all(m.model_id == "glm-5.2" for m in matches)
    # Unknown id returns empty without error.
    assert cat.find_model("definitely-not-a-real-model-xyz") == []