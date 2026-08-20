"""Tests for match ranking helpers (_format_completeness, _sort_matches)."""
from conftest import app


def _fmt(provider="p", model_id="m", **kw):
    return app.ModelFormat(
        provider=provider,
        model_id=model_id,
        name=kw.pop("name", "m"),
        context=kw.get("context"),
        output=kw.get("output"),
        cost_in=kw.get("cost_in"),
        cost_out=kw.get("cost_out"),
        cost_cache_read=kw.get("cost_cache_read"),
        cost_cache_write=kw.get("cost_cache_write"),
    )


def test_completeness_empty_format():
    # Bare formats still score 1: default (non-inferred) modalities count.
    assert app._format_completeness(_fmt()) == 1


def test_completeness_counts_fields():
    full = _fmt(context=100, output=50, cost_in=1.0, cost_out=2.0,
                cost_cache_read=0.1, cost_cache_write=1.5)
    assert app._format_completeness(full) >= 6


def test_sort_prefers_same_provider():
    a = _fmt(provider="zhipuai", context=100)
    b = _fmt(provider="richer", context=200, output=100, cost_in=1.0)
    out = app._sort_matches([a, b], "zhipuai")
    assert out[0].provider == "zhipuai"


def test_sort_breaks_ties_by_completeness():
    sparse = _fmt(provider="a")
    rich = _fmt(provider="b", context=200, output=100, cost_in=1.0)
    out = app._sort_matches([sparse, rich], "none-of-them")
    assert out[0].provider == "b"


def test_sort_stable_for_equal_formats():
    m1 = _fmt(provider="a", context=100)
    m2 = _fmt(provider="b", context=100)
    out = app._sort_matches([m1, m2], "other")
    assert [m.provider for m in out] == ["a", "b"]


def test_sort_single_match():
    m = _fmt(provider="only")
    assert app._sort_matches([m], "x") == [m]
