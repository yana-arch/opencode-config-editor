# Providers tab
class ProvidersTab(QWidget):
    """Enhanced providers tab with search and bulk operations"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.rows = []  # (provider_name, npm_edit, name_edit)

        layout = QVBoxLayout(self)

        # Search and buttons
        top_layout = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search providers...")
        self.search_edit.textChanged.connect(self._filter_providers)
        top_layout.addWidget(self.search_edit)

        for text, slot in [
            ("+ Add", self._add_provider),
            ("Import", self._import_providers),
            ("Fetch from API", self._fetch_provider_models),
            ("Export", self._export_providers),
            ("Enable All", lambda: self._set_all_enabled(True)),
            ("Disable All", lambda: self._set_all_enabled(False))
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            top_layout.addWidget(btn)

        layout.addLayout(top_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Provider", "npm", "Name", "Models / Options", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        layout.addWidget(self.table)

        # Status
        self.status_label = QLabel()
        layout.addWidget(self.status_label)

    def _filter_providers(self, text: str):
        """Filter providers by search text"""
        if not text:
            self.refresh()
            return

        text = text.lower()
        providers = self.app.cfg.data.get("provider", {}) if self.app.cfg else {}
        filtered = {
            name: cfg for name, cfg in providers.items()
            if text in name.lower() or
               (isinstance(cfg.get("npm"), str) and text in cfg["npm"].lower()) or
               (isinstance(cfg.get("name"), str) and text in cfg["name"].lower())
        }

        self._update_table(filtered)

    def _update_table(self, providers: Optional[dict] = None):
        """Update table with providers"""
        if providers is None:
            providers = self.app.cfg.data.get("provider", {}) if self.app.cfg else {}

        self.table.setRowCount(len(providers))
        self.rows = []

        for row, (name, cfg) in enumerate(sorted(providers.items())):
            if not isinstance(cfg, dict):
                cfg = {}

            # Provider name
            self.table.setItem(row, 0, QTableWidgetItem(name))

            # npm
            npm_edit = MaskedLineEdit(cfg.get("npm", ""), field_name="npm")
            npm_edit.edit.editingFinished.connect(self.app.mark_dirty)
            self.table.setCellWidget(row, 1, npm_edit)

            # Name
            name_edit = MaskedLineEdit(cfg.get("name", ""), field_name="name")
            name_edit.edit.editingFinished.connect(self.app.mark_dirty)
            self.table.setCellWidget(row, 2, name_edit)

            # Models/Options
            n_models = len(cfg.get("models", {})) if isinstance(cfg.get("models"), dict) else 0
            base_url = cfg.get("options", {}).get("baseURL", "") if isinstance(cfg.get("options"), dict) else ""

            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(2, 0, 2, 0)

            summary = QLabel(f"{n_models} models  {base_url}")
            summary.setToolTip(json.dumps(cfg, ensure_ascii=False, indent=2)[:4000])
            cell_layout.addWidget(summary, 1)

            models_btn = QPushButton("Models...")
            models_btn.clicked.connect(lambda _, n=name: self._edit_models(n))
            cell_layout.addWidget(models_btn)

            options_btn = QPushButton("Options...")
            options_btn.clicked.connect(lambda _, n=name: self._edit_options(n))
            cell_layout.addWidget(options_btn)

            self.table.setCellWidget(row, 3, cell)

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedWidth(60)
            edit_btn.clicked.connect(lambda _, n=name: self._edit_provider(n))
            actions_layout.addWidget(edit_btn)

            remove_btn = QPushButton("Remove")
            remove_btn.setFixedWidth(60)
            remove_btn.clicked.connect(lambda _, n=name: self._remove_provider(n))
            actions_layout.addWidget(remove_btn)

            self.table.setCellWidget(row, 4, actions_widget)

            self.rows.append((name, npm_edit, name_edit))

        self.status_label.setText(f"{len(providers)} providers")

    def refresh(self):
        """Refresh table with current data"""
        self._update_table()

    def _add_provider(self):
        """Add new provider"""
        self.app.snapshot_state()
        name, ok = QInputDialog.getText(
            self, "Add Provider", "Provider key:",
            QLineEdit.Normal, "new-provider"
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        providers = self.app.cfg.data.setdefault("provider", {})

        if name in providers:
            QMessageBox.warning(self, "Error", f"Provider '{name}' already exists")
            return

        providers[name] = {
            "npm": "@ai-sdk/openai",
            "name": name,
            "models": {}
        }
        self.app.mark_dirty()
        self.refresh()

    def _edit_provider(self, name: Optional[str] = None):
        """Edit provider"""
        self.app.snapshot_state()
        if name is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Edit", "Please select a provider to edit")
                return
            name = selected[0].text()

        providers = self.app.cfg.data.get("provider", {})
        if name not in providers:
            QMessageBox.warning(self, "Error", f"Provider '{name}' not found")
            return

        new_name, ok = QInputDialog.getText(
            self, "Edit Provider", "New provider key:",
            QLineEdit.Normal, name
        )
        if not ok:
            return

        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Error", "Provider key cannot be empty")
            return

        if new_name != name and new_name in providers:
            QMessageBox.warning(self, "Error", f"Provider '{new_name}' already exists")
            return

        if new_name != name:
            providers[new_name] = providers.pop(name)

        self.app.mark_dirty()
        self.refresh()

    def _remove_provider(self, name: Optional[str] = None):
        """Remove provider(s)"""
        self.app.snapshot_state()
        if name is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Remove", "Please select providers to remove")
                return

            names = {selected[i].text() for i in range(0, len(selected), self.table.columnCount())}
            if not _confirm(self, "Remove Providers", f"Remove {len(names)} selected providers?"):
                return

            providers = self.app.cfg.data.get("provider", {})
            for name in names:
                providers.pop(name, None)
        else:
            if not _confirm(self, "Remove Provider", f"Remove provider '{name}'?"):
                return

            self.app.cfg.data.get("provider", {}).pop(name, None)

        self.app.mark_dirty()
        self.refresh()

    def _import_providers(self):
        """Import providers from JSON"""
        self.app.snapshot_state()
        dlg = JsonImportDialog(
            self, "Import Providers",
            "Paste or load provider JSON. Supported formats:\n"
            "- Single provider object\n"
            "- {name: provider} map\n"
            "- Full config with 'provider' key"
        )
        if dlg.exec() != QDialog.Accepted:
            return

        try:
            parsed = parse_provider_import(dlg.result_data)
        except ValueError as e:
            QMessageBox.warning(self, "Import Error", str(e))
            return

        providers = self.app.cfg.data.setdefault("provider", {})
        added = 0
        updated = 0

        for name, cfg in parsed.items():
            if name in providers:
                if _confirm(
                    self, "Provider Exists",
                    f"Provider '{name}' already exists. Merge with existing?"
                ):
                    providers[name] = merge_dict(providers[name], cfg)
                    updated += 1
            else:
                providers[name] = cfg
                added += 1

        self.app.mark_dirty()
        self.refresh()
        QMessageBox.information(
            self, "Import Complete",
            f"Added {added} new providers, updated {updated} existing providers"
        )

    def _fetch_provider_models(self):
        """Fetch a provider's model list from its API, then auto-match the catalog."""
        self.app.snapshot_state()

        # Fill the dialog's Reference provider combo (silently loads bundled catalog).
        try_load_bundled_catalog(self.app.model_catalog)
        dlg = FetchProviderModelsDialog(self, catalog=self.app.model_catalog)
        if dlg.exec() != QDialog.Accepted:
            return

        key = dlg.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Fetch", "Provider key cannot be empty.")
            return

        selected = dlg.selected_models
        if not selected:
            QMessageBox.information(self, "Fetch", "No models selected.")
            return

        reference = dlg.reference_provider

        providers = self.app.cfg.data.setdefault("provider", {})
        prov = providers.setdefault(key, {"npm": "@ai-sdk/openai", "name": key, "models": {}})
        if not isinstance(prov.get("models"), dict):
            prov["models"] = {}
        for mid, spec in selected.items():
            prov["models"].setdefault(mid, dict(spec))

        self.app.mark_dirty()
        self._update_table()

        # Auto-match against the catalog in ONE review dialog (no per-model prompts).
        if not self.app.model_catalog.loaded():
            if not self.app._ensure_catalog():
                QMessageBox.information(
                    self, "Fetch Complete",
                    f"Added {len(selected)} models to '{key}'. "
                    "Catalog not loaded, skipped auto-match.")
                return

        catalog = self.app.model_catalog
        settings = SettingsManager()
        mappings = settings.get_reference_mappings()
        entries = []       # (model_id, old_spec, new_spec|None, status)
        ambiguous_data = {}
        fallback_data = {}  # {model_id: ModelFormat}

        for mid in sorted(prov["models"]):
            matches = catalog.find_model(mid)
            if not matches:
                fmt = None
                # 1. Previously persisted manual/auto mapping wins.
                saved = mappings.get(f"{key}/{mid}")
                if saved:
                    saved_matches = catalog.find_model(saved)
                    if saved_matches:
                        fmt = _sort_matches(saved_matches, reference or key)[0]
                # 2. Reference provider / normalized-id / prefix fallback.
                if fmt is None:
                    fmt = _find_fallback(mid, reference, catalog)
                if fmt is not None:
                    merged = _merge_model_spec(
                        prov["models"][mid], build_spec_from_format(fmt), overwrite=False)
                    entries.append((mid, dict(prov["models"][mid]), merged,
                                    f"fallback:{fmt.provider}"))
                    fallback_data[mid] = fmt
                else:
                    entries.append((mid, dict(prov["models"][mid]), None, "unknown"))
                continue
            chosen = _resolve_match(matches, key, mid)
            if chosen is None:
                entries.append((mid, dict(prov["models"][mid]), None, "ambiguous"))
                ambiguous_data[mid] = (key, matches)
                continue
            merged = _merge_model_spec(
                prov["models"][mid], build_spec_from_format(chosen), overwrite=False)
            status = "matched" if merged != (prov["models"][mid] or {}) else "unchanged"
            entries.append((mid, dict(prov["models"][mid]), merged, status))

        if not any(e[2] is not None or e[3] == "ambiguous" for e in entries):
            QMessageBox.information(
                self, "Fetch & Match",
                f"Added {len(selected)} models to '{key}'. "
                "None matched the catalog.")
            return

        preview = MatchFormatPreviewDialog(
            self, entries, ambiguous_data, fallback_data=fallback_data, catalog=catalog)
        if preview.exec() != QDialog.Accepted:
            return

        applied = 0
        for mid, old_spec, new_spec, status in preview.selected_entries:
            if status == "ambiguous":
                new_spec = preview.resolved_specs.get(mid, new_spec)
            elif status == "mapped":
                new_spec = preview.mapped_specs.get(mid, new_spec)
                if mid in preview.mapped_ids:
                    settings.add_reference_mapping(key, mid, preview.mapped_ids[mid])
            elif status.startswith("fallback:"):
                fmt = fallback_data.get(mid)
                if fmt is not None:
                    settings.add_reference_mapping(key, mid, fmt.model_id)
            if new_spec is None:
                continue
            prov["models"][mid] = _merge_model_spec(
                prov["models"][mid], new_spec, overwrite=False)
            applied += 1

        self.app.mark_dirty()
        self._update_table()
        QMessageBox.information(
            self, "Fetch & Match Complete",
            f"Added {len(selected)} models to '{key}', normalized {applied} from catalog."
        )

    def _export_providers(self):
        """Export providers to JSON file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Providers", "providers.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        providers = self.app.cfg.data.get("provider", {})
        if not providers:
            QMessageBox.information(self, "Export", "No providers to export")
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(providers, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _set_all_enabled(self, enabled: bool):
        """Enable/disable all providers"""
        # Providers don't have an enabled flag, but we can add one for UI purposes
        # This is just a placeholder for potential future functionality
        QMessageBox.information(self, "Info", "Providers don't have an enabled/disabled state")

    def _edit_models(self, name: str):
        """Edit models for provider"""
        self.app.snapshot_state()
        providers = self.app.cfg.data.get("provider", {})
        if name not in providers:
            return

        dlg = ModelsManagerDialog(self.app, name, providers[name])
        if dlg.exec() == QDialog.Accepted:
            providers[name]["models"] = dlg.result()
            self.app.mark_dirty()
            self.refresh()

    def _edit_options(self, name: str):
        """Edit options for provider"""
        self.app.snapshot_state()
        providers = self.app.cfg.data.get("provider", {})
        if name not in providers:
            return

        current = providers[name].get("options", {})
        dlg = JsonImportDialog(
            self, f"Options - {name}",
            "Edit provider options (baseURL, headers, etc.)"
        )
        dlg.editor.setPlainText(json.dumps(current, indent=2, ensure_ascii=False))

        if dlg.exec() == QDialog.Accepted:
            try:
                options = json.loads(dlg.editor.toPlainText())
                if not isinstance(options, dict):
                    raise ValueError("Options must be a JSON object")
                providers[name]["options"] = options
                self.app.mark_dirty()
                self.refresh()
            except (json.JSONDecodeError, ValueError) as e:
                QMessageBox.warning(self, "Error", str(e))

    def collect(self, data: dict):
        """Collect data from UI"""
        providers = data.setdefault("provider", {})
        seen = set()

        for row in range(self.table.rowCount()):
            old_name = self.rows[row][0]
            new_name = self.table.item(row, 0).text().strip()

            if not new_name:
                continue

            if new_name in seen:
                raise ValueError(f"Duplicate provider key: {new_name!r}")
            seen.add(new_name)

            npm_edit = self.rows[row][1]
            name_edit = self.rows[row][2]

            old_cfg = dict(providers.get(old_name, {}))
            old_cfg["npm"] = npm_edit.value()
            if name_edit.value():
                old_cfg["name"] = name_edit.value()
            else:
                old_cfg.pop("name", None)

            providers[new_name] = old_cfg

