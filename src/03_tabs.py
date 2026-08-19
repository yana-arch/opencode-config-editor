class ProvidersTab(QWidget):
    """Enhanced providers tab with search and bulk operations"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.rows = []  # (provider_name, npm_edit, name_edit)

        layout = QVBoxLayout(self)

        # Search and buttons
        top_layout = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search providers...")
        self.search_edit.textChanged.connect(self._filter_providers)
        top_layout.addWidget(self.search_edit)

        for text, slot in [
            ("+ Add", self._add_provider),
            ("Import", self._import_providers),
            ("Export", self._export_providers),
            ("Enable All", lambda: self._set_all_enabled(True)),
            ("Disable All", lambda: self._set_all_enabled(False))
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            top_layout.addWidget(btn)

        layout.addLayout(top_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Provider", "npm", "Name", "Models / Options", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        layout.addWidget(self.table)

        # Status
        self.status_label = QLabel()
        layout.addWidget(self.status_label)

    def _filter_providers(self, text: str):
        """Filter providers by search text"""
        if not text:
            self.refresh()
            return

        text = text.lower()
        providers = self.app.cfg.data.get("provider", {}) if self.app.cfg else {}
        filtered = {
            name: cfg for name, cfg in providers.items()
            if text in name.lower() or
               (isinstance(cfg.get("npm"), str) and text in cfg["npm"].lower()) or
               (isinstance(cfg.get("name"), str) and text in cfg["name"].lower())
        }

        self._update_table(filtered)

    def _update_table(self, providers: Optional[dict] = None):
        """Update table with providers"""
        if providers is None:
            providers = self.app.cfg.data.get("provider", {}) if self.app.cfg else {}

        self.table.setRowCount(len(providers))
        self.rows = []

        for row, (name, cfg) in enumerate(sorted(providers.items())):
            if not isinstance(cfg, dict):
                cfg = {}

            # Provider name
            self.table.setItem(row, 0, QTableWidgetItem(name))

            # npm
            npm_edit = MaskedLineEdit(cfg.get("npm", ""), field_name="npm")
            npm_edit.edit.editingFinished.connect(self.app.mark_dirty)
            self.table.setCellWidget(row, 1, npm_edit)

            # Name
            name_edit = MaskedLineEdit(cfg.get("name", ""), field_name="name")
            name_edit.edit.editingFinished.connect(self.app.mark_dirty)
            self.table.setCellWidget(row, 2, name_edit)

            # Models/Options
            n_models = len(cfg.get("models", {})) if isinstance(cfg.get("models"), dict) else 0
            base_url = cfg.get("options", {}).get("baseURL", "") if isinstance(cfg.get("options"), dict) else ""

            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(2, 0, 2, 0)

            summary = QLabel(f"{n_models} models  {base_url}")
            summary.setToolTip(json.dumps(cfg, ensure_ascii=False, indent=2)[:4000])
            cell_layout.addWidget(summary, 1)

            models_btn = QPushButton("Models...")
            models_btn.clicked.connect(lambda _, n=name: self._edit_models(n))
            cell_layout.addWidget(models_btn)

            options_btn = QPushButton("Options...")
            options_btn.clicked.connect(lambda _, n=name: self._edit_options(n))
            cell_layout.addWidget(options_btn)

            self.table.setCellWidget(row, 3, cell)

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedWidth(60)
            edit_btn.clicked.connect(lambda _, n=name: self._edit_provider(n))
            actions_layout.addWidget(edit_btn)

            remove_btn = QPushButton("Remove")
            remove_btn.setFixedWidth(60)
            remove_btn.clicked.connect(lambda _, n=name: self._remove_provider(n))
            actions_layout.addWidget(remove_btn)

            self.table.setCellWidget(row, 4, actions_widget)

            self.rows.append((name, npm_edit, name_edit))

        self.status_label.setText(f"{len(providers)} providers")

    def refresh(self):
        """Refresh table with current data"""
        self._update_table()

    def _add_provider(self):
        """Add new provider"""
        self.app.snapshot_state()
        name, ok = QInputDialog.getText(
            self, "Add Provider", "Provider key:",
            QLineEdit.Normal, "new-provider"
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        providers = self.app.cfg.data.setdefault("provider", {})

        if name in providers:
            QMessageBox.warning(self, "Error", f"Provider '{name}' already exists")
            return

        providers[name] = {
            "npm": "@ai-sdk/openai",
            "name": name,
            "models": {}
        }
        self.app.mark_dirty()
        self.refresh()

    def _edit_provider(self, name: Optional[str] = None):
        """Edit provider"""
        self.app.snapshot_state()
        if name is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Edit", "Please select a provider to edit")
                return
            name = selected[0].text()

        providers = self.app.cfg.data.get("provider", {})
        if name not in providers:
            QMessageBox.warning(self, "Error", f"Provider '{name}' not found")
            return

        new_name, ok = QInputDialog.getText(
            self, "Edit Provider", "New provider key:",
            QLineEdit.Normal, name
        )
        if not ok:
            return

        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Error", "Provider key cannot be empty")
            return

        if new_name != name and new_name in providers:
            QMessageBox.warning(self, "Error", f"Provider '{new_name}' already exists")
            return

        if new_name != name:
            providers[new_name] = providers.pop(name)

        self.app.mark_dirty()
        self.refresh()

    def _remove_provider(self, name: Optional[str] = None):
        """Remove provider(s)"""
        self.app.snapshot_state()
        if name is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Remove", "Please select providers to remove")
                return

            names = {selected[i].text() for i in range(0, len(selected), self.table.columnCount())}
            if not _confirm(self, "Remove Providers", f"Remove {len(names)} selected providers?"):
                return

            providers = self.app.cfg.data.get("provider", {})
            for name in names:
                providers.pop(name, None)
        else:
            if not _confirm(self, "Remove Provider", f"Remove provider '{name}'?"):
                return

            self.app.cfg.data.get("provider", {}).pop(name, None)

        self.app.mark_dirty()
        self.refresh()

    def _import_providers(self):
        """Import providers from JSON"""
        self.app.snapshot_state()
        dlg = JsonImportDialog(
            self, "Import Providers",
            "Paste or load provider JSON. Supported formats:\n"
            "- Single provider object\n"
            "- {name: provider} map\n"
            "- Full config with 'provider' key"
        )
        if dlg.exec() != QDialog.Accepted:
            return

        try:
            parsed = parse_provider_import(dlg.result_data)
        except ValueError as e:
            QMessageBox.warning(self, "Import Error", str(e))
            return

        providers = self.app.cfg.data.setdefault("provider", {})
        added = 0
        updated = 0

        for name, cfg in parsed.items():
            if name in providers:
                if _confirm(
                    self, "Provider Exists",
                    f"Provider '{name}' already exists. Merge with existing?"
                ):
                    providers[name] = merge_dict(providers[name], cfg)
                    updated += 1
            else:
                providers[name] = cfg
                added += 1

        self.app.mark_dirty()
        self.refresh()
        QMessageBox.information(
            self, "Import Complete",
            f"Added {added} new providers, updated {updated} existing providers"
        )

    def _export_providers(self):
        """Export providers to JSON file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Providers", "providers.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        providers = self.app.cfg.data.get("provider", {})
        if not providers:
            QMessageBox.information(self, "Export", "No providers to export")
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(providers, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _set_all_enabled(self, enabled: bool):
        """Enable/disable all providers"""
        # Providers don't have an enabled flag, but we can add one for UI purposes
        # This is just a placeholder for potential future functionality
        QMessageBox.information(self, "Info", "Providers don't have an enabled/disabled state")

    def _edit_models(self, name: str):
        """Edit models for provider"""
        self.app.snapshot_state()
        providers = self.app.cfg.data.get("provider", {})
        if name not in providers:
            return

        dlg = ModelsManagerDialog(self.app, name, providers[name])
        if dlg.exec() == QDialog.Accepted:
            providers[name]["models"] = dlg.result()
            self.app.mark_dirty()
            self.refresh()

    def _edit_options(self, name: str):
        """Edit options for provider"""
        self.app.snapshot_state()
        providers = self.app.cfg.data.get("provider", {})
        if name not in providers:
            return

        current = providers[name].get("options", {})
        dlg = JsonImportDialog(
            self, f"Options - {name}",
            "Edit provider options (baseURL, headers, etc.)"
        )
        dlg.editor.setPlainText(json.dumps(current, indent=2, ensure_ascii=False))

        if dlg.exec() == QDialog.Accepted:
            try:
                options = json.loads(dlg.editor.toPlainText())
                if not isinstance(options, dict):
                    raise ValueError("Options must be a JSON object")
                providers[name]["options"] = options
                self.app.mark_dirty()
                self.refresh()
            except (json.JSONDecodeError, ValueError) as e:
                QMessageBox.warning(self, "Error", str(e))

    def collect(self, data: dict):
        """Collect data from UI"""
        providers = data.setdefault("provider", {})
        seen = set()

        for row in range(self.table.rowCount()):
            old_name = self.rows[row][0]
            new_name = self.table.item(row, 0).text().strip()

            if not new_name:
                continue

            if new_name in seen:
                raise ValueError(f"Duplicate provider key: {new_name!r}")
            seen.add(new_name)

            npm_edit = self.rows[row][1]
            name_edit = self.rows[row][2]

            old_cfg = dict(providers.get(old_name, {}))
            old_cfg["npm"] = npm_edit.value()
            if name_edit.value():
                old_cfg["name"] = name_edit.value()
            else:
                old_cfg.pop("name", None)

            providers[new_name] = old_cfg

class MCPHeadersDialog(QDialog):
    """Edit the `headers` map (name -> value) of a remote MCP server.

    Used for HTTP auth headers such as `Authorization: Bearer <token>`.
    """

    def __init__(self, parent=None, headers=None):
        super().__init__(parent)
        self.setWindowTitle("MCP Headers")
        self.setMinimumSize(480, 320)
        headers = headers or {}

        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Header", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.table)

        btns = QHBoxLayout()
        add_b = QPushButton("+ Add")
        add_b.clicked.connect(self._add)
        rem_b = QPushButton("Remove")
        rem_b.clicked.connect(self._remove)
        btns.addWidget(add_b)
        btns.addWidget(rem_b)
        btns.addStretch(1)
        lay.addLayout(btns)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.table.blockSignals(True)
        for name, value in sorted(headers.items()):
            self._insert_row(str(name), str(value))
        self.table.blockSignals(False)

    def _insert_row(self, name, value):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(name))
        self.table.setItem(r, 1, QTableWidgetItem(value))

    def _add(self):
        name, ok = QInputDialog.getText(self, "Header", "Header name:")
        if ok and name.strip():
            self._insert_row(name.strip(), "")
            self.table.setCurrentCell(self.table.rowCount() - 1, 1)

    def _remove(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def headers(self) -> dict:
        out = {}
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0)
            value = self.table.item(r, 1)
            n = name.text().strip() if name else ""
            v = value.text() if value else ""
            if n:
                out[n] = v
        return out


class McpTab(QWidget):
    """Enhanced MCP tab with search and bulk operations"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.cbs = {}  # name -> QCheckBox

        layout = QVBoxLayout(self)

        # Search and buttons
        top_layout = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search servers...")
        self.search_edit.textChanged.connect(self._filter_servers)
        top_layout.addWidget(self.search_edit)

        for text, slot in [
            ("+ Add", self._add_server),
            ("Import", self._import_servers),
            ("Export", self._export_servers),
            ("Enable All", lambda: self._set_all_enabled(True)),
            ("Disable All", lambda: self._set_all_enabled(False))
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            top_layout.addWidget(btn)

        layout.addLayout(top_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Enabled", "Name", "Type", "Command / URL", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        layout.addWidget(self.table)

        # Status
        self.status_label = QLabel()
        layout.addWidget(self.status_label)

    def _filter_servers(self, text: str):
        """Filter servers by search text"""
        if not text:
            self.refresh()
            return

        text = text.lower()
        mcp = self.app.cfg.data.get("mcp", {}) if self.app.cfg else {}
        filtered = {
            name: cfg for name, cfg in mcp.items()
            if text in name.lower() or
               (isinstance(cfg.get("type"), str) and text in cfg["type"].lower()) or
               (isinstance(cfg.get("url"), str) and text in cfg["url"].lower()) or
               (isinstance(cfg.get("command"), list) and any(text in str(c).lower() for c in cfg["command"]))
        }

        self._update_table(filtered)

    def _update_table(self, servers: Optional[dict] = None):
        """Update table with servers"""
        if servers is None:
            servers = self.app.cfg.data.get("mcp", {}) if self.app.cfg else {}

        self.table.setRowCount(len(servers))
        self.cbs = {}

        for row, (name, cfg) in enumerate(sorted(servers.items())):
            if not isinstance(cfg, dict):
                cfg = {}

            # Enabled checkbox
            enabled_check = QCheckBox()
            enabled_check.setChecked(bool(cfg.get("enabled", True)))
            enabled_check.stateChanged.connect(lambda _, n=name: self._toggle_enabled(n))
            self.table.setCellWidget(row, 0, enabled_check)
            self.cbs[name] = enabled_check

            # Name
            self.table.setItem(row, 1, QTableWidgetItem(name))

            # Type
            self.table.setItem(row, 2, QTableWidgetItem(str(cfg.get("type", ""))))

            # Command/URL
            if cfg.get("type") == "local":
                cmd = " ".join(cfg.get("command", []))
            else:
                cmd = cfg.get("url", "")
            self.table.setItem(row, 3, QTableWidgetItem(cmd))

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedWidth(60)
            edit_btn.clicked.connect(lambda _, n=name: self._edit_server(n))
            actions_layout.addWidget(edit_btn)

            headers_btn = QPushButton("Headers")
            headers_btn.setFixedWidth(70)
            headers_btn.clicked.connect(lambda _, n=name: self._edit_headers(n))
            actions_layout.addWidget(headers_btn)

            remove_btn = QPushButton("Remove")
            remove_btn.setFixedWidth(60)
            remove_btn.clicked.connect(lambda _, n=name: self._remove_server(n))
            actions_layout.addWidget(remove_btn)

            self.table.setCellWidget(row, 4, actions_widget)

        self.status_label.setText(f"{len(servers)} servers")

    def refresh(self):
        """Refresh table with current data"""
        self._update_table()

    def _add_server(self):
        """Add new MCP server"""
        self.app.snapshot_state()
        name, ok = QInputDialog.getText(
            self, "Add MCP Server", "Server key:",
            QLineEdit.Normal, "new-server"
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        mcp = self.app.cfg.data.setdefault("mcp", {})

        if name in mcp:
            QMessageBox.warning(self, "Error", f"Server '{name}' already exists")
            return

        mcp[name] = {
            "type": "remote",
            "url": "https://",
            "enabled": True
        }
        self.app.mark_dirty()
        self.refresh()

    def _edit_server(self, name: Optional[str] = None):
        """Edit MCP server"""
        self.app.snapshot_state()
        if name is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Edit", "Please select a server to edit")
                return
            name = selected[0].text()

        mcp = self.app.cfg.data.get("mcp", {})
        if name not in mcp:
            QMessageBox.warning(self, "Error", f"Server '{name}' not found")
            return

        new_name, ok = QInputDialog.getText(
            self, "Edit MCP Server", "New server key:",
            QLineEdit.Normal, name
        )
        if not ok:
            return

        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Error", "Server key cannot be empty")
            return

        if new_name != name and new_name in mcp:
            QMessageBox.warning(self, "Error", f"Server '{new_name}' already exists")
            return

        if new_name != name:
            mcp[new_name] = mcp.pop(name)

        self.app.mark_dirty()
        self.refresh()

    def _edit_headers(self, name: Optional[str] = None):
        """Edit the `headers` map of a (typically remote) MCP server."""
        if name is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Headers", "Please select a server")
                return
            name = selected[0].text()

        mcp = self.app.cfg.data.get("mcp", {})
        cfg = mcp.get(name)
        if not isinstance(cfg, dict):
            QMessageBox.warning(self, "Error", f"Server '{name}' not found")
            return

        if cfg.get("type") == "local":
            QMessageBox.information(
                self, "Headers", "Headers apply to remote MCP servers only."
            )
            return

        headers = cfg.get("headers") if isinstance(cfg.get("headers"), dict) else {}
        dlg = MCPHeadersDialog(self, headers=headers)
        if dlg.exec() != QDialog.Accepted:
            return

        new_headers = dlg.headers()
        self.app.snapshot_state()
        if new_headers:
            cfg["headers"] = new_headers
        else:
            cfg.pop("headers", None)
        self.app.mark_dirty()
        self.refresh()

    def _remove_server(self, name: Optional[str] = None):
        """Remove MCP server(s)"""
        self.app.snapshot_state()
        if name is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Remove", "Please select servers to remove")
                return

            names = {selected[i].text() for i in range(0, len(selected), self.table.columnCount())}
            if not _confirm(self, "Remove Servers", f"Remove {len(names)} selected servers?"):
                return

            mcp = self.app.cfg.data.get("mcp", {})
            for name in names:
                mcp.pop(name, None)
        else:
            if not _confirm(self, "Remove Server", f"Remove server '{name}'?"):
                return

            self.app.cfg.data.get("mcp", {}).pop(name, None)

        self.app.mark_dirty()
        self.refresh()

    def _import_servers(self):
        """Import MCP servers from JSON"""
        self.app.snapshot_state()
        dlg = JsonImportDialog(
            self, "Import MCP Servers",
            "Paste or load MCP server JSON. Supported formats:\n"
            "- Single server object\n"
            "- {name: server} map\n"
            "- Full config with 'mcp' key"
        )
        if dlg.exec() != QDialog.Accepted:
            return

        try:
            parsed = parse_mcp_import(dlg.result_data)
        except ValueError as e:
            QMessageBox.warning(self, "Import Error", str(e))
            return

        mcp = self.app.cfg.data.setdefault("mcp", {})
        added = 0
        updated = 0

        for name, cfg in parsed.items():
            if name in mcp:
                if _confirm(
                    self, "Server Exists",
                    f"Server '{name}' already exists. Overwrite?"
                ):
                    mcp[name] = cfg
                    updated += 1
            else:
                mcp[name] = cfg
                added += 1

        self.app.mark_dirty()
        self.refresh()
        QMessageBox.information(
            self, "Import Complete",
            f"Added {added} new servers, updated {updated} existing servers"
        )

    def _export_servers(self):
        """Export MCP servers to JSON file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export MCP Servers", "mcp-servers.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        mcp = self.app.cfg.data.get("mcp", {})
        if not mcp:
            QMessageBox.information(self, "Export", "No MCP servers to export")
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(mcp, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _set_all_enabled(self, enabled: bool):
        """Enable/disable all servers"""
        self.app.snapshot_state()
        mcp = self.app.cfg.data.get("mcp", {})
        for name in mcp:
            mcp[name]["enabled"] = enabled
        self.app.mark_dirty()
        self.refresh()

    def _toggle_enabled(self, name: str):
        """Toggle enabled state for server"""
        self.app.snapshot_state()
        mcp = self.app.cfg.data.get("mcp", {})
        if name in mcp:
            mcp[name]["enabled"] = self.cbs[name].isChecked()
            self.app.mark_dirty()

    def collect(self, data: dict):
        """Collect data from UI"""
        # Enabled states are already applied live
        pass

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

class PermissionTab(QWidget):
    """Enhanced permission tab with search"""

    def __init__(self, app):
        super().__init__()
        self.app = app

        layout = QVBoxLayout(self)

        # Search
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search permissions...")
        self.search_edit.textChanged.connect(self._filter_permissions)
        layout.addWidget(self.search_edit)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Category", "Path", "Level"])
        self.tree.setColumnCount(3)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        layout.addWidget(self.tree)

        # Buttons
        button_layout = QHBoxLayout()
        add_btn = QPushButton("+ Add Rule")
        add_btn.clicked.connect(self._add_rule)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        button_layout.addWidget(add_btn)
        button_layout.addWidget(remove_btn)
        layout.addLayout(button_layout)

    def _filter_permissions(self, text: str):
        """Filter permissions by search text"""
        if not text:
            self.refresh()
            return

        text = text.lower()
        perm = self.app.cfg.data.get("permission", {}) if self.app.cfg else {}
        filtered = {}

        for category, rules in perm.items():
            if not isinstance(rules, dict):
                continue

            matching_rules = {
                path: level for path, level in rules.items()
                if text in category.lower() or text in path.lower() or text in str(level).lower()
            }

            if matching_rules:
                filtered[category] = matching_rules

        self._update_tree(filtered)

    def _update_tree(self, permissions: Optional[dict] = None):
        """Update tree with permissions"""
        if permissions is None:
            permissions = self.app.cfg.data.get("permission", {}) if self.app.cfg else {}

        self.tree.clear()

        for category, rules in permissions.items():
            if not isinstance(rules, dict):
                continue

            category_item = QTreeWidgetItem(self.tree)
            category_item.setText(0, category)
            category_item.setFlags(category_item.flags() | Qt.ItemIsEditable)

            for path, level in rules.items():
                rule_item = QTreeWidgetItem(category_item)
                rule_item.setText(1, path)
                rule_item.setText(2, str(level))
                rule_item.setFlags(rule_item.flags() | Qt.ItemIsEditable)

        self.tree.expandAll()

    def refresh(self):
        """Refresh tree with current data"""
        self._update_tree()

    def _add_rule(self):
        """Add new permission rule"""
        self.app.snapshot_state()
        category, ok = QInputDialog.getText(
            self, "Add Permission Rule", "Category:",
            QLineEdit.Normal, "filesystem"
        )
        if not ok or not category.strip():
            return

        path, ok = QInputDialog.getText(
            self, "Add Permission Rule", "Path:",
            QLineEdit.Normal, "/tmp/*"
        )
        if not ok or not path.strip():
            return

        level, ok = QInputDialog.getItem(
            self, "Add Permission Rule", "Level:",
            ["read", "write", "execute", "none"], 0, False
        )
        if not ok:
            return

        perm = self.app.cfg.data.setdefault("permission", {})
        if category not in perm:
            perm[category] = {}

        perm[category][path] = level
        self.app.mark_dirty()
        self.refresh()

    def _remove_selected(self):
        """Remove selected permission rules"""
        self.app.snapshot_state()
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.information(self, "Remove", "Please select rules to remove")
            return

        perm = self.app.cfg.data.get("permission", {})
        removed = 0

        for item in selected:
            if item.parent() is None:
                # Category
                category = item.text(0)
                if category in perm:
                    removed += len(perm[category])
                    perm.pop(category)
            else:
                # Rule
                category = item.parent().text(0)
                path = item.text(1)
                if category in perm and path in perm[category]:
                    removed += 1
                    perm[category].pop(path)
                    if not perm[category]:
                        perm.pop(category)

        self.app.mark_dirty()
        self.refresh()
        QMessageBox.information(self, "Remove", f"Removed {removed} permission rules")

    def collect(self, data: dict):
        """Collect data from UI"""
        # Permissions are edited directly in the config
        pass

class StringListEdit(QWidget):
    """Editable list of strings backed by a nested key path in the config."""

    def __init__(self, app, data_path, placeholder="item"):
        super().__init__()
        self.app = app
        self.data_path = data_path  # e.g. ["disabled_providers"]
        self.placeholder = placeholder

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setMaximumHeight(110)
        lay.addWidget(self.list)

        btns = QHBoxLayout()
        add_b = QPushButton("+")
        add_b.setFixedWidth(28)
        add_b.clicked.connect(self._add)
        rem_b = QPushButton("-")
        rem_b.setFixedWidth(28)
        rem_b.clicked.connect(self._remove)
        btns.addWidget(add_b)
        btns.addWidget(rem_b)
        btns.addStretch(1)
        lay.addLayout(btns)

    def _node(self, data):
        node = data
        for k in self.data_path:
            if not isinstance(node, dict):
                return None
            node = node.get(k)
        return node

    def refresh(self):
        self.list.clear()
        node = self._node(self.app.cfg.data if self.app.cfg else {})
        if isinstance(node, list):
            for item in node:
                self.list.addItem(str(item))

    def collect(self, data):
        vals = [self.list.item(i).text().strip()
                for i in range(self.list.count())
                if self.list.item(i).text().strip()]
        node = data
        for k in self.data_path[:-1]:
            if not isinstance(node.get(k), dict):
                node[k] = {}
            node = node[k]
        last = self.data_path[-1]
        if vals:
            node[last] = vals
        else:
            node.pop(last, None)

    def _add(self):
        text, ok = QInputDialog.getText(self, "Add", f"New {self.placeholder}:")
        if ok and text.strip():
            self.list.addItem(text.strip())
            self.app.mark_dirty()

    def _remove(self):
        rows = sorted({self.list.row(it) for it in self.list.selectedItems()}, reverse=True)
        for r in rows:
            self.list.takeItem(r)
        if rows:
            self.app.mark_dirty()


class BoolObjectCombo(QWidget):
    """Tri-state selector for bool|object keys (formatter, lsp).
    Custom-object values are preserved verbatim (edit via Raw JSON)."""

    def __init__(self, app, key):
        super().__init__()
        self.app = app
        self.key = key
        self._loading = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.combo.addItem("Disabled (omit)", "omit")
        self.combo.addItem("Enable built-ins (true)", "true")
        self.combo.addItem("Custom object (Raw JSON)", "custom")
        self.combo.currentIndexChanged.connect(self._changed)
        lay.addWidget(self.combo, 1)
        self.note = QLabel("")
        self.note.setStyleSheet("color: gray;")
        lay.addWidget(self.note, 2)

    def _changed(self):
        if not self._loading:
            self.app.mark_dirty()

    def refresh(self):
        self._loading = True
        node = self.app.cfg.data.get(self.key) if self.app.cfg else None
        if node is True:
            self.combo.setCurrentIndex(1)
        elif node is False or node is None:
            self.combo.setCurrentIndex(0)
        else:
            self.combo.setCurrentIndex(2)
        self.note.setText("preserved as-is; edit shape in Raw JSON" if self.combo.currentIndex() == 2 else "")
        self._loading = False

    def collect(self, data):
        idx = self.combo.currentIndex()
        if idx == 0:
            data.pop(self.key, None)
        elif idx == 1:
            data[self.key] = True
        # idx == 2 (custom): leave the existing base value untouched


class BoolMapEditor(QWidget):
    """Editable map<string,bool> backed by a nested key path (e.g. tools)."""

    def __init__(self, app, data_path):
        super().__init__()
        self.app = app
        self.data_path = data_path
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Item", "Enabled"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMaximumHeight(140)
        lay.addWidget(self.table)
        btns = QHBoxLayout()
        addb = QPushButton("+")
        addb.setFixedWidth(28)
        addb.clicked.connect(self._add)
        remb = QPushButton("-")
        remb.setFixedWidth(28)
        remb.clicked.connect(self._remove)
        btns.addWidget(addb)
        btns.addWidget(remb)
        btns.addStretch(1)
        lay.addLayout(btns)

    def _node(self, data):
        node = data
        for k in self.data_path:
            if not isinstance(node, dict):
                return None
            node = node.get(k)
        return node

    def refresh(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        node = self._node(self.app.cfg.data if self.app.cfg else {})
        if isinstance(node, dict):
            for name, enabled in sorted(node.items()):
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(str(name)))
                cb = QCheckBox()
                cb.setChecked(bool(enabled))
                self.table.setCellWidget(r, 1, cb)
                cb.stateChanged.connect(lambda *_: self._changed())
        self.table.blockSignals(False)

    def collect(self, data):
        node = data
        for k in self.data_path[:-1]:
            if not isinstance(node.get(k), dict):
                node[k] = {}
            node = node[k]
        last = self.data_path[-1]
        out = {}
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0)
            if not name or not name.text().strip():
                continue
            cb = self.table.cellWidget(r, 1)
            out[name.text().strip()] = bool(cb.isChecked())
        if out:
            node[last] = out
        else:
            node.pop(last, None)

    def _changed(self):
        self.app.mark_dirty()

    def _add(self):
        text, ok = QInputDialog.getText(self, "Add", "Item name:")
        if ok and text.strip():
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(text.strip()))
            cb = QCheckBox()
            cb.setChecked(True)
            self.table.setCellWidget(r, 1, cb)
            self.app.mark_dirty()

    def _remove(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        if rows:
            self.app.mark_dirty()


class RuntimeTab(QWidget):
    """Server, session, attachment, advanced and experimental settings."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._touched = set()

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        container = QWidget()
        scroll.setWidget(container)
        lay = QVBoxLayout(container)

        # ---- Server ----
        server_box = QGroupBox("Server (opencode serve / web)")
        sform = QFormLayout(server_box)
        self.server_port = self._spin(0)
        sform.addRow("Port", self.server_port)
        self.server_host = MaskedLineEdit("", field_name="hostname", placeholder="0.0.0.0")
        self.server_host.edit.editingFinished.connect(self._t("server"))
        sform.addRow("Hostname", self.server_host)
        self.server_mdns = QCheckBox("Enable mDNS discovery")
        self.server_mdns.stateChanged.connect(self._t("server"))
        sform.addRow("mDNS", self.server_mdns)
        self.server_mdns_domain = MaskedLineEdit("", field_name="mdnsDomain", placeholder="opencode.local")
        self.server_mdns_domain.edit.editingFinished.connect(self._t("server"))
        sform.addRow("mDNS Domain", self.server_mdns_domain)
        self.server_cors = StringListEdit(app, ["cors"], "origin")
        sform.addRow("CORS origins", self.server_cors)
        lay.addWidget(server_box)

        # ---- Session ----
        session_box = QGroupBox("Session (compaction / tool output)")
        sform = QFormLayout(session_box)
        self.comp_auto = QCheckBox("Auto-compact when context is full")
        self.comp_auto.stateChanged.connect(self._t("compaction"))
        sform.addRow("Compaction auto", self.comp_auto)
        self.comp_prune = QCheckBox("Prune old tool outputs")
        self.comp_prune.stateChanged.connect(self._t("compaction"))
        sform.addRow("Compaction prune", self.comp_prune)
        self.comp_reserved = self._spin(0)
        sform.addRow("Compaction reserved", self.comp_reserved)
        self.comp_tail = self._spin(0)
        sform.addRow("Compaction tail turns", self.comp_tail)
        self.comp_preserve = self._spin(0)
        sform.addRow("Preserve recent tokens", self.comp_preserve)
        self.tool_lines = self._spin(0)
        sform.addRow("Tool output max lines", self.tool_lines)
        self.tool_bytes = self._spin(0)
        sform.addRow("Tool output max bytes", self.tool_bytes)
        lay.addWidget(session_box)

        # ---- Attachment ----
        att_box = QGroupBox("Image attachments")
        aform = QFormLayout(att_box)
        self.att_resize = QCheckBox("Auto-resize oversized images")
        self.att_resize.stateChanged.connect(self._t("attachment"))
        aform.addRow("Auto resize", self.att_resize)
        self.att_w = self._spin(0)
        aform.addRow("Max width", self.att_w)
        self.att_h = self._spin(0)
        aform.addRow("Max height", self.att_h)
        self.att_bytes = self._spin(0)
        aform.addRow("Max base64 bytes", self.att_bytes)
        lay.addWidget(att_box)

        # ---- Advanced ----
        adv_box = QGroupBox("Advanced")
        aform = QFormLayout(adv_box)
        self.formatter = BoolObjectCombo(app, "formatter")
        self.formatter.combo.currentIndexChanged.connect(self._t("formatter"))
        aform.addRow("Formatter", self.formatter)
        self.lsp = BoolObjectCombo(app, "lsp")
        self.lsp.combo.currentIndexChanged.connect(self._t("lsp"))
        aform.addRow("LSP", self.lsp)
        self.watcher_ignore = StringListEdit(app, ["watcher", "ignore"], "glob")
        aform.addRow("Watcher ignore", self.watcher_ignore)
        self.instructions = StringListEdit(app, ["instructions"], "path/glob")
        aform.addRow("Instructions", self.instructions)
        self.skills_paths = StringListEdit(app, ["skills", "paths"], "path")
        aform.addRow("Skill paths", self.skills_paths)
        self.skills_urls = StringListEdit(app, ["skills", "urls"], "url")
        aform.addRow("Skill URLs", self.skills_urls)
        self.tools = BoolMapEditor(app, ["tools"])
        aform.addRow("Tools", self.tools)
        lay.addWidget(adv_box)

        # ---- Experimental ----
        exp_box = QGroupBox("Experimental")
        eform = QFormLayout(exp_box)
        self.exp_disable_paste = QCheckBox("Disable paste summary")
        self.exp_disable_paste.stateChanged.connect(self._t("experimental"))
        eform.addRow("Disable paste summary", self.exp_disable_paste)
        self.exp_batch = QCheckBox("Enable batch tool")
        self.exp_batch.stateChanged.connect(self._t("experimental"))
        eform.addRow("Batch tool", self.exp_batch)
        self.exp_otel = QCheckBox("Enable OpenTelemetry spans")
        self.exp_otel.stateChanged.connect(self._t("experimental"))
        eform.addRow("OpenTelemetry", self.exp_otel)
        self.exp_loop = QCheckBox("Continue loop on deny")
        self.exp_loop.stateChanged.connect(self._t("experimental"))
        eform.addRow("Continue loop on deny", self.exp_loop)
        self.exp_mcp_timeout = self._spin(0)
        eform.addRow("MCP timeout (ms)", self.exp_mcp_timeout)
        self.exp_primary_tools = StringListEdit(app, ["experimental", "primary_tools"], "tool")
        eform.addRow("Primary-only tools", self.exp_primary_tools)
        eform.addRow("Policies", self._build_policies_table())
        lay.addWidget(exp_box)
        lay.addStretch(1)

    # --- helpers ---
    def _spin(self, lo=0):
        s = QSpinBox()
        s.setRange(lo, 2**31 - 1)
        s.setSpecialValueText("(unset)")
        s.valueChanged.connect(lambda *_: self.app.mark_dirty())
        return s

    def _t(self, group):
        def _h(*_):
            self._touched.add(group)
            self.app.mark_dirty()
        return _h

    def _set_checked(self, cb, val):
        cb.blockSignals(True)
        cb.setChecked(bool(val))
        cb.blockSignals(False)

    def _set_spin(self, spin, val):
        spin.blockSignals(True)
        spin.setValue(int(val) if isinstance(val, int) and not isinstance(val, bool) else 0)
        spin.blockSignals(False)

    def _put(self, d, k, val, empty):
        if val != empty:
            d[k] = val
        else:
            d.pop(k, None)

    def _build_policies_table(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.policies = QTableWidget(0, 3)
        self.policies.setHorizontalHeaderLabels(["Effect", "Action", "Resource"])
        self.policies.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.policies.itemChanged.connect(lambda *_: self._t("experimental")())
        lay.addWidget(self.policies)
        btns = QHBoxLayout()
        addb = QPushButton("+")
        addb.setFixedWidth(28)
        addb.clicked.connect(self._add_policy)
        remb = QPushButton("-")
        remb.setFixedWidth(28)
        remb.clicked.connect(self._remove_policy)
        btns.addWidget(addb)
        btns.addWidget(remb)
        btns.addStretch(1)
        lay.addLayout(btns)
        return w

    def _add_policy(self):
        r = self.policies.rowCount()
        self.policies.insertRow(r)
        self.policies.setItem(r, 0, QTableWidgetItem("allow"))
        self.policies.setItem(r, 1, QTableWidgetItem("provider.use"))
        self.policies.setItem(r, 2, QTableWidgetItem(""))
        self._t("experimental")()

    def _remove_policy(self):
        rows = sorted({i.row() for i in self.policies.selectedItems()}, reverse=True)
        for r in rows:
            self.policies.removeRow(r)
        if rows:
            self._t("experimental")()

    # --- refresh ---
    def refresh(self):
        data = self.app.cfg.data if self.app.cfg else {}
        server = data.get("server") if isinstance(data.get("server"), dict) else {}
        self._set_spin(self.server_port, server.get("port"))
        self.server_host.set_value(server.get("hostname", ""))
        self._set_checked(self.server_mdns, server.get("mdns", False))
        self.server_mdns_domain.set_value(server.get("mdnsDomain", ""))
        self.server_cors.refresh()

        comp = data.get("compaction") if isinstance(data.get("compaction"), dict) else {}
        self._set_checked(self.comp_auto, comp.get("auto", True))
        self._set_checked(self.comp_prune, comp.get("prune", False))
        self._set_spin(self.comp_reserved, comp.get("reserved"))
        self._set_spin(self.comp_tail, comp.get("tail_turns"))
        self._set_spin(self.comp_preserve, comp.get("preserve_recent_tokens"))

        toolo = data.get("tool_output") if isinstance(data.get("tool_output"), dict) else {}
        self._set_spin(self.tool_lines, toolo.get("max_lines"))
        self._set_spin(self.tool_bytes, toolo.get("max_bytes"))

        att = data.get("attachment", {}).get("image") if isinstance(data.get("attachment"), dict) else None
        att = att if isinstance(att, dict) else {}
        self._set_checked(self.att_resize, att.get("auto_resize", True))
        self._set_spin(self.att_w, att.get("max_width"))
        self._set_spin(self.att_h, att.get("max_height"))
        self._set_spin(self.att_bytes, att.get("max_base64_bytes"))

        self.formatter.refresh()
        self.lsp.refresh()
        self.watcher_ignore.refresh()
        self.instructions.refresh()
        self.skills_paths.refresh()
        self.skills_urls.refresh()
        self.tools.refresh()

        exp = data.get("experimental") if isinstance(data.get("experimental"), dict) else {}
        self._set_checked(self.exp_disable_paste, exp.get("disable_paste_summary", False))
        self._set_checked(self.exp_batch, exp.get("batch_tool", False))
        self._set_checked(self.exp_otel, exp.get("openTelemetry", False))
        self._set_checked(self.exp_loop, exp.get("continue_loop_on_deny", False))
        self._set_spin(self.exp_mcp_timeout, exp.get("mcp_timeout"))
        self.exp_primary_tools.refresh()
        self.policies.blockSignals(True)
        self.policies.setRowCount(0)
        for pol in exp.get("policies", []) if isinstance(exp.get("policies"), list) else []:
            if not isinstance(pol, dict):
                continue
            r = self.policies.rowCount()
            self.policies.insertRow(r)
            self.policies.setItem(r, 0, QTableWidgetItem(str(pol.get("effect", ""))))
            self.policies.setItem(r, 1, QTableWidgetItem(str(pol.get("action", ""))))
            self.policies.setItem(r, 2, QTableWidgetItem(str(pol.get("resource", ""))))
        self.policies.blockSignals(False)

    # --- collect ---
    def collect(self, data):
        if "server" in self._touched:
            srv = data.setdefault("server", {})
            if not isinstance(srv, dict):
                data["server"] = srv = {}
            self._put(srv, "port", self.server_port.value() or None, None)
            self._put(srv, "hostname", self.server_host.value(), "")
            self._put(srv, "mdns", self.server_mdns.isChecked(), None)
            self._put(srv, "mdnsDomain", self.server_mdns_domain.value(), "")
            self.server_cors.collect(srv)
            if not srv:
                data.pop("server", None)

        if "compaction" in self._touched:
            comp = data.setdefault("compaction", {})
            self._put(comp, "auto", self.comp_auto.isChecked(), True)
            self._put(comp, "prune", self.comp_prune.isChecked(), False)
            self._put(comp, "reserved", self.comp_reserved.value() or None, None)
            self._put(comp, "tail_turns", self.comp_tail.value() or None, None)
            self._put(comp, "preserve_recent_tokens", self.comp_preserve.value() or None, None)
            if not comp:
                data.pop("compaction", None)

        if "tool_output" in self._touched or "compaction" in self._touched:
            toolo = data.setdefault("tool_output", {})
            self._put(toolo, "max_lines", self.tool_lines.value() or None, None)
            self._put(toolo, "max_bytes", self.tool_bytes.value() or None, None)
            if not toolo:
                data.pop("tool_output", None)

        if "attachment" in self._touched:
            att = data.setdefault("attachment", {}).setdefault("image", {})
            self._put(att, "auto_resize", self.att_resize.isChecked(), True)
            self._put(att, "max_width", self.att_w.value() or None, None)
            self._put(att, "max_height", self.att_h.value() or None, None)
            self._put(att, "max_base64_bytes", self.att_bytes.value() or None, None)
            if not att:
                data.get("attachment", {}).pop("image", None)
            if not data.get("attachment", {}):
                data.pop("attachment", None)

        if "formatter" in self._touched:
            self.formatter.collect(data)
        if "lsp" in self._touched:
            self.lsp.collect(data)

        if "watcher" in self._touched or "instructions" in self._touched \
                or "skills" in self._touched or "tools" in self._touched:
            self.watcher_ignore.collect(data.setdefault("watcher", {}))
            self.instructions.collect(data)
            self.skills_paths.collect(data.setdefault("skills", {}))
            self.skills_urls.collect(data.setdefault("skills", {}))
            self.tools.collect(data)

        if "experimental" in self._touched:
            exp = data.setdefault("experimental", {})
            self._put(exp, "disable_paste_summary", self.exp_disable_paste.isChecked(), False)
            self._put(exp, "batch_tool", self.exp_batch.isChecked(), False)
            self._put(exp, "openTelemetry", self.exp_otel.isChecked(), False)
            self._put(exp, "continue_loop_on_deny", self.exp_loop.isChecked(), False)
            self._put(exp, "mcp_timeout", self.exp_mcp_timeout.value() or None, None)
            self.exp_primary_tools.collect(exp)
            pols = []
            for r in range(self.policies.rowCount()):
                eff = self.policies.item(r, 0).text() if self.policies.item(r, 0) else ""
                act = self.policies.item(r, 1).text() if self.policies.item(r, 1) else ""
                res = self.policies.item(r, 2).text() if self.policies.item(r, 2) else ""
                if act and res:
                    pols.append({"effect": eff, "action": act, "resource": res})
            self._put(exp, "policies", pols, [])
            if not exp:
                data.pop("experimental", None)

        self._touched.clear()


class AgentEditDialog(QDialog):
    """Add/edit a custom agent."""

    def __init__(self, parent=None, name="", cfg=None):
        super().__init__(parent)
        self.setWindowTitle("Agent")
        self.setMinimumWidth(460)
        cfg = cfg or {}

        form = QFormLayout(self)
        self.name_edit = QLineEdit(name)
        form.addRow("Name", self.name_edit)
        self.desc_edit = QLineEdit(cfg.get("description", ""))
        form.addRow("Description", self.desc_edit)
        self.model_edit = QLineEdit(cfg.get("model", "") or "")
        form.addRow("Model", self.model_edit)
        self.mode_combo = QComboBox()
        for m in ["", "primary", "subagent", "all"]:
            self.mode_combo.addItem(m or "(inherit)", m)
        idx = self.mode_combo.findData(cfg.get("mode", ""))
        self.mode_combo.setCurrentIndex(max(0, idx))
        form.addRow("Mode", self.mode_combo)
        self.prompt_edit = QPlainTextEdit(cfg.get("prompt", "") or "")
        self.prompt_edit.setMaximumHeight(120)
        form.addRow("Prompt", self.prompt_edit)
        self.temp = self._double(-1000)
        if isinstance(cfg.get("temperature"), (int, float)):
            self.temp.setValue(cfg["temperature"])
        form.addRow("Temperature", self.temp)
        self.top_p = self._double(-1000)
        if isinstance(cfg.get("top_p"), (int, float)):
            self.top_p.setValue(cfg["top_p"])
        form.addRow("Top P", self.top_p)
        self.steps = QSpinBox()
        self.steps.setRange(-1, 10**6)
        self.steps.setSpecialValueText("(inherit)")
        if isinstance(cfg.get("steps"), int):
            self.steps.setValue(cfg["steps"])
        form.addRow("Steps", self.steps)
        self.hidden = QCheckBox("Hidden from @ menu")
        self.hidden.setChecked(bool(cfg.get("hidden", False)))
        form.addRow("Hidden", self.hidden)
        self.disable = QCheckBox("Disabled")
        self.disable.setChecked(bool(cfg.get("disable", False)))
        form.addRow("Disable", self.disable)
        self.color_edit = QLineEdit(cfg.get("color", "") or "")
        form.addRow("Color", self.color_edit)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _double(self, sentinel):
        d = QDoubleSpinBox()
        d.setRange(-1000, 1000)
        d.setDecimals(3)
        d.setValue(sentinel)
        d.setSpecialValueText("(inherit)")
        return d

    def values(self) -> dict:
        out = {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.text(),
            "model": self.model_edit.text().strip(),
            "mode": self.mode_combo.currentData() or "",
            "prompt": self.prompt_edit.toPlainText(),
            "hidden": self.hidden.isChecked(),
            "disable": self.disable.isChecked(),
            "color": self.color_edit.text().strip(),
        }
        if self.temp.value() != -1000:
            out["temperature"] = self.temp.value()
        if self.top_p.value() != -1000:
            out["top_p"] = self.top_p.value()
        if self.steps.value() != -1:
            out["steps"] = self.steps.value()
        return out


class AgentsTab(QWidget):
    """Manage `agent` definitions (custom + overrides of built-ins)."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search agents...")
        self.search_edit.textChanged.connect(self._filter)
        top.addWidget(self.search_edit)
        for text, slot in [("+ Add", self._add), ("Edit", self._edit), ("Remove", self._remove)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            top.addWidget(b)
        lay.addLayout(top)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Description", "Mode", "Model", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self.table)
        self.status = QLabel()
        lay.addWidget(self.status)

    def _agents(self):
        return self.app.cfg.data.get("agent", {}) if self.app.cfg else {}

    def refresh(self):
        self._update_table(self._agents())

    def _filter(self, t):
        if not t:
            self.refresh()
            return
        t = t.lower()
        self._update_table({n: c for n, c in self._agents().items() if t in n.lower()})

    def _update_table(self, agents):
        self.table.setRowCount(len(agents))
        for row, (name, cfg) in enumerate(sorted(agents.items())):
            if not isinstance(cfg, dict):
                cfg = {}
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(cfg.get("description", "")))
            self.table.setItem(row, 2, QTableWidgetItem(cfg.get("mode", "")))
            self.table.setItem(row, 3, QTableWidgetItem(cfg.get("model", "") or ""))
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0)
            eb = QPushButton("Edit")
            eb.setFixedWidth(60)
            eb.clicked.connect(lambda _, n=name: self._edit(n))
            rb = QPushButton("Remove")
            rb.setFixedWidth(70)
            rb.clicked.connect(lambda _, n=name: self._remove(n))
            l.addWidget(eb)
            l.addWidget(rb)
            self.table.setCellWidget(row, 4, w)
        self.status.setText(f"{len(agents)} agents")

    def _selected_name(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "Select", "Select an agent first.")
            return None
        return self.table.item(sel[0].row(), 0).text()

    def _add(self):
        dlg = AgentEditDialog(self)
        if dlg.exec() and dlg.values()["name"]:
            v = dlg.values()
            name = v.pop("name")
            self.app.snapshot_state()
            agents = self.app.cfg.data.setdefault("agent", {})
            agents[name] = {k: val for k, val in v.items() if val not in (None, "")}
            self.app.mark_dirty()
            self.refresh()

    def _edit(self, name=None):
        if name is None:
            name = self._selected_name()
            if not name:
                return
        cfg = dict(self._agents().get(name, {}))
        dlg = AgentEditDialog(self, name=name, cfg=cfg)
        if dlg.exec():
            v = dlg.values()
            newname = v.pop("name") or name
            self.app.snapshot_state()
            agents = self.app.cfg.data.setdefault("agent", {})
            merged = dict(cfg)  # preserve unknown keys (permission, options, tools, ...)
            for k, val in v.items():
                if val in (None, ""):
                    merged.pop(k, None)
                else:
                    merged[k] = val
            if newname != name:
                agents.pop(name, None)
            agents[newname] = merged
            self.app.mark_dirty()
            self.refresh()

    def _remove(self, name=None):
        if name is None:
            name = self._selected_name()
            if not name:
                return
        self.app.snapshot_state()
        agents = self.app.cfg.data.setdefault("agent", {})
        agents.pop(name, None)
        if not agents:
            self.app.cfg.data.pop("agent", None)
        self.app.mark_dirty()
        self.refresh()

    def collect(self, data):
        pass  # mutations applied live to cfg.data


class CommandEditDialog(QDialog):
    """Add/edit a custom command."""

    def __init__(self, parent=None, name="", cfg=None):
        super().__init__(parent)
        self.setWindowTitle("Command")
        self.setMinimumWidth(460)
        cfg = cfg or {}
        form = QFormLayout(self)
        self.name_edit = QLineEdit(name)
        form.addRow("Name", self.name_edit)
        self.desc_edit = QLineEdit(cfg.get("description", ""))
        form.addRow("Description", self.desc_edit)
        self.agent_edit = QLineEdit(cfg.get("agent", ""))
        form.addRow("Agent", self.agent_edit)
        self.model_edit = QLineEdit(cfg.get("model", "") or "")
        form.addRow("Model", self.model_edit)
        self.variant_edit = QLineEdit(cfg.get("variant", ""))
        form.addRow("Variant", self.variant_edit)
        self.subtask = QCheckBox("Run as subtask")
        self.subtask.setChecked(bool(cfg.get("subtask", False)))
        form.addRow("Subtask", self.subtask)
        self.template_edit = QPlainTextEdit(cfg.get("template", "") or "")
        self.template_edit.setMaximumHeight(150)
        form.addRow("Template", self.template_edit)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.text(),
            "agent": self.agent_edit.text().strip(),
            "model": self.model_edit.text().strip(),
            "variant": self.variant_edit.text().strip(),
            "subtask": self.subtask.isChecked(),
            "template": self.template_edit.toPlainText(),
        }


class CommandsTab(QWidget):
    """Manage `command` definitions (reusable slash commands)."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search commands...")
        self.search_edit.textChanged.connect(self._filter)
        top.addWidget(self.search_edit)
        for text, slot in [("+ Add", self._add), ("Edit", self._edit), ("Remove", self._remove)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            top.addWidget(b)
        lay.addLayout(top)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Description", "Agent", "Model"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self.table)
        self.status = QLabel()
        lay.addWidget(self.status)

    def _commands(self):
        return self.app.cfg.data.get("command", {}) if self.app.cfg else {}

    def refresh(self):
        self._update_table(self._commands())

    def _filter(self, t):
        if not t:
            self.refresh()
            return
        t = t.lower()
        self._update_table({n: c for n, c in self._commands().items() if t in n.lower()})

    def _update_table(self, commands):
        self.table.setRowCount(len(commands))
        for row, (name, cfg) in enumerate(sorted(commands.items())):
            if not isinstance(cfg, dict):
                cfg = {}
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(cfg.get("description", "")))
            self.table.setItem(row, 2, QTableWidgetItem(cfg.get("agent", "")))
            self.table.setItem(row, 3, QTableWidgetItem(cfg.get("model", "") or ""))
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0)
            eb = QPushButton("Edit")
            eb.setFixedWidth(60)
            eb.clicked.connect(lambda _, n=name: self._edit(n))
            rb = QPushButton("Remove")
            rb.setFixedWidth(70)
            rb.clicked.connect(lambda _, n=name: self._remove(n))
            l.addWidget(eb)
            l.addWidget(rb)
            self.table.setCellWidget(row, 4, w)
        self.status.setText(f"{len(commands)} commands")

    def _selected_name(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "Select", "Select a command first.")
            return None
        return self.table.item(sel[0].row(), 0).text()

    def _add(self):
        dlg = CommandEditDialog(self)
        if dlg.exec() and dlg.values()["name"] and dlg.values()["template"]:
            v = dlg.values()
            name = v.pop("name")
            self.app.snapshot_state()
            commands = self.app.cfg.data.setdefault("command", {})
            commands[name] = {k: val for k, val in v.items() if val not in (None, "")}
            self.app.mark_dirty()
            self.refresh()

    def _edit(self, name=None):
        if name is None:
            name = self._selected_name()
            if not name:
                return
        cfg = dict(self._commands().get(name, {}))
        dlg = CommandEditDialog(self, name=name, cfg=cfg)
        if dlg.exec() and dlg.values()["template"]:
            v = dlg.values()
            newname = v.pop("name") or name
            self.app.snapshot_state()
            commands = self.app.cfg.data.setdefault("command", {})
            merged = {k: val for k, val in v.items() if val not in (None, "")}
            if newname != name:
                commands.pop(name, None)
            commands[newname] = merged
            self.app.mark_dirty()
            self.refresh()

    def _remove(self, name=None):
        if name is None:
            name = self._selected_name()
            if not name:
                return
        self.app.snapshot_state()
        commands = self.app.cfg.data.setdefault("command", {})
        commands.pop(name, None)
        if not commands:
            self.app.cfg.data.pop("command", None)
        self.app.mark_dirty()
        self.refresh()

    def collect(self, data):
        pass  # mutations applied live to cfg.data


class TuiPluginEditor(QWidget):
    """Manage the tui.json `plugin` list + `plugin_enabled` state map.

    The `plugin` list entries may be plain strings or `[name, {opts}]` tuples;
    tuple-form options are preserved verbatim. A plugin is disabled by setting
    `plugin_enabled[name] = false` (it stays in the `plugin` list, so the
    disabled state is remembered and can be re-enabled — mirroring the
    settings.json PluginsTab behaviour).
    """

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.cbs = {}
        self.state_store = TuiPluginStateStore()
        self._entry_map = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search plugins...")
        self.search_edit.textChanged.connect(self._filter)
        top.addWidget(self.search_edit)
        for text, slot in [("+ Add", self._add), ("Remove", self._remove),
                           ("Enable All", lambda: self._set_all(True)),
                           ("Disable All", lambda: self._set_all(False))]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            top.addWidget(b)
        lay.addLayout(top)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Enabled", "Plugin", "Options"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        lay.addWidget(self.table)

        self.status = QLabel("Disabled plugins stay enabled/disabled via the editor cache "
                             "(no new attribute is written into tui.json).")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: gray;")
        lay.addWidget(self.status)

    @staticmethod
    def _name_of(entry):
        if isinstance(entry, str):
            return entry
        if isinstance(entry, list) and entry and isinstance(entry[0], str):
            return entry[0]
        return ""

    @staticmethod
    def _opts_of(entry):
        if isinstance(entry, list) and len(entry) >= 2 and isinstance(entry[1], dict):
            return entry[1]
        return None

    @property
    def _data(self):
        return self.app.cfg_tui.data if self.app.cfg_tui else {}

    def _entries(self):
        plugin = self._data.get("plugin", [])
        return plugin if isinstance(plugin, list) else []

    def _cfg_path(self):
        return self.app.cfg_tui.path if self.app.cfg_tui else None

    def _active_names(self):
        return {self._name_of(e) for e in self._entries()}

    def _is_enabled(self, name):
        return name in self._active_names()

    def _migrate_file_flag(self):
        data = self._data
        path = self._cfg_path()
        if path is None or not isinstance(data.get("plugin_enabled"), dict):
            return
        flagged = {n for n, v in data["plugin_enabled"].items() if v is False}
        plugin = data.get("plugin", [])
        if flagged:
            kept = []
            for entry in plugin:
                name = self._name_of(entry)
                if name in flagged:
                    self.state_store.set_entry(path, name, entry)
                else:
                    kept.append(entry)
            if kept:
                data["plugin"] = kept
            else:
                data.pop("plugin", None)
        data.pop("plugin_enabled", None)

    def _display_entries(self):
        path = self._cfg_path()
        store = self.state_store.get_entries(path) if path else {}
        active = list(self._entries())
        active_names = {self._name_of(e) for e in active}
        for name in sorted(store.keys()):
            if name not in active_names:
                active.append(store[name])
        return active

    def refresh(self):
        self._migrate_file_flag()
        path = self._cfg_path()
        if path is not None:
            active_names = self._active_names()
            stale = [n for n in self.state_store.get_entries(path) if n in active_names]
            if stale:
                self.state_store.clear(path, stale)
        self._update_table(self._display_entries())

    def _filter(self, text):
        if not text:
            self.refresh()
            return
        text = text.lower()
        entries = [e for e in self._display_entries() if text in self._name_of(e).lower()]
        self._update_table(entries)

    def _update_table(self, entries):
        self.table.blockSignals(True)
        self.table.setRowCount(len(entries))
        self.cbs = {}
        self._entry_map = {}
        for row, entry in enumerate(entries):
            name = self._name_of(entry)
            opts = self._opts_of(entry)
            self._entry_map[name] = entry

            cb = QCheckBox()
            cb.setChecked(self._is_enabled(name))
            cb.stateChanged.connect(lambda _, n=name: self._toggle(n))
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setAlignment(Qt.AlignCenter)
            cl.addWidget(cb)
            self.table.setCellWidget(row, 0, cell)
            self.cbs[name] = cb

            self.table.setItem(row, 1, QTableWidgetItem(name))
            self.table.setItem(row, 2, QTableWidgetItem(
                "(custom options)" if opts is not None else ""))
        self.table.blockSignals(False)
        self._update_status()

    def _update_status(self):
        n = self.table.rowCount()
        en = sum(1 for cb in self.cbs.values() if cb.isChecked())
        self.status.setText(f"{n} plugins ({en} enabled)")

    def _toggle(self, name: str):
        path = self._cfg_path()
        if path is None:
            return
        self.app.snapshot_state("tui")
        entry = self._entry_map.get(name, name)
        if self.cbs[name].isChecked():
            plugin = self._data.setdefault("plugin", [])
            if not isinstance(plugin, list):
                plugin = self._data["plugin"] = []
            if all(self._name_of(e) != name for e in plugin):
                plugin.append(entry)
            self.state_store.remove_entry(path, name)
        else:
            plugin = [e for e in self._data.get("plugin", []) if self._name_of(e) != name]
            if plugin:
                self._data["plugin"] = plugin
            else:
                self._data.pop("plugin", None)
            self.state_store.set_entry(path, name, entry)
        self.app.mark_dirty("tui")
        self._update_status()

    def _set_all(self, enabled: bool):
        path = self._cfg_path()
        if path is None:
            return
        self.app.snapshot_state("tui")
        if enabled:
            store = self.state_store.get_entries(path)
            plugin = self._data.setdefault("plugin", [])
            if not isinstance(plugin, list):
                plugin = self._data["plugin"] = []
            active_names = {self._name_of(e) for e in plugin}
            for name, entry in store.items():
                if name not in active_names:
                    plugin.append(entry)
            self.state_store.clear(path)
        else:
            for entry in self._data.get("plugin", []):
                name = self._name_of(entry)
                if name:
                    self.state_store.set_entry(path, name, entry)
            self._data.pop("plugin", None)
        for cb in self.cbs.values():
            cb.blockSignals(True)
            cb.setChecked(enabled)
            cb.blockSignals(False)
        self.app.mark_dirty("tui")
        self._update_status()

    def _add(self):
        name, ok = QInputDialog.getText(self, "Add Plugin", "Plugin (npm spec):",
                                        QLineEdit.Normal, "@opencode/plugin-example")
        if not ok or not name.strip():
            return
        name = name.strip()
        all_names = {self._name_of(e) for e in self._display_entries()}
        if name in all_names:
            QMessageBox.warning(self, "Error", f"Plugin '{name}' already exists")
            return
        self.app.snapshot_state("tui")
        path = self._cfg_path()
        if path is not None:
            self.state_store.remove_entry(path, name)
        plugin = self._data.setdefault("plugin", [])
        if not isinstance(plugin, list):
            plugin = self._data["plugin"] = []
        plugin.append(name)
        self.app.mark_dirty("tui")
        self.refresh()

    def _remove(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "Remove", "Select plugins to remove first.")
            return
        if not _confirm(self, "Remove Plugins", f"Remove {len(rows)} selected plugins?"):
            return
        self.app.snapshot_state("tui")
        names = {self.table.item(r, 1).text() if self.table.item(r, 1) else "" for r in rows}
        plugin = [e for e in self._data.get("plugin", []) if self._name_of(e) not in names]
        if plugin:
            self._data["plugin"] = plugin
        else:
            self._data.pop("plugin", None)
        path = self._cfg_path()
        if path is not None:
            self.state_store.clear(path, names)
        self.app.mark_dirty("tui")
        self.refresh()

    def collect(self, data):
        data.pop("plugin_enabled", None)


class TuiTab(QWidget):
    """Editor for the tui.json schema."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._touched = set()
        form = QFormLayout(self)

        self.schema_edit = MaskedLineEdit("", field_name="schema")
        self.schema_edit.edit.editingFinished.connect(self._t("schema"))
        form.addRow("$schema", self.schema_edit)

        self.theme_edit = MaskedLineEdit("", field_name="theme")
        self.theme_edit.edit.editingFinished.connect(self._t("theme"))
        form.addRow("Theme", self.theme_edit)

        self.diff_combo = QComboBox()
        for x in ["", "auto", "stacked"]:
            self.diff_combo.addItem(x or "(auto)", x)
        self.diff_combo.currentIndexChanged.connect(self._t("diff"))
        form.addRow("Diff style", self.diff_combo)

        self.mouse = QCheckBox("Enable mouse capture")
        self.mouse.stateChanged.connect(self._t("mouse"))
        form.addRow("Mouse", self.mouse)

        self.scroll_speed = QDoubleSpinBox()
        self.scroll_speed.setRange(0.001, 1000)
        self.scroll_speed.setDecimals(3)
        self.scroll_speed.setValue(1.0)
        self.scroll_speed.valueChanged.connect(self._t("scroll"))
        form.addRow("Scroll speed", self.scroll_speed)

        self.scroll_acc = QCheckBox("Enable scroll acceleration")
        self.scroll_acc.stateChanged.connect(self._t("scroll"))
        form.addRow("Scroll acceleration", self.scroll_acc)

        self.cursor_style = QComboBox()
        for x in ["", "block", "underline", "line", "default"]:
            self.cursor_style.addItem(x or "(inherit)", x)
        self.cursor_style.currentIndexChanged.connect(self._t("cursor"))
        form.addRow("Cursor style", self.cursor_style)

        self.cursor_blink = QCheckBox("Blinking cursor")
        self.cursor_blink.stateChanged.connect(self._t("cursor"))
        form.addRow("Cursor blinking", self.cursor_blink)

        self.leader_timeout = QSpinBox()
        self.leader_timeout.setRange(0, 10**6)
        self.leader_timeout.setSpecialValueText("(unset)")
        self.leader_timeout.valueChanged.connect(self._t("leader"))
        form.addRow("Leader timeout (ms)", self.leader_timeout)

        att = QGroupBox("Attention")
        aform = QFormLayout(att)
        self.att_enabled = QCheckBox("Enabled")
        self.att_enabled.stateChanged.connect(self._t("attention"))
        aform.addRow("Enabled", self.att_enabled)
        self.att_notif = QCheckBox("Notifications")
        self.att_notif.stateChanged.connect(self._t("attention"))
        aform.addRow("Notifications", self.att_notif)
        self.att_sound = QCheckBox("Sound")
        self.att_sound.stateChanged.connect(self._t("attention"))
        aform.addRow("Sound", self.att_sound)
        self.att_volume = QDoubleSpinBox()
        self.att_volume.setRange(0, 1)
        self.att_volume.setDecimals(2)
        self.att_volume.setValue(0.4)
        self.att_volume.valueChanged.connect(self._t("attention"))
        aform.addRow("Volume", self.att_volume)
        form.addRow(att)

        self.prompt_h = QSpinBox()
        self.prompt_h.setRange(0, 10**6)
        self.prompt_h.setSpecialValueText("(unset)")
        self.prompt_h.valueChanged.connect(self._t("prompt"))
        form.addRow("Prompt max height", self.prompt_h)

        self.prompt_w = QSpinBox()
        self.prompt_w.setRange(0, 10**6)
        self.prompt_w.setSpecialValueText("(auto)")
        self.prompt_w.valueChanged.connect(self._t("prompt"))
        form.addRow("Prompt max width", self.prompt_w)

        self.plugins = TuiPluginEditor(app)
        form.addRow("Plugins", self.plugins)

        info = QLabel("The `keybinds` map is edited in the Raw JSON tab.")
        info.setWordWrap(True)
        form.addRow(info)

    def _t(self, group):
        def _h(*_):
            self._touched.add(group)
            self.app.mark_dirty("tui")
        return _h

    def _set_checked(self, cb, val):
        cb.blockSignals(True)
        cb.setChecked(bool(val))
        cb.blockSignals(False)

    def _set_combo(self, combo, val, fallback):
        combo.blockSignals(True)
        idx = combo.findData(val)
        combo.setCurrentIndex(idx if idx >= 0 else fallback)
        combo.blockSignals(False)

    def _set_spin(self, spin, val):
        spin.blockSignals(True)
        spin.setValue(int(val) if isinstance(val, int) and not isinstance(val, bool) else 0)
        spin.blockSignals(False)

    def _set_double(self, spin, val):
        spin.blockSignals(True)
        spin.setValue(float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else spin.minimum())
        spin.blockSignals(False)

    def _put(self, d, k, val, empty):
        if val != empty:
            d[k] = val
        else:
            d.pop(k, None)

    def refresh(self):
        data = self.app.cfg_tui.data if self.app.cfg_tui else {}
        self.schema_edit.set_value(data.get("$schema", ""))
        self.theme_edit.set_value(data.get("theme", ""))
        self._set_combo(self.diff_combo, data.get("diff_style", ""), 0)
        self._set_checked(self.mouse, data.get("mouse", True))
        self._set_double(self.scroll_speed, data.get("scroll_speed", 1.0))
        acc = data.get("scroll_acceleration") if isinstance(data.get("scroll_acceleration"), dict) else {}
        self._set_checked(self.scroll_acc, acc.get("enabled", False))
        cursor = data.get("cursor") if isinstance(data.get("cursor"), dict) else {}
        self._set_combo(self.cursor_style, cursor.get("style", ""), 0)
        self._set_checked(self.cursor_blink, cursor.get("blinking", False))
        self._set_spin(self.leader_timeout, data.get("leader_timeout"))
        att = data.get("attention") if isinstance(data.get("attention"), dict) else {}
        self._set_checked(self.att_enabled, att.get("enabled", False))
        self._set_checked(self.att_notif, att.get("notifications", False))
        self._set_checked(self.att_sound, att.get("sound", False))
        self._set_double(self.att_volume, att.get("volume", 0.4))
        prompt = data.get("prompt") if isinstance(data.get("prompt"), dict) else {}
        self._set_spin(self.prompt_h, prompt.get("max_height"))
        self._set_spin(self.prompt_w, prompt.get("max_width"))
        self.plugins.refresh()

    def collect(self, data):
        if "schema" in self._touched:
            v = self.schema_edit.value()
            data["$schema"] = v if v else None
            if not v:
                data.pop("$schema", None)
        if "theme" in self._touched:
            self._put(data, "theme", self.theme_edit.value(), "")
        if "diff" in self._touched:
            self._put(data, "diff_style", self.diff_combo.currentData() or "", "")
        if "mouse" in self._touched:
            data["mouse"] = self.mouse.isChecked()
        if "scroll" in self._touched:
            self._put(data, "scroll_speed", self.scroll_speed.value(), 1.0)
            self._put(data, "scroll_acceleration",
                      {"enabled": self.scroll_acc.isChecked()} if self.scroll_acc.isChecked() else None, None)
        if "cursor" in self._touched:
            cursor = data.setdefault("cursor", {})
            self._put(cursor, "style", self.cursor_style.currentData() or "", "")
            self._put(cursor, "blinking", self.cursor_blink.isChecked(), False)
            if not cursor:
                data.pop("cursor", None)
        if "leader" in self._touched:
            self._put(data, "leader_timeout", self.leader_timeout.value() or None, None)
        if "attention" in self._touched:
            att = data.setdefault("attention", {})
            self._put(att, "enabled", self.att_enabled.isChecked(), False)
            self._put(att, "notifications", self.att_notif.isChecked(), False)
            self._put(att, "sound", self.att_sound.isChecked(), False)
            self._put(att, "volume", self.att_volume.value(), 0.4)
            if not att:
                data.pop("attention", None)
        if "prompt" in self._touched:
            prompt = data.setdefault("prompt", {})
            self._put(prompt, "max_height", self.prompt_h.value() or None, None)
            self._put(prompt, "max_width", self.prompt_w.value() or None, None)
            if not prompt:
                data.pop("prompt", None)
        self.plugins.collect(data)
        self._touched.clear()


class GeneralTab(QWidget):
    """Enhanced general tab with validation"""

    def __init__(self, app):
        super().__init__()
        self.app = app

        layout = QFormLayout(self)

        # Schema
        self.schema_edit = MaskedLineEdit("", field_name="schema")
        self.schema_edit.edit.editingFinished.connect(self.app.mark_dirty)
        layout.addRow("$schema", self.schema_edit)

        # Autoupdate: true | false | "notify"
        self.autoupdate_combo = QComboBox()
        for label, val in [("Off (false)", False), ("On (true)", True), ("Notify (\"notify\")", "notify")]:
            self.autoupdate_combo.addItem(label, val)
        self.autoupdate_combo.currentIndexChanged.connect(self.app.mark_dirty)
        layout.addRow("Autoupdate", self.autoupdate_combo)

        # Default model
        self.model_edit = MaskedLineEdit("", field_name="model")
        self.model_edit.edit.editingFinished.connect(self.app.mark_dirty)
        layout.addRow("Default Model", self.model_edit)

        # Small model
        self.small_model_edit = MaskedLineEdit("", field_name="small_model")
        self.small_model_edit.edit.editingFinished.connect(self.app.mark_dirty)
        layout.addRow("Small Model", self.small_model_edit)

        # Default agent
        self.default_agent_edit = MaskedLineEdit("", field_name="default_agent")
        self.default_agent_edit.edit.editingFinished.connect(self.app.mark_dirty)
        layout.addRow("Default Agent", self.default_agent_edit)

        # Subagent depth
        self.subagent_depth = QSpinBox()
        self.subagent_depth.setRange(0, 100)
        self.subagent_depth.setSpecialValueText("(default)")
        self.subagent_depth.valueChanged.connect(self._depth_changed)
        layout.addRow("Subagent Depth", self.subagent_depth)
        self._depth_touched = False

        # Username
        self.username_edit = MaskedLineEdit("", field_name="username")
        self.username_edit.edit.editingFinished.connect(self.app.mark_dirty)
        layout.addRow("Username", self.username_edit)

        # Shell
        self.shell_edit = MaskedLineEdit("", field_name="shell")
        self.shell_edit.edit.editingFinished.connect(self.app.mark_dirty)
        layout.addRow("Shell", self.shell_edit)

        # Log level
        self.loglevel_combo = QComboBox()
        for label, val in [("(default)", ""), ("DEBUG", "DEBUG"), ("INFO", "INFO"),
                           ("WARN", "WARN"), ("ERROR", "ERROR")]:
            self.loglevel_combo.addItem(label, val)
        self.loglevel_combo.currentIndexChanged.connect(self.app.mark_dirty)
        layout.addRow("Log Level", self.loglevel_combo)

        # Share
        self.share_combo = QComboBox()
        for label, val in [("(default)", ""), ("true", "true"), ("false", "false")]:
            self.share_combo.addItem(label, val)
        self.share_combo.currentIndexChanged.connect(self.app.mark_dirty)
        layout.addRow("Share", self.share_combo)

        # Snapshot (experimental)
        self.snapshot_check = QCheckBox("Enable snapshot caching")
        self.snapshot_check.stateChanged.connect(self._snapshot_changed)
        layout.addRow("Snapshot", self.snapshot_check)
        self._snapshot_touched = False

        # Disabled providers
        self.disabled_providers = StringListEdit(app, ["disabled_providers"], "provider")
        layout.addRow("Disabled Providers", self.disabled_providers)

        # Enabled providers
        self.enabled_providers = StringListEdit(app, ["enabled_providers"], "provider")
        layout.addRow("Enabled Providers", self.enabled_providers)

        # Info
        info_label = QLabel(
            "Runtime, agents, commands, providers, MCP, plugins, permission and "
            "TUI settings have their own tabs. Remaining options are editable in "
            "the Raw JSON tab."
        )
        info_label.setWordWrap(True)
        layout.addRow(info_label)

    def _depth_changed(self):
        self._depth_touched = True
        self.app.mark_dirty()

    def _snapshot_changed(self):
        self._snapshot_touched = True
        self.app.mark_dirty()

    def refresh(self):
        """Refresh fields with current data (signals blocked so programmatic
        population does not mark the document dirty)."""
        data = self.app.cfg.data if self.app.cfg else {}
        self.schema_edit.set_value(data.get("$schema", ""))
        au = data.get("autoupdate")
        idx = 0 if au is False or au is None else (1 if au is True else 2)
        self.autoupdate_combo.blockSignals(True)
        self.autoupdate_combo.setCurrentIndex(idx)
        self.autoupdate_combo.blockSignals(False)
        self.model_edit.set_value(data.get("model", ""))
        self.small_model_edit.set_value(data.get("small_model", ""))
        self.default_agent_edit.set_value(data.get("default_agent", ""))
        self._depth_touched = False
        self.subagent_depth.blockSignals(True)
        self.subagent_depth.setValue(int(data["subagent_depth"]) if isinstance(data.get("subagent_depth"), int) else 0)
        self.subagent_depth.blockSignals(False)
        self.username_edit.set_value(data.get("username", ""))
        self.shell_edit.set_value(data.get("shell", ""))
        ll = data.get("logLevel", "")
        ll_idx = self.loglevel_combo.findData(ll)
        self.loglevel_combo.blockSignals(True)
        self.loglevel_combo.setCurrentIndex(ll_idx if ll_idx >= 0 else 0)
        self.loglevel_combo.blockSignals(False)
        sh = data.get("share")
        sh_idx = self.share_combo.findData("true" if sh is True else ("false" if sh is False else ""))
        self.share_combo.blockSignals(True)
        self.share_combo.setCurrentIndex(sh_idx if sh_idx >= 0 else 0)
        self.share_combo.blockSignals(False)
        self._snapshot_touched = False
        self.snapshot_check.blockSignals(True)
        self.snapshot_check.setChecked(bool(data.get("snapshot", False)))
        self.snapshot_check.blockSignals(False)
        self.disabled_providers.refresh()
        self.enabled_providers.refresh()

    def collect(self, data: dict):
        """Collect data from UI (struct-tab, so combos always round-trip)."""
        if self.schema_edit.value():
            data["$schema"] = self.schema_edit.value()

        au = self.autoupdate_combo.currentData()
        if au is False:
            data.pop("autoupdate", None)
        else:
            data["autoupdate"] = au

        for key, edit in [
            ("model", self.model_edit),
            ("small_model", self.small_model_edit),
            ("default_agent", self.default_agent_edit),
            ("username", self.username_edit),
            ("shell", self.shell_edit),
        ]:
            value = edit.value()
            if value:
                data[key] = value
            else:
                data.pop(key, None)

        if self._depth_touched:
            data["subagent_depth"] = self.subagent_depth.value()

        ll = self.loglevel_combo.currentData()
        if ll:
            data["logLevel"] = ll
        else:
            data.pop("logLevel", None)

        sh = self.share_combo.currentData()
        if sh == "true":
            data["share"] = True
        elif sh == "false":
            data["share"] = False
        else:
            data.pop("share", None)

        if self._snapshot_touched:
            if self.snapshot_check.isChecked():
                data["snapshot"] = True
            else:
                data.pop("snapshot", None)

        self.disabled_providers.collect(data)
        self.enabled_providers.collect(data)

class RawJsonTab(QWidget):
    """Enhanced raw JSON editor with validation and formatting"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._raw_kind = "opencode"

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.file_combo = QComboBox()
        self.file_combo.addItem("opencode.json", "opencode")
        self.file_combo.addItem("tui.json", "tui")
        self.file_combo.currentIndexChanged.connect(self._switch_file)
        toolbar.addWidget(QLabel(" Raw: "))
        toolbar.addWidget(self.file_combo)

        format_btn = QPushButton("Pretty Print")
        format_btn.clicked.connect(self._format_json)
        toolbar.addWidget(format_btn)

        validate_btn = QPushButton("Validate")
        validate_btn.clicked.connect(self._validate)
        toolbar.addWidget(validate_btn)

        toolbar.addStretch()

        self.status_label = QLabel()
        toolbar.addWidget(self.status_label)

        layout.addLayout(toolbar)

        self.editor = QPlainTextEdit()
        font = QFont("Monospace")
        font.setStyleHint(QFont.Monospace)
        self.editor.setFont(font)
        self.highlighter = JSONHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._debounced_validate)
        self._modified = False
        layout.addWidget(self.editor)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._validate)

    @property
    def _modified(self):
        return self.__modified

    @_modified.setter
    def _modified(self, val):
        self.__modified = val

    def _switch_file(self):
        self.app._raw_kind = self.file_combo.currentData()
        self.refresh()

    def _debounced_validate(self):
        self._modified = True
        self.app.mark_dirty(self.app._raw_kind)
        self._timer.start()

    def _format_json(self):
        """Format JSON with pretty printing"""
        try:
            data = json.loads(self.editor.toPlainText())
            self.editor.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
            self._validate()
        except json.JSONDecodeError as e:
            self._set_status(f"Invalid JSON: {e}", "red")

    def _validate(self):
        text = self.editor.toPlainText()
        if not text.strip():
            self._set_status("Empty document", "gray")
            return
        kind = self.app._raw_kind
        cfg = self.app.cfg_tui if kind == "tui" else self.app.cfg_oc
        if cfg is None:
            self._set_status("No file loaded", "gray")
            return
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            self._set_status(f"Invalid JSON: {e}", "red")
            return
        hard_ok, hard, warnings = self.app.validate(text, kind)
        if not hard_ok:
            self._set_status(f"{len(hard)} issue(s)", "red")
            self.editor.setToolTip("\n".join(hard[:10]))
        elif warnings:
            self._set_status(f"Valid ✓ ({len(warnings)} schema notes)", "orange")
            self.editor.setToolTip("\n".join(warnings[:10]))
        else:
            self._set_status("Valid ✓", "green")
            self.editor.setToolTip("")

    def _set_status(self, text: str, color: str):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def refresh(self):
        kind = self.app._raw_kind
        cfg = self.app.cfg_tui if kind == "tui" else self.app.cfg_oc
        if cfg is None:
            self.editor.blockSignals(True)
            self.editor.setPlainText("")
            self.editor.blockSignals(False)
            self._modified = False
            return
        self.file_combo.blockSignals(True)
        idx = self.file_combo.findData(kind)
        self.file_combo.setCurrentIndex(max(0, idx))
        self.file_combo.blockSignals(False)
        self.editor.blockSignals(True)
        self.editor.setPlainText(json.dumps(cfg.data, indent=2, ensure_ascii=False))
        self.editor.blockSignals(False)
        self._modified = False
        self._validate()

    def collect(self, data: dict):
        try:
            parsed = json.loads(self.editor.toPlainText())
            data.clear()
            data.update(parsed)
        except json.JSONDecodeError:
            pass

def _confirm(parent, title: str, text: str) -> bool:
    """Show confirmation dialog"""
    return QMessageBox.question(
        parent, title, text,
        QMessageBox.Yes | QMessageBox.No
    ) == QMessageBox.Yes

