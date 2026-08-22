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

        # statusLine: boolean or {"type": "command", "command": "..."}
        self.statusline_chk = QCheckBox("enabled")
        self.statusline_cmd = QLineEdit()
        self.statusline_chk.stateChanged.connect(self._edited)
        self.statusline_cmd.textChanged.connect(self._edited)
        sl_box = QHBoxLayout()
        sl_box.addWidget(self.statusline_chk)
        sl_box.addWidget(self.statusline_cmd)
        form.addRow("statusLine:", sl_box)

        # skip-permission prompt toggles (settings.json booleans)
        self.skip_dangerous_chk = QCheckBox("skip dangerous-mode prompt")
        self.skip_fullaccess_chk = QCheckBox("skip full-access-mode prompt")
        self.skip_dangerous_chk.stateChanged.connect(self._edited)
        self.skip_fullaccess_chk.stateChanged.connect(self._edited)
        form.addRow("Permission prompts:", self.skip_dangerous_chk)
        form.addRow("", self.skip_fullaccess_chk)

        # MCP gating (settings.json) — controls how .mcp.json project servers
        # are approved. allowed/deniedMcpServers are object lists: edit in Raw.
        self.enable_all_mcp_chk = QCheckBox("enableAllProjectMcpServers")
        self.enable_all_mcp_chk.stateChanged.connect(self._edited)
        self.enabled_mcpjson_edit = QLineEdit()
        self.disabled_mcpjson_edit = QLineEdit()
        self.enabled_mcpjson_edit.textChanged.connect(self._edited)
        self.disabled_mcpjson_edit.textChanged.connect(self._edited)
        form.addRow("Project MCP:", self.enable_all_mcp_chk)
        form.addRow("enabledMcpjsonServers:", self.enabled_mcpjson_edit)
        form.addRow("disabledMcpjsonServers:", self.disabled_mcpjson_edit)

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

        # statusLine (bool or {type,command}) + skip-permission booleans
        sl = own.get("statusLine")
        self._orig_statusline = sl
        self.statusline_chk.blockSignals(True)
        self.statusline_cmd.blockSignals(True)
        self.statusline_chk.setChecked(bool(sl))
        self.statusline_cmd.setText(sl.get("command", "") if isinstance(sl, dict) else "")
        self.statusline_chk.blockSignals(False)
        self.statusline_cmd.blockSignals(False)
        self.skip_dangerous_chk.blockSignals(True)
        self.skip_fullaccess_chk.blockSignals(True)
        self.skip_dangerous_chk.setChecked(bool(own.get("skipDangerousModePermissionPrompt")))
        self.skip_fullaccess_chk.setChecked(bool(own.get("skipFullAccessModePermissionPrompt")))
        self._had_dangerous = "skipDangerousModePermissionPrompt" in own
        self._had_fullaccess = "skipFullAccessModePermissionPrompt" in own
        self.skip_dangerous_chk.blockSignals(False)
        self.skip_fullaccess_chk.blockSignals(False)

        # MCP gating fields
        self.enable_all_mcp_chk.blockSignals(True)
        self.enabled_mcpjson_edit.blockSignals(True)
        self.disabled_mcpjson_edit.blockSignals(True)
        self.enable_all_mcp_chk.setChecked(bool(own.get("enableAllProjectMcpServers")))
        for edit, key in ((self.enabled_mcpjson_edit, "enabledMcpjsonServers"),
                          (self.disabled_mcpjson_edit, "disabledMcpjsonServers")):
            val = own.get(key)
            edit.setText(", ".join(val) if isinstance(val, list) else "")
        self.enable_all_mcp_chk.blockSignals(False)
        self.enabled_mcpjson_edit.blockSignals(False)
        self.disabled_mcpjson_edit.blockSignals(False)

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
        # effortLevel: select this layer's OWN value only (do not bake in the
        # inherited effective value on save); show effective as a hint via the
        # "(default)" entry when unset.
        self.effort_combo.blockSignals(True)
        eidx = self.effort_combo.findData(own.get("effortLevel", ""))
        self.effort_combo.setCurrentIndex(eidx if eidx >= 0 else 0)
        self.effort_combo.blockSignals(False)

    def collect(self, data):
        self._put(data, "model", self.model_edit.text().strip(), "")
        self._put(data, "effortLevel", self.effort_combo.currentData() or "", "")
        self._put(data, "agent", self.agent_edit.text().strip(), "")
        self._put(data, "advisorModel", self.advisor_edit.text().strip(), "")

        # statusLine: write when enabled; explicitly drop when disabled so an
        # existing key is removed rather than left behind.
        if self.statusline_chk.isChecked():
            cmd = self.statusline_cmd.text().strip()
            value = {"type": "command", "command": cmd} if cmd else True
            self._put(data, "statusLine", value, None)
        else:
            data.pop("statusLine", None)
        # MCP gating: write when pre-existing in this layer or explicitly set.
        if "enableAllProjectMcpServers" in data or self.enable_all_mcp_chk.isChecked():
            self._put(data, "enableAllProjectMcpServers",
                      self.enable_all_mcp_chk.isChecked(), None)
        for edit, key in ((self.enabled_mcpjson_edit, "enabledMcpjsonServers"),
                          (self.disabled_mcpjson_edit, "disabledMcpjsonServers")):
            items = [x.strip() for x in edit.text().split(",") if x.strip()]
            if items or key in data:
                self._put(data, key, items, [])

        # skip-permission toggles: write when pre-existing in this layer (so
        # unchecking writes an explicit false) or when explicitly opted in.
        if "skipDangerousModePermissionPrompt" in data or self.skip_dangerous_chk.isChecked():
            self._put(data, "skipDangerousModePermissionPrompt",
                      self.skip_dangerous_chk.isChecked(), None)
        if "skipFullAccessModePermissionPrompt" in data or self.skip_fullaccess_chk.isChecked():
            self._put(data, "skipFullAccessModePermissionPrompt",
                      self.skip_fullaccess_chk.isChecked(), None)


class OpenclaudeRawTab(BaseTab):
    """Raw JSON editor for the selected layer (full fidelity, incl. secrets)."""

    def __init__(self, app):
        super().__init__(app)
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(" Layer: "))
        self.layer_combo = QComboBox()
        for lk in ("user", "project", "local", "global", "project-mcp"):
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
        if layer == "global":
            data = layered.global_data
        elif layer == "project-mcp":
            data = layered.project_mcp
        else:
            data = layered.layer(layer)
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
        self._dirty = False
        self._extra_profiles = []   # non-dict providerProfiles entries, kept verbatim
        self._had_profiles = False  # global file already had a providerProfiles key
        self._had_agent_models = False
        self._had_active = False    # global file already had activeProviderProfileId
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

        # activeProviderProfileId — openclaude uses this global key to select
        # which providerProfile is active. Editable here instead of Raw-only.
        abar = QHBoxLayout()
        abar.addWidget(QLabel("Active provider (activeProviderProfileId):"))
        self.active_combo = QComboBox()
        self.active_combo.currentIndexChanged.connect(self._edited)
        abar.addWidget(self.active_combo, 1)
        layout.addLayout(abar)

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

        # mcpServers — global ~/.openclaude.json (name + type + command/url;
        # other sub-keys on each server are preserved on save).
        layout.addWidget(QLabel("MCP servers — mcpServers in ~/.openclaude.json "
                                "(unknown sub-keys like env/headers preserved):"))
        self.mcp_table = QTableWidget(0, 3)
        self.mcp_table.setHorizontalHeaderLabels(["name", "type", "command / url"])
        self.mcp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.mcp_table)
        mcbtn = QHBoxLayout()
        add_mc = QPushButton("Add server")
        add_mc.clicked.connect(lambda: self._add_mcp_row())
        del_mc = QPushButton("Remove selected")
        del_mc.clicked.connect(self._remove_mcp_row)
        mcbtn.addWidget(add_mc)
        mcbtn.addWidget(del_mc)
        mcbtn.addStretch()
        layout.addLayout(mcbtn)

    def _edited(self, *_):
        if getattr(self, "_loading", False):
            return
        self._dirty = True
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

    # --- mcpServers rows ---
    def _add_mcp_row(self, server=None, name=""):
        server = server if isinstance(server, dict) else {}
        r = self.mcp_table.rowCount()
        self.mcp_table.insertRow(r)
        name_item = QTableWidgetItem(name or str(server.get("name", "")))
        # Preserve the original full server config (env, headers, args, ...).
        name_item.setData(Qt.UserRole, dict(server))
        self.mcp_table.setItem(r, 0, name_item)
        self.mcp_table.setItem(r, 1, QTableWidgetItem(str(server.get("type", ""))))
        self.mcp_table.setItem(r, 2, QTableWidgetItem(str(server.get("command") or server.get("url", ""))))
        self._edited()

    def _remove_mcp_row(self):
        r = self.mcp_table.currentRow()
        if r >= 0:
            self.mcp_table.removeRow(r)
            self._edited()

    def refresh(self):
        layered = getattr(self.app, "oc_layered", None)
        # Providers/routing live in the global ~/.openclaude.json file.
        data = layered.global_data if layered else {}

        self._loading = True
        try:
            self.models_table.setRowCount(0)
            profiles = data.get("providerProfiles")
            self._had_profiles = isinstance(profiles, list)
            self._extra_profiles = []
            if isinstance(profiles, list):
                for prof in profiles:
                    if isinstance(prof, dict):
                        self._add_model_row(prof)
                    else:
                        # Preserve malformed/non-dict entries verbatim on save.
                        self._extra_profiles.append(prof)
            # Back-compat: also surface legacy agentModels {key: {...}} as rows.
            agent_models = data.get("agentModels") if isinstance(data.get("agentModels"), dict) else {}
            self._had_agent_models = "agentModels" in data
            for key, spec in agent_models.items():
                spec = spec if isinstance(spec, dict) else {}
                row = dict(spec)   # keep any extra legacy keys
                row.update({"name": key, "provider": spec.get("provider", ""),
                            "baseUrl": spec.get("base_url", ""), "model": spec.get("model", ""),
                            "apiKey": spec.get("api_key", ""), "_legacy_agentModels": True})
                self._add_model_row(row)

            chain = data.get("providerFallbackChain")
            self.fallback_edit.blockSignals(True)
            self.fallback_edit.setText(", ".join(chain) if isinstance(chain, list) else "")
            self.fallback_edit.blockSignals(False)

            # Populate active-provider picker from the saved profiles (stable ids).
            self.active_combo.blockSignals(True)
            self.active_combo.clear()
            self.active_combo.addItem("(none / default)", "")
            if isinstance(profiles, list):
                for prof in profiles:
                    if isinstance(prof, dict) and prof.get("id"):
                        label = prof.get("name") or prof.get("id")
                        self.active_combo.addItem(str(label), str(prof["id"]))
            active_id = data.get("activeProviderProfileId")
            self._had_active = "activeProviderProfileId" in data
            aidx = self.active_combo.findData(str(active_id) if active_id else "")
            self.active_combo.setCurrentIndex(aidx if aidx >= 0 else 0)
            self.active_combo.blockSignals(False)

            self.routing_table.setRowCount(0)
            routing = data.get("agentRouting") if isinstance(data.get("agentRouting"), dict) else {}
            for agent, key in routing.items():
                self._add_route_row(str(agent), str(key))

            # mcpServers
            self.mcp_table.setRowCount(0)
            mcp = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {}
            self._had_mcp = "mcpServers" in data
            for name, server in mcp.items():
                if isinstance(server, dict):
                    self._add_mcp_row(server, name)
        finally:
            self._loading = False
            self._dirty = False

    def collect(self, data):
        profiles = list(self._extra_profiles)  # re-emit preserved non-dict entries
        legacy_models = {}
        seen_names = set()
        for r in range(self.models_table.rowCount()):
            name_item = self.models_table.item(r, 0)
            name = name_item.text().strip() if name_item else ""
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            orig = name_item.data(Qt.UserRole) if name_item else None
            orig = dict(orig) if isinstance(orig, dict) else {}
            provider = self._cell(r, 1)
            base_url = self._cell(r, 2)
            model = self._cell(r, 3)
            widget = self.models_table.cellWidget(r, 4)
            api_key = widget.value().strip() if widget else ""

            if orig.pop("_legacy_agentModels", False):
                spec = dict(orig)  # preserve extra legacy keys
                spec.pop("name", None)
                self._set_or_pop(spec, "provider", provider)
                self._set_or_pop(spec, "base_url", base_url)
                self._set_or_pop(spec, "model", model)
                self._set_or_pop(spec, "api_key", api_key)
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

        # Only write providerProfiles when the file already had it or we have rows,
        # so an untouched global file isn't polluted with an empty list.
        if "providerProfiles" in data or profiles:
            data["providerProfiles"] = profiles
        if legacy_models or "agentModels" in data:
            self._put(data, "agentModels", legacy_models, {})

        active = self.active_combo.currentData() or ""
        if "activeProviderProfileId" in data or active:
            self._put(data, "activeProviderProfileId", active, "")

        # mcpServers: rebuild each server from its preserved original full dict,
        # overlaying the edited type + command/url so unknown sub-keys survive.
        mcp = {}
        for r in range(self.mcp_table.rowCount()):
            nitem = self.mcp_table.item(r, 0)
            name = nitem.text().strip() if nitem else ""
            if not name:
                continue
            orig = nitem.data(Qt.UserRole) or {}
            orig = dict(orig) if isinstance(orig, dict) else {}
            typ = self._mcp_cell(r, 1)
            target = self._mcp_cell(r, 2)
            srv = dict(orig)
            if typ:
                srv["type"] = typ
            if typ == "remote":
                srv["url"] = target
                srv.pop("command", None)
            else:
                if target:
                    srv["command"] = target
                srv.pop("url", None)
            mcp[name] = srv
        if "mcpServers" in data or mcp:
            data["mcpServers"] = mcp

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

    def _mcp_cell(self, r, c):
        item = self.mcp_table.item(r, c)
        return item.text().strip() if item else ""

    @staticmethod
    def _set_or_pop(d, k, v):
        if v:
            d[k] = v
        else:
            d.pop(k, None)


class OpenclaudeMcpTab(BaseTab):
    """MCP servers across user/project/local scopes (+ policy read-only).

    Verified openclaude v0.28.0 storage:
      user    -> global ~/.openclaude.json -> mcpServers
      project -> <cwd>/.mcp.json           -> mcpServers
      local   -> global projects[file dict]     -> mcpServers
      policy  -> <managed>/managed-mcp.json (read-only display)
    Unknown sub-keys on each server (env, args, headers, ...) are preserved.
    """

    SCOPES = ("user", "project", "local")
    SOURCE_TYPES = ("github", "git", "url", "file", "directory", "npm")

    def __init__(self, app):
        super().__init__(app)
        self._scopes_cache = {"user": {}, "project": {}, "local": {}}
        self._dirty_scopes = set()
        self._project_mcp_orig = {}
        self._shown_scope = "user"

        layout = QVBoxLayout(self)
        sbar = QHBoxLayout()
        sbar.addWidget(QLabel("Scope:"))
        self.scope_combo = QComboBox()
        for sc in self.SCOPES:
            self.scope_combo.addItem(sc, sc)
        self.scope_combo.currentIndexChanged.connect(self._on_scope_change)
        sbar.addWidget(self.scope_combo)
        sbar.addStretch()
        layout.addLayout(sbar)

        layout.addWidget(QLabel("Servers (unknown sub-keys like args/env/headers "
                                "are preserved; edit complex servers in Raw):"))
        self.mcp_table = QTableWidget(0, 5)
        self.mcp_table.setHorizontalHeaderLabels(
            ["name", "transport", "command / url", "env (K=V, ...)", "headers (K=V, ...)"])
        self.mcp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.mcp_table)
        btns = QHBoxLayout()
        add_b = QPushButton("Add server")
        add_b.clicked.connect(lambda: self._add_row())
        del_b = QPushButton("Remove selected")
        del_b.clicked.connect(self._remove_row)
        btns.addWidget(add_b)
        btns.addWidget(del_b)
        btns.addStretch()
        layout.addLayout(btns)

        self.managed_label = QLabel("")
        self.managed_label.setWordWrap(True)
        self.managed_label.setStyleSheet("color: gray;")
        layout.addWidget(self.managed_label)

    # --- table helpers ---
    def _add_row(self, name="", server=None):
        server = server if isinstance(server, dict) else {}
        r = self.mcp_table.rowCount()
        self.mcp_table.insertRow(r)
        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.UserRole, dict(server))
        self.mcp_table.setItem(r, 0, name_item)
        typ = str(server.get("type") or ("http" if server.get("url") else "stdio"))
        self.mcp_table.setItem(r, 1, QTableWidgetItem(typ))
        target = server.get("command") if isinstance(server.get("command"), str) else \
            "" if not server.get("url") else str(server.get("url"))
        self.mcp_table.setItem(r, 2, QTableWidgetItem(str(target or "")))
        env = server.get("env") if isinstance(server.get("env"), dict) else {}
        self.mcp_table.setItem(r, 3, QTableWidgetItem(
            ", ".join(f"{k}={v}" for k, v in env.items())))
        headers = server.get("headers") if isinstance(server.get("headers"), dict) else {}
        self.mcp_table.setItem(r, 4, QTableWidgetItem(
            ", ".join(f"{k}={v}" for k, v in headers.items())))
        self._edited()

    def _remove_row(self):
        r = self.mcp_table.currentRow()
        if r >= 0:
            self.mcp_table.removeRow(r)
            self._edited()

    def _cell(self, r, c):
        item = self.mcp_table.item(r, c)
        return item.text().strip() if item else ""

    @staticmethod
    def _pairs(text):
        out = {}
        for part in text.split(","):
            if "=" in part:
                k, _, v = part.partition("=")
                if k.strip():
                    out[k.strip()] = v.strip()
        return out

    # --- scope switching keeps unsaved edits per scope ---
    def _on_scope_change(self, *_):
        prev = getattr(self, "_shown_scope", None)
        new_scope = self.scope_combo.currentData() or "user"
        if prev and prev != new_scope:
            self._scopes_cache[prev] = self._collect_scope_table()
        self._shown_scope = new_scope
        self._load_scope_table(new_scope)

    def _load_scope_table(self, scope):
        self.mcp_table.setRowCount(0)
        for name, srv in self._scopes_cache.get(scope, {}).items():
            if isinstance(srv, dict):
                self._add_row(name, srv)

    def _collect_scope_table(self) -> dict:
        """Rebuild the visible rows into a servers dict, preserving unknown keys."""
        out = {}
        for r in range(self.mcp_table.rowCount()):
            nitem = self.mcp_table.item(r, 0)
            name = nitem.text().strip() if nitem else ""
            if not name:
                continue
            orig = nitem.data(Qt.UserRole) or {}
            srv = dict(orig) if isinstance(orig, dict) else {}
            typ = self._cell(r, 1)
            target = self._cell(r, 2)
            env_text = self._cell(r, 3)
            hdr_text = self._cell(r, 4)
            if typ:
                srv["type"] = typ
            else:
                srv.pop("type", None)
            if typ == "http":
                srv["url"] = target
                srv.pop("command", None)
            elif target:
                srv["command"] = target
                srv.pop("url", None)
            if env_text:
                srv["env"] = self._pairs(env_text)
            else:
                srv.pop("env", None)
            if hdr_text:
                srv["headers"] = self._pairs(hdr_text)
            else:
                srv.pop("headers", None)
            out[name] = srv
        return out

    def _edited(self, *_):
        if getattr(self, "_loading", False):
            return
        scope = getattr(self, "_shown_scope", None)
        if scope:
            self._dirty_scopes.add(scope)
            self.app.status_bar.showMessage("Unsaved changes\u2026")

    def refresh(self):
        layered = getattr(self.app, "oc_layered", None)
        self._loading = True
        try:
            if layered:
                guser = layered.global_data.get("mcpServers")
                self._scopes_cache["user"] = guser if isinstance(guser, dict) else {}
                pmc = layered.project_mcp
                self._project_mcp_orig = dict(pmc) if isinstance(pmc, dict) else {}
                psrv = self._project_mcp_orig.get("mcpServers")
                self._scopes_cache["project"] = psrv if isinstance(psrv, dict) else {}
                self._scopes_cache["local"] = layered.local_mcp()
            idx = self.scope_combo.findData(getattr(self.app, "oc_mcp_scope", None) or "user")
            self.scope_combo.blockSignals(True)
            self.scope_combo.setCurrentIndex(max(0, idx))
            self.scope_combo.blockSignals(False)
            self._shown_scope = self.scope_combo.currentData() or "user"
            self._load_scope_table(self._shown_scope)
            managed = layered.managed_mcp_servers() if layered else {}
            if managed:
                names = ", ".join(sorted(managed.keys()))
                self.managed_label.setText(
                    f"Policy servers from {layered.managed_mcp_file} (read-only): {names}")
            else:
                self.managed_label.setText("No managed-mcp.json policy layer found.")
        finally:
            self._loading = False
            self._dirty_scopes = set()

    def commit_current(self):
        """Flush the visible table into the cache of the shown scope."""
        self._scopes_cache[self._shown_scope] = self._collect_scope_table()

    def global_dirty(self) -> bool:
        return "user" in self._dirty_scopes or "local" in self._dirty_scopes

    def project_dirty(self) -> bool:
        return "project" in self._dirty_scopes

    def collect_global(self, gdata):
        """Apply dirty user/local scopes into the global data dict."""
        if "user" in self._dirty_scopes:
            servers = self._scopes_cache["user"]
            if servers:
                gdata["mcpServers"] = servers
            else:
                gdata.pop("mcpServers", None)
        if "local" in self._dirty_scopes:
            layered = getattr(self.app, "oc_layered", None)
            if layered is None:
                return
            projects = gdata.get("projects")
            projects = dict(projects) if isinstance(projects, dict) else {}
            key = layered.project_key()
            entry = projects.get(key)
            entry = dict(entry) if isinstance(entry, dict) else {}
            servers = self._scopes_cache["local"]
            if servers:
                entry["mcpServers"] = servers
            else:
                entry.pop("mcpServers", None)
            if entry:
                projects[key] = entry
            else:
                projects.pop(key, None)
            if projects or "projects" in gdata:
                gdata["projects"] = projects

    def project_mcp_data(self) -> dict:
        base = dict(self._project_mcp_orig)
        servers = self._scopes_cache["project"]
        if servers or "mcpServers" in base:
            base["mcpServers"] = servers
        return base


class OpenclaudePluginsTab(BaseTab):
    """Plugin + marketplace settings keys (settings.json of the selected layer).

    Shapes verified against openclaude v0.28.0 SettingsSchema:
      enabledPlugins: {"plugin-id@marketplace-id": true|false|["version"]}
      extraKnownMarketplaces: {name: {source: {source:"github"|... , ...},
                                      installLocation?, autoUpdate?}}
    blockedMarketplaces / pluginConfigs are object lists/dicts: Raw only.
    """

    MARKET_TYPES = ("github", "git", "url", "file", "directory", "npm")

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        layout = QVBoxLayout(self)

        info = QLabel("Plugins live in the selected settings layer. Complex values "
                      "(version arrays, blockedMarketplaces, pluginConfigs) — edit in Raw.")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(QLabel("enabledPlugins — plugin-id@marketplace-id → true/false:"))
        self.plugins_table = QTableWidget(0, 2)
        self.plugins_table.setHorizontalHeaderLabels(["plugin@marketplace", "value (true/false/[..])"])
        self.plugins_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.plugins_table)
        pbtns = QHBoxLayout()
        add_p = QPushButton("Add plugin")
        add_p.clicked.connect(lambda: self._add_plugin_row())
        del_p = QPushButton("Remove selected")
        del_p.clicked.connect(self._remove_plugin_row)
        pbtns.addWidget(add_p)
        pbtns.addWidget(del_p)
        pbtns.addStretch()
        layout.addLayout(pbtns)

        layout.addWidget(QLabel("extraKnownMarketplaces — additional marketplace sources:"))
        self.market_table = QTableWidget(0, 5)
        self.market_table.setHorizontalHeaderLabels(
            ["name", "source type", "repo / url / path / package", "ref", "autoUpdate"])
        self.market_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.market_table)
        mbtns = QHBoxLayout()
        add_m = QPushButton("Add marketplace")
        add_m.clicked.connect(lambda: self._add_market_row())
        del_m = QPushButton("Remove selected")
        del_m.clicked.connect(self._remove_market_row)
        mbtns.addWidget(add_m)
        mbtns.addWidget(del_m)
        mbtns.addStretch()
        layout.addLayout(mbtns)

        self.cache_label = QLabel("")
        self.cache_label.setWordWrap(True)
        self.cache_label.setStyleSheet("color: gray;")
        layout.addWidget(self.cache_label)

    def _edited(self, *_):
        if getattr(self, "_loading", False):
            return
        self.app.status_bar.showMessage("Unsaved changes\u2026")

    # --- plugins rows ---
    def _add_plugin_row(self, pid=""):
        r = self.plugins_table.rowCount()
        self.plugins_table.insertRow(r)
        item = QTableWidgetItem(pid)
        item.setData(Qt.UserRole, None)
        self.plugins_table.setItem(r, 0, item)
        self.plugins_table.setItem(r, 1, QTableWidgetItem("true"))
        self._edited()

    def _remove_plugin_row(self):
        r = self.plugins_table.currentRow()
        if r >= 0:
            self.plugins_table.removeRow(r)
            self._edited()

    # --- marketplace rows ---
    def _add_market_row(self, name="", entry=None):
        entry = entry if isinstance(entry, dict) else {}
        src = entry.get("source") if isinstance(entry.get("source"), dict) else {}
        stype = src.get("source", "github")
        value = ""
        for fname in ("repo", "url", "path", "package"):
            if fname in src:
                value = str(src[fname])
                break
        r = self.market_table.rowCount()
        self.market_table.insertRow(r)
        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.UserRole, dict(entry))  # preserve installLocation etc.
        self.market_table.setItem(r, 0, name_item)
        self.market_table.setItem(r, 1, QTableWidgetItem(stype if stype in self.MARKET_TYPES else "github"))
        self.market_table.setItem(r, 2, QTableWidgetItem(value))
        self.market_table.setItem(r, 3, QTableWidgetItem(str(src.get("ref", "") or "")))
        chk = QCheckBox()
        chk.setChecked(bool(entry.get("autoUpdate")))
        chk.stateChanged.connect(self._edited)
        self.market_table.setCellWidget(r, 4, chk)
        self._edited()

    def _remove_market_row(self):
        r = self.market_table.currentRow()
        if r >= 0:
            self.market_table.removeRow(r)
            self._edited()

    def _pcell(self, r, c):
        item = self.plugins_table.item(r, c)
        return item.text().strip() if item else ""

    def _mcell(self, r, c):
        item = self.market_table.item(r, c)
        return item.text().strip() if item else ""

    def refresh(self):
        layered = getattr(self.app, "oc_layered", None)
        own = layered.layer(self.app.oc_layer) if layered else {}
        self._loading = True
        try:
            self.plugins_table.setRowCount(0)
            enabled = own.get("enabledPlugins")
            enabled = enabled if isinstance(enabled, dict) else {}
            for pid, val in enabled.items():
                r = self.plugins_table.rowCount()
                self._add_plugin_row(pid)
                if isinstance(val, list):
                    text = json.dumps(val)
                    self.plugins_table.item(r, 1).setData(Qt.UserRole, json.dumps(val))
                else:
                    text = "true" if val else "false"
                    self.plugins_table.item(r, 1).setData(Qt.UserRole, text)
                self.plugins_table.item(r, 1).setText(text)

            self.market_table.setRowCount(0)
            markets = own.get("extraKnownMarketplaces")
            markets = markets if isinstance(markets, dict) else {}
            for name, entry in markets.items():
                if isinstance(entry, dict):
                    self._add_market_row(name, entry)

            # Read-only listing of cached marketplaces under the config dir.
            cache_txt = ""
            if layered:
                plug_dir = layered.config_dir / "plugins"
                mk_dir = plug_dir / "marketplaces"
                try:
                    if mk_dir.is_dir():
                        found = sorted(p.name for p in mk_dir.iterdir() if p.is_dir())
                        if found:
                            cache_txt = f"Cached marketplaces ({mk_dir}): " + ", ".join(found)
                except OSError:
                    pass
            self.cache_label.setText(cache_txt or "")
        finally:
            self._loading = False

    def collect(self, data):
        # enabledPlugins
        plugins = {}
        for r in range(self.plugins_table.rowCount()):
            pid = self._pcell(r, 0)
            if not pid:
                continue
            item = self.plugins_table.item(r, 1)
            text = (item.text().strip() if item else "").lower()
            orig = item.data(Qt.UserRole) if item else None
            if text == "true":
                plugins[pid] = True
            elif text == "false":
                plugins[pid] = False
            elif text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        plugins[pid] = [str(v) for v in parsed]
                        continue
                except json.JSONDecodeError:
                    pass
                plugins[pid] = orig  # keep original verbatim when unparsable
        if "enabledPlugins" in data or plugins:
            data["enabledPlugins"] = plugins

        # extraKnownMarketplaces
        markets = {}
        for r in range(self.market_table.rowCount()):
            name = self._mcell(r, 0)
            if not name:
                continue
            nitem = self.market_table.item(r, 0)
            entry = nitem.data(Qt.UserRole) or {}
            entry = dict(entry) if isinstance(entry, dict) else {}
            stype = self._mcell(r, 1)
            value = self._mcell(r, 2)
            ref = self._mcell(r, 3)
            chk = self.market_table.cellWidget(r, 4)
            src = {"source": stype if stype in self.MARKET_TYPES else "github"}
            field = {"github": "repo", "git": "url", "url": "url",
                     "file": "path", "directory": "path", "npm": "package"}.get(src["source"], "repo")
            if value:
                src[field] = value
            if ref and src["source"] in ("github", "git"):
                src["ref"] = ref
            entry["source"] = src
            if chk is not None and not chk.isChecked():
                entry.pop("autoUpdate", None)
            elif chk is not None and chk.isChecked():
                entry["autoUpdate"] = True
            markets[name] = entry
        if "extraKnownMarketplaces" in data or markets:
            data["extraKnownMarketplaces"] = markets
