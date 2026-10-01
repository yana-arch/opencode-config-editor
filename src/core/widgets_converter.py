# Universal Cross-Config Converter GUI Dialog
# ---------------------------------------------------------------------------


_OMP_COMPONENTS = ("providers", "mcp_servers", "plugins", "permissions", "prompts", "settings")


class CrossConfigConverterDialog(QDialog):
    """Dialog to convert and transfer configurations across OpenCode, OpenClaude, OMP v1, Claude Desktop, and Cursor."""

    def __init__(self, parent=None, app_context=None):
        super().__init__(parent)
        self.setWindowTitle("🔄 Universal AI Config Converter & Importer/Exporter")
        self.setMinimumSize(920, 620)
        self.app_context = app_context
        self.source_data: Dict[str, Any] = {}
        self.source_valid = False
        self.unmapped_keys: List[str] = []
        self.converted_data: Dict[str, Any] = {}

        layout = QVBoxLayout(self)

        # Header description
        info = QLabel(
            "Convert, migrate, or bundle configurations seamlessly between OpenCode, OpenClaude, OMP v1, Cursor, and Claude Desktop."
        )
        info.setStyleSheet("color: #666; margin-bottom: 6px;")
        layout.addWidget(info)

        # Splitter: Source & Options on Left, Target & Preview on Right
        splitter = QSplitter(Qt.Horizontal)

        # Left Panel: Source & Selections
        left_panel = QWidget()
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)

        # Source Selection Group
        src_group = QGroupBox("1. Source Configuration")
        src_lay = QVBoxLayout(src_group)

        src_top = QHBoxLayout()
        self.src_type_combo = QComboBox()
        self.src_type_combo.addItem("Current Active OpenCode Config", "active_opencode")
        self.src_type_combo.addItem("Current Active OpenClaude Config", "active_openclaude")
        self.src_type_combo.addItem("Load from File...", "file")
        self.src_type_combo.addItem("Paste Custom JSON", "custom")
        self.src_type_combo.currentIndexChanged.connect(self._on_source_type_changed)
        src_top.addWidget(self.src_type_combo, 1)

        self.load_file_btn = QPushButton("Browse...")
        self.load_file_btn.clicked.connect(self._load_source_file)
        self.load_file_btn.hide()
        src_top.addWidget(self.load_file_btn)
        src_lay.addLayout(src_top)

        self.src_editor = QTextEdit()
        self.src_editor.setPlaceholderText("Source JSON will appear here...")
        self.src_editor.textChanged.connect(self._on_source_text_changed)
        src_lay.addWidget(self.src_editor)
        left_lay.addWidget(src_group, 2)

        # Component Filters Group
        comp_group = QGroupBox("2. Select Components to Transfer")
        comp_lay = QVBoxLayout(comp_group)

        self.comp_checks = {
            "providers": QCheckBox("Providers & Models"),
            "mcp_servers": QCheckBox("MCP Servers"),
            "plugins": QCheckBox("Plugins"),
            "permissions": QCheckBox("Permissions (allow / deny / ask)"),
            "prompts": QCheckBox("Instructions / Prompts"),
            "settings": QCheckBox("Environment & TUI Settings"),
        }
        for chk in self.comp_checks.values():
            chk.setChecked(True)
            chk.stateChanged.connect(self._run_conversion)
            comp_lay.addWidget(chk)

        left_lay.addWidget(comp_group, 1)
        splitter.addWidget(left_panel)

        # Right Panel: Target & Output Preview
        right_panel = QWidget()
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(0, 0, 0, 0)

        # Target Selection Group
        tgt_group = QGroupBox("3. Target Format")
        tgt_lay = QVBoxLayout(tgt_group)

        self.tgt_format_combo = QComboBox()
        self.tgt_format_combo.addItem("OpenCode Config (opencode.json)", "opencode")
        self.tgt_format_combo.addItem("OpenClaude Global (~/.openclaude.json / .mcp.json)", "openclaude_global")
        self.tgt_format_combo.addItem("OpenClaude Settings (settings.json)", "openclaude_settings")
        self.tgt_format_combo.addItem("OMP v1 Universal Bundle (omp.json)", "omp")
        self.tgt_format_combo.addItem("Claude Desktop / Cursor MCP (mcpServers)", "claude_desktop")
        self.tgt_format_combo.currentIndexChanged.connect(self._run_conversion)
        tgt_lay.addWidget(self.tgt_format_combo)
        right_lay.addWidget(tgt_group)

        # Output Preview Group
        out_group = QGroupBox("4. Resulting Output Preview")
        out_lay = QVBoxLayout(out_group)
        self.out_editor = QTextEdit()
        self.out_editor.setReadOnly(True)
        out_lay.addWidget(self.out_editor)
        self.unmapped_label = QLabel("")
        self.unmapped_label.setWordWrap(True)
        self.unmapped_label.setStyleSheet("color: #b26a00;")
        self.unmapped_label.setVisible(False)
        out_lay.addWidget(self.unmapped_label)

        out_btns = QHBoxLayout()
        copy_btn = QPushButton("📋 Copy Result")
        copy_btn.clicked.connect(self._copy_result)
        out_btns.addWidget(copy_btn)

        save_btn = QPushButton("💾 Save to File...")
        save_btn.clicked.connect(self._save_to_file)
        out_btns.addWidget(save_btn)
        out_lay.addLayout(out_btns)

        right_lay.addWidget(out_group, 1)
        splitter.addWidget(right_panel)
        splitter.setSizes([430, 490])
        layout.addWidget(splitter, 1)

        # Bottom Actions
        bottom_bar = QHBoxLayout()
        self.apply_btn = QPushButton("⚡ Apply Directly to Active Config")
        self.apply_btn.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.apply_btn.clicked.connect(self._apply_to_active)
        bottom_bar.addWidget(self.apply_btn)

        bottom_bar.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom_bar.addWidget(close_btn)
        layout.addLayout(bottom_bar)

        # Initial source load
        self._on_source_type_changed(0)

    def _on_source_type_changed(self, idx: int):
        src_type = self.src_type_combo.currentData()
        self.load_file_btn.setVisible(src_type == "file")

        if src_type == "active_opencode":
            if self.app_context and getattr(self.app_context, "cfg", None):
                self.source_data = dict(self.app_context.cfg.data)
                self.src_editor.setPlainText(json.dumps(self.source_data, indent=2, ensure_ascii=False))
            else:
                self.src_editor.setPlainText("{\n  \"provider\": {}\n}")
        elif src_type == "active_openclaude":
            layered = getattr(self.app_context, "oc_layered", None) if self.app_context else None
            if layered is not None:
                combined = dict(layered.global_data or {})
                for key, val in (layered.effective() or {}).items():
                    combined.setdefault(key, val)
                # .mcp.json holds {"mcpServers": {...}}; merge just the servers,
                # or they end up double-nested under mcpServers.mcpServers.
                project_servers = (layered.project_mcp or {}).get("mcpServers")
                if isinstance(project_servers, dict) and project_servers:
                    existing = combined.get("mcpServers")
                    combined["mcpServers"] = (
                        {**existing, **project_servers} if isinstance(existing, dict) else dict(project_servers)
                    )
                self.src_editor.setPlainText(json.dumps(combined, indent=2, ensure_ascii=False))
            else:
                self.src_editor.setPlainText("{\n  \"mcpServers\": {}\n}")
        elif src_type == "file":
            self.src_editor.setPlaceholderText("Click 'Browse...' to select a config file to import.")
        elif src_type == "custom":
            self.src_editor.setPlaceholderText("Paste any JSON config here...")

    def _load_source_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Config File to Import", "",
            "JSON files (*.json *.jsonc);;All files (*)"
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
            data = loads_jsonc(content)
            self.src_editor.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Failed to load file: {e}")

    def _on_source_text_changed(self):
        text = self.src_editor.toPlainText().strip()
        if not text:
            self.source_data = {}
            self.converted_data = {}
            self.source_valid = False
            self.out_editor.clear()
            return
        try:
            data = loads_jsonc(text)
        except Exception:
            self.source_valid = False
            self.source_data = {}
            self.converted_data = {}
            self.out_editor.setPlainText("// Invalid JSON input in source editor")
            return
        if not isinstance(data, dict):
            self.source_valid = False
            self.source_data = {}
            self.converted_data = {}
            self.out_editor.setPlainText("// Source JSON must be an object")
            return
        self.source_valid = True
        self.source_data = data
        self._run_conversion()

    def _get_selected_components(self) -> List[str]:
        return [k for k, chk in self.comp_checks.items() if chk.isChecked()]

    def _run_conversion(self):
        if not self.source_data:
            self.converted_data = {}
            self.unmapped_keys = []
            self.out_editor.clear()
            self.unmapped_label.setText("")
            self.unmapped_label.setVisible(False)
            return

        target_fmt = self.tgt_format_combo.currentData()
        comps = self._get_selected_components()
        src_fmt = detect_config_format(self.source_data)

        # 1. Normalize source to OMP bundle first as intermediate universal format
        if src_fmt == "omp":
            omp_bundle = self.source_data
        elif src_fmt == "openclaude_global":
            omp_bundle = export_to_omp(openclaude_global=self.source_data)
        elif src_fmt == "openclaude_settings":
            omp_bundle = export_to_omp(openclaude_settings=self.source_data)
        elif src_fmt == "claude_desktop":
            omp_bundle = export_to_omp(openclaude_global=self.source_data)
        else:
            # Assume opencode
            omp_bundle = export_to_omp(opencode_cfg=self.source_data)

        # 2. Convert OMP bundle to target format
        if target_fmt == "omp":
            # OMP is the intermediate format itself: honour the component filter
            omp_bundle = {k: v for k, v in omp_bundle.items() if k not in _OMP_COMPONENTS or k in comps}
            self.converted_data = omp_bundle
        elif target_fmt == "claude_desktop":
            mcp_data = import_from_omp(omp_bundle, "openclaude_global", comps)
            self.converted_data = {"mcpServers": mcp_data.get("mcpServers", {})}
        else:
            self.converted_data = import_from_omp(omp_bundle, target_fmt, comps)

        self.unmapped_keys = self._find_unmapped_keys(src_fmt)
        if self.unmapped_keys:
            self.unmapped_label.setText(
                "Not transferred (no mapping for this target): " + ", ".join(self.unmapped_keys)
            )
            self.unmapped_label.setVisible(True)
        else:
            self.unmapped_label.setText("")
            self.unmapped_label.setVisible(False)
        self.out_editor.setPlainText(json.dumps(self.converted_data, indent=2, ensure_ascii=False))

    def _find_unmapped_keys(self, src_fmt: str) -> List[str]:
        """Top-level source keys the conversion has no mapping for."""
        handled = {
            "opencode": {"provider", "mcp", "plugin", "permission", "instructions", "tui"},
            "openclaude_global": {"mcpServers", "providerProfiles"},
            "openclaude_settings": {"permissions", "env"},
            "claude_desktop": {"mcpServers"},
        }.get(src_fmt, set())
        if src_fmt == "omp":
            handled = set(_OMP_COMPONENTS)
        return sorted(str(k) for k in self.source_data if str(k) not in handled)

    def _copy_result(self):
        text = self.out_editor.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            QMessageBox.information(self, "Copied", "Converted configuration copied to clipboard.")

    def _save_to_file(self):
        if not self.source_valid or not self.converted_data:
            QMessageBox.warning(self, "No Data", "Nothing to save: fix the source JSON first.")
            return
        target_fmt = self.tgt_format_combo.currentData()
        default_name = f"{target_fmt}-config.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Converted Config", default_name,
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return
        target = Path(path)
        try:
            payload = json.loads(json.dumps(self.converted_data))
            # Merge into an existing file so unrelated keys (app state, other
            # sections) survive; only keys the conversion produced are written.
            if target.is_file():
                existing = loads_jsonc(target.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    payload = deep_merge(existing, copy.deepcopy(payload))
            atomic_write_json(target, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            QMessageBox.information(self, "Saved", f"Exported successfully to {path}")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save file: {e}")

    def _apply_to_active(self):
        if not self.source_valid:
            QMessageBox.warning(self, "No Data", "Fix the source JSON before applying.")
            return
        if not self.converted_data:
            QMessageBox.warning(self, "No Data", "No converted data to apply.")
            return

        if not self.app_context:
            QMessageBox.warning(self, "Error", "No active editor instance found.")
            return
        target_fmt = self.tgt_format_combo.currentData()

        # Apply merges into in-memory data (or writes straight to disk for OpenClaude) and
        # then reloads the tabs. Any pending form/Raw edit lives only in the tab widgets
        # until Save, so refresh would silently drop it. Settle those edits first.
        if target_fmt == "opencode":
            unsaved = (
                bool(getattr(self.app_context, "dirty_oc", False))
                or bool(getattr(self.app_context, "dirty_tui", False))
                or bool(getattr(getattr(self.app_context, "tab_raw", None), "_modified", False))
            )
        else:
            unsaved = (
                bool(getattr(self.app_context, "oc_form_dirty", False))
                or bool(getattr(getattr(self.app_context, "_agent_raw_tab", None), "_modified", False))
            )
        if unsaved:
            action = _confirm_unsaved(self.app_context, "apply the converted configuration")
            if action == "cancel":
                return
            if action == "save":
                self.app_context._save()

        if target_fmt == "opencode" and getattr(self.app_context, "cfg", None):
            if not _confirm(self, "Apply Config", "Merge converted settings into current OpenCode configuration?"):
                return
            self.app_context.snapshot_state("opencode")
            self.app_context.cfg.data = deep_merge(
                self.app_context.cfg.data, copy.deepcopy(self.converted_data)
            )
            self.app_context.mark_dirty("opencode")
            self.app_context.refresh_tabs()
            QMessageBox.information(self, "Success", "Applied converted settings to OpenCode configuration.")
            self.accept()

        elif "openclaude" in target_fmt:
            layered = getattr(self.app_context, "oc_layered", None)
            if layered is None:
                QMessageBox.information(
                    self, "Format Mismatch",
                    f"Please export to file or copy result to use with {target_fmt}.",
                )
                return
            if not _confirm(self, "Apply Config", "Apply converted settings into current OpenClaude configuration?"):
                return
            if target_fmt == "openclaude_global":
                merged = deep_merge(dict(layered.global_data or {}), copy.deepcopy(self.converted_data))
                ok, msg = layered.save_global(merged)
            else:
                merged = deep_merge(dict(layered.layer("user") or {}), copy.deepcopy(self.converted_data))
                ok, msg = layered.save_layer("user", merged)
            if not ok:
                QMessageBox.warning(self, "Save Error", msg)
                return
            self.app_context.refresh_tabs()
            QMessageBox.information(self, "Success", "Applied converted settings to OpenClaude configuration.")
            self.accept()
        else:
            QMessageBox.information(self, "Format Mismatch", f"Please export to file or copy result to use with {target_fmt}.")
