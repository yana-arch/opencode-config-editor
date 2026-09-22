# Connectivity & Health Check GUI Components
# ---------------------------------------------------------------------------
import json
from typing import Dict, Optional
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QMessageBox, QTextEdit, QGroupBox, QSplitter
)


class ProviderPingWorker(QThread):
    """Background worker to test a provider connection without freezing the GUI."""
    finished_one = Signal(str, object)  # provider_key, ConnectionTestResult

    def __init__(self, providers_to_test: Dict[str, dict]):
        super().__init__()
        self.providers_to_test = providers_to_test

    def run(self):
        for key, pdata in self.providers_to_test.items():
            if not isinstance(pdata, dict):
                continue
            opts = pdata.get("options", {}) if isinstance(pdata.get("options"), dict) else {}
            base_url = opts.get("baseURL", "")
            api_key = opts.get("apiKey", "")
            npm = pdata.get("npm", "")

            # Guess adapter
            adapter = "openai"
            if "anthropic" in npm:
                adapter = "anthropic"
            elif "google" in npm:
                adapter = "gemini"

            # If no base_url specified, use default for known npm
            if not base_url:
                if "anthropic" in npm:
                    base_url = "https://api.anthropic.com"
                elif "openai" in npm and not "openai-compatible" in npm:
                    base_url = "https://api.openai.com/v1"
                elif "google" in npm:
                    base_url = "https://generativelanguage.googleapis.com"

            if not base_url:
                res = ConnectionTestResult(
                    success=False,
                    message="No baseURL configured for this provider.",
                )
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

    def __init__(self, parent=None, providers: Optional[dict] = None, auto_run: bool = True):
        super().__init__(parent)
        self.setWindowTitle("⚡ Provider Connectivity & Health Check")
        self.setMinimumSize(780, 520)
        self.providers = providers or {}
        self.results: Dict[str, ConnectionTestResult] = {}
        self.worker: Optional[ProviderPingWorker] = None

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
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(1500)

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

        self.run_btn.setEnabled(False)
        self.progress.show()
        self.progress.setRange(0, len(self.providers))
        self.progress.setValue(0)

        for r in range(self.table.rowCount()):
            self.table.setItem(r, 1, QTableWidgetItem("Testing..."))
            self.table.setItem(r, 2, QTableWidgetItem("-"))
            self.table.setItem(r, 3, QTableWidgetItem("-"))

        self.worker = ProviderPingWorker(self.providers)
        self.worker.finished_one.connect(self._on_provider_tested)
        self.worker.finished.connect(self._on_all_finished)
        self.worker.start()

    def _test_selected(self):
        selected_rows = sorted({i.row() for i in self.table.selectedItems()})
        if not selected_rows:
            QMessageBox.information(self, "Selection", "Please select a provider row to test.")
            return

        subset = {}
        for r in selected_rows:
            key = self.table.item(r, 0).text()
            if key in self.providers:
                subset[key] = self.providers[key]
                self.table.setItem(r, 1, QTableWidgetItem("Testing..."))

        self.worker = ProviderPingWorker(subset)
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
        self.run_btn.setEnabled(True)
        self.progress.hide()

    def _on_selection_changed(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        key = self.table.item(row, 0).text()
        res = self.results.get(key)
        if not res:
            self.detail_text.setHtml(f"<h3>{key}</h3><p>Testing or not yet run...</p>")
            return

        color = "green" if res.success else "red"
        html = f"<h3>Provider: <span style='color:{color}'>{key}</span></h3>"
        html += f"<p><b>Status:</b> {'SUCCESS' if res.success else 'FAILED'}</p>"
        html += f"<p><b>Latency:</b> {res.latency_ms:.1f} ms</p>"
        html += f"<p><b>Message:</b> {res.message}</p>"

        if res.models:
            html += f"<h4>Discovered Models ({len(res.models)}):</h4><ul>"
            for m in res.models:
                html += f"<li><code>{m}</code></li>"
            html += "</ul>"
        elif res.raw_error:
            html += f"<h4>Diagnostic Log:</h4><pre style='background:#f5f5f5; padding:6px;'>{res.raw_error}</pre>"

        self.detail_text.setHtml(html)
