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
        _layer_change_guarded(self, self.layer_combo)

    def _edited(self, *_):
        self.app.oc_form_dirty = True
        self.app.status_bar.showMessage("Unsaved changes…")

    def refresh(self):
        layered = getattr(self.app, "oc_layered", None)
        own = layered.layer(self.app.oc_layer) if layered else {}
        eff = layered.effective() if layered else {}
        self._set_combo(self.layer_combo, self.app.oc_layer, 0)

        # statusLine (bool or {type,command}) + skip-permission booleans
        sl = own.get("statusLine")
        self._orig_statusline = sl
        self._set_checked(self.statusline_chk, bool(sl))
        self._set_text(self.statusline_cmd,
                       sl.get("command", "") if isinstance(sl, dict) else "")
        self._set_checked(self.skip_dangerous_chk, own.get("skipDangerousModePermissionPrompt"))
        self._set_checked(self.skip_fullaccess_chk, own.get("skipFullAccessModePermissionPrompt"))
        self._had_dangerous = "skipDangerousModePermissionPrompt" in own
        self._had_fullaccess = "skipFullAccessModePermissionPrompt" in own

        # MCP gating fields
        self._set_checked(self.enable_all_mcp_chk, own.get("enableAllProjectMcpServers"))
        for edit, key in ((self.enabled_mcpjson_edit, "enabledMcpjsonServers"),
                          (self.disabled_mcpjson_edit, "disabledMcpjsonServers")):
            val = own.get(key)
            self._set_text(edit, ", ".join(val) if isinstance(val, list) else "")

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
        eff_val = own.get("effortLevel", "")
        if eff_val and self.effort_combo.findData(eff_val) < 0:
            self.effort_combo.blockSignals(True)
            self.effort_combo.addItem(f"(current) {eff_val}", eff_val)
            self.effort_combo.blockSignals(False)
        self._set_combo(self.effort_combo, eff_val, 0)

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
        new_layer = self.layer_combo.currentData()
        old_layer = self._current_raw_layer()
        if new_layer == old_layer:
            return
        if self._modified:
            act = _confirm_unsaved(self.app,
                                   f"leave Raw layer '{old_layer}' with unsaved edits")
            if act == "cancel":
                self._set_combo(self.layer_combo, old_layer, 0)
                return
            if act == "save":
                self.app._save()          # raw-priority path saves this buffer
        self._raw_layer = new_layer
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
        self._set_text(self.editor, json.dumps(data, indent=2, ensure_ascii=False))
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
        # Cell edits (existing rows) must mark the tab dirty, else the global
        # rewrite is skipped on save.
        self.models_table.itemChanged.connect(self._edited)
        self.routing_table.itemChanged.connect(self._edited)
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
        if getattr(self, "_loading", False):
            return
        self._dirty = True
        self.app.oc_form_dirty = True
        self.app.status_bar.showMessage("Unsaved changes\u2026")

    # --- provider rows (providerProfiles) ---
    def _add_model_row(self, profile=None):
        profile = profile if isinstance(profile, dict) else {}
        r = self.models_table.rowCount()
        self.models_table.insertRow(r)
        name_item = QTableWidgetItem(str(profile.get("name", "")))
        # Preserve the original profile dict (id, authHeader, authScheme, ...).
        self.preserve(name_item, profile)
        self.models_table.setItem(r, 0, name_item)
        self.models_table.setItem(r, 1, QTableWidgetItem(str(profile.get("provider", ""))))
        self.models_table.setItem(r, 2, QTableWidgetItem(str(profile.get("baseUrl", ""))))
        self.models_table.setItem(r, 3, QTableWidgetItem(str(profile.get("model", ""))))
        masked = MaskedLineEdit(str(profile.get("apiKey", "")), field_name="apiKey")
        masked.textChanged.connect(self._edited)
        self.models_table.setCellWidget(r, 4, masked)
        self._edited()

    def _remove_model_row(self):
        if self.remove_current(self.models_table):
            self._edited()

    # --- agentRouting rows ---
    def _add_route_row(self, agent="", key=""):
        r = self.routing_table.rowCount()
        self.routing_table.insertRow(r)
        self.routing_table.setItem(r, 0, QTableWidgetItem(agent))
        self.routing_table.setItem(r, 1, QTableWidgetItem(key))
        self._edited()

    def _remove_route_row(self):
        if self.remove_current(self.routing_table):
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
            self._set_text(self.fallback_edit,
                           ", ".join(chain) if isinstance(chain, list) else "")

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
            orig = self.preserved(name_item) if name_item else {}
            provider = self._cell(r, 1)
            base_url = self._cell(r, 2)
            model = self._cell(r, 3)
            widget = self.models_table.cellWidget(r, 4)
            api_key = widget.value().strip() if widget else ""

            if orig.pop("_legacy_agentModels", False):
                spec = dict(orig)  # preserve extra legacy keys
                for mirror in ("name", "provider", "baseUrl", "model", "apiKey"):
                    spec.pop(mirror, None)   # UI mirrors, not schema keys
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

        known_ids = {p.get("id") for p in profiles if isinstance(p, dict)}
        active = self.active_combo.currentData() or ""
        if active and known_ids and active not in known_ids:
            active = ""                     # profile was deleted; don't dangle
        if "activeProviderProfileId" in data or active:
            self._put(data, "activeProviderProfileId", active, "")

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
        return self.cell_text(self.models_table, r, c)

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

    SCOPES = OPENCLAUDE_MCP_SCOPES          # from constants (single source)
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

        layout.addWidget(QLabel("Servers (args comma-separated; unknown sub-keys "
                                "preserved; edit complex servers in Raw):"))
        self.mcp_table = QTableWidget(0, 6)
        self.mcp_table.setHorizontalHeaderLabels(
            ["name", "transport", "command / url", "args (comma-separated)",
             "env (K=V, ...)", "headers (K=V, ...)"])
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

        # Typing into an existing cell must mark the scope dirty too, else
        # global/.mcp.json writes get skipped on save.
        self.mcp_table.itemChanged.connect(self._edited)

    # --- table helpers ---
    def _add_row(self, name="", server=None):
        server = server if isinstance(server, dict) else {}
        r = self.mcp_table.rowCount()
        self.mcp_table.insertRow(r)
        name_item = QTableWidgetItem(name)
        self.preserve(name_item, server)
        self.mcp_table.setItem(r, 0, name_item)
        typ = str(server.get("type") or ("http" if server.get("url") else "stdio"))
        self.mcp_table.setItem(r, 1, QTableWidgetItem(typ))
        target = server.get("command") if isinstance(server.get("command"), str) else \
            "" if not server.get("url") else str(server.get("url"))
        self.mcp_table.setItem(r, 2, QTableWidgetItem(str(target or "")))
        args = server.get("args") if isinstance(server.get("args"), list) else []
        args_text = ", ".join(str(a) for a in args)
        self.mcp_table.setItem(r, 3, QTableWidgetItem(args_text))
        # env/headers often carry API keys - always masked (reveal via the
        # eye toggle), like provider apiKeys.
        texts = {}
        for key in ("env", "headers"):
            val = server.get(key) if isinstance(server.get(key), dict) else {}
            texts[key] = ", ".join(f"{k}={v}" for k, v in val.items())
        for col, key in ((4, "env"), (5, "headers")):
            w = MaskedLineEdit(texts[key], field_name=key,
                               placeholder="KEY=value, ...", secret=True)
            w.textChanged.connect(self._edited)
            self.mcp_table.setCellWidget(r, col, w)
        # Remember the initially-rendered texts so collect() can tell "user
        # cleared it" apart from "never touched" (byte-fidelity for e.g. env:{}).
        name_item.setData(Qt.UserRole + 1,
                          {"env": texts["env"], "headers": texts["headers"],
                           "args": args_text})
        self._edited()

    def _remove_row(self):
        if self.remove_current(self.mcp_table):
            self._edited()

    def _cell(self, r, c):
        return self.cell_text(self.mcp_table, r, c)

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
        # Loading a scope's rows is population, not an edit — suppress the
        # itemChanged/_add_row dirty marks so merely VIEWING a scope never
        # causes its file to be rewritten.
        self._loading = True
        try:
            self._load_scope_table(new_scope)
        finally:
            self._loading = False

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
            srv = dict(self.preserved(nitem))
            typ = self._cell(r, 1)
            target = self._cell(r, 2)
            args_text = self._cell(r, 3)
            env_w = self.mcp_table.cellWidget(r, 4)
            hdr_w = self.mcp_table.cellWidget(r, 5)
            env_text = env_w.value().strip() if env_w else ""
            hdr_text = hdr_w.value().strip() if hdr_w else ""
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
            # args/env/headers: only rewrite when the user actually edited the
            # cell; an untouched cell keeps the original verbatim (e.g. env:{}).
            initial = nitem.data(Qt.UserRole + 1) or {}
            for key, cur in (("args", args_text), ("env", env_text), ("headers", hdr_text)):
                if cur != str(initial.get(key, "")).strip():
                    if key == "args" and cur:
                        srv["args"] = [a.strip() for a in cur.split(",") if a.strip()]
                    elif key != "args" and cur:
                        srv[key] = self._pairs(cur)
                    else:
                        srv.pop(key, None)
            out[name] = srv
        return out

    def _edited(self, *_):
        if getattr(self, "_loading", False):
            return
        scope = getattr(self, "_shown_scope", None)
        if scope:
            self._dirty_scopes.add(scope)
            self.app.oc_form_dirty = True
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
            self._set_combo(self.scope_combo,
                            getattr(self.app, "oc_mcp_scope", None) or "user", 0)
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

    MARKET_TYPES = OpenclaudeMcpTab.SOURCE_TYPES   # same vocabulary, one definition

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Edit layer:"))
        self.layer_combo = QComboBox()
        for lk in ("user", "project", "local"):
            self.layer_combo.addItem(lk, lk)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_change)
        top.addWidget(self.layer_combo)
        top.addStretch()
        layout.addLayout(top)

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

        self.empty_hint = QLabel("")
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet("color: gray;")
        layout.addWidget(self.empty_hint)

    def _on_layer_change(self, *_):
        _layer_change_guarded(self, self.layer_combo)

    def _edited(self, *_):
        if getattr(self, "_loading", False):
            return
        self.app.oc_form_dirty = True
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
        if self.remove_current(self.plugins_table):
            self._edited()

    # --- marketplace rows ---
    def _add_market_row(self, name="", entry=None):
        entry = entry if isinstance(entry, dict) else {}
        src = entry.get("source") if isinstance(entry.get("source"), dict) else {}
        stype = str(src.get("source", "github"))
        value = ""
        for fname in ("repo", "url", "path", "package"):
            if fname in src:
                value = str(src[fname])
                break
        r = self.market_table.rowCount()
        self.market_table.insertRow(r)
        name_item = QTableWidgetItem(name)
        self.preserve(name_item, entry)  # keep installLocation etc.
        ref_text = str(src.get("ref", "") or "")
        item_snapshot = {"name": name, "stype": stype, "value": value,
                         "ref": ref_text, "auto": bool(entry.get("autoUpdate"))}
        name_item.setData(Qt.UserRole + 1, item_snapshot)
        self.market_table.setItem(r, 0, name_item)
        self.market_table.setItem(r, 1, QTableWidgetItem(stype))
        self.market_table.setItem(r, 2, QTableWidgetItem(value))
        self.market_table.setItem(r, 3, QTableWidgetItem(ref_text))
        chk = QCheckBox()
        chk.setChecked(bool(entry.get("autoUpdate")))
        chk.stateChanged.connect(self._edited)
        self.market_table.setCellWidget(r, 4, chk)
        self._edited()

    def _remove_market_row(self):
        if self.remove_current(self.market_table):
            self._edited()

    def _pcell(self, r, c):
        return self.cell_text(self.plugins_table, r, c)

    def _mcell(self, r, c):
        return self.cell_text(self.market_table, r, c)

    def refresh(self):
        layered = getattr(self.app, "oc_layered", None)
        own = layered.layer(self.app.oc_layer) if layered else {}
        self._loading = True
        try:
            self._set_combo(self.layer_combo, self.app.oc_layer, 0)
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
            # empty-state hint: point at layers that DO hold plugin settings
            if self.plugins_table.rowCount() or self.market_table.rowCount():
                self.empty_hint.setText("")
            else:
                msg = f"No plugin settings in the '{getattr(self.app, 'oc_layer', '?')}' layer."
                found = []
                if layered:
                    for lk in ("user", "project", "local"):
                        if lk == self.app.oc_layer:
                            continue
                        data = layered.layer(lk)
                        if isinstance(data.get("enabledPlugins"), dict) and data["enabledPlugins"]:
                            found.append(f"{lk} (plugins)")
                        if isinstance(data.get("extraKnownMarketplaces"), dict) and data["extraKnownMarketplaces"]:
                            found.append(f"{lk} (marketplaces)")
                if found:
                    msg += " Found in: " + ", ".join(found) + \
                           " — switch 'Edit layer' above."
                self.empty_hint.setText(msg)
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
            entry = self.preserved(nitem)
            stype = self._mcell(r, 1)
            value = self._mcell(r, 2)
            ref = self._mcell(r, 3)
            chk = self.market_table.cellWidget(r, 4)
            snap = nitem.data(Qt.UserRole + 1) or {}
            auto_now = bool(chk.isChecked()) if chk else False
            untouched = (
                name == str(snap.get("name", ""))
                and stype == str(snap.get("stype", ""))
                and value == str(snap.get("value", ""))
                and ref == str(snap.get("ref", ""))
                and auto_now == bool(snap.get("auto", False)))
            if untouched:
                markets[name] = entry     # byte-fidelity for unedited sources
                continue
            src = {"source": stype or "github"}
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


class OpenclaudeHooksTab(BaseTab):
    """Structured editor for settings.json `hooks`.

    Verified shape (binary schema + real configs):
      hooks: {EventName: [ {matcher?: "*",
                            hooks: [{type: "command", command, timeout?, ...},
                                    ...]},
                           ... ] }
    One table row per hook ENTRY. Fidelity model:
    - every row remembers its original (event, group-index, entry-index);
    - untouched rows/events round-trip byte-for-byte (unknown group/entry
      keys survive);
    - editing patches only the touched fields; clearing removes them;
    - deleting a row removes exactly that entry (its group too when emptied);
    - new/moved rows append as fresh groups under their event, grouped by
      matcher text.
    """

    KNOWN_EVENTS = ("SessionStart", "SessionEnd", "UserPromptSubmit", "Stop",
                    "StopFailure", "SubagentStart", "SubagentStop",
                    "TeammateIdle", "PreToolUse", "PostToolUse",
                    "PostToolUseFailure", "PermissionRequest", "Notification",
                    "PreCompact")
    TYPE_FIELDS = {"command": "command", "http": "url", "prompt": "prompt"}

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Edit layer:"))
        self.layer_combo = QComboBox()
        for lk in ("user", "project", "local"):
            self.layer_combo.addItem(lk, lk)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_change)
        top.addWidget(self.layer_combo)
        top.addStretch()
        layout.addLayout(top)

        info = QLabel("hooks — one row per hook entry. Events: "
                      + ", ".join(self.KNOWN_EVENTS)
                      + " (free text allowed). Unknown group/entry keys are "
                        "preserved; edit exotic shapes in Raw.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.hooks_table = QTableWidget(0, 5)
        self.hooks_table.setHorizontalHeaderLabels(
            ["event", "matcher", "type", "command / url / prompt", "timeout"])
        self.hooks_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.hooks_table)
        btns = QHBoxLayout()
        add_b = QPushButton("Add hook")
        add_b.clicked.connect(lambda: self._add_row("SessionStart"))
        del_b = QPushButton("Remove selected")
        del_b.clicked.connect(self._remove_hook_row)
        btns.addWidget(add_b)
        btns.addWidget(del_b)
        btns.addStretch()
        layout.addLayout(btns)

        self.empty_hint = QLabel("")
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet("color: gray;")
        layout.addWidget(self.empty_hint)
        self.hooks_table.itemChanged.connect(self._edited)

    def _on_layer_change(self, *_):
        _layer_change_guarded(self, self.layer_combo)

    @staticmethod
    def _count_hook_entries(hooks):
        """Count hook entries in a parsed hooks dict (0 for odd shapes)."""
        n = 0
        for groups in hooks.values() if isinstance(hooks, dict) else []:
            if isinstance(groups, list):
                for grp in groups:
                    if isinstance(grp, dict) and isinstance(grp.get("hooks"), list):
                        n += sum(1 for e in grp["hooks"] if isinstance(e, dict))
        return n

    def _update_empty_hint(self, layered, own):
        if self.hooks_table.rowCount():
            self.empty_hint.setText("")
            return
        msg = f"No hooks in the '{getattr(self.app, 'oc_layer', '?')}' layer."
        found = []
        if layered:
            for lk in ("user", "project", "local"):
                if lk == self.app.oc_layer:
                    continue
                n = self._count_hook_entries(layered.layer(lk).get("hooks"))
                if n:
                    found.append(f"{lk} ({n} entries)")
        if found:
            msg += " Hooks found in: " + ", ".join(found) + \
                   " — switch 'Edit layer' above."
        self.empty_hint.setText(msg)

    def _edited(self, *_):
        if getattr(self, "_loading", False):
            return
        self.app.oc_form_dirty = True
        self.app.status_bar.showMessage("Unsaved changes\u2026")

    def _add_row(self, event="", matcher="", typ="command", target="",
                 timeout="", orig=None, gi=None, ei=None):
        orig = orig if isinstance(orig, dict) else {"group": {}, "entry": {}}
        r = self.hooks_table.rowCount()
        self.hooks_table.insertRow(r)
        item = QTableWidgetItem(event)
        item.setData(Qt.UserRole, {"group": orig.get("group") or {},
                                   "entry": orig.get("entry") or {}})
        snapshot = {"event": event, "matcher": matcher, "type": typ,
                    "target": target, "timeout": timeout,
                    "gi": gi if gi is not None else -1,
                    "ei": ei if ei is not None else -1}
        item.setData(Qt.UserRole + 1, snapshot)
        self.hooks_table.setItem(r, 0, item)
        self.hooks_table.setItem(r, 1, QTableWidgetItem(matcher))
        self.hooks_table.setItem(r, 2, QTableWidgetItem(typ))
        self.hooks_table.setItem(r, 3, QTableWidgetItem(target))
        self.hooks_table.setItem(r, 4, QTableWidgetItem(timeout))
        self._edited()

    def _remove_hook_row(self):
        if self.remove_current(self.hooks_table):
            self._edited()

    def _cell(self, r, c):
        return self.cell_text(self.hooks_table, r, c)

    @staticmethod
    def _entry_from_cells(typ, target, timeout):
        entry = {"type": typ} if typ else {}
        field = OpenclaudeHooksTab.TYPE_FIELDS.get(typ)
        if target and field:
            entry[field] = target
        if timeout.strip().isdigit():
            entry["timeout"] = int(timeout.strip())
        return entry

    def _rows_snapshot(self):
        """Current cell values + stored metadata for every row, in table order."""
        rows = []
        for r in range(self.hooks_table.rowCount()):
            item = self.hooks_table.item(r, 0)
            if item is None:
                continue
            meta = item.data(Qt.UserRole + 1) or {}
            rows.append({
                "r": r,
                "stored_event": str(meta.get("event", "")),
                "cur_event": self._cell(r, 0),
                "matcher": self._cell(r, 1),
                "typ": self._cell(r, 2),
                "target": self._cell(r, 3),
                "timeout": self._cell(r, 4),
                "meta": meta,
                "orig": self.preserved(item),
            })
        return rows

    @staticmethod
    def _row_touched(row):
        m = row["meta"]
        return (row["cur_event"] != str(m.get("event", ""))
                or row["matcher"] != str(m.get("matcher", ""))
                or row["typ"] != str(m.get("type", ""))
                or row["target"] != str(m.get("target", ""))
                or row["timeout"] != str(m.get("timeout", "")))

    def refresh(self):
        layered = getattr(self.app, "oc_layered", None)
        own = layered.layer(self.app.oc_layer) if layered else {}
        self._loading = True
        try:
            self._set_combo(self.layer_combo, self.app.oc_layer, 0)
            self.hooks_table.setRowCount(0)
            hooks = own.get("hooks") if isinstance(own.get("hooks"), dict) else {}
            for ev, groups in hooks.items():
                if not isinstance(groups, list):
                    continue          # odd shapes stay verbatim via Raw/passthrough
                for gi, grp in enumerate(groups):
                    entries = grp.get("hooks") if isinstance(grp, dict) else None
                    if not isinstance(entries, list):
                        continue
                    matcher = str(grp.get("matcher", "") or "")
                    for ei, entry in enumerate(entries):
                        if not isinstance(entry, dict):
                            continue
                        typ = str(entry.get("type", "command"))
                        field = self.TYPE_FIELDS.get(typ, "command")
                        target = str(entry.get(field, "") or "")
                        timeout = (str(entry.get("timeout"))
                                   if entry.get("timeout") is not None else "")
                        self._add_row(str(ev), matcher, typ, target, timeout,
                                      orig={"group": grp, "entry": entry},
                                      gi=gi, ei=ei)
        finally:
            self._loading = False
            self._update_empty_hint(layered, own)

    def collect(self, data):
        rows = self._rows_snapshot()
        if "hooks" not in data and not rows:
            return
        orig_hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
        out = {}

        def place_new(pending):
            """Group brand-new/moved rows by matcher text into fresh groups."""
            buckets = {}
            for row in pending:
                buckets.setdefault(row["matcher"], []).append(row)
            groups = []
            for mtext, rs in buckets.items():
                grp = {}
                if mtext:
                    grp["matcher"] = mtext
                grp["hooks"] = [
                    self._entry_from_cells(x["typ"], x["target"], x["timeout"])
                    for x in rs]
                groups.append(grp)
            return groups

        for ev, groups in orig_hooks.items():
            # Map original entries to their rows. Fresh rows (gi=-1) never map;
            # membership is tracked by id() because dict equality would treat
            # identical-looking rows as the same object.
            slot = {}
            slotted = set()
            for row in rows:
                if (row["stored_event"] == ev and row["cur_event"] == ev
                        and int(row["meta"].get("gi", -1)) >= 0):
                    slot[(row["meta"]["gi"], row["meta"]["ei"])] = row
                    slotted.add(id(row))
            pending = [row for row in rows
                       if row["cur_event"] == ev and id(row) not in slotted]
            if not slot and not pending:
                continue             # event emptied or all rows moved away
            new_groups = []
            for gi, grp in enumerate(groups):
                entries = (grp.get("hooks")
                           if isinstance(grp, dict) and isinstance(grp.get("hooks"), list)
                           else None)
                if entries is None:
                    new_groups.append(grp)   # unknown shape: verbatim
                    continue
                kept = dict(grp)
                live = []
                matcher_new = None
                for ei, entry in enumerate(entries):
                    row = slot.get((gi, ei))
                    if row is None:
                        continue             # entry removed
                    if not self._row_touched(row):
                        live.append(entry)   # byte-verbatim
                        continue
                    e2 = dict(entry) if isinstance(entry, dict) else {}
                    for f in self.TYPE_FIELDS.values():
                        e2.pop(f, None)
                    e2.update(self._entry_from_cells(row["typ"], row["target"],
                                                     row["timeout"]))
                    if not row["typ"]:
                        e2.pop("type", None)
                    if "timeout" not in e2:
                        e2.pop("timeout", None)
                    live.append(e2)
                    if row["matcher"] != str(row["meta"].get("matcher", "")):
                        matcher_new = row["matcher"]
                if not live:
                    continue                 # group emptied by removals
                kept["hooks"] = live
                if matcher_new is not None:
                    if matcher_new:
                        kept["matcher"] = matcher_new
                    else:
                        kept.pop("matcher", None)
                new_groups.append(kept)
            new_groups.extend(place_new(pending))
            if new_groups:
                out[ev] = new_groups

        # Rows added under events the file never had (or moved to new names);
        # rows under existing events were already placed by the loop above.
        pending = [row for row in rows
                   if row["cur_event"] and row["cur_event"] not in orig_hooks]
        pend_by_ev = {}
        for row in pending:
            pend_by_ev.setdefault(row["cur_event"], []).append(row)
        for ev, rs in pend_by_ev.items():
            merged = list(out.get(ev, []))
            merged.extend(place_new(rs))
            out[ev] = merged

        if out or "hooks" in data:
            data["hooks"] = out
