# Model editing and management dialogs (Models Manager and friends)
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
        for fname, edit in [
            ("input", self.cost_in_edit),
            ("output", self.cost_out_edit),
            ("cache_read", self.cost_cache_read_edit),
            ("cache_write", self.cost_cache_write_edit)
        ]:
            value = edit.text().strip()
            if value:
                try:
                    cost[fname] = float(value)
                except ValueError:
                    QMessageBox.warning(self, "Error", f"Invalid cost value for {fname}")
                    return
        if cost:
            spec["cost"] = cost

        # Limits
        limit = {}
        for fname, edit in [
            ("context", self.limit_ctx_edit),
            ("output", self.limit_out_edit)
        ]:
            value = edit.text().strip()
            if value:
                try:
                    limit[fname] = int(value)
                except ValueError:
                    QMessageBox.warning(self, "Error", f"Invalid limit value for {fname}")
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

