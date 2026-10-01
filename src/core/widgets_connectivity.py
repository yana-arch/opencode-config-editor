# Connectivity & Health Check GUI Components
# ---------------------------------------------------------------------------

# Exact npm packages whose endpoints can be tested with an API key, and the
# matching fetch adapter. Package names are matched whole (not by substring) so
# e.g. '@ai-sdk/google-vertex' is never probed against AI Studio.
_KNOWN_PROVIDER_PACKAGES = {
    "@ai-sdk/anthropic": "anthropic",
    "@ai-sdk/openai": "openai",
    "@ai-sdk/openai-compatible": "openai",
    "@ai-sdk/google": "gemini",
}

# Default endpoint per first-party package, keyed by npm name (not by adapter)
# so '@ai-sdk/openai-compatible' can be excluded.
_PACKAGE_DEFAULT_URLS = {
    "@ai-sdk/anthropic": "https://api.anthropic.com",
    "@ai-sdk/openai": "https://api.openai.com/v1",
    "@ai-sdk/google": "https://generativelanguage.googleapis.com",
}

# Default endpoint per adapter, for providers that are configured with just a
# key (the docs' own 'provider.anthropic.options.apiKey' example has no npm
# and no baseURL). The key is the provider id opencode ships under.
_BUILTIN_PROVIDERS = {
    "anthropic": ("anthropic", "https://api.anthropic.com"),
    "openai": ("openai", "https://api.openai.com/v1"),
    "google": ("gemini", "https://generativelanguage.googleapis.com"),
}


def resolve_provider_target(key: str, pdata: dict, config_dir: Optional[Path] = None):
    """Work out which endpoint and adapter to test for one provider entry.

    Returns (adapter, base_url, api_key, error). 'error' is non-empty when the
    provider cannot be tested at all (no endpoint and no known package); the
    placeholder variables in options are expanded here.
    """
    opts = pdata.get("options") if isinstance(pdata.get("options"), dict) else {}
    base_url = resolve_config_placeholders(opts.get("baseURL", ""), config_dir)
    api_key = resolve_config_placeholders(opts.get("apiKey", ""), config_dir)
    npm = pdata.get("npm", "") or ""
    if not isinstance(npm, str):
        npm = ""

    adapter = _KNOWN_PROVIDER_PACKAGES.get(npm)
    if adapter is None and npm not in ("", None):
        # Unknown package: only test it if it configures its own baseURL.
        return "openai", base_url, api_key, ""

    if adapter is None:
        builtin = _BUILTIN_PROVIDERS.get(key)
        if builtin is None:
            return "openai", base_url, api_key, ""
        adapter, default_url = builtin
        return adapter, base_url or default_url, api_key, ""

    # Only the first-party packages get a default endpoint. openai-compatible
    # is excluded on purpose: it fronts other vendors (OpenRouter, Ollama,
    # vLLM), so defaulting it to api.openai.com would ship the user's key to
    # the wrong vendor. It must configure its own baseURL.
    default_url = _PACKAGE_DEFAULT_URLS.get(npm)
    return adapter, base_url or (default_url or ""), api_key, ""


class ProviderPingWorker(QThread):
    """Background worker to test a provider connection without freezing the GUI."""
    finished_one = Signal(str, object)  # provider_key, ConnectionTestResult

    def __init__(self, providers_to_test: Dict[str, dict], config_dir: Optional[Path] = None):
        super().__init__()
        self.providers_to_test = providers_to_test
        self.config_dir = config_dir

    def run(self):
        for key, pdata in self.providers_to_test.items():
            if self.isInterruptionRequested():
                return
            if not isinstance(pdata, dict):
                continue

            adapter, base_url, api_key, error = resolve_provider_target(
                key, pdata, self.config_dir
            )

            if error:
                res = ConnectionTestResult(success=False, message=error)
            elif not base_url:
                npm = pdata.get("npm", "") or ""
                if npm:
                    msg = (f"'{npm}' cannot be tested: configure options.baseURL "
                           "in the provider to test this endpoint.")
                else:
                    msg = "No baseURL configured for this provider."
                res = ConnectionTestResult(success=False, message=msg)
            else:
                res = test_provider_connection(
                    base_url=base_url,
                    api_key=api_key,
                    adapter=adapter,
                    timeout=12,
                    allow_local=True,
                )
            self.finished_one.emit(key, res)


class ProviderHealthCheckDialog(QDialog):
    """Dialog to run live health checks on all configured providers."""

    def __init__(self, parent=None, providers: Optional[dict] = None, auto_run: bool = True,
                 config_path: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("⚡ Provider Connectivity & Health Check")
        self.setMinimumSize(780, 520)
        self.providers = providers or {}
        self.results: Dict[str, ConnectionTestResult] = {}
        self.worker: Optional[ProviderPingWorker] = None
        # {file:} paths resolve relative to the config file being edited; the
        # default is the global opencode config dir.
        if config_path:
            self.config_dir = Path(config_path).expanduser().parent
        else:
            self.config_dir = Path.home() / ".config" / "opencode"

        layout = QVBoxLayout(self)

        # Header description
        info = QLabel(
            "Test endpoint reachability, response latency, authentication keys, and discovered models for your configured providers."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; margin-bottom: 6px;")
        layout.addWidget(info)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        layout.addWidget(self.progress)

        # Splitter: Left table, right details
        splitter = QSplitter(Qt.Horizontal)

        # Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Provider", "Status", "Latency", "Models"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.table)

        # Right side: Detail box
        right_box = QGroupBox("Health Diagnostic Details")
        right_lay = QVBoxLayout(right_box)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("Select a provider row to view detailed response and model list...")
        right_lay.addWidget(self.detail_text)
        splitter.addWidget(right_box)
        splitter.setSizes([450, 330])

        layout.addWidget(splitter, 1)

        # Buttons
        btns = QHBoxLayout()
        self.run_btn = QPushButton("▶ Run All Tests")
        self.run_btn.clicked.connect(self.run_tests)
        btns.addWidget(self.run_btn)

        self.retest_sel_btn = QPushButton("↺ Test Selected")
        self.retest_sel_btn.clicked.connect(self._test_selected)
        btns.addWidget(self.retest_sel_btn)

        btns.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

        self._populate_table()
        if auto_run and self.providers:
            self.run_tests()

    def _stop_worker(self):
        """Stop the running worker cooperatively and wait for it to unwind.

        QThread.terminate() is never used: killing a thread mid-request can
        deadlock the interpreter's own locks and freeze the editor.
        """
        worker = self.worker
        if not worker or not worker.isRunning():
            self.worker = None
            return
        # Parent the thread to the dialog so Qt keeps it alive while it drains.
        worker.setParent(self)
        worker.requestInterruption()
        try:
            worker.finished_one.disconnect()
        except (RuntimeError, TypeError):
            pass
        if worker.wait(3000):
            # Fully unwound: safe to drop the last reference.
            self.worker = None
        # else: a request is still blocked (DNS, dropped SYN, silent server).
        # Keep the reference and let _on_all_finished clear it, otherwise the
        # QThread is destroyed while running and the process aborts.

    def _busy(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def _set_running(self, running: bool):
        """Keep both start buttons disabled for the whole run."""
        self.run_btn.setEnabled(not running)
        self.retest_sel_btn.setEnabled(not running)
        if running:
            self.progress.show()
        else:
            self.progress.hide()

    def closeEvent(self, event):
        self._stop_worker()
        super().closeEvent(event)

    def reject(self):
        self._stop_worker()
        super().reject()

    def accept(self):
        self._stop_worker()
        super().accept()

    def _populate_table(self):
        self.table.setRowCount(0)
        for key in sorted(self.providers.keys()):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(key))
            self.table.setItem(r, 1, QTableWidgetItem("Ready"))
            self.table.setItem(r, 2, QTableWidgetItem("-"))
            self.table.setItem(r, 3, QTableWidgetItem("-"))

    def run_tests(self):
        if not self.providers:
            QMessageBox.information(self, "No Providers", "No providers configured to test.")
            return
        if self._busy():
            return

        self._set_running(True)
        self.progress.setRange(0, len(self.providers))
        self.progress.setValue(0)

        for r in range(self.table.rowCount()):
            self.table.setItem(r, 1, QTableWidgetItem("Testing..."))
            self.table.setItem(r, 2, QTableWidgetItem("-"))
            self.table.setItem(r, 3, QTableWidgetItem("-"))

        self.worker = ProviderPingWorker(self.providers, self.config_dir)
        self.worker.finished_one.connect(self._on_provider_tested)
        self.worker.finished.connect(self._on_all_finished)
        self.worker.start()

    def _test_selected(self):
        selected_rows = sorted({i.row() for i in self.table.selectedItems()})
        if not selected_rows:
            QMessageBox.information(self, "Selection", "Please select a provider row to test.")
            return
        if self._busy():
            return

        subset = {}
        for r in selected_rows:
            key = self.table.item(r, 0).text()
            if key in self.providers:
                subset[key] = self.providers[key]
                self.table.setItem(r, 1, QTableWidgetItem("Testing..."))

        self._set_running(True)
        self.worker = ProviderPingWorker(subset, self.config_dir)
        self.worker.finished_one.connect(self._on_provider_tested)
        self.worker.finished.connect(self._on_all_finished)
        self.worker.start()

    def _on_provider_tested(self, key: str, res: ConnectionTestResult):
        self.results[key] = res
        self.progress.setValue(self.progress.value() + 1)

        # Find row
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).text() == key:
                if res.success:
                    status_item = QTableWidgetItem("✓ OK")
                    status_item.setForeground(Qt.darkGreen)
                    lat_item = QTableWidgetItem(f"{res.latency_ms:.0f} ms")
                    mod_item = QTableWidgetItem(str(res.model_count or 0))
                else:
                    status_item = QTableWidgetItem("✗ Error")
                    status_item.setForeground(Qt.red)
                    lat_item = QTableWidgetItem(f"{res.latency_ms:.0f} ms" if res.latency_ms else "-")
                    mod_item = QTableWidgetItem("-")

                self.table.setItem(r, 1, status_item)
                self.table.setItem(r, 2, lat_item)
                self.table.setItem(r, 3, mod_item)
                break

        self._on_selection_changed()

    def _on_all_finished(self):
        self.worker = None
        self._set_running(False)

    def _on_selection_changed(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        key = self.table.item(row, 0).text()
        res = self.results.get(key)
        if not res:
            self.detail_text.setHtml(
                f"<h3>{html.escape(key)}</h3><p>Testing or not yet run...</p>"
            )
            return

        # Escape every provider-controlled value: raw errors look like
        # '<urlopen error ...>', which setHtml() would swallow as a tag.
        esc_key = html.escape(key)
        color = "green" if res.success else "red"
        out = f"<h3>Provider: <span style='color:{color}'>{esc_key}</span></h3>"
        out += f"<p><b>Status:</b> {'SUCCESS' if res.success else 'FAILED'}</p>"
        out += f"<p><b>Latency:</b> {res.latency_ms:.1f} ms</p>"
        out += f"<p><b>Message:</b> {html.escape(res.message)}</p>"

        if res.models:
            out += f"<h4>Discovered Models ({len(res.models)}):</h4><ul>"
            for m in res.models:
                out += f"<li><code>{html.escape(str(m))}</code></li>"
            out += "</ul>"
        elif res.raw_error:
            out += ("<h4>Diagnostic Log:</h4>"
                    f"<pre style='background:#f5f5f5; padding:6px;'>{html.escape(res.raw_error)}</pre>")

        self.detail_text.setHtml(out)
