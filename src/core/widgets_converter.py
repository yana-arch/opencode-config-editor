# Universal Cross-Config Converter GUI Dialog
# ---------------------------------------------------------------------------
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QTextEdit, QGroupBox, QSplitter,
    QFileDialog, QMessageBox, QTabWidget, QWidget, QApplication
)


class CrossConfigConverterDialog(QDialog):
    """Dialog to convert and transfer configurations across OpenCode, OpenClaude, OMP v1, Claude Desktop, and Cursor."""

    def __init__(self, parent=None, app_context=None):
        super().__init__(parent)
        self.setWindowTitle("🔄 Universal AI Config Converter & Importer/Exporter")
        self.setMinimumSize(920, 620)
        self.app_context = app_context
        self.source_data: Dict[str, Any] = {}
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
            if self.app_context and hasattr(self.app_context, "cf"):
                # Layered config file
                cf = self.app_context.cf
                combined = {
                    "settings": cf.effective(),
                    "global": cf.global_data,
                    "project_mcp": cf.project_mcp,
                }
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
            self.out_editor.clear()
            return
        try:
            self.source_data = loads_jsonc(text)
            self._run_conversion()
        except Exception:
            self.out_editor.setPlainText("// Invalid JSON input in source editor")

    def _get_selected_components(self) -> List[str]:
        return [k for k, chk in self.comp_checks.items() if chk.isChecked()]

    def _run_conversion(self):
        if not self.source_data:
            self.out_editor.clear()
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
            self.converted_data = omp_bundle
        elif target_fmt == "claude_desktop":
            mcp_data = import_from_omp(omp_bundle, "openclaude_global", comps)
            self.converted_data = {"mcpServers": mcp_data.get("mcpServers", {})}
        else:
            self.converted_data = import_from_omp(omp_bundle, target_fmt, comps)

        self.out_editor.setPlainText(json.dumps(self.converted_data, indent=2, ensure_ascii=False))

    def _copy_result(self):
        text = self.out_editor.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            QMessageBox.information(self, "Copied", "Converted configuration copied to clipboard.")

    def _save_to_file(self):
        target_fmt = self.tgt_format_combo.currentData()
        default_name = f"{target_fmt}-config.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Converted Config", default_name,
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            Path(path).write_text(self.out_editor.toPlainText(), encoding="utf-8")
            QMessageBox.information(self, "Saved", f"Exported successfully to {path}")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save file: {e}")

    def _apply_to_active(self):
        if not self.converted_data:
            QMessageBox.warning(self, "No Data", "No converted data to apply.")
            return

        if not self.app_context:
            QMessageBox.warning(self, "Error", "No active editor instance found.")
            return

        target_fmt = self.tgt_format_combo.currentData()

        if target_fmt == "opencode" and getattr(self.app_context, "cfg", None):
            if not _confirm(self, "Apply Config", "Merge converted settings into current OpenCode configuration?"):
                return
            self.app_context.snapshot_state()
            for k, v in self.converted_data.items():
                if isinstance(v, dict) and isinstance(self.app_context.cfg.data.get(k), dict):
                    self.app_context.cfg.data[k].update(v)
                else:
                    self.app_context.cfg.data[k] = v
            self.app_context.mark_dirty()
            if hasattr(self.app_context, "refresh_all_tabs"):
                self.app_context.refresh_all_tabs()
            QMessageBox.information(self, "Success", "Applied converted settings to OpenCode configuration.")
            self.accept()

        elif "openclaude" in target_fmt and hasattr(self.app_context, "cf"):
            if not _confirm(self, "Apply Config", "Apply converted settings into current OpenClaude configuration?"):
                return
            cf = self.app_context.cf
            if target_fmt == "openclaude_global":
                for k, v in self.converted_data.items():
                    if isinstance(v, dict) and isinstance(cf.global_data.get(k), dict):
                        cf.global_data[k].update(v)
                    else:
                        cf.global_data[k] = v
                cf.save_global(cf.global_data)
            elif target_fmt == "openclaude_settings":
                user_layer = cf.layers.get("user", {})
                for k, v in self.converted_data.items():
                    if isinstance(v, dict) and isinstance(user_layer.get(k), dict):
                        user_layer[k].update(v)
                    else:
                        user_layer[k] = v
                cf.save_layer("user", user_layer)
            QMessageBox.information(self, "Success", "Applied converted settings to OpenClaude configuration.")
            self.accept()
        else:
            QMessageBox.information(self, "Format Mismatch", f"Please export to file or copy result to use with {target_fmt}.")
