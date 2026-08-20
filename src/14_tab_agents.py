# Agents tab
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


