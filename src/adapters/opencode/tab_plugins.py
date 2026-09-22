# Plugins tab
def _name_of_plugin(entry) -> str:
    """Extract plugin name/specifier from string or [name, options] tuple."""
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, (list, tuple)) and entry and isinstance(entry[0], str):
        return entry[0].strip()
    return ""


def _opts_of_plugin(entry) -> Optional[dict]:
    """Extract options dict from [name, options] tuple, if any."""
    if isinstance(entry, (list, tuple)) and len(entry) >= 2 and isinstance(entry[1], dict):
        return entry[1]
    return None


def _format_opts_summary(opts: Optional[dict]) -> str:
    """Format short summary of options for table display."""
    if not opts:
        return ""
    try:
        s = json.dumps(opts, ensure_ascii=False)
        return s if len(s) <= 45 else s[:42] + "..."
    except Exception:
        return "(options)"


class PluginsTab(QWidget):
    """Enhanced plugins tab with search, options configuration, and bulk operations."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.state_store = PluginStateStore()
        self.cbs = {}  # name -> QCheckBox
        self._entries = {}  # name -> full_entry (str or [name, opts])

        layout = QVBoxLayout(self)

        # Search and buttons
        top_layout = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search plugins or options...")
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
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Enabled", "Plugin", "Options", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table)

        # Status
        self.status_label = QLabel(
            "Disabled plugins are removed from the saved config but remembered in cache "
            "with their options intact so you can re-enable them later."
        )
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

    def _get_raw_plugins(self) -> list:
        """Get plugin list from config data."""
        plugins = self.app.cfg.data.get("plugin", []) if self.app.cfg else []
        return plugins if isinstance(plugins, list) else []

    def _display_entries(self) -> List[Any]:
        """Combine active plugins from config and remembered-disabled ones."""
        active = self._get_raw_plugins()
        seen_names = set()
        entries = []

        # 1) Add active config entries
        for e in active:
            name = _name_of_plugin(e)
            if name and name not in seen_names:
                seen_names.add(name)
                entries.append(e)

        # 2) Add remembered disabled entries from state store
        if self.app.cfg:
            disabled_entries = self.state_store.get_entries(self.app.cfg.path)
            for name, entry in sorted(disabled_entries.items()):
                if name not in seen_names:
                    seen_names.add(name)
                    entries.append(entry)

        return entries

    def _filter_plugins(self, text: str):
        """Filter plugins by search text matching name or options."""
        if not text:
            self.refresh()
            return

        text = text.lower()
        all_entries = self._display_entries()
        disabled_names = self.state_store.get_disabled(self.app.cfg.path) if self.app.cfg else set()

        filtered = []
        for e in all_entries:
            name = _name_of_plugin(e)
            opts = _opts_of_plugin(e)
            opts_str = json.dumps(opts, ensure_ascii=False).lower() if opts else ""
            if text in name.lower() or text in opts_str:
                filtered.append((e, name not in disabled_names))

        self._populate_table(filtered)

    def _update_table(self):
        """Update table with full current entries list."""
        all_entries = self._display_entries()
        disabled_names = self.state_store.get_disabled(self.app.cfg.path) if self.app.cfg else set()
        pairs = [(e, _name_of_plugin(e) not in disabled_names) for e in all_entries]
        self._populate_table(pairs)

    def _populate_table(self, pairs: List[Tuple[Any, bool]]):
        """Populate table widget rows."""
        self.table.blockSignals(True)
        self.table.setRowCount(len(pairs))
        self.cbs = {}
        self._entries = {}

        for row, (entry, enabled) in enumerate(pairs):
            name = _name_of_plugin(entry)
            opts = _opts_of_plugin(entry)
            self._entries[name] = entry

            # Col 0: Enabled checkbox
            cb = QCheckBox()
            cb.setChecked(enabled)
            cb.stateChanged.connect(self.app.mark_dirty)
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setAlignment(Qt.AlignCenter)
            cell_layout.addWidget(cb)
            self.table.setCellWidget(row, 0, cell)
            self.cbs[name] = cb

            # Col 1: Plugin name
            name_item = QTableWidgetItem(name)
            self.table.setItem(row, 1, name_item)

            # Col 2: Options summary
            opts_item = QTableWidgetItem(_format_opts_summary(opts))
            if opts:
                opts_item.setToolTip(json.dumps(opts, indent=2, ensure_ascii=False))
            self.table.setItem(row, 2, opts_item)

            # Col 3: Configure Options button
            cfg_btn = QPushButton("⚙ Options")
            cfg_btn.clicked.connect(lambda _, n=name: self._configure_plugin(n))
            self.table.setCellWidget(row, 3, cfg_btn)

        self.table.blockSignals(False)
        self._update_status()

    def _update_status(self):
        total = self.table.rowCount()
        en = sum(1 for cb in self.cbs.values() if cb.isChecked())
        self.status_label.setText(
            f"{total} plugins ({en} enabled). Disabled plugins are remembered in cache with options intact."
        )

    def refresh(self):
        """Refresh table with current data."""
        self._update_table()

    def _on_double_click(self, row: int, col: int):
        """Open options config dialog on row double click."""
        name_item = self.table.item(row, 1)
        if name_item:
            self._configure_plugin(name_item.text())

    def _configure_plugin(self, name: str):
        """Open dialog to edit plugin options."""
        entry = self._entries.get(name, name)
        current_opts = _opts_of_plugin(entry)

        dlg = PluginOptionsDialog(self, name, current_opts)
        if dlg.exec() != QDialog.Accepted:
            return

        self.app.snapshot_state()
        new_opts = dlg.result_options
        if new_opts:
            self._entries[name] = [name, new_opts]
        else:
            self._entries[name] = name

        # Update table row summary
        row = self._find_plugin_row(name)
        if row >= 0:
            opts_item = QTableWidgetItem(_format_opts_summary(new_opts))
            if new_opts:
                opts_item.setToolTip(json.dumps(new_opts, indent=2, ensure_ascii=False))
            self.table.setItem(row, 2, opts_item)

        self.app.mark_dirty()

    def _add_plugin(self):
        """Add new plugin with optional initial options."""
        dlg = AddPluginDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        name = dlg.plugin_name
        if not name:
            return

        if name in self.cbs:
            QMessageBox.warning(self, "Error", f"Plugin '{name}' already exists")
            return

        self.app.snapshot_state()
        opts = dlg.plugin_options
        entry = [name, opts] if opts else name
        self._entries[name] = entry

        # Insert row
        row = self.table.rowCount()
        self.table.insertRow(row)

        cb = QCheckBox()
        cb.setChecked(True)
        cb.stateChanged.connect(self.app.mark_dirty)
        cell = QWidget()
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.setAlignment(Qt.AlignCenter)
        cell_layout.addWidget(cb)
        self.table.setCellWidget(row, 0, cell)
        self.cbs[name] = cb

        self.table.setItem(row, 1, QTableWidgetItem(name))
        opts_item = QTableWidgetItem(_format_opts_summary(opts))
        if opts:
            opts_item.setToolTip(json.dumps(opts, indent=2, ensure_ascii=False))
        self.table.setItem(row, 2, opts_item)

        cfg_btn = QPushButton("⚙ Options")
        cfg_btn.clicked.connect(lambda _, n=name: self._configure_plugin(n))
        self.table.setCellWidget(row, 3, cfg_btn)

        self.app.mark_dirty()
        self._update_status()

    def _import_plugins(self):
        """Import plugins from JSON."""
        self.app.snapshot_state()
        dlg = JsonImportDialog(
            self, "Import Plugins",
            "Paste or load plugins JSON. Supported formats:\n"
            "- Array of plugins: [\"pkg\", [\"pkg-with-opts\", {\"lang\": \"en\"}]]\n"
            "- Object containing 'plugin': {'plugin': [...]}"
        )
        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.result_data
        if isinstance(data, dict) and "plugin" in data:
            data = data["plugin"]

        if not isinstance(data, list):
            QMessageBox.warning(self, "Import Error", "Expected a JSON array of plugins")
            return

        added = 0
        for item in data:
            name = _name_of_plugin(item)
            if name and name not in self.cbs:
                opts = _opts_of_plugin(item)
                entry = [name, opts] if opts else name
                self._entries[name] = entry

                row = self.table.rowCount()
                self.table.insertRow(row)

                cb = QCheckBox()
                cb.setChecked(True)
                cb.stateChanged.connect(self.app.mark_dirty)
                cell = QWidget()
                cell_layout = QHBoxLayout(cell)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setAlignment(Qt.AlignCenter)
                cell_layout.addWidget(cb)
                self.table.setCellWidget(row, 0, cell)
                self.cbs[name] = cb

                self.table.setItem(row, 1, QTableWidgetItem(name))
                opts_item = QTableWidgetItem(_format_opts_summary(opts))
                if opts:
                    opts_item.setToolTip(json.dumps(opts, indent=2, ensure_ascii=False))
                self.table.setItem(row, 2, opts_item)

                cfg_btn = QPushButton("⚙ Options")
                cfg_btn.clicked.connect(lambda _, n=name: self._configure_plugin(n))
                self.table.setCellWidget(row, 3, cfg_btn)

                added += 1

        self.app.mark_dirty()
        self._update_status()
        QMessageBox.information(self, "Import Complete", f"Added {added} new plugins")

    def _export_plugins(self):
        """Export plugins to JSON file preserving options."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Plugins", "plugins.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        active_entries = []
        for name, cb in self.cbs.items():
            if cb.isChecked():
                active_entries.append(self._entries.get(name, name))

        if not active_entries:
            QMessageBox.information(self, "Export", "No enabled plugins to export")
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(active_entries, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _set_all_enabled(self, enabled: bool):
        """Enable/disable all plugins."""
        self.app.snapshot_state()
        for cb in self.cbs.values():
            cb.setChecked(enabled)
        self.app.mark_dirty()
        self._update_status()

    def _remove_selected(self):
        """Remove selected plugins."""
        self.app.snapshot_state()
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Remove", "Please select plugins to remove")
            return

        names = {
            self.table.item(item.row(), 1).text()
            for item in selected if self.table.item(item.row(), 1) is not None
        }
        if not names:
            return

        if not _confirm(self, "Remove Plugins", f"Remove {len(names)} selected plugin(s)?"):
            return

        for name in names:
            row = self._find_plugin_row(name)
            if row >= 0:
                self.table.removeRow(row)
            self.cbs.pop(name, None)
            self._entries.pop(name, None)
            if self.app.cfg:
                self.state_store.remove_entry(self.app.cfg.path, name)

        self.app.mark_dirty()
        self._update_status()

    def _find_plugin_row(self, plugin_name: str) -> int:
        """Find row index for plugin name."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and item.text() == plugin_name:
                return row
        return -1

    def collect(self, data: dict):
        """Collect data from UI into config dict, preserving options tuples."""
        active = []
        disabled_dict = {}

        for name, cb in self.cbs.items():
            entry = self._entries.get(name, name)
            if cb.isChecked():
                active.append(entry)
            else:
                disabled_dict[name] = entry

        data["plugin"] = active
        if self.app.cfg:
            self.state_store.set_disabled(self.app.cfg.path, disabled_dict)


