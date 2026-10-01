"""Dialog-level regressions for the provider health check.

HC-1 cooperative stop, HC-2 single-run guard, HC-7 escaped details.
All network access is stubbed: the per-provider call is monkeypatched so no
sockets are opened and no timing races are involved.
"""
import time

import pytest

from conftest import HAS_QT, app

pytestmark = pytest.mark.skipif(not HAS_QT, reason="PySide6 not available - skipping GUI tests")


@pytest.fixture
def no_network(monkeypatch):
    """Replace the connectivity call the worker resolves at run time."""
    calls = []

    def fake(base_url, api_key="", adapter="openai", timeout=10, allow_local=True):
        calls.append({"base_url": base_url, "api_key": api_key, "adapter": adapter})
        return app.ConnectionTestResult(
            success=True, message="ok", latency_ms=1.0, model_count=1, models=["m1"])

    monkeypatch.setattr(app, "test_provider_connection", fake)
    return calls


def _forbid_terminate(self):
    """Deterministic lock: QThread.terminate() must never be used (HC-1)."""
    raise AssertionError("QThread.terminate() is not allowed; stop cooperatively")


def _gated(gate, timeout=10.0, sink=None):
    """A fake provider call that blocks on `gate` and then returns a result."""

    def fake(base_url, api_key="", adapter="openai", timeout=10, allow_local=True):
        if sink is not None:
            sink.append(base_url)
        gate.wait(timeout)
        return app.ConnectionTestResult(
            success=True, message="ok", latency_ms=1.0, model_count=1, models=["m1"])

    return fake


def _drain(qapp, dialog, timeout_s=5.0):
    """Pump events until the worker's finished handler ran. Returns fast."""
    import time
    end = time.time() + timeout_s
    while time.time() < end:
        qapp.processEvents()
        if dialog.worker is None:
            qapp.processEvents()
            return True
        time.sleep(0.005)
    qapp.processEvents()
    return dialog.worker is None


PROVIDERS = {
    "anthropic": {"options": {"apiKey": "sk-ant"}},
    "openai": {"options": {"baseURL": "http://127.0.0.1:1/v1", "apiKey": "k"}},
    "vertex": {"npm": "@ai-sdk/google-vertex", "options": {"apiKey": "S"}},
}


# ---------------------------------------------------------------- HC-1 -----


def test_stop_worker_unwinds_thread(qapp, no_network, monkeypatch):
    """HC-1: stopping unwinds the worker and must never terminate() it."""
    import threading

    monkeypatch.setattr(app.ProviderPingWorker, "terminate", _forbid_terminate)
    gate = threading.Event()
    monkeypatch.setattr(app, "test_provider_connection", _gated(gate))
    dlg = app.ProviderHealthCheckDialog(providers=PROVIDERS, auto_run=True)
    qapp.processEvents()
    worker = dlg.worker
    assert worker.isRunning()

    gate.set()  # let the in-flight request finish so wait() succeeds
    dlg._stop_worker()

    assert not worker.isRunning(), "thread must unwind, not stay half-killed"
    assert dlg.worker is None, "a fully stopped worker may be released"
    qapp.processEvents()


def test_stopped_worker_is_still_referenced_when_wait_times_out(
        qapp, no_network, monkeypatch):
    """A request still blocked at close time must keep its worker alive.

    Dropping the last reference to a running QThread aborts the process.
    """
    import threading

    monkeypatch.setattr(app.ProviderPingWorker, "terminate", _forbid_terminate)
    gate = threading.Event()
    monkeypatch.setattr(app, "test_provider_connection", _gated(gate, timeout=30.0))
    dlg = app.ProviderHealthCheckDialog(providers=PROVIDERS, auto_run=True)
    qapp.processEvents()
    worker = dlg.worker
    assert worker.isRunning()

    # The gate stays shut, so wait(3000) times out with the thread still busy.
    dlg._stop_worker()

    assert worker.isRunning(), "precondition: request is still blocked"
    assert dlg.worker is worker, "the running worker must stay referenced"

    gate.set()
    assert worker.wait(5000), "worker should finish once the request returns"
    qapp.processEvents()
    assert dlg.worker is None, "reference released after it unwinds"


def test_worker_releases_interruption_check(qapp, no_network, monkeypatch):
    """The run loop must observe the interruption flag and return."""
    import threading

    gate = threading.Event()
    tested = []

    def blocked(base_url, api_key="", adapter="openai", timeout=10, allow_local=True):
        tested.append(base_url)
        gate.wait(2.0)
        return app.ConnectionTestResult(success=True, message="ok")

    monkeypatch.setattr(app, "test_provider_connection", blocked)
    many = {f"p{i}": {"options": {"baseURL": f"http://x.test/{i}"}} for i in range(50)}
    worker = app.ProviderPingWorker(many, None)
    results = []
    worker.finished_one.connect(lambda k, r: results.append(k))
    worker.start()
    deadline = time.time() + 5.0
    while not tested and time.time() < deadline:
        qapp.processEvents()
    assert tested, "worker never started"

    worker.requestInterruption()
    gate.set()
    assert worker.wait(5000), "worker must return at the interruption check"
    qapp.processEvents()
    assert len(results) < 50, "worker must stop at the interruption check"


def test_close_during_run_returns_promptly(qapp, no_network, monkeypatch):
    """Closing mid-run must not block the GUI thread (HC-1 deadlock)."""
    monkeypatch.setattr(app.ProviderPingWorker, "terminate", _forbid_terminate)

    def slow(base_url, api_key="", adapter="openai", timeout=10, allow_local=True):
        time.sleep(0.05)
        return app.ConnectionTestResult(success=True, message="ok")

    monkeypatch.setattr(app, "test_provider_connection", slow)
    many = {f"p{i}": {"options": {"baseURL": "http://x.test"}} for i in range(200)}
    dlg = app.ProviderHealthCheckDialog(providers=many, auto_run=True)
    qapp.processEvents()
    assert dlg.worker is not None and dlg.worker.isRunning()

    t0 = time.perf_counter()
    dlg.reject()
    elapsed = time.perf_counter() - t0

    assert elapsed < 4.0, f"close blocked for {elapsed:.1f}s"
    assert not dlg.worker or not dlg.worker.isRunning()


def test_stopped_worker_emits_no_more_results(qapp, no_network, monkeypatch):
    import threading

    monkeypatch.setattr(app.ProviderPingWorker, "terminate", _forbid_terminate)
    gate = threading.Event()
    monkeypatch.setattr(app, "test_provider_connection", _gated(gate, timeout=30.0))
    many = {f"p{i}": {"options": {"baseURL": "http://x.test"}} for i in range(100)}
    dlg = app.ProviderHealthCheckDialog(providers=many, auto_run=True)
    qapp.processEvents()
    dlg.reject()
    results_after_close = len(dlg.results)
    gate.set()
    for _ in range(50):
        qapp.processEvents()
    assert len(dlg.results) == results_after_close


# ---------------------------------------------------------------- HC-2 -----


def test_second_start_is_refused_while_worker_runs(qapp, no_network, monkeypatch):
    import threading

    gate = threading.Event()
    monkeypatch.setattr(app, "test_provider_connection", _gated(gate, timeout=30.0))
    dlg = app.ProviderHealthCheckDialog(providers=PROVIDERS, auto_run=True)
    first = dlg.worker
    qapp.processEvents()
    assert first.isRunning()

    dlg.table.selectRow(1)
    dlg._test_selected()

    assert dlg.worker is first, "running worker must not be replaced"
    assert first.isRunning()
    assert dlg.run_btn.isEnabled() is False
    assert dlg.retest_sel_btn.isEnabled() is False

    gate.set()
    assert _drain(qapp, dlg)
    assert dlg.run_btn.isEnabled() is True
    assert dlg.retest_sel_btn.isEnabled() is True


def test_run_all_is_refused_while_worker_runs(qapp, no_network, monkeypatch):
    import threading

    gate = threading.Event()
    monkeypatch.setattr(app, "test_provider_connection", _gated(gate, timeout=30.0))
    dlg = app.ProviderHealthCheckDialog(providers=PROVIDERS, auto_run=True)
    first = dlg.worker
    dlg.run_tests()
    assert dlg.worker is first
    gate.set()
    _drain(qapp, dlg)


def test_run_all_and_test_selected_both_work_when_idle(qapp, no_network):
    dlg = app.ProviderHealthCheckDialog(providers=PROVIDERS, auto_run=False)
    dlg.run_tests()
    assert _drain(qapp, dlg)
    assert len(dlg.results) == len(PROVIDERS)

    dlg.table.selectRow(0)
    dlg._test_selected()
    assert _drain(qapp, dlg)


# ------------------------------------------------------------- HC-3/4/8 ----


def test_worker_resolves_env_placeholder_before_request(qapp, no_network, monkeypatch):
    monkeypatch.setenv("OCCE_DLG_KEY", "sk-real")
    provs = {"p": {"npm": "@ai-sdk/openai", "options": {"apiKey": "{env:OCCE_DLG_KEY}"}}}
    dlg = app.ProviderHealthCheckDialog(providers=provs, auto_run=False)
    dlg.run_tests()
    assert _drain(qapp, dlg)
    assert no_network[0]["api_key"] == "sk-real"


def test_worker_resolves_file_placeholder_against_config_path(qapp, no_network, tmp_path):
    (tmp_path / "k.txt").write_text("sk-from-file")
    provs = {"p": {"npm": "@ai-sdk/openai", "options": {"apiKey": "{file:k.txt}"}}}
    cfg = tmp_path / "opencode.json"
    dlg = app.ProviderHealthCheckDialog(
        providers=provs, auto_run=False, config_path=str(cfg))
    assert dlg.config_dir == tmp_path
    dlg.run_tests()
    assert _drain(qapp, dlg)
    assert no_network[0]["api_key"] == "sk-from-file"


def test_builtin_provider_without_npm_is_tested(qapp, no_network):
    dlg = app.ProviderHealthCheckDialog(
        providers={"anthropic": {"options": {"apiKey": "sk-ant"}}}, auto_run=False)
    dlg.run_tests()
    assert _drain(qapp, dlg)
    assert no_network[0]["base_url"] == "https://api.anthropic.com"
    assert no_network[0]["adapter"] == "anthropic"
    assert dlg.results["anthropic"].success is True


def test_untestable_package_is_reported_without_sending_key(qapp, no_network):
    provs = {"vertex": {"npm": "@ai-sdk/google-vertex", "options": {"apiKey": "SECRET"}}}
    dlg = app.ProviderHealthCheckDialog(providers=provs, auto_run=False)
    dlg.run_tests()
    assert _drain(qapp, dlg)
    assert no_network == [], "unknown package must not be probed"
    res = dlg.results["vertex"]
    assert res.success is False
    assert "SECRET" not in res.message


def test_openai_compatible_gets_no_default_endpoint():
    """@ai-sdk/openai-compatible fronts other vendors; never default it."""
    _, base, key, _ = app.resolve_provider_target(
        "openrouter", {"npm": "@ai-sdk/openai-compatible", "options": {"apiKey": "k"}})
    assert base == ""
    assert key == "k"


def test_openai_compatible_with_unset_env_url_sends_nothing(qapp, no_network, monkeypatch):
    monkeypatch.delenv("UNSET_BASE", raising=False)
    provs = {"or": {"npm": "@ai-sdk/openai-compatible",
                    "options": {"baseURL": "{env:UNSET_BASE}", "apiKey": "sk-or-SECRET"}}}
    dlg = app.ProviderHealthCheckDialog(providers=provs, auto_run=False)
    dlg.run_tests()
    assert _drain(qapp, dlg)
    assert no_network == [], "key must not be sent to api.openai.com"
    res = dlg.results["or"]
    assert res.success is False
    assert "sk-or-SECRET" not in res.message


def test_openai_compatible_with_own_base_url_is_tested(qapp, no_network):
    provs = {"ollama": {"npm": "@ai-sdk/openai-compatible",
                        "options": {"baseURL": "http://127.0.0.1:11434/v1", "apiKey": "k"}}}
    dlg = app.ProviderHealthCheckDialog(providers=provs, auto_run=False)
    dlg.run_tests()
    assert _drain(qapp, dlg)
    assert no_network[0]["base_url"] == "http://127.0.0.1:11434/v1"



# ---------------------------------------------------------------- HC-7 -----


def test_raw_error_shown_verbatim_in_diagnostic_log(qapp):
    dlg = app.ProviderHealthCheckDialog(providers={"p": {}}, auto_run=False)
    dlg.results["p"] = app.ConnectionTestResult(
        success=False, message="Network error: Connection refused",
        raw_error="<urlopen error [Errno 111] Connection refused>")
    dlg.table.selectRow(0)
    qapp.processEvents()
    text = dlg.detail_text.toPlainText()
    assert "<urlopen error [Errno 111] Connection refused>" in text


def test_details_html_escapes_markup(qapp):
    dlg = app.ProviderHealthCheckDialog(providers={"p": {}}, auto_run=False)
    dlg.results["p"] = app.ConnectionTestResult(
        success=False, message="a <b>&</b> error", raw_error="x<y&z")
    dlg.table.selectRow(0)
    qapp.processEvents()
    shown = dlg.detail_text.toPlainText()
    assert "a <b>&</b> error" in shown


def test_model_ids_are_escaped(qapp):
    dlg = app.ProviderHealthCheckDialog(providers={"p": {}}, auto_run=False)
    dlg.results["p"] = app.ConnectionTestResult(
        success=True, message="ok", models=["a<b&c"])
    dlg.table.selectRow(0)
    qapp.processEvents()
    assert "a<b&c" in dlg.detail_text.toPlainText()