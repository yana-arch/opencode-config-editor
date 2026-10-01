"""Tests for ModelsManagerDialog's "Fetch from API" path.

The fetch dialog is replaced by a stub (it lives in widgets_catalog.py and owns
its own worker thread), so these tests exercise the caller-side contract only:
the fetch must not touch the live provider until the Models dialog is accepted.
"""
import pytest

from conftest import app

pytestmark = pytest.mark.skipif(not app.HAS_QT, reason="PySide6 not available")


class FakeCatalog:
    def loaded(self):
        return False


class FakeApp:
    def __init__(self, providers):
        self.cfg = type("C", (), {"data": {"provider": providers, "mcp": {}}})()
        self.model_catalog = FakeCatalog()
        self.dirty = False

    def mark_dirty(self):
        self.dirty = True

    def snapshot_state(self):
        pass

    def load_model_catalog(self):
        return False


class _Field:
    def __init__(self, text):
        self._t = text

    def text(self):
        return self._t


class _Check:
    def __init__(self, value):
        self._v = value

    def isChecked(self):
        return self._v


class StubFetchDialog:
    """Stands in for FetchProviderModelsDialog."""

    result_code = app.QDialog.Rejected
    adapter = "openai"
    url = "https://other.example/v1"
    api_key = "new-key"

    def __init__(self, parent, catalog=None, provider_key="", providers=None,
                 lock_key=False):
        self.provider_key = provider_key
        self.providers = providers
        self.lock_key = lock_key
        self.key_edit = _Field(provider_key)
        self.url_edit = _Field(StubFetchDialog.url)
        self.apikey_edit = _Field(StubFetchDialog.api_key)
        self.save_apikey_check = _Check(True)
        self.sync_check = _Check(False)
        self.selected_models = {"m3": {}}
        self.fetched_models = {"m3": {}}

    def _current_adapter(self):
        return StubFetchDialog.adapter

    def exec(self):
        return StubFetchDialog.result_code

    def api_base_url(self):
        return app.api_base_url_for(self._current_adapter(),
                                    self.url_edit.text())


@pytest.fixture
def fetch(monkeypatch, qapp):
    """Install the stub and silence the post-fetch info popup."""
    monkeypatch.setattr(app, "FetchProviderModelsDialog", StubFetchDialog)
    monkeypatch.setattr(app.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(app.QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(app, "_confirm", lambda *a, **k: True)

    def run(adapter="openai", accept_fetch=True, url=None, provider=None):
        StubFetchDialog.adapter = adapter
        StubFetchDialog.result_code = (
            app.QDialog.Accepted if accept_fetch else app.QDialog.Rejected)
        if url is not None:
            StubFetchDialog.url = url
        live = provider or {"p": {"npm": "@ai-sdk/openai-compatible",
                                 "models": {"m1": {}, "m2": {}},
                                 "options": {"baseURL": "https://old/v1"}}}
        key = next(iter(live))
        fake = FakeApp(live)
        parent = app.QWidget()
        dlg = app.ModelsManagerDialog(parent, key, live[key])
        dlg.app = fake
        dlg._parent_keepalive = parent
        return dlg, live, fake

    yield run
    StubFetchDialog.result_code = app.QDialog.Rejected


# ---------------------------------------------------------------------------
# F5: nothing reaches the live provider until the Models dialog is accepted
# ---------------------------------------------------------------------------

def test_cancelled_fetch_leaves_live_provider_untouched(fetch):
    dlg, live, fake = fetch(accept_fetch=False)
    dlg._fetch_from_api()
    assert sorted(live["p"]["models"]) == ["m1", "m2"]
    assert live["p"]["options"] == {"baseURL": "https://old/v1"}
    assert fake.dirty is False


def test_accepted_fetch_then_cancel_leaves_live_provider_untouched(fetch):
    dlg, live, fake = fetch(accept_fetch=True)
    dlg._fetch_from_api()
    # Still untouched before the Models dialog is accepted.
    assert sorted(live["p"]["models"]) == ["m1", "m2"]
    assert live["p"]["options"] == {"baseURL": "https://old/v1"}
    dlg.reject()
    assert sorted(live["p"]["models"]) == ["m1", "m2"]
    assert live["p"]["options"] == {"baseURL": "https://old/v1"}
    assert fake.dirty is False


def test_accepted_fetch_then_accept_commits_options(fetch):
    dlg, live, fake = fetch(accept_fetch=True)
    dlg._fetch_from_api()
    dlg.accept()
    assert live["p"]["options"]["baseURL"] == "https://other.example/v1"
    assert live["p"]["options"]["apiKey"] == "new-key"


def test_fetch_shows_new_models_in_the_working_copy(fetch):
    dlg, live, fake = fetch(accept_fetch=True)
    dlg._fetch_from_api()
    assert "m3" in dlg.models


# ---------------------------------------------------------------------------
# F2: a list/catalog format must not persist the listing URL as baseURL
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("adapter", ["models_dev", "generic"])
def test_list_format_never_writes_baseurl(fetch, adapter):
    provider = {"q": {"models": {}, "options": {"baseURL": "https://keep/v1"}}}
    dlg, live, fake = fetch(adapter=adapter, accept_fetch=True, provider=provider)
    dlg._fetch_from_api()
    dlg.accept()
    assert live["q"]["options"]["baseURL"] == "https://keep/v1"


def test_sdk_format_persists_the_api_base(fetch):
    provider = {"q": {"models": {}, "options": {"baseURL": "https://keep/v1"}}}
    dlg, live, fake = fetch(adapter="anthropic", accept_fetch=True, provider=provider,
                            url="https://api.anthropic.com/v1")
    dlg._fetch_from_api()
    dlg.accept()
    assert live["q"]["options"]["baseURL"] == "https://api.anthropic.com/v1"


# ---------------------------------------------------------------------------
# F11: the provider key is locked for an existing provider
# ---------------------------------------------------------------------------

def test_fetch_from_models_dialog_locks_the_provider_key(monkeypatch, fetch):
    seen = {}
    original_init = StubFetchDialog.__init__

    def spy(self, parent, catalog=None, provider_key="", providers=None,
            lock_key=False):
        seen["lock_key"] = lock_key
        original_init(self, parent, catalog=catalog, provider_key=provider_key,
                      providers=providers, lock_key=lock_key)

    monkeypatch.setattr(StubFetchDialog, "__init__", spy)
    dlg, _live, _fake = fetch(accept_fetch=False)
    dlg._fetch_from_api()
    assert seen["lock_key"] is True


@pytest.mark.parametrize("lock", [True, False])
def test_fetch_dialog_key_field_read_only_follows_lock(qapp, monkeypatch, lock):
    monkeypatch.setattr(app, "_confirm", lambda *a, **k: True)
    dlg = app.FetchProviderModelsDialog(
        None, provider_key="p", providers={"p": {"models": {}}},
        lock_key=lock)
    assert dlg.key_edit.isReadOnly() is lock
    assert dlg.apikey_edit.isReadOnly() is lock
