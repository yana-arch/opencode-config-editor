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

        info = QLabel("Editable text = this layer's own value; greyed placeholder = "
                      "value inherited from the effective merge (user → project → local). "
                      "Saving writes only the fields you set into the selected layer.")
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
        own = layered.layer(self.app.oc_layer) if layered else {}
        eff = layered.effective() if layered else {}
        idx = self.layer_combo.findData(self.app.oc_layer)
        self.layer_combo.blockSignals(True)
        self.layer_combo.setCurrentIndex(max(0, idx))
        self.layer_combo.blockSignals(False)

        def _set(edit, key):
            # Show the selected layer's own value as editable text; show the
            # effective (inherited) value as greyed placeholder so nothing looks
            # empty when the value comes from another layer.
            edit.blockSignals(True)
            edit.setText(str(own.get(key, "")))
            inherited = str(eff.get(key, ""))
            edit.setPlaceholderText(f"inherited: {inherited}" if inherited else "(unset)")
            edit.blockSignals(False)

        _set(self.model_edit, "model")
        _set(self.agent_edit, "agent")
        _set(self.advisor_edit, "advisorModel")
        self.effort_combo.blockSignals(True)
        eff_val = own.get("effortLevel", eff.get("effortLevel", ""))
        eidx = self.effort_combo.findData(eff_val)
        self.effort_combo.setCurrentIndex(eidx if eidx >= 0 else 0)
        self.effort_combo.blockSignals(False)

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
    """Editor for provider connections in the global ~/.openclaude.json.

    OpenClaude stores providers as a `providerProfiles` list of
    {id, name, provider, baseUrl, model, apiKey, ...}. Extra/unknown fields on
    each profile (authHeader, authScheme, id, ...) are preserved on save.
    agentRouting / providerFallbackChain are also edited here when present.
    """

    COLS = ["name", "provider", "baseUrl", "model", "apiKey"]

    def __init__(self, app):
        super().__init__(app)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Providers — providerProfiles in ~/.openclaude.json "
                                "(apiKey is masked; other fields like id/authScheme are preserved):"))
        self.models_table = QTableWidget(0, len(self.COLS))
        self.models_table.setHorizontalHeaderLabels(self.COLS)
        self.models_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.models_table)
        mbtn = QHBoxLayout()
        add_m = QPushButton("Add provider")
        add_m.clicked.connect(lambda: self._add_model_row())
        del_m = QPushButton("Remove selected")
        del_m.clicked.connect(self._remove_model_row)
        mbtn.addWidget(add_m)
        mbtn.addWidget(del_m)
        mbtn.addStretch()
        layout.addLayout(mbtn)

        fbar = QHBoxLayout()
        fbar.addWidget(QLabel("providerFallbackChain (comma-separated):"))
        self.fallback_edit = QLineEdit()
        self.fallback_edit.textChanged.connect(self._edited)
        fbar.addWidget(self.fallback_edit)
        layout.addLayout(fbar)

        layout.addWidget(QLabel("Agent routing — agent → profile/model key ('default' = fallback):"))
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
        self.app.status_bar.showMessage("Unsaved changes\u2026")

    # --- provider rows (providerProfiles) ---
    def _add_model_row(self, profile=None):
        profile = profile if isinstance(profile, dict) else {}
        r = self.models_table.rowCount()
        self.models_table.insertRow(r)
        name_item = QTableWidgetItem(str(profile.get("name", "")))
        # Preserve the original profile dict (id, authHeader, authScheme, ...).
        name_item.setData(Qt.UserRole, dict(profile))
        self.models_table.setItem(r, 0, name_item)
        self.models_table.setItem(r, 1, QTableWidgetItem(str(profile.get("provider", ""))))
        self.models_table.setItem(r, 2, QTableWidgetItem(str(profile.get("baseUrl", ""))))
        self.models_table.setItem(r, 3, QTableWidgetItem(str(profile.get("model", ""))))
        masked = MaskedLineEdit(str(profile.get("apiKey", "")), field_name="apiKey")
        self.models_table.setCellWidget(r, 4, masked)
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
        # Providers/routing live in the global ~/.openclaude.json file.
        data = layered.global_data if layered else {}

        self.models_table.setRowCount(0)
        profiles = data.get("providerProfiles")
        if isinstance(profiles, list):
            for prof in profiles:
                if isinstance(prof, dict):
                    self._add_model_row(prof)
        # Back-compat: also surface legacy agentModels {key: {...}} as rows.
        agent_models = data.get("agentModels") if isinstance(data.get("agentModels"), dict) else {}
        for key, spec in agent_models.items():
            spec = spec if isinstance(spec, dict) else {}
            self._add_model_row({"name": key, "provider": spec.get("provider", ""),
                                 "baseUrl": spec.get("base_url", ""), "model": spec.get("model", ""),
                                 "apiKey": spec.get("api_key", ""), "_legacy_agentModels": True})

        chain = data.get("providerFallbackChain")
        self.fallback_edit.blockSignals(True)
        self.fallback_edit.setText(", ".join(chain) if isinstance(chain, list) else "")
        self.fallback_edit.blockSignals(False)

        self.routing_table.setRowCount(0)
        routing = data.get("agentRouting") if isinstance(data.get("agentRouting"), dict) else {}
        for agent, key in routing.items():
            self._add_route_row(str(agent), str(key))

    def collect(self, data):
        profiles = []
        legacy_models = {}
        for r in range(self.models_table.rowCount()):
            name_item = self.models_table.item(r, 0)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            orig = name_item.data(Qt.UserRole) if name_item else None
            orig = dict(orig) if isinstance(orig, dict) else {}
            provider = self._cell(r, 1)
            base_url = self._cell(r, 2)
            model = self._cell(r, 3)
            widget = self.models_table.cellWidget(r, 4)
            api_key = widget.value().strip() if widget else ""

            if orig.pop("_legacy_agentModels", False):
                spec = {}
                if provider:
                    spec["provider"] = provider
                if base_url:
                    spec["base_url"] = base_url
                if model:
                    spec["model"] = model
                if api_key:
                    spec["api_key"] = api_key
                legacy_models[name] = spec
                continue

            prof = dict(orig)
            prof["name"] = name
            if not prof.get("id"):
                prof["id"] = f"provider_{os.urandom(6).hex()}"
            self._set_or_pop(prof, "provider", provider)
            self._set_or_pop(prof, "baseUrl", base_url)
            self._set_or_pop(prof, "model", model)
            self._set_or_pop(prof, "apiKey", api_key)
            profiles.append(prof)

        self._put(data, "providerProfiles", profiles, [])
        if legacy_models or "agentModels" in data:
            self._put(data, "agentModels", legacy_models, {})

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

    def _cell(self, r, c):
        item = self.models_table.item(r, c)
        return item.text().strip() if item else ""

    @staticmethod
    def _set_or_pop(d, k, v):
        if v:
            d[k] = v
        else:
            d.pop(k, None)
