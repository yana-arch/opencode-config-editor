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
        # Names removed from the table since the last Save. The store is only
        # rewritten by collect(), so Undo/Reload still restore these entries.
        self._removed = set()
        self._visible_cbs = {}  # name -> checkbox for rows currently in the table
        # name -> bool, the user's in-session choice. Repopulating the table
        # (e.g. clearing a filter) must not lose an unsaved toggle.
        self._checked = {}

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
                if name not in seen_names and name not in self._removed:
                    seen_names.add(name)
                    entries.append(entry)

        return entries

    def _active_names(self) -> set:
        """Names currently present in the config's plugin[] list."""
        return {_name_of_plugin(e) for e in self._get_raw_plugins()} - {""}

    def _disabled_names(self) -> set:
        """Remembered-disabled names that are not enabled in the config.

        A plugin listed in `plugin[]` wins over any store entry (which may come
        from a stale legacy file), so migrating old state can never silently
        re-disable a plugin the user has since re-enabled."""
        disabled = self.state_store.get_disabled(self.app.cfg.path) if self.app.cfg else set()
        return set(disabled) - self._active_names() - self._removed

    def _filter_plugins(self, text: str):
        """Filter plugins by search text matching name or options."""
        if not text:
            self.refresh()
            return

        text = text.lower()
        all_entries = self._display_entries()
        disabled_names = self._disabled_names()

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
        disabled_names = self._disabled_names()
        pairs = [(e, _name_of_plugin(e) not in disabled_names) for e in all_entries]
        self._populate_table(pairs)

    def _populate_table(self, pairs: List[Tuple[Any, bool]]):
        """Populate table widget rows. `_entries` keeps every known plugin, so a
        filtered-out row is still collected on Save."""
        self.table.blockSignals(True)
        self.table.setRowCount(len(pairs))
        new_cbs = {}

        for row, (entry, enabled) in enumerate(pairs):
            name = _name_of_plugin(entry)
            opts = _opts_of_plugin(entry)
            self._entries[name] = entry
            enabled = self._checked.get(name, enabled)

            # Col 0: Enabled checkbox
            cb = QCheckBox()
            cb.setChecked(enabled)
            cb.stateChanged.connect(
                lambda _state, n=name, box=cb: self._checked.__setitem__(n, box.isChecked()))
            self._checked.setdefault(name, enabled)
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setAlignment(Qt.AlignCenter)
            cell_layout.addWidget(cb)
            self.table.setCellWidget(row, 0, cell)
            new_cbs[name] = cb

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

        # Only the visible rows get fresh checkboxes; hidden rows keep the
        # checkbox object (and its checked state) from before the filter.
        merged = {n: cb for n, cb in self.cbs.items() if n not in new_cbs}
        merged.update(new_cbs)
        self.cbs = merged
        self._visible_cbs = new_cbs


        self.table.blockSignals(False)
        self._update_status()

    def _update_status(self):
        total = self.table.rowCount()
        en = sum(1 for cb in self._visible_cbs.values() if cb.isChecked())
        self.status_label.setText(
            f"{total} plugins ({en} enabled). Disabled plugins are remembered in cache with options intact."
        )

    def refresh(self):
        """Refresh table with current data. Staged removals are dropped, so
        Undo/Reload brings a removed plugin back from the state store."""
        self._removed.clear()
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
        self._visible_cbs[name] = cb

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
                self._visible_cbs[name] = cb

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
        """Enable/disable all plugins, including any hidden by a filter."""
        self.app.snapshot_state()
        for name, cb in self.cbs.items():
            cb.setChecked(enabled)
            self._checked[name] = enabled
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
            self._visible_cbs.pop(name, None)
            self._checked.pop(name, None)
            self._removed.add(name)

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
        """Collect data from UI into config dict, preserving options tuples.

        The table only ever holds the rows a search filter left visible, so the
        state comes from `_entries` / `_checked` (all known plugins), never from
        the visible `cbs`.
        """
        disabled_names = self._disabled_names()
        active = []
        disabled_dict = {}

        for name, entry in self._entries.items():
            if name in self._removed:
                continue
            if self._checked.get(name, True) and name not in disabled_names:
                active.append(entry)
            else:
                disabled_dict[name] = entry

        data["plugin"] = active
        if self.app.cfg:
            self.state_store.set_disabled(self.app.cfg.path, disabled_dict)
        self._removed.clear()


