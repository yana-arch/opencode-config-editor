# Runtime tab and its small editor widgets
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


