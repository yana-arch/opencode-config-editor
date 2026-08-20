# Raw JSON tab and shared confirm helper
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

