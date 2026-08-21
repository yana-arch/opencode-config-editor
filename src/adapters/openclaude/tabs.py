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


class OpenclaudeAgentModelsTab(BaseTab):
    """Editor for agentModels (with masked api_key), agentRouting and
    providerFallbackChain of the selected layer."""

    def __init__(self, app):
        super().__init__(app)
        layout = QVBoxLayout(self)

        # --- agentModels ---
        layout.addWidget(QLabel("Agent models — provider connections (api_key is masked):"))
        self.models_table = QTableWidget(0, 4)
        self.models_table.setHorizontalHeaderLabels(["key", "base_url", "model", "api_key"])
        self.models_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.models_table)
        mbtn = QHBoxLayout()
        add_m = QPushButton("Add model")
        add_m.clicked.connect(lambda: self._add_model_row())
        del_m = QPushButton("Remove selected")
        del_m.clicked.connect(self._remove_model_row)
        mbtn.addWidget(add_m)
        mbtn.addWidget(del_m)
        mbtn.addStretch()
        layout.addLayout(mbtn)

        # --- providerFallbackChain ---
        fbar = QHBoxLayout()
        fbar.addWidget(QLabel("providerFallbackChain (comma-separated):"))
        self.fallback_edit = QLineEdit()
        self.fallback_edit.textChanged.connect(self._edited)
        fbar.addWidget(self.fallback_edit)
        layout.addLayout(fbar)

        # --- agentRouting ---
        layout.addWidget(QLabel("Agent routing — agent → agentModels key ('default' = fallback):"))
        self.routing_table = QTableWidget(0, 2)
        self.routing_table.setHorizontalHeaderLabels(["agent", "modelKey"])
        self.routing_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.routing_table)
        rbtn = QHBoxLayout()
        add_r = QPushButton("Add route")
        add_r.clicked.connect(lambda: self._add_route_row())
        del_r = QPushButton("Remove selected")
        del_r.clicked.connect(self._remove_route_row)
        rbtn.addWidget(add_r)
        rbtn.addWidget(del_r)
        rbtn.addStretch()
        layout.addLayout(rbtn)

    def _edited(self, *_):
        self.app.status_bar.showMessage("Unsaved changes…")

    # --- agentModels rows ---
    def _add_model_row(self, key="", base_url="", model="", api_key=""):
        r = self.models_table.rowCount()
        self.models_table.insertRow(r)
        self.models_table.setItem(r, 0, QTableWidgetItem(key))
        self.models_table.setItem(r, 1, QTableWidgetItem(base_url))
        self.models_table.setItem(r, 2, QTableWidgetItem(model))
        masked = MaskedLineEdit(api_key, field_name="api_key")
        self.models_table.setCellWidget(r, 3, masked)
        self._edited()

    def _remove_model_row(self):
        r = self.models_table.currentRow()
        if r >= 0:
            self.models_table.removeRow(r)
            self._edited()

    # --- agentRouting rows ---
    def _add_route_row(self, agent="", key=""):
        r = self.routing_table.rowCount()
        self.routing_table.insertRow(r)
        self.routing_table.setItem(r, 0, QTableWidgetItem(agent))
        self.routing_table.setItem(r, 1, QTableWidgetItem(key))
        self._edited()

    def _remove_route_row(self):
        r = self.routing_table.currentRow()
        if r >= 0:
            self.routing_table.removeRow(r)
            self._edited()

    def refresh(self):
        layered = getattr(self.app, "oc_layered", None)
        data = layered.layer(self.app.oc_layer) if layered else {}

        self.models_table.setRowCount(0)
        agent_models = data.get("agentModels") if isinstance(data.get("agentModels"), dict) else {}
        for key, spec in agent_models.items():
            spec = spec if isinstance(spec, dict) else {}
            self._add_model_row(key, spec.get("base_url", ""), spec.get("model", ""),
                                spec.get("api_key", ""))

        chain = data.get("providerFallbackChain")
        self.fallback_edit.blockSignals(True)
        self.fallback_edit.setText(", ".join(chain) if isinstance(chain, list) else "")
        self.fallback_edit.blockSignals(False)

        self.routing_table.setRowCount(0)
        routing = data.get("agentRouting") if isinstance(data.get("agentRouting"), dict) else {}
        for agent, key in routing.items():
            self._add_route_row(str(agent), str(key))

    def collect(self, data):
        models = {}
        for r in range(self.models_table.rowCount()):
            key_item = self.models_table.item(r, 0)
            key = key_item.text().strip() if key_item else ""
            if not key:
                continue
            spec = {}
            base_item = self.models_table.item(r, 1)
            model_item = self.models_table.item(r, 2)
            widget = self.models_table.cellWidget(r, 3)
            base_url = base_item.text().strip() if base_item else ""
            model = model_item.text().strip() if model_item else ""
            api_key = widget.value().strip() if widget else ""
            if base_url:
                spec["base_url"] = base_url
            if model:
                spec["model"] = model
            if api_key:
                spec["api_key"] = api_key
            models[key] = spec
        self._put(data, "agentModels", models, {})

        chain = [c.strip() for c in self.fallback_edit.text().split(",") if c.strip()]
        self._put(data, "providerFallbackChain", chain, [])

        routing = {}
        for r in range(self.routing_table.rowCount()):
            agent_item = self.routing_table.item(r, 0)
            key_item = self.routing_table.item(r, 1)
            agent = agent_item.text().strip() if agent_item else ""
            key = key_item.text().strip() if key_item else ""
            if agent and key:
                routing[agent] = key
        self._put(data, "agentRouting", routing, {})
