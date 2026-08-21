# openclaude editor tabs. Minimal but functional: a Settings form (scalar keys)
# and a per-layer Raw JSON editor. Both operate on the layer currently selected
# on the window (win.oc_layer) via win.oc_layered (a LayeredConfigFile).

class OpenclaudeSettingsTab(BaseTab):
    """Form for common scalar settings of the selected layer."""

    EFFORTS = ["", "low", "medium", "high", "xhigh", "max"]
    LAYERS = ["user", "project", "local"]

    def __init__(self, app):
        super().__init__(app)
        form = QFormLayout(self)

        self.layer_combo = QComboBox()
        for lk in self.LAYERS:
            self.layer_combo.addItem(lk, lk)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_change)
        form.addRow("Edit layer:", self.layer_combo)

        self.model_edit = QLineEdit()
        self.effort_combo = QComboBox()
        for e in self.EFFORTS:
            self.effort_combo.addItem(e or "(default)", e)
        self.agent_edit = QLineEdit()
        self.advisor_edit = QLineEdit()
        for w in (self.model_edit, self.agent_edit, self.advisor_edit):
            w.textChanged.connect(self._edited)
        self.effort_combo.currentIndexChanged.connect(self._edited)

        form.addRow("model:", self.model_edit)
        form.addRow("effortLevel:", self.effort_combo)
        form.addRow("agent:", self.agent_edit)
        form.addRow("advisorModel:", self.advisor_edit)

        info = QLabel("Values shown are for the selected layer only. The effective "
                      "config is the deep-merge user → project → local.")
        info.setWordWrap(True)
        info.setStyleSheet("color: gray;")
        form.addRow(info)

    def _on_layer_change(self, *_):
        self.app.oc_layer = self.layer_combo.currentData()
        self.app.refresh_tabs()

    def _edited(self, *_):
        self.app.status_bar.showMessage("Unsaved changes…")

    def refresh(self):
        layered = getattr(self.app, "oc_layered", None)
        data = layered.layer(self.app.oc_layer) if layered else {}
        idx = self.layer_combo.findData(self.app.oc_layer)
        self.layer_combo.blockSignals(True)
        self.layer_combo.setCurrentIndex(max(0, idx))
        self.layer_combo.blockSignals(False)
        for w in (self.model_edit, self.agent_edit, self.advisor_edit, self.effort_combo):
            w.blockSignals(True)
        self.model_edit.setText(str(data.get("model", "")))
        self.agent_edit.setText(str(data.get("agent", "")))
        self.advisor_edit.setText(str(data.get("advisorModel", "")))
        eidx = self.effort_combo.findData(data.get("effortLevel", ""))
        self.effort_combo.setCurrentIndex(eidx if eidx >= 0 else 0)
        for w in (self.model_edit, self.agent_edit, self.advisor_edit, self.effort_combo):
            w.blockSignals(False)

    def collect(self, data):
        self._put(data, "model", self.model_edit.text().strip(), "")
        self._put(data, "effortLevel", self.effort_combo.currentData() or "", "")
        self._put(data, "agent", self.agent_edit.text().strip(), "")
        self._put(data, "advisorModel", self.advisor_edit.text().strip(), "")


class OpenclaudeRawTab(BaseTab):
    """Raw JSON editor for the selected layer (full fidelity, incl. secrets)."""

    def __init__(self, app):
        super().__init__(app)
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(" Layer: "))
        self.layer_combo = QComboBox()
        for lk in ("user", "project", "local", "global"):
            self.layer_combo.addItem(lk, lk)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_change)
        bar.addWidget(self.layer_combo)
        bar.addStretch()
        layout.addLayout(bar)

        self.editor = QPlainTextEdit()
        font = QFont("Monospace")
        font.setStyleHint(QFont.Monospace)
        self.editor.setFont(font)
        self.highlighter = JSONHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._on_text)
        self._modified = False
        layout.addWidget(self.editor)

    def _on_layer_change(self, *_):
        self._raw_layer = self.layer_combo.currentData()
        self.refresh()

    def _on_text(self, *_):
        self._modified = True
        self.app.status_bar.showMessage("Unsaved changes…")

    def _current_raw_layer(self):
        return getattr(self, "_raw_layer", None) or self.layer_combo.currentData() or "project"

    def refresh(self):
        layered = getattr(self.app, "oc_layered", None)
        layer = self._current_raw_layer()
        if layered is None:
            return
        data = layered.global_data if layer == "global" else layered.layer(layer)
        self.editor.blockSignals(True)
        self.editor.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
        self.editor.blockSignals(False)
        self._modified = False

    def parsed(self):
        """Return (layer, dict) from the editor, or (layer, None) if invalid."""
        try:
            return self._current_raw_layer(), json.loads(self.editor.toPlainText())
        except json.JSONDecodeError:
            return self._current_raw_layer(), None
