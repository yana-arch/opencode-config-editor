# Plugins tab
class PluginsTab(QWidget):
    """Enhanced plugins tab with search and bulk operations"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.state_store = PluginStateStore()
        self.cbs = {}  # plugin -> QCheckBox

        layout = QVBoxLayout(self)

        # Search and buttons
        top_layout = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search plugins...")
        self.search_edit.textChanged.connect(self._filter_plugins)
        top_layout.addWidget(self.search_edit)

        for text, slot in [
            ("+ Add", self._add_plugin),
            ("Import", self._import_plugins),
            ("Export", self._export_plugins),
            ("Enable All", lambda: self._set_all_enabled(True)),
            ("Disable All", lambda: self._set_all_enabled(False)),
            ("Remove Selected", self._remove_selected)
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            top_layout.addWidget(btn)

        layout.addLayout(top_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Enabled", "Plugin"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        layout.addWidget(self.table)

        # Status
        self.status_label = QLabel(
            "Disabled plugins are removed from the saved config but remembered "
            "so you can re-enable them later."
        )
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

    def _filter_plugins(self, text: str):
        """Filter plugins by search text"""
        if not text:
            self.refresh()
            return

        text = text.lower()
        plugins = self._get_plugins()
        disabled = self.state_store.get_disabled(self.app.cfg.path) if self.app.cfg else set()

        filtered = [
            (p, p not in disabled) for p in plugins
            if text in p.lower()
        ]

        self._update_table(filtered)

    def _update_table(self, plugins: Optional[List[Tuple[str, bool]]] = None):
        """Update table with plugins"""
        if plugins is None:
            plugins = self._get_plugins()
            disabled = self.state_store.get_disabled(self.app.cfg.path) if self.app.cfg else set()
            plugins = [(p, p not in disabled) for p in plugins]

        self.table.setRowCount(len(plugins))
        self.cbs = {}

        for row, (plugin, enabled) in enumerate(plugins):
            # Enabled checkbox
            enabled_check = QCheckBox()
            enabled_check.setChecked(enabled)
            enabled_check.stateChanged.connect(self.app.mark_dirty)
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setAlignment(Qt.AlignCenter)
            cell_layout.addWidget(enabled_check)
            self.table.setCellWidget(row, 0, cell)
            self.cbs[plugin] = enabled_check

            # Plugin
            self.table.setItem(row, 1, QTableWidgetItem(plugin))

    def _get_plugins(self) -> List[str]:
        """Get all plugins: active (from config) plus remembered-disabled ones,
        so disabled plugins reappear in the list and can be re-enabled."""
        plugins = self.app.cfg.data.get("plugin", []) if self.app.cfg else []
        if not isinstance(plugins, list):
            plugins = []
        active = {str(p) for p in plugins}
        if self.app.cfg is not None:
            active |= self.state_store.get_disabled(self.app.cfg.path)
        return sorted(active)

    def refresh(self):
        """Refresh table with current data"""
        self._update_table()

    def _add_plugin(self):
        """Add new plugin"""
        self.app.snapshot_state()
        plugin, ok = QInputDialog.getText(
            self, "Add Plugin", "Plugin (npm spec):",
            QLineEdit.Normal, "@opencode/plugin-example"
        )
        if not ok or not plugin.strip():
            return

        plugin = plugin.strip()
        if plugin in self.cbs:
            QMessageBox.warning(self, "Error", f"Plugin '{plugin}' already exists")
            return

        self._insert_plugin(plugin, True)
        self.app.mark_dirty()

    def _insert_plugin(self, plugin: str, enabled: bool):
        """Insert plugin into table"""
        self.table.insertRow(self.table.rowCount())
        row = self.table.rowCount() - 1

        # Enabled checkbox
        enabled_check = QCheckBox()
        enabled_check.setChecked(enabled)
        enabled_check.stateChanged.connect(self.app.mark_dirty)
        cell = QWidget()
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.setAlignment(Qt.AlignCenter)
        cell_layout.addWidget(enabled_check)
        self.table.setCellWidget(row, 0, cell)
        self.cbs[plugin] = enabled_check

        # Plugin
        self.table.setItem(row, 1, QTableWidgetItem(plugin))

    def _import_plugins(self):
        """Import plugins from JSON"""
        self.app.snapshot_state()
        dlg = JsonImportDialog(
            self, "Import Plugins",
            "Paste or load plugins JSON. Supported formats:\n"
            "- Array of plugin strings\n"
            "- {'plugin': [...]} object"
        )
        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.result_data
        if isinstance(data, dict) and "plugin" in data:
            data = data["plugin"]

        if not isinstance(data, list):
            QMessageBox.warning(self, "Import Error", "Expected a JSON array of plugin strings")
            return

        existing = set(self.cbs.keys())
        added = 0

        for item in data:
            if isinstance(item, str) and item not in existing:
                self._insert_plugin(item, True)
                added += 1

        self.app.mark_dirty()
        QMessageBox.information(self, "Import Complete", f"Added {added} new plugins")

    def _export_plugins(self):
        """Export plugins to JSON file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Plugins", "plugins.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        plugins = [p for p, cb in self.cbs.items() if cb.isChecked()]
        if not plugins:
            QMessageBox.information(self, "Export", "No plugins to export")
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(plugins, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _set_all_enabled(self, enabled: bool):
        """Enable/disable all plugins"""
        self.app.snapshot_state()
        for cb in self.cbs.values():
            cb.setChecked(enabled)
        self.app.mark_dirty()

    def _remove_selected(self):
        """Remove selected plugins"""
        self.app.snapshot_state()
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Remove", "Please select plugins to remove")
            return

        plugins = {selected[i].text() for i in range(0, len(selected), self.table.columnCount())}
        if not plugins:
            return

        if not _confirm(self, "Remove Plugins", f"Remove {len(plugins)} selected plugins?"):
            return

        for plugin in plugins:
            row = self._find_plugin_row(plugin)
            if row >= 0:
                self.table.removeRow(row)
            self.cbs.pop(plugin, None)

        self.app.mark_dirty()

    def _find_plugin_row(self, plugin: str) -> int:
        """Find row for plugin"""
        for row in range(self.table.rowCount()):
            if self.table.item(row, 1).text() == plugin:
                return row
        return -1

    def collect(self, data: dict):
        """Collect data from UI"""
        active = []
        disabled = []

        for plugin, cb in self.cbs.items():
            if cb.isChecked():
                active.append(plugin)
            else:
                disabled.append(plugin)

        data["plugin"] = active
        if self.app.cfg:
            self.state_store.set_disabled(self.app.cfg.path, set(disabled))

