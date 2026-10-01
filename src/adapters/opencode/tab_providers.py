def match_models_against_catalog(key, models_dict, catalog, reference_provider=None):
    """Build a list of potential catalog matches for the given models.
    Returns (entries, ambiguous_data, fallback_data).
    """
    settings = SettingsManager()
    mappings = settings.get_reference_mappings()
    entries = []       # (model_id, old_spec, new_spec|None, status)
    ambiguous_data = {}
    fallback_data = {}  # {model_id: ModelFormat}

    for mid in sorted(models_dict):
        matches = catalog.find_model(mid)
        if not matches:
            fmt = None
            # 1. Previously persisted manual/auto mapping wins.
            saved = mappings.get(f"{key}/{mid}")
            if saved:
                saved_matches = catalog.find_model(saved)
                if saved_matches:
                    fmt = _sort_matches(saved_matches, reference_provider or key)[0]
            # 2. Reference provider / normalized-id / prefix fallback.
            if fmt is None:
                fmt = _find_fallback(mid, reference_provider, catalog)
            if fmt is not None:
                merged = _merge_model_spec(
                    models_dict[mid], build_spec_from_format(fmt, mid), overwrite=False)
                entries.append((mid, dict(models_dict[mid]), merged,
                                f"fallback:{fmt.provider}"))
                fallback_data[mid] = fmt
            else:
                entries.append((mid, dict(models_dict[mid]), None, "unknown"))
            continue
        chosen = _resolve_match(matches, key, mid)
        if chosen is None:
            entries.append((mid, dict(models_dict[mid]), None, "ambiguous"))
            ambiguous_data[mid] = (key, matches)
            continue
        merged = _merge_model_spec(
            models_dict[mid], build_spec_from_format(chosen, mid), overwrite=False)
        status = "matched" if merged != (models_dict[mid] or {}) else "unchanged"
        entries.append((mid, dict(models_dict[mid]), merged, status))
    return entries, ambiguous_data, fallback_data


# Providers tab
class ProvidersTab(QWidget):
    """Providers tab: search, inline edits, soft delete via the trash file."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.rows = []  # live rows only: (provider_key, npm_edit, name_edit)

        layout = QVBoxLayout(self)

        # Search and buttons
        top_layout = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search providers...")
        self.search_edit.textChanged.connect(self._filter_providers)
        top_layout.addWidget(self.search_edit)

        self.show_trash_chk = QCheckBox("Show deleted")
        self.show_trash_chk.setToolTip(f"Removed providers are kept in {PROVIDER_TRASH_FILE}")
        self.show_trash_chk.toggled.connect(lambda _: self._update_table())
        top_layout.addWidget(self.show_trash_chk)

        for text, slot in [
            ("+ Add", self._add_provider),
            ("+ Fetch from API", self._fetch_new_provider),
            ("⚡ Health Check", self._health_check_providers),
            ("Import", self._import_providers),
            ("Export", self._export_providers),
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
        # Editing a live row's key cell renames the provider immediately.
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        # Status
        self.status_label = QLabel()
        layout.addWidget(self.status_label)

    # --- data helpers ---
    def _providers(self) -> dict:
        return section(self.app.cfg.data, "provider") if self.app.cfg else {}

    def _cfg_path(self):
        """Path of the loaded config file; None (no file) means no trash."""
        return getattr(self.app.cfg, "path", None)

    def _trashed(self) -> dict:
        """Trash entries of this config file whose key is not a live provider.
        Derived, so undoing a remove hides its entry again."""
        path = self._cfg_path()
        if path is None:
            return {}
        live = self._providers()
        return {k: v for k, v in ProviderTrashStore().entries(path).items() if k not in live}

    @staticmethod
    def _matches(key, cfg, text: str) -> bool:
        if not text:
            return True
        if text in key.lower():
            return True
        if not isinstance(cfg, dict):
            return False
        return any(isinstance(cfg.get(f), str) and text in cfg[f].lower()
                   for f in ("npm", "name"))

    @staticmethod
    def _summary(cfg) -> str:
        cfg = cfg if isinstance(cfg, dict) else {}
        n_models = len(cfg["models"]) if isinstance(cfg.get("models"), dict) else 0
        base_url = cfg["options"].get("baseURL", "") if isinstance(cfg.get("options"), dict) else ""
        return f"{n_models} models  {base_url}"

    def _filter_providers(self, text: str = ""):
        """Filter providers by search text (the table reads the search box)."""
        self._update_table()

    def _update_table(self):
        """Rebuild the table: live rows (search-filtered) first, then the
        deleted ones when "Show deleted" is checked."""
        text = self.search_edit.text().lower()
        providers = self._providers()
        trashed = self._trashed()
        live = [(k, v) for k, v in sorted(providers.items()) if self._matches(k, v, text)]
        dead = ([(k, v) for k, v in sorted(trashed.items()) if self._matches(k, v, text)]
                if self.show_trash_chk.isChecked() else [])

        prev = self.table.blockSignals(True)   # a rebuild is never an edit
        try:
            self.rows = []
            self.table.setRowCount(0)
            self.table.setRowCount(len(live) + len(dead))
            for row, (key, cfg) in enumerate(live):
                self._fill_live_row(row, key, cfg)
            for row, (key, entry) in enumerate(dead, start=len(live)):
                self._fill_trash_row(row, key, entry)
        finally:
            self.table.blockSignals(prev)
        self._update_status(len(providers), len(trashed))

    def _update_status(self, n_live=None, n_trashed=None):
        n_live = len(self._providers()) if n_live is None else n_live
        n_trashed = len(self._trashed()) if n_trashed is None else n_trashed
        text = f"{n_live} providers"
        if n_trashed:
            text += f" · {n_trashed} deleted"
        self.status_label.setText(text)

    def _fill_live_row(self, row, key, cfg):
        valid = isinstance(cfg, dict)   # non-dict entries are fixed in Raw JSON
        cfg = cfg if valid else {}
        self.table.setItem(row, 0, QTableWidgetItem(key))

        npm_edit = MaskedLineEdit(cfg.get("npm", ""), field_name="npm")
        npm_edit.edit.editingFinished.connect(
            lambda r=row, w=npm_edit: self._commit_inline(r, "npm", w))
        npm_edit.setEnabled(valid)
        self.table.setCellWidget(row, 1, npm_edit)

        name_edit = MaskedLineEdit(cfg.get("name", ""), field_name="name")
        name_edit.edit.editingFinished.connect(
            lambda r=row, w=name_edit: self._commit_inline(r, "name", w))
        name_edit.setEnabled(valid)
        self.table.setCellWidget(row, 2, name_edit)

        cell = QWidget()
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(2, 0, 2, 0)
        summary = QLabel(self._summary(cfg))
        summary.setToolTip(self._tooltip_json(cfg))
        cell_layout.addWidget(summary, 1)
        # Buttons resolve the key at click time: the key cell renames in place.
        for text, slot in (("Models...", self._edit_models), ("Options...", self._edit_options)):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, r=row, s=slot: s(self._row_key(r)))
            btn.setEnabled(valid)
            cell_layout.addWidget(btn)
        self.table.setCellWidget(row, 3, cell)

        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        for text, slot in (("Edit", self._edit_provider), ("Remove", self._remove_provider)):
            btn = QPushButton(text)
            btn.setFixedWidth(60)
            btn.clicked.connect(lambda _, r=row, s=slot: s(self._row_key(r)))
            actions_layout.addWidget(btn)
        self.table.setCellWidget(row, 4, actions_widget)

        self.rows.append((key, npm_edit, name_edit))

    @staticmethod
    def _tooltip_json(cfg):
        """Provider JSON for the summary tooltip, with the API key masked."""
        if not isinstance(cfg, dict):
            return ""
        shown = dict(cfg)
        options = shown.get("options")
        if isinstance(options, dict) and options.get("apiKey"):
            options = dict(options)
            options["apiKey"] = _mask(str(options["apiKey"]))
            shown["options"] = options
        return json.dumps(shown, ensure_ascii=False, indent=2)[:4000]

    def _fill_trash_row(self, row, key, entry):
        """Display-only row for a deleted provider: Restore / Delete permanently."""
        cfg = entry if isinstance(entry, dict) else {}
        for col, text in enumerate((key, cfg.get("npm", ""), cfg.get("name", ""),
                                    self._summary(cfg))):
            item = QTableWidgetItem(str(text))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
            item.setForeground(Qt.gray)
            self.table.setItem(row, col, item)

        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        restore_btn = QPushButton("Restore")
        restore_btn.clicked.connect(lambda _, k=key: self._restore_provider(k))
        actions_layout.addWidget(restore_btn)
        purge_btn = QPushButton("Delete permanently")
        purge_btn.clicked.connect(lambda _, k=key: self._hard_delete_provider(k))
        actions_layout.addWidget(purge_btn)
        self.table.setCellWidget(row, 4, actions_widget)

    def _row_key(self, row):
        return self.rows[row][0] if 0 <= row < len(self.rows) else None

    def _row_of(self, key):
        return next((i for i, r in enumerate(self.rows) if r[0] == key), None)

    def _set_key_cell(self, item, text):
        prev = self.table.blockSignals(True)
        item.setText(text)
        self.table.blockSignals(prev)

    def _on_item_changed(self, item):
        """Write-through rename from a live row's key cell."""
        row = item.row()
        if item.column() != 0 or not 0 <= row < len(self.rows):
            return  # deleted rows are display-only and never collected
        old = self.rows[row][0]
        new = item.text().strip()
        if new == old:
            if item.text() != old:
                self._set_key_cell(item, old)
            return
        providers = self._providers()
        if old not in providers:
            self._set_key_cell(item, old)
            return
        if not new or new in providers:
            self._set_key_cell(item, old)
            QMessageBox.warning(self, "Rename Provider",
                                "Provider key cannot be empty" if not new
                                else f"Provider '{new}' already exists")
            return
        self.app.snapshot_state()
        providers[new] = providers.pop(old)
        self.rows[row] = (new,) + tuple(self.rows[row][1:])
        if item.text() != new:
            self._set_key_cell(item, new)
        self.app.mark_dirty()
        self._update_status()

    _FIELD_COL = {"npm": 1, "name": 2}

    def _commit_inline(self, row, field, widget):
        """Write-through for the npm/name cells so a table rebuild (search,
        dialogs, Show deleted, ...) never drops an inline edit."""
        if not 0 <= row < len(self.rows) or self.rows[row][self._FIELD_COL[field]] is not widget:
            return  # stale widget from a previous rebuild
        prov = self._providers().get(self.rows[row][0])
        if not isinstance(prov, dict):
            return
        value = widget.value()
        if not self._differs(prov, field, value):
            return
        self.app.snapshot_state()
        self._apply_field(prov, field, value)
        self.app.mark_dirty()

    @staticmethod
    def _differs(prov: dict, field: str, value: str) -> bool:
        cur = prov.get(field)
        return value != ("" if cur is None else str(cur))

    @staticmethod
    def _apply_field(prov: dict, field: str, value: str):
        """Set the field, or drop it when empty (never writes "npm": "")."""
        if value:
            prov[field] = value
        else:
            prov.pop(field, None)

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

    def _edit_provider(self, name: str):
        """Rename a provider via a dialog."""
        self.app.snapshot_state()
        providers = self._providers()
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

    def _remove_provider(self, name: str):
        """Soft delete: move the provider into the trash file, then drop it from
        the config. It leaves the config file on the next Save."""
        providers = self._providers()
        if name not in providers:
            QMessageBox.warning(self, "Error", f"Provider '{name}' not found")
            self.refresh()
            return
        if not _confirm(self, "Remove Provider",
                        f"Remove provider '{name}'?\n\n"
                        "It can be restored via \"Show deleted\"."):
            return

        entry = copy.deepcopy(providers[name])
        row = self._row_of(name)
        if isinstance(entry, dict) and row is not None:
            # Include inline edits that haven't been committed yet.
            for fld, widget in zip(("npm", "name"), self.rows[row][1:]):
                if self._differs(entry, fld, widget.value()):
                    self._apply_field(entry, fld, widget.value())
        path = self._cfg_path()
        try:
            if path is None:
                raise OSError("no config file is loaded")
            ProviderTrashStore().put(path, name, entry)
        except (OSError, TypeError, ValueError) as e:
            QMessageBox.critical(self, "Remove Provider",
                                 f"Could not save '{name}' to the trash file, "
                                 f"nothing was removed:\n{e}")
            return

        self.app.snapshot_state()
        providers.pop(name, None)
        self.app.mark_dirty()
        self.refresh()

    def _restore_provider(self, name: str):
        """Copy a deleted provider back into the config. The trash entry stays
        until a successful save prunes it, so restore-then-discard loses nothing."""
        path = self._cfg_path()
        entry = ProviderTrashStore().entries(path).get(name) if path is not None else None
        if entry is None:
            QMessageBox.warning(self, "Restore Provider",
                                f"'{name}' is no longer in the trash file")
            self.refresh()
            return
        providers = self.app.cfg.data.setdefault("provider", {})
        if not isinstance(providers, dict):
            QMessageBox.warning(self, "Restore Provider",
                                "The config's 'provider' value is not an object; fix it in Raw JSON")
            return
        if name in providers:
            QMessageBox.warning(self, "Restore Provider",
                                f"Provider '{name}' already exists; rename or remove it first")
            return
        self.app.snapshot_state()
        providers[name] = entry
        self.app.mark_dirty()
        self.refresh()

    def _hard_delete_provider(self, name: str):
        """Permanently drop a deleted provider from the trash file."""
        path = self._cfg_path()
        if path is None:
            return
        if not _confirm(self, "Delete Permanently",
                        f"Permanently delete provider '{name}' from the trash?\n\n"
                        "This cannot be undone."):
            return
        try:
            ProviderTrashStore().discard(path, name)
        except OSError as e:
            QMessageBox.critical(self, "Delete Permanently", str(e))
            return
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

    def _fetch_new_provider(self):
        """Add a NEW provider by fetching its model list from an API, then
        auto-match the fetched models against the catalog.

        Updating an existing provider's models lives in that provider's
        Models... dialog ("Fetch from API"); this toolbar entry is for
        bringing in a provider that isn't in the config yet (the provider
        key is editable in the dialog).
        """
        self.app.snapshot_state()

        # Fill the dialog's reference-provider combo (silently loads bundled catalog).
        try_load_bundled_catalog(self.app.model_catalog)
        providers = self.app.cfg.data.setdefault("provider", {})
        dlg = FetchProviderModelsDialog(self, catalog=self.app.model_catalog,
                                        providers=providers)
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

        existing_cfg = providers.get(key)
        existing_models = {}
        if isinstance(existing_cfg, dict) and isinstance(existing_cfg.get("models"), dict):
            existing_models = existing_cfg["models"]

        # api_base_url() is format-aware: a list/catalog fetch stored the raw
        # listing URL as options.baseURL, which is not a usable API endpoint.
        base_url = dlg.api_base_url()
        prov, summary = apply_fetched_provider(
            providers, key, selected,
            base_url=base_url,
            api_key=dlg.apikey_edit.text().strip(),
            save_api_key=dlg.save_apikey_check.isChecked(),
            npm=npm_for_fetch(dlg._current_adapter(), dlg.url_edit.text().strip()))

        removed = []
        if dlg.sync_check.isChecked():
            stale = stale_configured_models(existing_models, dlg.fetched_models)
            if stale:
                shown = ", ".join(stale[:8])
                if len(stale) > 8:
                    shown += f", ... (+{len(stale) - 8} more)"
                if _confirm(self, "Sync Models",
                            f"Remove {len(stale)} configured model(s) the API no "
                            f"longer lists?\n{shown}"):
                    for mid in stale:
                        prov["models"].pop(mid, None)
                    removed = stale

        self.app.mark_dirty()
        self._update_table()

        # Auto-match against the catalog in ONE review dialog (no per-model prompts).
        if not self.app.model_catalog.loaded():
            if not self.app._ensure_catalog():
                QMessageBox.information(
                    self, "Fetch Complete",
                    f"'{key}': added {len(summary['added'])} new model(s), "
                    f"kept {len(summary['kept'])} configured. "
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
                        prov["models"][mid], build_spec_from_format(fmt, mid), overwrite=False)
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
                prov["models"][mid], build_spec_from_format(chosen, mid), overwrite=False)
            status = "matched" if merged != (prov["models"][mid] or {}) else "unchanged"
            entries.append((mid, dict(prov["models"][mid]), merged, status))

        if not any(e[2] is not None or e[3] == "ambiguous" for e in entries):
            QMessageBox.information(
                self, "Fetch & Match",
                f"'{key}': added {len(summary['added'])} new model(s), "
                f"kept {len(summary['kept'])} configured. "
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
        sync_note = f", removed {len(removed)} stale" if removed else ""
        QMessageBox.information(
            self, "Fetch & Match Complete",
            f"'{key}': added {len(summary['added'])} new model(s), "
            f"kept {len(summary['kept'])} configured{sync_note}, "
            f"normalized {applied} from catalog."
        )

    def _export_providers(self):
        """Export providers to JSON file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Providers", "providers.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        providers = section(self.app.cfg.data, "provider")
        if not providers:
            QMessageBox.information(self, "Export", "No providers to export")
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(providers, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _edit_models(self, name: str):
        """Edit models for provider"""
        self.app.snapshot_state()
        providers = section(self.app.cfg.data, "provider")
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
        providers = section(self.app.cfg.data, "provider")
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

    def _health_check_providers(self):
        """Run connectivity and health check for configured providers"""
        providers = section(self.app.cfg.data, "provider") if self.app.cfg else {}
        # Project-scoped {file:...} API keys resolve against the config's dir.
        cfg_path = str(self.app.cfg.path) if self.app.cfg else ""
        dlg = ProviderHealthCheckDialog(self, providers=providers, config_path=cfg_path)
        dlg.exec()

    def collect(self, data: dict):
        """Apply npm/name edits still pending in a focused cell (e.g. Save via
        shortcut). Committed edits and renames already live in cfg.data
        (write-through), so untouched fields keep whatever `data` holds (incl.
        Raw JSON edits) and providers missing from `data` are never recreated."""
        providers = data.get("provider")
        if not isinstance(providers, dict):
            return
        cfg_providers = self._providers()
        for key, npm_edit, name_edit in self.rows:
            prov = providers.get(key)
            if not isinstance(prov, dict):
                continue    # removed (e.g. in Raw JSON) or malformed: never resurrect
            base = cfg_providers.get(key)
            base = base if isinstance(base, dict) else {}
            for fld, widget in (("npm", npm_edit), ("name", name_edit)):
                if self._differs(base, fld, widget.value()):
                    self._apply_field(prov, fld, widget.value())
