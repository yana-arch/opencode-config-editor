# Commands tab
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


