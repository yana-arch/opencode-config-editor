# GUI Components
def _esc_html(s) -> str:
    return html.escape(str(s), quote=True)

class MaskedLineEdit(QWidget):
    """Line edit with optional masking for sensitive fields"""

    SECRET_HINT = re.compile(r"(key|token|secret|password|auth)", re.I)

    def __init__(self, value="", parent=None, field_name="", placeholder=""):
        super().__init__(parent)
        self.field_name = field_name
        self.is_secret = bool(self.SECRET_HINT.search(field_name))
        self._real_value = str(value) if value is not None else ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setText(self._display_value())
        layout.addWidget(self.edit)

        if self.is_secret:
            self.toggle_btn = QPushButton("👁")
            self.toggle_btn.setCheckable(True)
            self.toggle_btn.setFixedWidth(30)
            self.toggle_btn.toggled.connect(self._toggle_visibility)
            layout.addWidget(self.toggle_btn)

    def _display_value(self) -> str:
        """Get display value (masked if secret)"""
        if not self.is_secret or self.toggle_btn.isChecked():
            return self._real_value
        return _mask(self._real_value)

    def _toggle_visibility(self, checked: bool):
        """Toggle visibility of secret value"""
        self.edit.setText(self._display_value())

    def set_value(self, value):
        """Set value"""
        self._real_value = str(value) if value is not None else ""
        self.edit.setText(self._display_value())

    def value(self) -> str:
        """Get current value"""
        if self.is_secret and not self.toggle_btn.isChecked():
            return self._real_value
        return self.edit.text()

def _mask(v: str, visible: bool = False) -> str:
    """Mask sensitive value"""
    if v is None:
        return ""
    s = str(v)
    if visible or not s:
        return s
    if len(s) <= 4:
        return "*" * len(s)
    return s[:3] + "*" * (len(s) - 4) + s[-1]

class SearchableTableWidget(QTableWidget):
    """Table widget with search/filter functionality"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_text = ""
        self._original_data = []

    def set_data(self, data: List[dict]):
        """Set table data"""
        self._original_data = data
        self._apply_filter()

    def set_search_text(self, text: str):
        """Set search text"""
        self._search_text = text.lower()
        self._apply_filter()

    def _apply_filter(self):
        """Apply current filter to data"""
        if not self._search_text:
            self.setRowCount(len(self._original_data))
            for row, item in enumerate(self._original_data):
                self._populate_row(row, item)
            return

        filtered = [
            item for item in self._original_data
            if self._matches_search(item)
        ]
        self.setRowCount(len(filtered))
        for row, item in enumerate(filtered):
            self._populate_row(row, item)

    def _matches_search(self, item: dict) -> bool:
        """Check if item matches search text"""
        search = self._search_text.lower()
        for col in range(self.columnCount()):
            header = self.horizontalHeaderItem(col).text().lower()
            value = str(item.get(header, "")).lower()
            if search in value:
                return True
        return False

    def _populate_row(self, row: int, item: dict):
        """Populate table row with item data"""
        for col in range(self.columnCount()):
            header = self.horizontalHeaderItem(col).text()
            value = item.get(header, "")
            self.setItem(row, col, QTableWidgetItem(str(value)))

class ModelEditDialog(QDialog):
    """Enhanced model edit dialog with validation"""

    def __init__(self, parent, model_id: str = "", spec: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Model" if model_id else "Add Model")
        self.resize(500, 600)

        spec = spec or {}
        layout = QFormLayout(self)

        # Model ID
        self.id_edit = QLineEdit(model_id)
        self.id_edit.setPlaceholderText("e.g. gpt-4o")
        layout.addRow("Model ID*", self.id_edit)

        # Basic fields
        self.name_edit = QLineEdit(spec.get("name", ""))
        self.name_edit.setPlaceholderText("Human-readable name")
        layout.addRow("Name", self.name_edit)

        self.attachment_check = QCheckBox("Supports file attachments")
        self.attachment_check.setChecked(spec.get("attachment", False))
        layout.addRow("", self.attachment_check)

        self.reasoning_check = QCheckBox("Supports reasoning")
        self.reasoning_check.setChecked(spec.get("reasoning", False))
        layout.addRow("", self.reasoning_check)

        self.temperature_check = QCheckBox("Supports temperature setting")
        self.temperature_check.setChecked(spec.get("temperature", False))
        layout.addRow("", self.temperature_check)

        self.tool_call_check = QCheckBox("Supports tool calls")
        self.tool_call_check.setChecked(spec.get("tool_call", True))
        layout.addRow("", self.tool_call_check)

        # Cost fields
        cost_group = QGroupBox("Cost (per 1M tokens)")
        cost_layout = QFormLayout()

        self.cost_in_edit = QLineEdit(str(spec.get("cost", {}).get("input", "")))
        self.cost_in_edit.setPlaceholderText("e.g. 5.00")
        cost_layout.addRow("Input ($)", self.cost_in_edit)

        self.cost_out_edit = QLineEdit(str(spec.get("cost", {}).get("output", "")))
        self.cost_out_edit.setPlaceholderText("e.g. 15.00")
        cost_layout.addRow("Output ($)", self.cost_out_edit)

        self.cost_cache_read_edit = QLineEdit(str(spec.get("cost", {}).get("cache_read", "")))
        cost_layout.addRow("Cache Read ($)", self.cost_cache_read_edit)

        self.cost_cache_write_edit = QLineEdit(str(spec.get("cost", {}).get("cache_write", "")))
        cost_layout.addRow("Cache Write ($)", self.cost_cache_write_edit)

        cost_group.setLayout(cost_layout)
        layout.addRow(cost_group)

        # Limit fields
        limit_group = QGroupBox("Limits")
        limit_layout = QFormLayout()

        self.limit_ctx_edit = QLineEdit(str(spec.get("limit", {}).get("context", "")))
        self.limit_ctx_edit.setPlaceholderText("e.g. 128000")
        limit_layout.addRow("Context (tokens)", self.limit_ctx_edit)

        self.limit_out_edit = QLineEdit(str(spec.get("limit", {}).get("output", "")))
        self.limit_out_edit.setPlaceholderText("e.g. 4096")
        limit_layout.addRow("Output (tokens)", self.limit_out_edit)

        limit_group.setLayout(limit_layout)
        layout.addRow(limit_group)

        # Additional fields
        self.extra_edit = QPlainTextEdit()
        extra_data = {k: v for k, v in spec.items() if k not in {
            "name", "attachment", "reasoning", "temperature", "tool_call",
            "cost", "limit"
        }}
        self.extra_edit.setPlainText(json.dumps(extra_data, indent=2))
        layout.addRow("Additional Fields (JSON)", self.extra_edit)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        self.result_id = None
        self.result_spec = None

    def _accept(self):
        """Validate and accept dialog"""
        model_id = self.id_edit.text().strip()
        if not model_id:
            QMessageBox.warning(self, "Error", "Model ID is required")
            return

        try:
            extra_data = json.loads(self.extra_edit.toPlainText() or "{}")
            if not isinstance(extra_data, dict):
                raise ValueError("Additional fields must be a JSON object")
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Error", f"Invalid JSON in additional fields: {e}")
            return
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        # Build spec
        spec = dict(extra_data)

        if self.name_edit.text().strip():
            spec["name"] = self.name_edit.text().strip()

        spec["attachment"] = self.attachment_check.isChecked()
        spec["reasoning"] = self.reasoning_check.isChecked()
        spec["temperature"] = self.temperature_check.isChecked()
        spec["tool_call"] = self.tool_call_check.isChecked()

        # Cost
        cost = {}
        for field, edit in [
            ("input", self.cost_in_edit),
            ("output", self.cost_out_edit),
            ("cache_read", self.cost_cache_read_edit),
            ("cache_write", self.cost_cache_write_edit)
        ]:
            value = edit.text().strip()
            if value:
                try:
                    cost[field] = float(value)
                except ValueError:
                    QMessageBox.warning(self, "Error", f"Invalid cost value for {field}")
                    return
        if cost:
            spec["cost"] = cost

        # Limits
        limit = {}
        for field, edit in [
            ("context", self.limit_ctx_edit),
            ("output", self.limit_out_edit)
        ]:
            value = edit.text().strip()
            if value:
                try:
                    limit[field] = int(value)
                except ValueError:
                    QMessageBox.warning(self, "Error", f"Invalid limit value for {field}")
                    return
        if limit:
            spec["limit"] = limit

        self.result_id = model_id
        self.result_spec = spec
        self.accept()

class ModelsManagerDialog(QDialog):
    """Enhanced models manager with bulk operations"""

    def __init__(self, app, provider_key: str, provider_cfg: dict):
        super().__init__(app)
        self.app = app
        self.provider_key = provider_key
        self.provider_cfg = provider_cfg
        self.models = dict(provider_cfg.get("models", {})) if isinstance(provider_cfg.get("models"), dict) else {}
        self.setWindowTitle(f"Models - {provider_key}")
        self.resize(900, 600)

        layout = QVBoxLayout(self)

        # Search bar
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search models...")
        self.search_edit.textChanged.connect(self._filter_models)
        search_layout.addWidget(self.search_edit)

        # Buttons
        button_layout = QHBoxLayout()
        for text, slot in [
            ("+ Add", self._add_model),
            ("Edit", self._edit_model),
            ("Remove", self._remove_model),
            ("Import", self._import_models),
            ("Export", self._export_models),
            ("Apply Catalog", self._apply_catalog),
            ("Match from Catalog", self._match_catalog),
            ("Bulk Edit", self._bulk_edit)
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            button_layout.addWidget(btn)

        layout.addLayout(search_layout)
        layout.addLayout(button_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Name", "Attachment", "Reasoning", "Cost (in/out)",
            "Context/Output", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        layout.addWidget(self.table)

        # Status bar
        self.status_label = QLabel()
        layout.addWidget(self.status_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._update_table()

    def _update_table(self):
        """Update table with current models"""
        self.table.setRowCount(len(self.models))
        for row, (model_id, spec) in enumerate(sorted(self.models.items())):
            if not isinstance(spec, dict):
                spec = {}

            # ID
            self.table.setItem(row, 0, QTableWidgetItem(model_id))

            # Name
            self.table.setItem(row, 1, QTableWidgetItem(spec.get("name", "")))

            # Attachment
            self.table.setItem(row, 2, QTableWidgetItem("✓" if spec.get("attachment") else ""))

            # Reasoning
            self.table.setItem(row, 3, QTableWidgetItem("✓" if spec.get("reasoning") else ""))

            # Cost
            cost = spec.get("cost", {}) if isinstance(spec.get("cost"), dict) else {}
            cost_text = f"{cost.get('input', '')}/{cost.get('output', '')}"
            self.table.setItem(row, 4, QTableWidgetItem(cost_text))

            # Limits
            limit = spec.get("limit", {}) if isinstance(spec.get("limit"), dict) else {}
            limit_text = f"{limit.get('context', '')}/{limit.get('output', '')}"
            self.table.setItem(row, 5, QTableWidgetItem(limit_text))

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedWidth(60)
            edit_btn.clicked.connect(lambda _, m=model_id: self._edit_model(m))
            actions_layout.addWidget(edit_btn)

            remove_btn = QPushButton("Remove")
            remove_btn.setFixedWidth(60)
            remove_btn.clicked.connect(lambda _, m=model_id: self._remove_model(m))
            actions_layout.addWidget(remove_btn)

            match_btn = QPushButton("Match")
            match_btn.setFixedWidth(60)
            match_btn.clicked.connect(lambda _, m=model_id: self._match_single(m))
            actions_layout.addWidget(match_btn)

            self.table.setCellWidget(row, 6, actions_widget)

        self.status_label.setText(f"{len(self.models)} models")

    def _filter_models(self, text: str):
        """Filter models by search text"""
        if not text:
            self._update_table()
            return

        text = text.lower()
        filtered = {
            mid: spec for mid, spec in self.models.items()
            if text in mid.lower() or
               (isinstance(spec.get("name"), str) and text in spec["name"].lower())
        }

        self.table.setRowCount(len(filtered))
        for row, (model_id, spec) in enumerate(sorted(filtered.items())):
            if not isinstance(spec, dict):
                spec = {}

            self.table.setItem(row, 0, QTableWidgetItem(model_id))
            self.table.setItem(row, 1, QTableWidgetItem(spec.get("name", "")))
            self.table.setItem(row, 2, QTableWidgetItem("✓" if spec.get("attachment") else ""))
            self.table.setItem(row, 3, QTableWidgetItem("✓" if spec.get("reasoning") else ""))

            cost = spec.get("cost", {}) if isinstance(spec.get("cost"), dict) else {}
            cost_text = f"{cost.get('input', '')}/{cost.get('output', '')}"
            self.table.setItem(row, 4, QTableWidgetItem(cost_text))

            limit = spec.get("limit", {}) if isinstance(spec.get("limit"), dict) else {}
            limit_text = f"{limit.get('context', '')}/{limit.get('output', '')}"
            self.table.setItem(row, 5, QTableWidgetItem(limit_text))

            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedWidth(60)
            edit_btn.clicked.connect(lambda _, m=model_id: self._edit_model(m))
            actions_layout.addWidget(edit_btn)

            remove_btn = QPushButton("Remove")
            remove_btn.setFixedWidth(60)
            remove_btn.clicked.connect(lambda _, m=model_id: self._remove_model(m))
            actions_layout.addWidget(remove_btn)

            match_btn = QPushButton("Match")
            match_btn.setFixedWidth(60)
            match_btn.clicked.connect(lambda _, m=model_id: self._match_single(m))
            actions_layout.addWidget(match_btn)

            self.table.setCellWidget(row, 6, actions_widget)

        self.status_label.setText(f"{len(filtered)} models (filtered)")

    def _add_model(self):
        """Add new model"""
        dlg = ModelEditDialog(self)
        if dlg.exec() == QDialog.Accepted:
            if dlg.result_id in self.models:
                if not _confirm(self, "Model exists", f"Overwrite existing model '{dlg.result_id}'?"):
                    return
            self.models[dlg.result_id] = dlg.result_spec
            self._update_table()
            self.app.mark_dirty()

    def _edit_model(self, model_id: Optional[str] = None):
        """Edit existing model"""
        if model_id is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Edit", "Please select a model to edit")
                return
            model_id = selected[0].text()

        if model_id not in self.models:
            QMessageBox.warning(self, "Error", f"Model '{model_id}' not found")
            return

        dlg = ModelEditDialog(self, model_id, self.models[model_id])
        if dlg.exec() == QDialog.Accepted:
            if dlg.result_id != model_id:
                self.models.pop(model_id)
            self.models[dlg.result_id] = dlg.result_spec
            self._update_table()
            self.app.mark_dirty()

    def _remove_model(self, model_id: Optional[str] = None):
        """Remove model(s)"""
        if model_id is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Remove", "Please select models to remove")
                return

            model_ids = {selected[i].text() for i in range(0, len(selected), self.table.columnCount())}
            if not _confirm(self, "Remove Models", f"Remove {len(model_ids)} selected models?"):
                return

            for mid in model_ids:
                self.models.pop(mid, None)
        else:
            if not _confirm(self, "Remove Model", f"Remove model '{model_id}'?"):
                return
            self.models.pop(model_id, None)

        self._update_table()
        self.app.mark_dirty()

    def _import_models(self):
        """Import models from JSON"""
        dlg = JsonImportDialog(
            self, "Import Models",
            "Paste or load models JSON. Supported formats:\n"
            "- {modelId: spec} map\n"
            "- {'models': {modelId: spec}} object\n"
            "- Array of model specs with 'id' field"
        )
        if dlg.exec() != QDialog.Accepted:
            return

        try:
            models_map = _extract_models_map(dlg.result_data)
        except ValueError as e:
            QMessageBox.warning(self, "Import Error", str(e))
            return

        added = 0
        updated = 0
        for model_id, spec in models_map.items():
            if model_id in self.models:
                updated += 1
            else:
                added += 1
            self.models[model_id] = spec

        self._update_table()
        self.app.mark_dirty()
        QMessageBox.information(
            self, "Import Complete",
            f"Added {added} new models, updated {updated} existing models"
        )

    def _export_models(self):
        """Export models to JSON file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Models", f"{self.provider_key}-models.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.models, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _apply_catalog(self):
        """Apply model catalog to update existing models"""
        if not self.app.model_catalog.loaded():
            if hasattr(self.app, "_ensure_catalog"):
                if not self.app._ensure_catalog():
                    return
            else:
                if not _confirm(self, "No Catalog", "No model catalog loaded. Load one now?"):
                    return
                if not self.app.load_model_catalog():
                    return

        catalog = self.app.model_catalog
        models = catalog.models_for(self.provider_key, self.provider_cfg.get("npm"))

        if not models:
            QMessageBox.information(self, "Apply Catalog", "No matching models found in catalog")
            return

        # Show preview dialog
        preview_dlg = CatalogPreviewDialog(self, models, self.models)
        if preview_dlg.exec() != QDialog.Accepted:
            return

        overwrite = preview_dlg.overwrite_checkbox.isChecked()
        updated = 0

        for model_id in preview_dlg.selected_models:
            if model_id in self.models and model_id in models:
                self.models[model_id] = _merge_model_spec(
                    self.models[model_id], models[model_id], overwrite
                )
                updated += 1

        self._update_table()
        self.app.mark_dirty()
        QMessageBox.information(
            self, "Apply Catalog",
            f"Updated {updated} models from catalog"
        )

    def _match_catalog(self):
        """Match & format all models in this provider against the catalog."""
        self._match_models(set(self.models.keys()))

    def _match_single(self, model_id: str):
        """Match & format a single model against the catalog."""
        self._match_models({model_id})

    def _match_models(self, model_ids):
        """Preview and apply matched catalog format for the given models."""
        if not self.app.model_catalog.loaded():
            if hasattr(self.app, "_ensure_catalog"):
                if not self.app._ensure_catalog():
                    return
            else:
                if not _confirm(self, "No Catalog", "No model catalog loaded. Load one now?"):
                    return
                if not self.app.load_model_catalog():
                    return

        catalog = self.app.model_catalog
        scope = set(model_ids)

        entries = []  # (model_id, old_spec, new_spec, status)
        ambiguous_data = {}
        for mid in sorted(scope):
            if mid not in self.models:
                continue
            matches = catalog.find_model(mid)
            if not matches:
                entries.append((mid, dict(self.models[mid]), None, "unknown"))
                continue
            chosen = _resolve_match(matches, self.provider_key, mid)
            if chosen is None:
                entries.append((mid, dict(self.models[mid]), None, "ambiguous"))
                ambiguous_data[mid] = (self.provider_key, matches)
                continue
            merged = _merge_model_spec(
                self.models[mid], build_spec_from_format(chosen), overwrite=False)
            status = "matched" if merged != (self.models[mid] or {}) else "unchanged"
            entries.append((mid, dict(self.models[mid]), merged, status))

        if not any(e[2] is not None or e[3] == "ambiguous" for e in entries):
            QMessageBox.information(
                self, "Match from Catalog",
                "No models matched. Check the model ids against the catalog."
            )
            return

        dlg = MatchFormatPreviewDialog(
            self, entries, ambiguous_data, catalog=self.app.model_catalog)
        if dlg.exec() != QDialog.Accepted:
            return

        overwrite = dlg.overwrite_checkbox.isChecked()
        applied = 0
        for mid, old_spec, new_spec, status in dlg.selected_entries:
            # Use the provider picked in the combo for ambiguous entries.
            if status == "ambiguous":
                new_spec = dlg.resolved_specs.get(mid, new_spec)
            elif status == "mapped":
                new_spec = dlg.mapped_specs.get(mid, new_spec)
            if new_spec is None:
                continue
            self.models[mid] = _merge_model_spec(
                self.models[mid], new_spec, overwrite=overwrite)
            applied += 1

        self._update_table()
        self.app.mark_dirty()
        if applied:
            QMessageBox.information(
                self, "Match from Catalog", f"Updated {applied} model(s) from catalog")
        else:
            QMessageBox.information(self, "Match from Catalog", "No changes were applied.")

    def _bulk_edit(self):
        """Bulk edit selected models"""
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Bulk Edit", "Please select models to edit")
            return

        model_ids = {selected[i].text() for i in range(0, len(selected), self.table.columnCount())}
        if not model_ids:
            return

        dlg = BulkEditDialog(self, self.models, model_ids)
        if dlg.exec() == QDialog.Accepted:
            for model_id in model_ids:
                if model_id in self.models:
                    self.models[model_id] = dlg.apply_to_model(self.models[model_id])
            self._update_table()
            self.app.mark_dirty()

    def result(self) -> dict:
        """Get result models"""
        return self.models

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
                self.resolved_specs[mid] = build_spec_from_format(combo.currentData())
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
        spec = build_spec_from_format(fmt)
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
            self.resolved_specs[mid] = build_spec_from_format(fmt)
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

class BulkEditDialog(QDialog):
    """Dialog for bulk editing model fields"""

    def __init__(self, parent, models: dict, model_ids: set):
        super().__init__(parent)
        self.setWindowTitle("Bulk Edit Models")
        self.resize(500, 400)

        self.models = models
        self.model_ids = model_ids

        layout = QVBoxLayout(self)

        # Info
        info_label = QLabel(f"Editing {len(model_ids)} models")
        layout.addWidget(info_label)

        # Fields to edit
        self.field_combo = QComboBox()
        self.field_combo.addItems(MODEL_FIELDS)
        layout.addWidget(self.field_combo)

        # Value
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("Leave empty to remove field")
        layout.addWidget(self.value_edit)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def apply_to_model(self, model: dict) -> dict:
        """Apply bulk edit to a model"""
        field = self.field_combo.currentText()
        value = self.value_edit.text().strip()

        if not field:
            return model

        model = dict(model)

        # Handle nested fields
        if "." in field:
            parts = field.split(".")
            current = model
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
                if not isinstance(current, dict):
                    current = {}
            last_part = parts[-1]

            if value:
                try:
                    if last_part in ("input", "output", "cache_read", "cache_write"):
                        current[last_part] = float(value)
                    else:
                        current[last_part] = int(value)
                except ValueError:
                    pass
            else:
                current.pop(last_part, None)
                # Clean up empty parent objects
                for part in reversed(parts[:-1]):
                    parent = model
                    for p in parts[:parts.index(part)]:
                        parent = parent[p]
                    if not parent.get(part):
                        parent.pop(part, None)
        else:
            if value:
                if field in ("attachment", "reasoning", "temperature", "tool_call"):
                    model[field] = value.lower() in ("true", "1", "yes")
                else:
                    try:
                        model[field] = int(value)
                    except ValueError:
                        try:
                            model[field] = float(value)
                        except ValueError:
                            model[field] = value
            else:
                model.pop(field, None)

        return model

class JsonImportDialog(QDialog):
    """Enhanced JSON import dialog with syntax highlighting"""

    def __init__(self, parent, title: str, hint: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 500)
        self.result_data = None

        layout = QVBoxLayout(self)

        if hint:
            hint_label = QLabel(hint)
            hint_label.setWordWrap(True)
            layout.addWidget(hint_label)

        # Buttons
        button_layout = QHBoxLayout()
        load_btn = QPushButton("Load from file...")
        load_btn.clicked.connect(self._load_file)
        paste_btn = QPushButton("Paste from clipboard")
        paste_btn.clicked.connect(self._paste)
        button_layout.addWidget(load_btn)
        button_layout.addWidget(paste_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Editor
        self.editor = QPlainTextEdit()
        font = QFont("Monospace")
        font.setStyleHint(QFont.Monospace)
        self.editor.setFont(font)
        self.highlighter = JSONHighlighter(self.editor.document())
        layout.addWidget(self.editor)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_file(self):
        """Load JSON from file"""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load JSON", str(Path.home()),
            "JSON files (*.json);;All files (*)"
        )
        if path:
            try:
                self.editor.setPlainText(Path(path).read_text(encoding="utf-8"))
            except OSError as e:
                QMessageBox.warning(self, "Load Error", str(e))

    def _paste(self):
        """Paste from clipboard"""
        cb = QApplication.clipboard()
        self.editor.setPlainText(cb.text())

    def _accept(self):
        """Validate and accept"""
        try:
            self.result_data = json.loads(self.editor.toPlainText())
            self.accept()
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", str(e))


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


class FetchProviderModelsDialog(QDialog):
    """Fetch a provider's model list from its API and preview the results."""

    def __init__(self, parent, provider_key: str = "new-provider", catalog=None):
        super().__init__(parent)
        self.setWindowTitle("Fetch Provider Models from API")
        self.resize(720, 560)
        self.fetched_models = {}   # {model_id: spec}
        self.provider_key = provider_key
        self._worker = None

        # Silently load the bundled catalog so the Reference combo can be filled.
        self.catalog = catalog
        try_load_bundled_catalog(self.catalog)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.key_edit = QLineEdit(provider_key)
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
        form.addRow("Base URL:", self.url_edit)

        self.apikey_edit = QLineEdit()
        self.apikey_edit.setEchoMode(QLineEdit.Password)
        self.apikey_edit.setPlaceholderText("(sent as a header, never saved to config)")
        form.addRow("API key:", self.apikey_edit)

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
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Add", "Model ID", "Name"])
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
        # Sensible default base URLs per adapter.
        defaults = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com",
            "gemini": "https://generativelanguage.googleapis.com",
            "models_dev": "https://models.dev/api.json",
            "generic": "",
        }
        if not self.url_edit.text().strip() or self.url_edit.text() in defaults.values():
            self.url_edit.setText(defaults.get(adapter, ""))
        self.apikey_edit.setEnabled(adapter != "models_dev")

    def _build_spec(self) -> ProviderFetchSpec:
        return ProviderFetchSpec(
            base_url=self.url_edit.text().strip(),
            adapter=self._current_adapter(),
            api_key=self.apikey_edit.text(),
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
        self.fetched_models = models
        self.fetch_btn.setEnabled(True)
        self.status_label.setText(f"Fetched {len(models)} models")
        self._populate(models)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(models))

    def _on_failed(self, msg: str):
        self.fetch_btn.setEnabled(True)
        self.status_label.setText("Fetch failed")
        QMessageBox.warning(self, "Fetch Error", msg)

    def _populate(self, models: dict):
        self.table.setRowCount(len(models))
        for row, (mid, spec) in enumerate(sorted(models.items())):
            check = QCheckBox()
            check.setChecked(True)
            self.table.setCellWidget(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(mid))
            self.table.setItem(row, 2, QTableWidgetItem(spec.get("name", "")))

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
                import csv
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
                spec = build_spec_from_format(chosen)
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

