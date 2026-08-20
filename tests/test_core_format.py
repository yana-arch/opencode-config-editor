"""Unit tests for the core model-format normalization and catalog matching.

Covers the functions introduced by the "Model Format Match & Apply" feature:
_parse_modalities, build_spec_from_format, _merge_model_spec, _resolve_match
and apply_catalog_to_config.
"""
import pytest

from conftest import app


def _fmt(**kw):
    """Convenience ModelFormat factory with sensible defaults."""
    return app.ModelFormat(
        provider=kw.get("provider", "prov"),
        model_id=kw.get("model_id", "m1"),
        name=kw.get("name", "m1"),
        context=kw.get("context"),
        output=kw.get("output"),
        cost_in=kw.get("cost_in"),
        cost_out=kw.get("cost_out"),
    )


# ---------------------------------------------------------------------------
# _parse_modalities
# ---------------------------------------------------------------------------

def test_parse_modalities_structured():
    mods = app._parse_modalities(
        {"modalities": {"input": ["text", "image"], "output": ["text"]}})
    assert mods.input_mods == ["text", "image"]
    assert mods.output_mods == ["text"]
    assert not mods.inferred
    assert mods.has_image_input


def test_parse_modalities_list_infers_output():
    mods = app._parse_modalities({"modalities": ["text", "image"]})
    assert mods.input_mods == ["text", "image"]
    assert mods.output_mods == ["text"]
    assert mods.inferred


def test_parse_modalities_missing_falls_back_to_text():
    mods = app._parse_modalities({})
    assert mods.input_mods == ["text"]
    assert mods.output_mods == ["text"]


def test_parse_modalities_attachment_implies_image():
    mods = app._parse_modalities({"attachment": True})
    assert "image" in mods.input_mods
    assert mods.inferred


def test_parse_modalities_via_alias_key():
    mods = app._parse_modalities({"supported_media": ["text", "pdf"]})
    assert mods.input_mods == ["text", "pdf"]


# ---------------------------------------------------------------------------
# build_spec_from_format
# ---------------------------------------------------------------------------

def test_build_spec_from_format_basic():
    spec = app.build_spec_from_format(_fmt(context=128000, output=4096))
    assert spec["limit"] == {"context": 128000, "output": 4096}
    assert "name" not in spec  # name == model_id, so omitted


def test_build_spec_from_format_omits_none():
    spec = app.build_spec_from_format(_fmt())
    assert "limit" not in spec
    assert "cost" not in spec


def test_build_spec_from_format_costs():
    spec = app.build_spec_from_format(
        _fmt(cost_in=2.0, cost_out=10.0))
    assert spec["cost"] == {"input": 2.0, "output": 10.0}


def test_build_spec_from_format_name_included_when_distinct():
    spec = app.build_spec_from_format(_fmt(name="Fancy Model"))
    assert spec["name"] == "Fancy Model"


def test_build_spec_from_format_modalities_omitted_when_inferred():
    fmt = _fmt()
    fmt.modalities = app.Modalities(input_mods=["text"], output_mods=["text"], inferred=True)
    spec = app.build_spec_from_format(fmt)
    assert "modalities" not in spec


# ---------------------------------------------------------------------------
# _merge_model_spec
# ---------------------------------------------------------------------------

def test_merge_fills_missing_without_overwrite():
    merged = app._merge_model_spec(
        {"name": "mine"}, {"limit": {"context": 128000}}, overwrite=False)
    assert merged["limit"]["context"] == 128000
    assert merged["name"] == "mine"  # untouched


def test_merge_overwrite_replaces():
    merged = app._merge_model_spec(
        {"limit": {"context": 1000}}, {"limit": {"context": 128000}}, overwrite=True)
    assert merged["limit"]["context"] == 128000


def test_merge_without_overwrite_keeps_existing():
    merged = app._merge_model_spec(
        {"limit": {"context": 1000}}, {"limit": {"context": 128000}}, overwrite=False)
    assert merged["limit"]["context"] == 1000


def test_merge_handles_non_dict_existing():
    merged = app._merge_model_spec(None, {"limit": {"context": 128000}}, overwrite=False)
    assert merged["limit"]["context"] == 128000


def test_merge_nested_cost_partial():
    merged = app._merge_model_spec(
        {"cost": {"input": 1.0}}, {"cost": {"input": 5.0, "output": 2.0}}, overwrite=False)
    assert merged["cost"]["input"] == 1.0   # kept
    assert merged["cost"]["output"] == 2.0  # filled


# ---------------------------------------------------------------------------
# _resolve_match
# ---------------------------------------------------------------------------

def test_resolve_single_match():
    m = _fmt()
    assert app._resolve_match([m], "other") is m


def test_resolve_prefers_same_provider():
    a = _fmt(provider="anthropic", model_id="x")
    b = _fmt(provider="other", model_id="x")
    assert app._resolve_match([a, b], "anthropic") is a


def test_resolve_uses_callback_when_no_same_provider():
    a = _fmt(provider="a", model_id="x")
    b = _fmt(provider="b", model_id="x")
    picked = app._resolve_match([a, b], "nope", "x",
                                resolve_fn=lambda p, m, matches: matches[1])
    assert picked is b


def test_resolve_returns_none_when_ambiguous_and_no_callback():
    a = _fmt(provider="a", model_id="x")
    b = _fmt(provider="b", model_id="x")
    assert app._resolve_match([a, b], "nope", "x") is None


# ---------------------------------------------------------------------------
# apply_catalog_to_config
# ---------------------------------------------------------------------------

class _FakeCatalog:
    """Minimal catalog exposing just formats() and find_model()."""

    def __init__(self, fmts):
        self._fmts = fmts  # {provider: {mid: ModelFormat}}
        self._index = {}
        for pid, models in fmts.items():
            for mid in models:
                self._index.setdefault(mid, []).append(pid)

    def formats(self):
        return self._fmts

    def find_model(self, mid):
        out = []
        for pid in self._index.get(mid, []):
            if mid in self._fmts[pid]:
                out.append(self._fmts[pid][mid])
        return out


def _catalog(*formats):
    fmts = {}
    for f in formats:
        fmts.setdefault(f.provider, {})[f.model_id] = f
    return _FakeCatalog(fmts)


def test_apply_fills_missing_keeps_user_values():
    cat = _catalog(_fmt(provider="p", model_id="m1", context=128000, output=4096))
    cfg = {"p": {"models": {"m1": {"name": "mine"}}}}
    report = app.apply_catalog_to_config(cat, cfg, overwrite=False)
    assert cfg["p"]["models"]["m1"]["name"] == "mine"
    assert cfg["p"]["models"]["m1"]["limit"]["context"] == 128000
    assert any("p/m1" in x for x in report.filled)


def test_apply_overwrite_replaces():
    cat = _catalog(_fmt(provider="p", model_id="m1", context=128000))
    cfg = {"p": {"models": {"m1": {"limit": {"context": 1000}}}}}
    app.apply_catalog_to_config(cat, cfg, overwrite=True)
    assert cfg["p"]["models"]["m1"]["limit"]["context"] == 128000


def test_apply_adds_new_when_requested():
    cat = _catalog(_fmt(provider="p", model_id="m2", context=64000))
    cfg = {"p": {"models": {"m1": {"name": "x"}}}}
    app.apply_catalog_to_config(cat, cfg, add_new=True)
    assert "m2" in cfg["p"]["models"]


def test_apply_does_not_add_new_when_disabled():
    cat = _catalog(_fmt(provider="p", model_id="m2", context=64000))
    cfg = {"p": {"models": {"m1": {"name": "x"}}}}
    app.apply_catalog_to_config(cat, cfg, add_new=False)
    assert "m2" not in cfg["p"]["models"]


def test_apply_unknown_model_reported():
    cat = _catalog(_fmt(provider="p", model_id="m1", context=64000))
    cfg = {"p": {"models": {"ghost": {"name": "x"}}}}
    report = app.apply_catalog_to_config(cat, cfg)
    assert any("ghost" in u for u in report.unknown)


def test_apply_ambiguous_reported_and_unresolved_without_callback():
    cat = _catalog(_fmt(provider="a", model_id="x", context=100),
                   _fmt(provider="b", model_id="x", context=200))
    cfg = {"nope": {"models": {"x": {}}}}
    report = app.apply_catalog_to_config(cat, cfg)
    assert report.ambiguous
    assert "limit" not in cfg["nope"]["models"]["x"]


def test_apply_ambiguous_resolved_via_callback():
    cat = _catalog(_fmt(provider="a", model_id="x", context=100),
                   _fmt(provider="b", model_id="x", context=200))
    cfg = {"nope": {"models": {"x": {}}}}
    app.apply_catalog_to_config(
        cat, cfg, resolve_fn=lambda p, m, matches: matches[1])
    assert cfg["nope"]["models"]["x"]["limit"]["context"] == 200


def test_apply_report_any_changes():
    report = app.ApplyReport()
    assert not report.any_changes()
    report.filled.append("p/m")
    assert report.any_changes()