# GUI Components
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

