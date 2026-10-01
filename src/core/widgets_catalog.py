# Catalog dialogs: preview/match, browse, apply, fetch and format card
class CatalogPreviewDialog(QDialog):
    """Dialog to preview catalog application"""

    def __init__(self, parent, catalog_models: dict, existing_models: dict):
        super().__init__(parent)
        self.setWindowTitle("Apply Model Catalog")
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        # Info
        info_label = QLabel(
            f"Found {len(catalog_models)} models in catalog that match this provider.\n"
            "Select which models to update and whether to overwrite existing values."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Search
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search models...")
        self.search_edit.textChanged.connect(self._filter_models)
        search_layout.addWidget(self.search_edit)
        layout.addLayout(search_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Apply", "Model ID", "Name", "Current Values", "Catalog Values"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        # Overwrite checkbox
        self.overwrite_checkbox = QCheckBox("Overwrite existing values (otherwise only fill missing fields)")
        layout.addWidget(self.overwrite_checkbox)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Populate table
        self.catalog_models = catalog_models
        self.existing_models = existing_models
        self._update_table()

    def _update_table(self):
        """Update table with models"""
        self.table.setRowCount(len(self.catalog_models))
        for row, (model_id, catalog_spec) in enumerate(sorted(self.catalog_models.items())):
            # Apply checkbox
            apply_check = QCheckBox()
            apply_check.setChecked(model_id in self.existing_models)
            self.table.setCellWidget(row, 0, apply_check)

            # Model ID
            self.table.setItem(row, 1, QTableWidgetItem(model_id))

            # Name
            name = catalog_spec.get("name", "")
            self.table.setItem(row, 2, QTableWidgetItem(name))

            # Current values
            current_spec = self.existing_models.get(model_id, {})
            current_text = self._spec_to_text(current_spec)
            self.table.setItem(row, 3, QTableWidgetItem(current_text))

            # Catalog values
            catalog_text = self._spec_to_text(catalog_spec)
            self.table.setItem(row, 4, QTableWidgetItem(catalog_text))

    def _filter_models(self, text: str):
        """Filter models by search text"""
        if not text:
            self._update_table()
            return

        text = text.lower()
        filtered = {
            mid: spec for mid, spec in self.catalog_models.items()
            if text in mid.lower() or
               (isinstance(spec.get("name"), str) and text in spec["name"].lower())
        }

        self.table.setRowCount(len(filtered))
        for row, (model_id, catalog_spec) in enumerate(sorted(filtered.items())):
            apply_check = QCheckBox()
            apply_check.setChecked(model_id in self.existing_models)
            self.table.setCellWidget(row, 0, apply_check)

            self.table.setItem(row, 1, QTableWidgetItem(model_id))
            self.table.setItem(row, 2, QTableWidgetItem(catalog_spec.get("name", "")))

            current_spec = self.existing_models.get(model_id, {})
            current_text = self._spec_to_text(current_spec)
            self.table.setItem(row, 3, QTableWidgetItem(current_text))

            catalog_text = self._spec_to_text(catalog_spec)
            self.table.setItem(row, 4, QTableWidgetItem(catalog_text))

    def _spec_to_text(self, spec: dict) -> str:
        """Convert model spec to display text"""
        parts = []
        if "name" in spec:
            parts.append(f"name: {spec['name']}")
        if "attachment" in spec:
            parts.append(f"attachment: {spec['attachment']}")
        if "reasoning" in spec:
            parts.append(f"reasoning: {spec['reasoning']}")
        if "cost" in spec and isinstance(spec["cost"], dict):
            cost = spec["cost"]
            if "input" in cost or "output" in cost:
                parts.append(f"cost: {cost.get('input', '')}/{cost.get('output', '')}")
        if "limit" in spec and isinstance(spec["limit"], dict):
            limit = spec["limit"]
            if "context" in limit or "output" in limit:
                parts.append(f"limit: {limit.get('context', '')}/{limit.get('output', '')}")
        return ", ".join(parts)

    @property
    def selected_models(self) -> List[str]:
        """Get selected model IDs"""
        selected = []
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 0).isChecked():
                selected.append(self.table.item(row, 1).text())
        return selected

class CatalogModelPickerDialog(QDialog):
    """Searchable picker over catalog formats (used to map unknown models)."""

    def __init__(self, parent, catalog, initial_filter: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Map to Catalog Model")
        self.resize(520, 520)
        self._formats = list(catalog.all_formats()) if catalog is not None else []
        self.selected_format = None

        layout = QVBoxLayout(self)
        self.search = QLineEdit(initial_filter)
        self.search.setPlaceholderText("Filter by provider, model id or name...")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self._accept())
        layout.addWidget(self.list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._filter()

    def _filter(self):
        text = self.search.text().lower()
        self.list.clear()
        shown = 0
        for fmt in self._formats:
            label = f"{fmt.provider} · {fmt.model_id}"
            if text and text not in label.lower() and text not in (fmt.name or "").lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, fmt)
            self.list.addItem(item)
            shown += 1
            if shown >= 400:  # keep the list snappy on huge catalogs
                break

    def _accept(self):
        item = self.list.currentItem()
        if item is not None:
            self.selected_format = item.data(Qt.UserRole)
        if self.selected_format is not None:
            self.accept()


class MatchFormatPreviewDialog(QDialog):
    """Preview old vs new model config after matching against the catalog."""

    def __init__(self, parent, entries, ambiguous_data=None,
                 fallback_data=None, catalog=None):
        super().__init__(parent)
        self.setWindowTitle("Preview Matched Models")
        self.resize(900, 600)
        # entries: list of (model_id, old_spec, new_spec|None, status)
        self.entries = entries
        self.resolved_specs = {}
        self._ambiguous_data = ambiguous_data or {}
        self.fallback_data = fallback_data or {}   # {model_id: ModelFormat}
        self.mapped_specs = {}                     # {model_id: spec}
        self.mapped_ids = {}                       # {model_id: catalog model_id}
        self.catalog = catalog

        layout = QVBoxLayout(self)

        info = QLabel(
            "Review each model below. 'Old' is your current config, 'New' is the "
            "matched catalog format. Check the ones you want to apply."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.overwrite_checkbox = QCheckBox("Overwrite existing values (otherwise only fill missing fields)")
        layout.addWidget(self.overwrite_checkbox)

        # Bulk resolve bar: set every ambiguous row to one provider at once.
        self.bulk_bar = QWidget()
        bulk_layout = QHBoxLayout(self.bulk_bar)
        bulk_layout.setContentsMargins(0, 0, 0, 0)
        bulk_layout.addWidget(QLabel("Set all ambiguous to:"))
        self.bulk_combo = QComboBox()
        self.bulk_combo.setMinimumWidth(220)
        bulk_layout.addWidget(self.bulk_combo)
        bulk_btn = QPushButton("Apply to all")
        bulk_btn.clicked.connect(self._bulk_resolve)
        bulk_layout.addWidget(bulk_btn)
        self.apply_fallback_check = QCheckBox("Apply fallback")
        self.apply_fallback_check.setChecked(True)
        self.apply_fallback_check.toggled.connect(self._on_fallback_toggle)
        bulk_layout.addWidget(self.apply_fallback_check)
        bulk_layout.addStretch()
        layout.addWidget(self.bulk_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Apply", "Model ID", "Status", "Old Config", "New Config", "Catalog Provider"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self._show_diff)

        # Diff panel: side-by-side visual old -> new for the selected row.
        self.diff_title = QLabel("Select a row to preview the change")
        self.diff_title.setStyleSheet("font-weight: bold;")
        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setMinimumHeight(180)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.table)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.diff_title)
        rl.addWidget(self.diff_view)
        splitter.addWidget(right)
        splitter.setSizes([360, 220])
        layout.addWidget(splitter)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate()

    def _flat(self, d, prefix=""):
        """Flatten a nested dict into (path, value) leaves."""
        out = []
        if not isinstance(d, dict):
            return [(prefix, d)]
        for k, v in d.items():
            p = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out.extend(self._flat(v, p))
            else:
                out.append((p, v))
        return out

    def _show_diff(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.diff_title.setText("Select a row to preview the change")
            self.diff_view.clear()
            return
        row = rows[0].row()
        if not (0 <= row < len(self.entries)):
            return
        mid, old_spec, new_spec, status = self.entries[row]
        if status == "ambiguous":
            new_spec = self.resolved_specs.get(mid, new_spec)
        self.diff_title.setText(
            f"{mid} — {status}"
            + (" (ambiguous: pick a catalog provider)" if status == "ambiguous" else ""))
        self.diff_view.setHtml(self._diff_html(old_spec or {}, new_spec))

    def _diff_html(self, old, new) -> str:
        """Render an HTML table comparing old vs new field-by-field."""
        if new is None:
            return "<b>No catalog match for this model.</b>"
        old_flat = dict(self._flat(old))
        new_flat = dict(self._flat(new))
        keys = sorted(set(old_flat) | set(new_flat))

        def esc(v):
            return _esc_html(json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)

        rows_html = []
        for k in keys:
            o = old_flat.get(k)
            n = new_flat.get(k)
            if o is None and n is None:
                continue
            if o == n:
                rows_html.append(
                    f"<tr><td class='k'>{_esc_html(k)}</td>"
                    f"<td class='same'>{esc(n)}</td></tr>")
            elif o is None:
                rows_html.append(
                    f"<tr><td class='k'>{_esc_html(k)}</td>"
                    f"<td class='add' style='color:#1a7f37'>+ {esc(n)}</td></tr>")
            elif n is None:
                rows_html.append(
                    f"<tr><td class='k'>{_esc_html(k)}</td>"
                    f"<td class='del' style='color:#d1242f; text-decoration:line-through'>- {esc(o)}</td></tr>")
            else:
                rows_html.append(
                    f"<tr><td class='k'>{_esc_html(k)}</td>"
                    f"<td class='chg' style='color:#9a6700'>{esc(o)} → {esc(n)}</td></tr>")

        return (
            "<style>table{border-collapse:collapse;width:100%;font-family:monospace;font-size:12px}"
            ".k{color:#57606a;padding:2px 10px 2px 0;vertical-align:top;white-space:nowrap}</style>"
            "<table>" + "".join(rows_html) + "</table>"
        ) if rows_html else "<i>No changes</i>"

    def _populate(self):
        self.table.setRowCount(len(self.entries))
        for row, (mid, old_spec, new_spec, status) in enumerate(self.entries):
            apply_check = QCheckBox()
            # Ambiguous rows are pre-checked too: their combo already defaults
            # to the best provider (same-name first, then most complete).
            apply_check.setChecked(
                (new_spec is not None and status != "unchanged") or status == "ambiguous")
            self.table.setCellWidget(row, 0, apply_check)

            self.table.setItem(row, 1, QTableWidgetItem(mid))
            status_item = QTableWidgetItem(status)
            if status.startswith("fallback:"):
                status_item.setForeground(QColor("#0969da"))
            elif status == "mapped":
                status_item.setForeground(QColor("#8250df"))
            self.table.setItem(row, 2, status_item)

            old_text = json.dumps(old_spec, ensure_ascii=False) if old_spec else "(empty)"
            if new_spec is not None:
                new_text = json.dumps(new_spec, ensure_ascii=False)
            elif status == "ambiguous":
                new_text = "choose a provider"
            else:
                new_text = "no match"
            self.table.setItem(row, 3, QTableWidgetItem(old_text))
            self.table.setItem(row, 4, QTableWidgetItem(new_text))

            # Resolve column: combo box listing catalog providers matching this id.
            resolve_widget = QWidget()
            resolve_layout = QHBoxLayout(resolve_widget)
            resolve_layout.setContentsMargins(2, 0, 2, 0)
            combo = QComboBox()
            provider_key, matches = self._ambiguous_data.get(mid, (None, []))
            if status == "ambiguous" and matches:
                # Same-name provider first, then the most complete formats,
                # so the pre-selection is a sensible default.
                for m in _sort_matches(matches, provider_key):
                    combo.addItem(m.provider, m)
                combo.setCurrentIndex(0)
                combo.currentIndexChanged.connect(
                    lambda _, r=row, mm=mid: self._on_combo_change(r, mm))
                # reflect the default selection now
                self.resolved_specs[mid] = build_spec_from_format(combo.currentData(), mid)
                self._refresh_new_cell(row, mid)
            else:
                combo.setEnabled(False)
                combo.addItem("—")
                # Unknown rows can be mapped to a catalog model manually.
                if status == "unknown" and self.catalog is not None:
                    map_btn = QPushButton("Map…")
                    map_btn.clicked.connect(
                        lambda _, r=row, mm=mid: self._map_unknown(r, mm))
                    resolve_layout.addWidget(map_btn)
            resolve_layout.addWidget(combo, 1)
            self.table.setCellWidget(row, 5, resolve_widget)

        self._fill_bulk_combo()
        self.table.resizeColumnsToContents()

    def _fill_bulk_combo(self):
        """List providers across ambiguous rows, most frequent first."""
        counts = {}
        for mid, (_pk, matches) in self._ambiguous_data.items():
            entry = next((e for e in self.entries if e[0] == mid), None)
            if entry is None or entry[3] != "ambiguous":
                continue
            for m in matches:
                counts[m.provider] = counts.get(m.provider, 0) + 1
            self.bulk_combo.clear()
        for prov, _n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            self.bulk_combo.addItem(prov)
        n_ambiguous = sum(1 for e in self.entries if e[3] == "ambiguous")
        has_fallback = any(e[3].startswith("fallback:") for e in self.entries)
        self.bulk_bar.setVisible(
            (self.bulk_combo.count() > 0 and n_ambiguous > 1) or has_fallback)

    def _on_fallback_toggle(self, checked: bool):
        """Check/uncheck every fallback row according to the Apply fallback box."""
        for row, (mid, _old, _new, status) in enumerate(self.entries):
            if not status.startswith("fallback:"):
                continue
            check = self.table.cellWidget(row, 0)
            if check is not None:
                check.setChecked(checked)

    def _map_unknown(self, row, mid):
        """Manually map an unknown model to a catalog format."""
        if self.catalog is None:
            return
        old_spec = self.entries[row][1] or {}
        dlg = CatalogModelPickerDialog(self, self.catalog, initial_filter=mid)
        if dlg.exec() != QDialog.Accepted or dlg.selected_format is None:
            return
        fmt = dlg.selected_format
        spec = build_spec_from_format(fmt, mid)
        self.mapped_specs[mid] = spec
        self.mapped_ids[mid] = fmt.model_id
        # Update the entry in place so selected_entries carries the new spec.
        self.entries[row] = (mid, old_spec, spec, "mapped")
        status_item = QTableWidgetItem("mapped")
        status_item.setForeground(QColor("#8250df"))
        self.table.setItem(row, 2, status_item)
        self.table.setItem(row, 4, QTableWidgetItem(json.dumps(spec, ensure_ascii=False)))
        check = self.table.cellWidget(row, 0)
        if check is not None:
            check.setChecked(True)
        self._show_diff()

    def _bulk_resolve(self):
        """Point every ambiguous row's combo at the chosen provider where possible."""
        provider = self.bulk_combo.currentText()
        if not provider:
            return
        for row, (mid, _old, _new, status) in enumerate(self.entries):
            if status != "ambiguous":
                continue
            combo = self.table.cellWidget(row, 5).findChild(QComboBox)
            if combo is None:
                continue
            idx = combo.findText(provider)
            if idx >= 0 and combo.currentIndex() != idx:
                combo.setCurrentIndex(idx)  # triggers _on_combo_change

    def _on_combo_change(self, row, mid):
        combo = self.table.cellWidget(row, 5).findChild(QComboBox)
        fmt = combo.currentData()
        if fmt is not None:
            self.resolved_specs[mid] = build_spec_from_format(fmt, mid)
            self._refresh_new_cell(row, mid)
            check = self.table.cellWidget(row, 0)
            if check is not None:
                check.setChecked(True)
            self._show_diff()

    def _refresh_new_cell(self, row, mid):
        spec = self.resolved_specs.get(mid)
        self.table.setItem(row, 4, QTableWidgetItem(
            json.dumps(spec, ensure_ascii=False) if spec else "choose a provider"))
        self.table.setItem(row, 2, QTableWidgetItem("matched" if spec else "ambiguous"))
        self.table.resizeColumnsToContents()

    @property
    def selected_entries(self):
        out = []
        for row in range(self.table.rowCount()):
            check = self.table.cellWidget(row, 0)
            if check is not None and check.isChecked():
                out.append(self.entries[row])
        return out

# Default base URL per fetch adapter. Gemini's API lives under /v1beta.
_FETCH_BASE_URL_DEFAULTS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "models_dev": "https://models.dev/api.json",
    "generic": "",
}


_APIKEY_PLACEHOLDER_RE = re.compile(r"\{(?:env|file):[^{}]*\}")


def _has_placeholder(value: str) -> bool:
    """True if `value` uses opencode's {env:VAR} / {file:path} references."""
    return isinstance(value, str) and bool(_APIKEY_PLACEHOLDER_RE.search(value))

class _ModelFetchWorker(QThread):
    """Runs fetch_provider_models off the UI thread."""
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, spec):
        super().__init__()
        self.spec = spec

    def run(self):
        try:
            models = fetch_provider_models(self.spec)
            self.finished_ok.emit(models)
        except Exception as e:  # FetchError and anything unexpected
            self.failed.emit(str(e))


class _CatalogSyncWorker(QThread):
    """Runs ModelCatalog.fetch_online off the UI thread.

    Downloading, JSONC-stripping and re-parsing a multi-megabyte catalog all
    take long enough to freeze the window, so the download never runs on the
    GUI thread. Reuse this worker from anywhere else that updates the catalog.
    """
    finished_ok = Signal(str, int)   # message, model count
    failed = Signal(str)             # error message

    def __init__(self, catalog, url=None):
        super().__init__()
        self.catalog = catalog
        self.url = url

    def run(self):
        try:
            ok, msg, count = self.catalog.fetch_online(self.url)
        except Exception as e:
            self.failed.emit(str(e))
            return
        if ok:
            self.finished_ok.emit(msg, count)
        else:
            self.failed.emit(msg)


class FetchProviderModelsDialog(QDialog):
    """Fetch a provider's model list from its API and preview the results."""
    def __init__(self, parent, provider_key: str = "new-provider", catalog=None,
                 providers=None, lock_key: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Fetch Provider Models from API")
        self.resize(720, 560)
        self.fetched_models = {}   # {model_id: spec}
        self.provider_key = provider_key
        self.providers = providers  # full provider map, for existing-status display
        self._worker = None
        self._lock_key = lock_key
        self._fetched_signature = None  # (url, api key, adapter) the table matches
        self._auto_base_url = ""   # last base URL we auto-filled from a default
        self._closed = False

        # Silently load the bundled catalog so the Reference combo can be filled.
        self.catalog = catalog
        try_load_bundled_catalog(self.catalog)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.key_edit = QLineEdit(provider_key)
        # The fetch is always for this provider; letting the key be edited only
        # mislabels the Status column, since the result is applied to
        # provider_key regardless (F11).
        self.key_edit.setReadOnly(lock_key)
        self.key_edit.textChanged.connect(self._apply_status)
        form.addRow("Provider key:", self.key_edit)

        self.format_combo = QComboBox()
        for adapter, preset in FETCH_ADAPTERS.items():
            self.format_combo.addItem(preset["label"], adapter)
        self.format_combo.currentIndexChanged.connect(self._on_format_change)
        form.addRow("API format:", self.format_combo)

        # Optional provider used as a fallback source for models not in the catalog.
        self.reference_combo = QComboBox()
        self.reference_combo.addItem("Auto (exact match only)", "")
        if self.catalog is not None and self.catalog.loaded():
            for pid in sorted(self.catalog.by_provider.keys()):
                self.reference_combo.addItem(pid, pid)
        self.reference_combo.setToolTip(
            "Models not found in the catalog will borrow their format from this "
            "provider (fill-missing only). Manual 'Map…' overrides still win.")
        form.addRow("Reference provider:", self.reference_combo)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://api.openai.com/v1")
        self.url_edit.textChanged.connect(self._invalidate_fetch)
        form.addRow("Base URL:", self.url_edit)

        self.apikey_edit = QLineEdit()
        self.apikey_edit.setEchoMode(QLineEdit.Password)
        self.apikey_edit.setPlaceholderText("(sent as a header to fetch the model list)")
        self.apikey_edit.textChanged.connect(self._invalidate_fetch)
        self.apikey_edit.setReadOnly(lock_key)
        if lock_key:
            self.apikey_edit.setToolTip(
                "This provider already has an API key configured; it is reused as-is.")
        form.addRow("API key:", self.apikey_edit)

        # Saving a reference like "{env:OPENAI_API_KEY}" would freeze the
        # variable name into the config; the checkbox default is set in
        # _prefill_from_provider once the stored key is known.
        self.save_apikey_check = QCheckBox("Save API key to config (options.apiKey)")
        self.save_apikey_check.setChecked(True)
        self.save_apikey_check.setToolTip(
            "Writes the key into opencode.json (provider options.apiKey), opencode's "
            "documented mechanism. Uncheck to keep it out of the config file.")
        form.addRow("", self.save_apikey_check)

        layout.addLayout(form)

        # Generic-only advanced fields
        self.generic_box = QGroupBox("Generic JSON options")
        gform = QFormLayout(self.generic_box)
        self.items_path_edit = QLineEdit()
        self.items_path_edit.setPlaceholderText("data  (dotted path to the array)")
        self.id_field_edit = QLineEdit()
        self.id_field_edit.setPlaceholderText("id")
        self.name_field_edit = QLineEdit()
        self.name_field_edit.setPlaceholderText("name")
        gform.addRow("Items path:", self.items_path_edit)
        gform.addRow("ID field:", self.id_field_edit)
        gform.addRow("Name field:", self.name_field_edit)
        layout.addWidget(self.generic_box)

        self.allow_local_check = QCheckBox("Allow local URL (Ollama / LM Studio / localhost)")
        layout.addWidget(self.allow_local_check)

        self.sync_check = QCheckBox(
            "Sync: also remove configured models that the API no longer lists")
        self.sync_check.setToolTip(
            "Only affects a provider key that already exists. Off = add-only, "
            "every configured model is kept.")
        self.sync_check.setVisible(providers is not None)
        layout.addWidget(self.sync_check)

        # Fetch controls
        fetch_row = QHBoxLayout()
        self.fetch_btn = QPushButton("Fetch models")
        self.fetch_btn.clicked.connect(self._fetch)
        fetch_row.addWidget(self.fetch_btn)
        self.status_label = QLabel("")
        fetch_row.addWidget(self.status_label, 1)
        layout.addLayout(fetch_row)

        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Add", "Model ID", "Name", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        select_row = QHBoxLayout()
        all_btn = QPushButton("Select all")
        all_btn.clicked.connect(lambda: self._set_all(True))
        none_btn = QPushButton("Select none")
        none_btn.clicked.connect(lambda: self._set_all(False))
        select_row.addWidget(all_btn)
        select_row.addWidget(none_btn)
        select_row.addStretch()
        layout.addLayout(select_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Add Selected")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._on_format_change()
        self._prefill_from_provider()
        # Re-apply the adapter-dependent state now that the stored URL/key are
        # in place (a locked key needs a non-empty value to stay usable).
        self._on_format_change()

    # Providers whose npm package determines the API shape even before the
    # stored options are read: guessing the format first stops an Anthropic
    # key from being sent to an OpenAI endpoint.
    _NPM_ADAPTER = {
        "@ai-sdk/anthropic": "anthropic",
        "@ai-sdk/google": "gemini",
        "@ai-sdk/openai": "openai",
    }
    _PROVIDER_ID_ADAPTER = {
        "anthropic": "anthropic",
        "google": "gemini",
        "gemini": "gemini",
        "openai": "openai",
        "google-generative-ai": "gemini",
    }

    def _infer_adapter_from_provider(self) -> str:
        """Best-guess API format from the provider's npm package or id."""
        if not isinstance(self.providers, dict):
            return ""
        prov = self.providers.get(self.provider_key)
        if not isinstance(prov, dict):
            return ""
        npm = prov.get("npm")
        if isinstance(npm, str) and npm in self._NPM_ADAPTER:
            return self._NPM_ADAPTER[npm]
        pid = str(self.provider_key or "").lower()
        return self._PROVIDER_ID_ADAPTER.get(pid, "")

    def _select_adapter(self, adapter: str):
        idx = self.format_combo.findData(adapter)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)

    def _prefill_from_provider(self):
        """Pre-fill URL/key from the target provider's saved options, so
        re-fetching an existing provider starts from its real endpoint."""
        # Infer the format before reading the stored options: prefilling first
        # would send an Anthropic key to the default OpenAI URL.
        inferred = self._infer_adapter_from_provider()
        if inferred:
            self._select_adapter(inferred)

        if not isinstance(self.providers, dict):
            return
        prov = self.providers.get(self.provider_key)
        opts = prov.get("options") if isinstance(prov, dict) else None
        if not isinstance(opts, dict):
            return
        if opts.get("baseURL"):
            self.url_edit.setText(str(opts["baseURL"]))
        key = opts.get("apiKey")
        if isinstance(key, str) and key:
            # Keep "{env:…}"/"{file:…}" verbatim so Save writes it back
            # unchanged; it is only resolved when building the request.
            self.apikey_edit.setText(key)
            self.save_apikey_check.setChecked(not _has_placeholder(key))

    def _current_adapter(self) -> str:
        return self.format_combo.currentData()

    @property
    def reference_provider(self):
        """Selected fallback provider name, or None for Auto."""
        data = self.reference_combo.currentData()
        return data or None

    def _on_format_change(self):
        adapter = self._current_adapter()
        self.generic_box.setVisible(adapter == "generic")
        # Replace the URL only while it is still the default we last applied, so
        # switching format never clobbers a URL the user typed.
        if not self.url_edit.text().strip() or self.url_edit.text() == self._auto_base_url:
            self.url_edit.setText(_FETCH_BASE_URL_DEFAULTS.get(adapter, ""))
        self._auto_base_url = self.url_edit.text()
        # A locked key stays usable (it is the provider's existing key); only
        # *editing* it is blocked.
        self.apikey_edit.setEnabled(
            adapter != "models_dev" and (not self._lock_key or bool(self.apikey_edit.text())))
        self._invalidate_fetch()

    def _request_signature(self):
        """What the current table contents were fetched with."""
        return (self.url_edit.text().strip(),
                self.apikey_edit.text(),
                self._current_adapter())

    def _invalidate_fetch(self, *_):
        """Changing the endpoint, key or format makes the table stale."""
        if self._fetched_signature is None:
            return
        if self._request_signature() == self._fetched_signature:
            return
        self._fetched_signature = None
        self.fetched_models = {}
        self.table.setRowCount(0)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.status_label.setText("Settings changed — fetch again")

    def api_base_url(self) -> str:
        """The URL to store as the fetched provider's ``options.baseURL``.

        API-style formats keep their base URL, normalised with the version
        segment the AI SDK expects; list/catalog formats (models.dev, generic
        JSON) store nothing. The policy lives in api_base_url_for.
        """
        return api_base_url_for(self._current_adapter(),
                                self.url_edit.text().strip())

    def _build_spec(self) -> ProviderFetchSpec:
        return ProviderFetchSpec(
            base_url=self.url_edit.text().strip(),
            adapter=self._current_adapter(),
            # Only the outgoing request resolves {env:}/{file:} references;
            # the field itself keeps the reference text for Save.
            api_key=resolve_config_placeholders(self.apikey_edit.text()),
            items_path=self.items_path_edit.text().strip(),
            id_field=self.id_field_edit.text().strip(),
            name_field=self.name_field_edit.text().strip(),
            allow_local=self.allow_local_check.isChecked(),
        )

    def _fetch(self):
        if not self.url_edit.text().strip():
            QMessageBox.warning(self, "Fetch", "Please enter a base URL.")
            return
        self.fetch_btn.setEnabled(False)
        self.status_label.setText("Fetching…")
        self._worker = _ModelFetchWorker(self._build_spec())
        self._worker.finished_ok.connect(self._on_fetched)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_fetched(self, models: dict):
        # The dialog may have been closed (or the settings changed) while the
        # request was in flight; that result is no longer wanted.
        if self._closed:
            return
        self.fetched_models = models
        self._fetched_signature = self._request_signature()
        self.fetch_btn.setEnabled(True)
        self.status_label.setText(f"Fetched {len(models)} models")
        self._populate(models)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(models))

    def _on_failed(self, msg: str):
        if self._closed:
            return
        self.fetch_btn.setEnabled(True)
        self.status_label.setText("Fetch failed")
        QMessageBox.warning(self, "Fetch Error", msg)

    def closeEvent(self, event):
        self._closed = True
        super().closeEvent(event)

    def _populate(self, models: dict):
        self.table.setRowCount(len(models))
        for row, (mid, spec) in enumerate(sorted(models.items())):
            check = QCheckBox()
            check.setChecked(True)
            self.table.setCellWidget(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(mid))
            self.table.setItem(row, 2, QTableWidgetItem(spec.get("name", "")))
        self._apply_status()

    def _existing_model_ids(self) -> set:
        if not isinstance(self.providers, dict):
            return set()
        prov = self.providers.get(self.key_edit.text().strip())
        models = prov.get("models") if isinstance(prov, dict) else None
        return set(models.keys()) if isinstance(models, dict) else set()

    def _apply_status(self, *_):
        existing = self._existing_model_ids()
        for row in range(self.table.rowCount()):
            mid_item = self.table.item(row, 1)
            if mid_item is None:
                continue
            status = "existing" if mid_item.text() in existing else "new"
            self.table.setItem(row, 3, QTableWidgetItem(status))

    def _set_all(self, checked: bool):
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            if w is not None:
                w.setChecked(checked)

    @property
    def selected_models(self) -> dict:
        """Return {model_id: spec} for checked rows."""
        out = {}
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            if w is not None and w.isChecked():
                mid = self.table.item(row, 1).text()
                out[mid] = self.fetched_models.get(mid, {})
        return out



class ModelFormatCard(QFrame):
    """Card showing normalized details of a single model format."""

    def __init__(self, fmt: Optional[ModelFormat] = None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumWidth(280)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)

        self.title_label = QLabel("Select a model")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        self.title_label.setFont(title_font)
        self.title_label.setWordWrap(True)
        self._layout.addWidget(self.title_label)

        self.sub_label = QLabel("")
        self.sub_label.setStyleSheet("color: gray;")
        self.sub_label.setWordWrap(True)
        self._layout.addWidget(self.sub_label)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self._layout.addWidget(self.info_label)

        self.set_format(fmt)

    def set_format(self, fmt: Optional[ModelFormat]):
        if fmt is None:
            self.title_label.setText("No model selected")
            self.sub_label.setText("")
            self.info_label.setText("Click a row in the table to see its normalized format.")
            return

        self.title_label.setText(f"{fmt.provider} · {fmt.model_id}")
        self.sub_label.setText(fmt.name)
        lines = [
            f"Context: {fmt.context_k()}",
            f"Output: {fmt.output_k()}",
            f"Modalities: {fmt.modalities.label()}",
            f"Cost in/out: {fmt.cost_in_label()} / {fmt.cost_out_label()}",
            f"Cache read/write: {_fmt_cost(fmt.cost_cache_read)} / {_fmt_cost(fmt.cost_cache_write)}",
        ]
        caps = []
        if fmt.attachment:
            caps.append("attachment")
        if fmt.reasoning:
            caps.append("reasoning")
        if fmt.tools:
            caps.append("tool_call")
        if fmt.temperature:
            caps.append("temperature")
        if caps:
            lines.append("Capabilities: " + ", ".join(caps))
        if fmt.modalities.inferred:
            lines.append("(modalities inferred)")
        self.info_label.setText("\n".join(lines))


class TierSettingsDialog(QDialog):
    """Dialog to edit configurable context/output tiers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Catalog Tier Settings")
        self.resize(400, 320)
        self.settings = SettingsManager()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Enter tier thresholds in thousands of tokens (e.g. 4, 8, 32, 128, 200).\n"
            "Separate by commas. Used to bucket models by context / output size."
        ))

        form = QFormLayout()
        self.context_edit = QLineEdit()
        self.output_edit = QLineEdit()
        form.addRow("Context tiers (k):", self.context_edit)
        form.addRow("Output tiers (k):", self.output_edit)
        layout.addLayout(form)

        self.context_edit.setText(",".join(str(x // 1000 if x >= 1000 else x)
                                            for x in self.settings.get_context_tiers()))
        self.output_edit.setText(",".join(str(x // 1000 if x >= 1000 else x)
                                          for x in self.settings.get_output_tiers()))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _parse_k(self, text: str, fallback) -> List[int]:
        vals = []
        for tok in text.replace(",", " ").split():
            try:
                vals.append(int(float(tok) * 1000))
            except ValueError:
                continue
        return vals or list(fallback)

    def _accept(self):
        self.settings.set_context_tiers(
            self._parse_k(self.context_edit.text(), SettingsManager.DEFAULT_CONTEXT_TIERS))
        self.settings.set_output_tiers(
            self._parse_k(self.output_edit.text(), SettingsManager.DEFAULT_OUTPUT_TIERS))
        self.accept()


class ModelCatalogDialog(QDialog):
    """Browse the whole model catalog with filters and format detail."""

    COLUMNS = ["Provider", "Model ID", "Name", "Context", "Output", "Modalities", "Cost in/out"]

    def __init__(self, parent, catalog):
        super().__init__(parent)
        self.setWindowTitle("Browse Model Catalog")
        self.resize(960, 600)
        self.catalog = catalog
        self.settings = SettingsManager()

        layout = QVBoxLayout(self)

        # Filter bar
        filters = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search model / name...")
        self.search_edit.textChanged.connect(self._refresh)
        filters.addWidget(self.search_edit)

        self.provider_combo = QComboBox()
        self.provider_combo.addItem("All providers")
        for pid in sorted(catalog.by_provider.keys()):
            self.provider_combo.addItem(pid)
        self.provider_combo.currentTextChanged.connect(self._refresh)
        filters.addWidget(self.provider_combo)

        self.context_combo = QComboBox()
        self._fill_tier_combo(self.context_combo, "context")
        self.context_combo.currentIndexChanged.connect(self._refresh)
        filters.addWidget(QLabel("Context ≥"))
        filters.addWidget(self.context_combo)

        self.output_combo = QComboBox()
        self._fill_tier_combo(self.output_combo, "output")
        self.output_combo.currentIndexChanged.connect(self._refresh)
        filters.addWidget(QLabel("Output ≥"))
        filters.addWidget(self.output_combo)
        filters.addStretch()
        layout.addLayout(filters)

        mod_filters = QHBoxLayout()
        self.image_check = QCheckBox("Image input")
        self.pdf_check = QCheckBox("PDF input")
        self.tools_check = QCheckBox("Tools")
        self.reasoning_check = QCheckBox("Reasoning")
        for cb in (self.image_check, self.pdf_check, self.tools_check, self.reasoning_check):
            cb.stateChanged.connect(self._refresh)
            mod_filters.addWidget(cb)
        mod_filters.addStretch()
        layout.addLayout(mod_filters)

        # Splitter: table + card
        splitter = QSplitter()
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_select)
        splitter.addWidget(self.table)

        self.card = ModelFormatCard()
        splitter.addWidget(self.card)
        splitter.setSizes([680, 280])
        layout.addWidget(splitter)

        # Status + buttons
        bottom = QHBoxLayout()
        self.status_label = QLabel("")
        bottom.addWidget(self.status_label)
        bottom.addStretch()

        tiers_btn = QPushButton("Tiers…")
        tiers_btn.clicked.connect(self._edit_tiers)
        bottom.addWidget(tiers_btn)

        export_btn = QPushButton("Export…")
        export_btn.clicked.connect(self._export)
        bottom.addWidget(export_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        self._refresh()

    def _fill_tier_combo(self, combo: QComboBox, attr: str):
        combo.addItem("any")
        tiers = (self.settings.get_context_tiers() if attr == "context"
                 else self.settings.get_output_tiers())
        for t in tiers:
            combo.addItem(f"{_fmt_tokens(t)}")

    def _refresh(self):
        search = self.search_edit.text().lower()
        provider = self.provider_combo.currentText()
        ctx_min = self._tier_value(self.context_combo)
        out_min = self._tier_value(self.output_combo)

        rows = []
        for fmt in self.catalog.all_formats():
            if provider != "All providers" and fmt.provider != provider:
                continue
            if search and search not in fmt.model_id.lower() and search not in fmt.name.lower():
                continue
            if ctx_min and (fmt.context is None or fmt.context < ctx_min):
                continue
            if out_min and (fmt.output is None or fmt.output < out_min):
                continue
            if self.image_check.isChecked() and not fmt.modalities.has_image_input:
                continue
            if self.pdf_check.isChecked() and not fmt.modalities.has_pdf_input:
                continue
            if self.tools_check.isChecked() and not fmt.tools:
                continue
            if self.reasoning_check.isChecked() and not fmt.reasoning:
                continue
            rows.append(fmt)

        self.table.setRowCount(len(rows))
        self._row_formats = []
        for r, fmt in enumerate(rows):
            self._row_formats.append(fmt)
            vals = [
                fmt.provider, fmt.model_id, fmt.name, fmt.context_k(), fmt.output_k(),
                fmt.modalities.label(), f"{fmt.cost_in_label()}/{fmt.cost_out_label()}",
            ]
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.status_label.setText(f"{len(rows)} models")

    def _tier_value(self, combo: QComboBox):
        txt = combo.currentText()
        if not txt or txt == "any":
            return 0
        if txt.endswith("M"):
            return int(float(txt[:-1]) * 1000000)
        if txt.endswith("k"):
            return int(float(txt[:-1]) * 1000)
        try:
            return int(txt)
        except ValueError:
            return 0

    def _on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows or not getattr(self, "_row_formats", None):
            self.card.set_format(None)
            return
        idx = rows[0].row()
        if 0 <= idx < len(self._row_formats):
            self.card.set_format(self._row_formats[idx])

    def _edit_tiers(self):
        dlg = TierSettingsDialog(self)
        dlg.exec()
        self.context_combo.clear()
        self.output_combo.clear()
        self._fill_tier_combo(self.context_combo, "context")
        self._fill_tier_combo(self.output_combo, "output")
        self._refresh()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Models", "models.csv",
            "CSV files (*.csv);;JSON files (*.json);;All files (*)"
        )
        if not path:
            return
        rows = [self._row_formats[r] for r in range(self.table.rowCount())
                if 0 <= r < len(getattr(self, "_row_formats", []))]
        try:
            if path.endswith(".json"):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump([build_spec_from_format(f) | {"provider": f.provider,
                                                            "model_id": f.model_id}
                               for f in rows], f, indent=2, ensure_ascii=False)
            else:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["provider", "model_id", "name", "context",
                                     "output", "cost_in", "cost_out"])
                    for fm in rows:
                        writer.writerow([fm.provider, fm.model_id, fm.name,
                                         fm.context or "", fm.output or "",
                                         fm.cost_in or "", fm.cost_out or ""])
            QMessageBox.information(self, "Export Complete", f"Exported {len(rows)} models")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))


class ApplyCatalogDialog(QDialog):
    """Match configured models against the catalog and apply normalized format."""

    def __init__(self, parent, catalog, config_providers):
        super().__init__(parent)
        self.setWindowTitle("Match & Format Models from Catalog")
        self.resize(980, 620)
        self.catalog = catalog
        self.config_providers = config_providers

        layout = QVBoxLayout(self)
        info = QLabel(
            "Matches the models already configured in your config against the model catalog, "
            "then fills in normalized format (context, output, modalities, cost).\n"
            "Models with an id present in the catalog but missing from config can also be added."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Controls
        ctrl = QHBoxLayout()
        self.overwrite_check = QCheckBox("Overwrite existing values")
        self.add_new_check = QCheckBox("Add new models from catalog")
        self.add_new_check.setChecked(True)
        ctrl.addWidget(self.overwrite_check)
        ctrl.addWidget(self.add_new_check)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Model ID", "Provider (config)", "Catalog source", "Status",
            "Context", "Modalities"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemDoubleClicked.connect(self._resolve_ambiguous)
        layout.addWidget(self.table)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Apply to Config")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.overwrite_check.stateChanged.connect(lambda _: self._scan())
        self.add_new_check.stateChanged.connect(lambda _: self._scan())
        self._picks = {}
        self._scan()

    def _scan(self):
        self.rows = []
        self.fmt_cache = self.catalog.formats()
        overwrite = self.overwrite_check.isChecked()

        for prov_name, prov_cfg in (self.config_providers or {}).items():
            if not isinstance(prov_cfg, dict):
                continue
            models = prov_cfg.get("models")
            if not isinstance(models, dict):
                continue
            for mid in models:
                matches = self.catalog.find_model(mid)
                if not matches:
                    self.rows.append([mid, prov_name, "", "unknown", "", ""])
                    continue
                chosen = _resolve_match(matches, prov_name, mid,
                                        self._pick_provider)
                if chosen is None:
                    self.rows.append([mid, prov_name,
                                      ", ".join(m.provider for m in matches),
                                      "ambiguous", "", ""])
                    continue
                spec = build_spec_from_format(chosen, mid)
                merged = _merge_model_spec(models[mid], spec, overwrite)
                status = "matched" if merged != (models[mid] or {}) else "unchanged"
                self.rows.append([mid, prov_name, chosen.provider, status,
                                  chosen.context_k(), chosen.modalities.label()])

        if self.add_new_check.isChecked():
            for prov_name, prov_cfg in (self.config_providers or {}).items():
                if not isinstance(prov_cfg, dict):
                    continue
                existing = set(prov_cfg.get("models", {})) if isinstance(prov_cfg.get("models"), dict) else set()
                for fmt in self.fmt_cache.get(prov_name, {}).values():
                    if fmt.model_id not in existing:
                        self.rows.append([fmt.model_id, prov_name, prov_name, "added",
                                          fmt.context_k(), fmt.modalities.label()])

        self._populate()

    def _populate(self):
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            for c, val in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(val))
        counts = {"matched": 0, "filled": 0, "unchanged": 0, "unknown": 0,
                  "ambiguous": 0, "added": 0}
        for row in self.rows:
            counts[row[3]] = counts.get(row[3], 0) + 1
        parts = [f"{k}: {v}" for k, v in counts.items() if v]
        self.status_label.setText("  ".join(parts))

    def _pick_provider(self, prov_name, mid, matches):
        """Return the user's chosen provider for an ambiguous match, else None."""
        key = (prov_name, mid)
        picked = self._picks.get(key)
        if picked is not None:
            return next((m for m in matches if m.provider == picked), matches[0])
        return None

    def _resolve_ambiguous(self, item):
        row = item.row()
        if self.rows[row][3] != "ambiguous":
            return
        mid, prov = self.rows[row][0], self.rows[row][1]
        matches = self.catalog.find_model(mid)
        providers = [m.provider for m in matches]
        choice, ok = QInputDialog.getItem(
            self, "Choose Catalog Source",
            f"Model '{mid}' matches multiple providers. Choose one:",
            providers, 0, False
        )
        if ok and choice:
            self._picks[(prov, mid)] = choice
            fmt = next((m for m in matches if m.provider == choice), matches[0])
            self.rows[row][2] = choice
            self.rows[row][3] = "matched"
            self.rows[row][4] = fmt.context_k()
            self.rows[row][5] = fmt.modalities.label()
            self._populate()

    def apply(self) -> ApplyReport:
        """Apply the current choices to the live config providers."""
        report = apply_catalog_to_config(
            self.catalog,
            self.config_providers,
            overwrite=self.overwrite_check.isChecked(),
            add_new=self.add_new_check.isChecked(),
            resolve_fn=self._pick_provider,
        )
        return report


class EditCustomModelDialog(QDialog):
    """Dialog to add or edit a custom model spec in the catalog."""

    def __init__(self, parent, model_id: str = "", spec: Optional[dict] = None, provider: str = "custom"):
        super().__init__(parent)
        self.setWindowTitle("Edit Custom Model" if model_id else "Add Custom Model")
        self.resize(560, 480)
        self.result_model_id = ""
        self.result_provider = ""
        self.result_spec = {}
        # Fields the dialog does not expose (cost, aliases, extra modalities,
        # ...) are carried over untouched when the spec is rebuilt.
        self._original_spec = dict(spec or {})

        spec = dict(self._original_spec)
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Model ID
        self.id_edit = QLineEdit(model_id)
        self.id_edit.setPlaceholderText("e.g. glm-5.3-flash, custom-gpt-5")
        form.addRow("Model ID *:", self.id_edit)

        # Name
        init_name = spec.get("name") or (humanize_model_id(model_id) if model_id else "")
        self.name_edit = QLineEdit(init_name)
        self.name_edit.setPlaceholderText("e.g. GLM 5.3 Flash")
        form.addRow("Display Name:", self.name_edit)

        self.id_edit.textChanged.connect(self._on_id_changed)

        # Provider
        init_prov = spec.get("provider") or provider or "custom"
        self.prov_edit = QLineEdit(init_prov)
        self.prov_edit.setPlaceholderText("e.g. custom, zhipu, openai")
        form.addRow("Provider Key:", self.prov_edit)

        # Context limit
        limit = spec.get("limit", {}) if isinstance(spec.get("limit"), dict) else {}
        self.ctx_spin = QSpinBox()
        self.ctx_spin.setRange(0, 10000000)
        self.ctx_spin.setSingleStep(4000)
        self.ctx_spin.setValue(int(limit["context"]) if isinstance(limit.get("context"), (int, float)) else 128000)
        form.addRow("Context Window (tokens):", self.ctx_spin)

        # Output limit
        self.out_spin = QSpinBox()
        self.out_spin.setRange(0, 1000000)
        self.out_spin.setSingleStep(1000)
        self.out_spin.setValue(int(limit["output"]) if isinstance(limit.get("output"), (int, float)) else 8192)
        form.addRow("Max Output Tokens:", self.out_spin)

        # Features
        feat_box = QGroupBox("Capabilities & Features")
        feat_layout = QGridLayout(feat_box)
        self.att_cb = QCheckBox("Attachment (Images/Files)")
        self.att_cb.setChecked(bool(spec.get("attachment", True)))
        self.reas_cb = QCheckBox("Reasoning / Thinking")
        self.reas_cb.setChecked(bool(spec.get("reasoning", False)))
        self.tools_cb = QCheckBox("Tool Calling")
        self.tools_cb.setChecked(bool(spec.get("tool_call", True)))
        self.temp_cb = QCheckBox("Temperature Control")
        self.temp_cb.setChecked(bool(spec.get("temperature", True)))
        # Flags absent from the stored spec are only written when the user
        # actually toggles them, so an unedited OK never invents them.
        self._initial_feature_state = {
            key: box.isChecked()
            for key, box in (("attachment", self.att_cb), ("reasoning", self.reas_cb),
                             ("tool_call", self.tools_cb), ("temperature", self.temp_cb))
        }

        feat_layout.addWidget(self.att_cb, 0, 0)
        feat_layout.addWidget(self.reas_cb, 0, 1)
        feat_layout.addWidget(self.tools_cb, 1, 0)
        feat_layout.addWidget(self.temp_cb, 1, 1)
        form.addRow(feat_box)

        # Modalities
        mods = spec.get("modalities", {}) if isinstance(spec.get("modalities"), dict) else {}
        in_mods = set(mods.get("input", ["text", "image"]))
        out_mods = set(mods.get("output", ["text"]))

        mod_box = QGroupBox("Modalities")
        mod_layout = QHBoxLayout(mod_box)
        self.mod_in_image = QCheckBox("Input Image")
        self.mod_in_image.setChecked("image" in in_mods)
        self.mod_in_audio = QCheckBox("Input Audio")
        self.mod_in_audio.setChecked("audio" in in_mods)
        self.mod_out_image = QCheckBox("Output Image")
        self.mod_out_image.setChecked("image" in out_mods)

        mod_layout.addWidget(self.mod_in_image)
        mod_layout.addWidget(self.mod_in_audio)
        mod_layout.addWidget(self.mod_out_image)
        form.addRow(mod_box)

        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_id_changed(self, text: str):
        prev = self.id_edit.property("_prev_id") or ""
        if not self.name_edit.text() or self.name_edit.text() == humanize_model_id(prev):
            self.name_edit.setText(humanize_model_id(text))
        self.id_edit.setProperty("_prev_id", text)

    def _accept(self):
        mid = self.id_edit.text().strip()
        if not mid:
            QMessageBox.warning(self, "Missing Model ID", "Please specify a Model ID.")
            return

        name = self.name_edit.text().strip() or humanize_model_id(mid)
        prov = self.prov_edit.text().strip() or "custom"

        # Start from the stored spec so fields this dialog does not show
        # (cost, aliases, extra modalities, ...) survive an unedited OK.
        spec = dict(self._original_spec)

        limit = dict(spec["limit"]) if isinstance(spec.get("limit"), dict) else {}
        limit["context"] = self.ctx_spin.value()
        limit["output"] = self.out_spin.value()
        spec["limit"] = limit

        spec["name"] = name
        spec["provider"] = prov

        # Booleans: keep stored flags as they are, and only introduce a flag
        # the user actually toggled (never flip "absent" into "true").
        for key, box in (("attachment", self.att_cb),
                         ("reasoning", self.reas_cb),
                         ("tool_call", self.tools_cb),
                         ("temperature", self.temp_cb)):
            if key in spec:
                spec[key] = box.isChecked()
            elif box.isChecked() != self._initial_feature_state[key]:
                spec[key] = box.isChecked()

        mods = dict(spec["modalities"]) if isinstance(spec.get("modalities"), dict) else {}
        known_in = {"text", "image", "audio"}
        known_out = {"text", "image"}
        in_mods = [m for m in mods.get("input", []) if m not in known_in]
        out_mods = [m for m in mods.get("output", []) if m not in known_out]
        in_mods.insert(0, "text")
        if self.mod_in_image.isChecked():
            in_mods.insert(1, "image")
        if self.mod_in_audio.isChecked() and "audio" not in in_mods:
            in_mods.append("audio")
        out_mods.insert(0, "text")
        if self.mod_out_image.isChecked() and "image" not in out_mods:
            out_mods.append("image")
        if "modalities" in spec:
            spec["modalities"] = {"input": in_mods, "output": out_mods}

        self.result_model_id = mid
        self.result_provider = prov
        self.result_spec = spec
        self.accept()


class EditPatternRuleDialog(QDialog):
    """Dialog to create or edit a pattern mapping rule."""

    def __init__(self, parent, rule: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Pattern Mapping Rule" if rule else "Add Pattern Mapping Rule")
        self.resize(500, 320)
        self.result_rule = {}

        rule = rule or {}
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.pat_edit = QLineEdit(rule.get("pattern", ""))
        self.pat_edit.setPlaceholderText("e.g. glm-*, deepseek-*, or regex:^my-proxy/.*")
        form.addRow("Pattern (wildcard/regex) *:", self.pat_edit)

        self.prov_edit = QLineEdit(rule.get("reference_provider", ""))
        self.prov_edit.setPlaceholderText("e.g. zhipu, openai, google, anthropic")
        form.addRow("Reference Provider *:", self.prov_edit)

        self.model_edit = QLineEdit(rule.get("reference_model", ""))
        self.model_edit.setPlaceholderText("e.g. glm-4-flash, gpt-4o (optional)")
        form.addRow("Reference Model (optional):", self.model_edit)

        self.desc_edit = QLineEdit(rule.get("description", ""))
        self.desc_edit.setPlaceholderText("e.g. Map all GLM models to Zhipu capabilities")
        form.addRow("Description:", self.desc_edit)

        layout.addLayout(form)

        hint = QLabel(
            "<small><b>Examples:</b><br>"
            "• <code>glm-*</code> with provider <code>zhipu</code>: any model like <code>glm-5.3-flash</code> gets Zhipu features.<br>"
            "• <code>my-proxy/*</code> with provider <code>openai</code> and model <code>gpt-4o</code>: matches proxy models to GPT-4o spec."
            "</small>"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _accept(self):
        pat = self.pat_edit.text().strip()
        prov = self.prov_edit.text().strip()
        if not pat or not prov:
            QMessageBox.warning(self, "Missing Fields", "Pattern and Reference Provider are required.")
            return

        self.result_rule = {
            "pattern": pat,
            "reference_provider": prov,
            "reference_model": self.model_edit.text().strip(),
            "description": self.desc_edit.text().strip(),
        }
        self.accept()


class CustomCatalogManagerDialog(QDialog):
    """Comprehensive dialog to manage custom model specs, pattern rules, and online catalog updates."""

    def __init__(self, parent, catalog: ModelCatalog):
        super().__init__(parent)
        self.setWindowTitle("Model Catalog & Matching Rules Manager")
        self.resize(900, 600)
        self.catalog = catalog
        self.settings = SettingsManager()
        self._sync_worker = None
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Custom Models
        self.custom_tab = QWidget()
        self._setup_custom_models_tab()
        self.tabs.addTab(self.custom_tab, "Custom Model Specs")

        # Tab 2: Pattern Rules
        self.rules_tab = QWidget()
        self._setup_pattern_rules_tab()
        self.tabs.addTab(self.rules_tab, "Pattern Mapping Rules")

        # Tab 3: Online Sync & Sources
        self.sync_tab = QWidget()
        self._setup_sync_tab()
        self.tabs.addTab(self.sync_tab, "Catalog Sources & Update")

        # Bottom Close button
        btn_layout = QHBoxLayout()
        self.status_lbl = QLabel()
        self._refresh_status()
        btn_layout.addWidget(self.status_lbl)
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _setup_custom_models_tab(self):
        lay = QVBoxLayout(self.custom_tab)

        tb = QHBoxLayout()
        self.custom_search = QLineEdit()
        self.custom_search.setPlaceholderText("Search custom models...")
        self.custom_search.textChanged.connect(self._filter_custom_models)
        tb.addWidget(self.custom_search)

        for text, slot in [
            ("+ Add Model", self._add_custom_model),
            ("Edit", self._edit_selected_custom_model),
            ("Delete", self._delete_selected_custom_model),
            ("Import JSON", self._import_custom_models),
            ("Export JSON", self._export_custom_models),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            tb.addWidget(b)
        lay.addLayout(tb)

        self.custom_table = QTableWidget(0, 6)
        self.custom_table.setHorizontalHeaderLabels([
            "Model ID", "Name", "Provider", "Context", "Output", "Features"
        ])
        self.custom_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.custom_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.custom_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.custom_table.cellDoubleClicked.connect(lambda row, col: self._edit_selected_custom_model())
        lay.addWidget(self.custom_table)

        self._refresh_custom_models_table()

    def _read_custom_models(self, warn: bool = False) -> dict:
        """Read the custom-model file; an unparseable file yields an empty map
        plus a warning instead of raising through the dialog's UI paths."""
        try:
            return self.catalog.get_all_custom_models()
        except ValueError as e:
            if warn:
                QMessageBox.warning(self, "Custom Models File Error", str(e))
            return {}

    def _refresh_custom_models_table(self):
        models = self._read_custom_models(warn=True)
        self._populate_custom_models_table(models)

    def _populate_custom_models_table(self, models: dict):
        self.custom_table.setRowCount(len(models))
        for row, (mid, spec) in enumerate(sorted(models.items())):
            spec = spec if isinstance(spec, dict) else {}
            self.custom_table.setItem(row, 0, QTableWidgetItem(mid))
            self.custom_table.setItem(row, 1, QTableWidgetItem(spec.get("name") or humanize_model_id(mid)))
            self.custom_table.setItem(row, 2, QTableWidgetItem(spec.get("provider", "custom")))
            limit = spec.get("limit", {}) if isinstance(spec.get("limit"), dict) else {}
            ctx = limit.get("context")
            out = limit.get("output")
            self.custom_table.setItem(row, 3, QTableWidgetItem(f"{ctx:,}" if ctx else "—"))
            self.custom_table.setItem(row, 4, QTableWidgetItem(f"{out:,}" if out else "—"))

            feats = []
            if spec.get("attachment"):
                feats.append("Attachment")
            if spec.get("reasoning"):
                feats.append("Reasoning")
            if spec.get("tool_call"):
                feats.append("Tools")
            self.custom_table.setItem(row, 5, QTableWidgetItem(", ".join(feats) if feats else "—"))

    def _filter_custom_models(self, text: str):
        all_models = self._read_custom_models()
        if not text:
            self._populate_custom_models_table(all_models)
            return
        text = text.lower()
        filtered = {
            mid: spec for mid, spec in all_models.items()
            if text in mid.lower() or text in str(spec.get("name", "")).lower() or text in str(spec.get("provider", "")).lower()
        }
        self._populate_custom_models_table(filtered)

    def _add_custom_model(self):
        dlg = EditCustomModelDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.result_model_id:
            self.catalog.save_custom_model(dlg.result_model_id, dlg.result_spec, dlg.result_provider)
            self._refresh_custom_models_table()
            self._refresh_status()

    def _edit_selected_custom_model(self):
        selected = self.custom_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        mid_item = self.custom_table.item(row, 0)
        if not mid_item:
            return
        mid = mid_item.text()
        all_models = self._read_custom_models()
        spec = all_models.get(mid, {})
        dlg = EditCustomModelDialog(self, mid, spec, spec.get("provider", "custom"))
        if dlg.exec() == QDialog.Accepted and dlg.result_model_id:
            if dlg.result_model_id != mid:
                self.catalog.delete_custom_model(mid)
            self.catalog.save_custom_model(dlg.result_model_id, dlg.result_spec, dlg.result_provider)
            self._refresh_custom_models_table()
            self._refresh_status()

    def _delete_selected_custom_model(self):
        selected = self.custom_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        mid = self.custom_table.item(row, 0).text()
        if _confirm(self, "Delete Custom Model", f"Delete custom model spec '{mid}'?"):
            self.catalog.delete_custom_model(mid)
            self._refresh_custom_models_table()
            self._refresh_status()

    def _import_custom_models(self):
        dlg = JsonImportDialog(
            self, "Import Custom Models",
            "Paste or load custom models JSON. Supported format: { \"model_id\": { \"name\": \"...\", ... } }"
        )
        if dlg.exec() == QDialog.Accepted and dlg.result_data:
            data = dlg.result_data
            if not isinstance(data, dict):
                QMessageBox.warning(self, "Import Error",
                                    "Custom models JSON must be an object.")
                return
            # Reject anything that is not `{model_id: {spec}}` before writing:
            # a stray "$schema" string would be saved and then break the loader.
            invalid = [k for k, v in data.items() if not isinstance(v, dict)]
            if invalid:
                QMessageBox.warning(
                    self, "Import Error",
                    "These entries are not model objects and were not imported: "
                    + ", ".join(sorted(map(str, invalid))[:10]),
                )
                return
            if not data:
                QMessageBox.warning(self, "Import Error", "No custom models found.")
                return
            try:
                current = self.catalog.get_all_custom_models()
            except ValueError as e:
                QMessageBox.warning(self, "Import Error", str(e))
                return
            current.update(data)
            try:
                CUSTOM_MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(
                    CUSTOM_MODELS_FILE,
                    json.dumps(current, indent=2, ensure_ascii=False),
                )
                self.catalog._reload_after_custom_change()
                self._refresh_custom_models_table()
                self._refresh_status()
                QMessageBox.information(self, "Import", f"Imported {len(data)} custom model(s).")
            except Exception as e:
                QMessageBox.warning(self, "Import Error", str(e))

    def _export_custom_models(self):
        models = self._read_custom_models()
        if not models:
            QMessageBox.information(self, "Export", "No custom models to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Custom Models", "custom_models.json",
            "JSON files (*.json);;All files (*)"
        )
        if path:
            try:
                Path(path).write_text(json.dumps(models, indent=2, ensure_ascii=False), encoding="utf-8")
                QMessageBox.information(self, "Export Complete", f"Exported to {path}")
            except OSError as e:
                QMessageBox.warning(self, "Export Error", str(e))

    def _setup_pattern_rules_tab(self):
        lay = QVBoxLayout(self.rules_tab)

        tb = QHBoxLayout()
        for text, slot in [
            ("+ Add Rule", self._add_pattern_rule),
            ("Edit", self._edit_selected_pattern_rule),
            ("Delete", self._delete_selected_pattern_rule),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            tb.addWidget(b)
        tb.addStretch()
        lay.addLayout(tb)

        self.rules_table = QTableWidget(0, 4)
        self.rules_table.setHorizontalHeaderLabels([
            "Pattern", "Reference Provider", "Reference Model", "Description"
        ])
        self.rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.rules_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.rules_table.cellDoubleClicked.connect(lambda row, col: self._edit_selected_pattern_rule())
        lay.addWidget(self.rules_table)

        # Interactive Tester Box
        test_box = QGroupBox("Interactive Pattern Rule Tester")
        test_lay = QHBoxLayout(test_box)
        self.test_input = QLineEdit()
        self.test_input.setPlaceholderText("Type a model ID to test pattern matching, e.g. glm-5.3-flash...")
        self.test_input.textChanged.connect(self._test_pattern_match)
        test_lay.addWidget(self.test_input, 2)
        self.test_result = QLabel("Enter a model ID above to test")
        self.test_result.setStyleSheet("color: #0969da; font-weight: bold;")
        test_lay.addWidget(self.test_result, 3)
        lay.addWidget(test_box)

        self._refresh_pattern_rules_table()

    def _refresh_pattern_rules_table(self):
        rules = self.catalog.get_all_pattern_rules()
        self.rules_table.setRowCount(len(rules))
        for row, rule in enumerate(rules):
            self.rules_table.setItem(row, 0, QTableWidgetItem(rule.get("pattern", "")))
            self.rules_table.setItem(row, 1, QTableWidgetItem(rule.get("reference_provider", "")))
            self.rules_table.setItem(row, 2, QTableWidgetItem(rule.get("reference_model", "")))
            self.rules_table.setItem(row, 3, QTableWidgetItem(rule.get("description", "")))

    def _add_pattern_rule(self):
        dlg = EditPatternRuleDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.result_rule:
            rules = self.catalog.get_all_pattern_rules()
            rules.append(dlg.result_rule)
            self.catalog.save_pattern_rules(rules)
            self._refresh_pattern_rules_table()
            self._refresh_status()

    def _edit_selected_pattern_rule(self):
        selected = self.rules_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        rules = self.catalog.get_all_pattern_rules()
        if row < len(rules):
            dlg = EditPatternRuleDialog(self, rules[row])
            if dlg.exec() == QDialog.Accepted and dlg.result_rule:
                rules[row] = dlg.result_rule
                self.catalog.save_pattern_rules(rules)
                self._refresh_pattern_rules_table()
                self._refresh_status()

    def _delete_selected_pattern_rule(self):
        selected = self.rules_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        rules = self.catalog.get_all_pattern_rules()
        if row < len(rules) and _confirm(self, "Delete Rule", f"Delete rule for pattern '{rules[row].get('pattern')}'?"):
            rules.pop(row)
            self.catalog.save_pattern_rules(rules)
            self._refresh_pattern_rules_table()
            self._refresh_status()

    def _test_pattern_match(self, text: str):
        mid = text.strip()
        if not mid:
            self.test_result.setText("Enter a model ID above to test")
            return
        matches = self.catalog.find_model(mid)
        if matches:
            fmt = matches[0]
            self.test_result.setText(
                f"✓ Matches! Provider: {fmt.provider} | Name: {fmt.name or humanize_model_id(mid)} | Context: {fmt.context_k()}"
            )
        else:
            self.test_result.setText("✗ No match found in catalog or pattern rules")

    def _setup_sync_tab(self):
        lay = QVBoxLayout(self.sync_tab)

        form = QFormLayout()
        self.url_edit = QLineEdit(self.settings.get_catalog_url())
        reset_btn = QPushButton("Reset URL")
        reset_btn.clicked.connect(lambda: self.url_edit.setText(DEFAULT_CATALOG_URL))
        url_lay = QHBoxLayout()
        url_lay.addWidget(self.url_edit, 1)
        url_lay.addWidget(reset_btn)
        form.addRow("Online Catalog URL:", url_lay)
        lay.addLayout(form)

        btn_row = QHBoxLayout()
        self.sync_btn = QPushButton("🔄 Update Catalog Online Now")
        self.sync_btn.setStyleSheet("padding: 8px 16px; font-weight: bold;")
        self.sync_btn.clicked.connect(self._sync_online)
        btn_row.addWidget(self.sync_btn)

        load_file_btn = QPushButton("Load Catalog from Local JSON...")
        load_file_btn.clicked.connect(self._load_local_catalog)
        btn_row.addWidget(load_file_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self.sync_info = QLabel()
        self.sync_info.setWordWrap(True)
        self.sync_info.setStyleSheet("background: palette(window); padding: 12px; border-radius: 6px;")
        lay.addWidget(self.sync_info)
        lay.addStretch()
        self._update_sync_info()

    def _update_sync_info(self):
        src = self.catalog.source or "None"
        cnt = len(self.catalog.flat)
        try:
            custom_cnt = len(self.catalog.get_all_custom_models())
        except ValueError:
            custom_cnt = -1
        rules_cnt = len(self.catalog.get_all_pattern_rules())
        last = self.catalog.last_updated or "Never"
        custom_label = "unreadable — fix or delete custom_models.json" if custom_cnt < 0 \
            else f"{custom_cnt:,}"
        self.sync_info.setText(
            f"<b>Active Catalog Source:</b> {src}<br>"
            f"<b>Total Catalog Models:</b> {cnt:,}<br>"
            f"<b>User Custom Models:</b> {custom_label}<br>"
            f"<b>Active Pattern Rules:</b> {rules_cnt:,}<br>"
            f"<b>Last Loaded / Updated:</b> {last}"
        )

    def _sync_online(self):
        """Start the online catalog update on a worker thread."""
        url = self.url_edit.text().strip()
        self.settings.set_catalog_url(url)
        self.sync_btn.setEnabled(False)
        self.sync_btn.setText("Updating...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self._sync_worker = _CatalogSyncWorker(self.catalog, url)
        self._sync_worker.finished_ok.connect(self._on_sync_ok)
        self._sync_worker.failed.connect(self._on_sync_failed)
        self._sync_worker.start()

    def _on_sync_ok(self, msg: str, count: int):
        QApplication.restoreOverrideCursor()
        self.sync_btn.setEnabled(True)
        self.sync_btn.setText("🔄 Update Catalog Online Now")
        QMessageBox.information(self, "Catalog Update", msg)
        self._update_sync_info()
        self._refresh_status()

    def _on_sync_failed(self, msg: str):
        QApplication.restoreOverrideCursor()
        self.sync_btn.setEnabled(True)
        self.sync_btn.setText("🔄 Update Catalog Online Now")
        QMessageBox.warning(self, "Catalog Update Error", msg)

    def _load_local_catalog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Catalog JSON", str(Path.home()),
            "JSON files (*.json);;All files (*)"
        )
        if path:
            try:
                self.catalog.load(Path(path))
                self._update_sync_info()
                self._refresh_status()
                QMessageBox.information(self, "Catalog Loaded", f"Successfully loaded {len(self.catalog.flat)} models.")
            except Exception as e:
                QMessageBox.warning(self, "Load Error", str(e))

    def _refresh_status(self):
        cnt = len(self.catalog.flat)
        try:
            custom_cnt = len(self.catalog.get_all_custom_models())
        except ValueError:
            custom_cnt = "error"
        rules_cnt = len(self.catalog.get_all_pattern_rules())
        self.status_lbl.setText(
            f"Catalog: {cnt:,} models | Custom: {custom_cnt} | Pattern Rules: {rules_cnt}"
        )


