# MCP servers tab

def _mcp_matches(cfg, text: str) -> bool:
    """Search-text match over a server entry; non-dict entries never match."""
    if not isinstance(cfg, dict):
        return False
    if text in str(cfg.get("type", "")).lower():
        return True
    if text in str(cfg.get("url", "")).lower():
        return True
    if isinstance(cfg.get("command"), list):
        return any(text in str(c).lower() for c in cfg["command"])
    return False

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
        item = QTableWidgetItem(_mask(str(value)) if value else "")
        # The real value lives in UserRole so it can round-trip unedited.
        item.setData(Qt.UserRole, str(value))
        self.table.setItem(r, 1, item)

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
            if not n:
                continue
            if value is None:
                out[n] = ""
                continue
            # An untouched cell still shows the mask; take the stored secret.
            # Once the user types (or clears), the text is what they meant.
            shown = value.text()
            real = str(value.data(Qt.UserRole) or "")
            out[n] = real if shown == _mask(real) else shown
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
            ("🧩 Hub / Templates", self._open_mcp_hub),
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
            self._update_table()
            return

        text = text.lower()
        mcp = self.app.cfg.data.get("mcp", {}) if self.app.cfg else {}
        filtered = {
            name: cfg for name, cfg in mcp.items()
            if text in name.lower() or _mcp_matches(cfg, text)
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

            # Name / Type are not round-trippable from the table (the key is
            # the map key, and type decides the entry's shape), so read-only.
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, name_item)

            type_item = QTableWidgetItem(str(cfg.get("type", "")))
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, type_item)

            # Command/URL. Local commands are argv lists, and shlex.split
            # round-trips exactly what the join displayed.
            if cfg.get("type") == "local":
                cmd = " ".join(cfg.get("command", []))
            else:
                cmd = cfg.get("url", "")
            self.table.setItem(row, 3, QTableWidgetItem(str(cmd or "")))

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
        """Refresh the table, keeping the active search filter applied."""
        self._filter_servers(self.search_edit.text())

    def _visible_names(self) -> dict:
        """{name: cfg} for the rows currently shown in the table."""
        mcp = (self.app.cfg.data.get("mcp", {}) if self.app.cfg else {})
        return {
            name: mcp[name] for name in
            (self.table.item(r, 1).text() for r in range(self.table.rowCount()))
            if name in mcp
        }

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

        # Headers only exist on type=remote entries; a type-less toggle entry
        # ({enabled: false}) matches no schema branch once headers are added.
        if cfg.get("type") != "remote":
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
        """Enable/disable every dict entry (non-dict entries are left alone)"""
        self.app.snapshot_state()
        mcp = self.app.cfg.data.get("mcp", {})
        changed = False
        for name in mcp:
            if isinstance(mcp[name], dict):
                mcp[name]["enabled"] = enabled
                changed = True
        if changed:
            self.app.mark_dirty()
        self.refresh()

    def _toggle_enabled(self, name: str):
        """Toggle enabled state for server"""
        mcp = self.app.cfg.data.get("mcp", {})
        cfg = mcp.get(name)
        if isinstance(cfg, dict) and name in self.cbs:
            self.app.snapshot_state()
            cfg["enabled"] = self.cbs[name].isChecked()
            self.app.mark_dirty()


    def _open_mcp_hub(self):
        """Open MCP Template Hub to install curated MCP servers"""
        dlg = MCPTemplateHubDialog(self, target_mode="opencode")
        if dlg.exec() == QDialog.Accepted:
            key = dlg.result_server_key
            cfg = dlg.result_server_config
            if not key or not cfg:
                return
            mcp = self.app.cfg.data.setdefault("mcp", {})
            if key in mcp:
                if not _confirm(self, "Overwrite Server", f"Server '{key}' already exists. Overwrite?"):
                    return
            self.app.snapshot_state()
            mcp[key] = cfg
            self.app.mark_dirty()
            self.refresh()
            QMessageBox.information(self, "Installed", f"MCP server '{key}' installed successfully.")

    def collect(self, data: dict):
        """Write the Command/URL column back into cfg.data['mcp'].

        Name and Type are read-only in the table, so only column 3 can carry
        an edit. Remote entries take the cell text as their url; local entries
        are re-split with shlex so what was displayed round-trips.
        """
        mcp = self.app.cfg.data.get("mcp", {})
        changed = False
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, 1)
            cell = self.table.item(r, 3)
            if name_item is None or cell is None:
                continue
            name = name_item.text()
            cfg = mcp.get(name)
            if not isinstance(cfg, dict):
                continue
            text = cell.text().strip()
            if cfg.get("type") == "local":
                new = shlex.split(text) if text else []
                if cfg.get("command") != new:
                    cfg["command"] = new
                    changed = True
            elif cfg.get("url", "") != text:
                cfg["url"] = text
                changed = True
        if changed:
            self.app.snapshot_state()
            self.app.mark_dirty()

