# MCP Template Hub GUI Dialog
# ---------------------------------------------------------------------------
import json
from typing import Dict, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QComboBox,
    QGroupBox, QTextEdit, QSplitter, QFileDialog, QMessageBox,
    QFormLayout, QWidget
)


class MCPTemplateHubDialog(QDialog):
    """Visual App Store / Hub for browsing and 1-click installing MCP Servers."""

    def __init__(self, parent=None, target_mode: str = "opencode"):
        super().__init__(parent)
        self.setWindowTitle("🧩 MCP Server Hub & Templates")
        self.setMinimumSize(860, 560)
        self.target_mode = target_mode  # "opencode" or "openclaude"
        self.selected_template: Optional[MCPTemplate] = None
        self.result_server_key: str = ""
        self.result_server_config: dict = {}

        layout = QVBoxLayout(self)

        # Header description
        info = QLabel(
            "Browse curated Model Context Protocol (MCP) servers and install them directly into your configuration."
        )
        info.setStyleSheet("color: #666; margin-bottom: 4px;")
        layout.addWidget(info)

        # Filter bar
        filter_bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search MCP servers...")
        self.search_edit.textChanged.connect(self._filter_templates)
        filter_bar.addWidget(self.search_edit, 2)

        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories")
        cats = sorted({t.category for t in MCP_REGISTRY})
        for c in cats:
            self.category_combo.addItem(c)
        self.category_combo.currentIndexChanged.connect(self._filter_templates)
        filter_bar.addWidget(self.category_combo, 1)

        layout.addLayout(filter_bar)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left: List of templates
        self.template_list = QListWidget()
        self.template_list.currentRowChanged.connect(self._on_template_selected)
        splitter.addWidget(self.template_list)

        # Right: Configurator & preview
        right_panel = QWidget()
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(0, 0, 0, 0)

        # Template Header / Description
        self.desc_group = QGroupBox("Server Info")
        desc_lay = QVBoxLayout(self.desc_group)
        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        desc_lay.addWidget(self.desc_label)
        right_lay.addWidget(self.desc_group)

        # Parameters Form
        self.param_group = QGroupBox("Configuration Parameters")
        self.param_form = QFormLayout(self.param_group)
        self.key_edit = QLineEdit()
        self.key_edit.textChanged.connect(self._update_preview)
        self.param_form.addRow("Server Key:", self.key_edit)

        self.param_widgets: Dict[str, QLineEdit] = {}
        self.env_widgets: Dict[str, QLineEdit] = {}
        self.url_edit: Optional[QLineEdit] = None

        right_lay.addWidget(self.param_group)

        # Preview box
        self.preview_group = QGroupBox(f"Configuration Preview ({target_mode.capitalize()})")
        prev_lay = QVBoxLayout(self.preview_group)
        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setMaximumHeight(140)
        prev_lay.addWidget(self.preview_edit)
        right_lay.addWidget(self.preview_group)

        splitter.addWidget(right_panel)
        splitter.setSizes([320, 540])
        layout.addWidget(splitter, 1)

        # Bottom buttons
        btns = QHBoxLayout()
        self.install_btn = QPushButton(f"✓ Install into {target_mode.capitalize()}")
        self.install_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.install_btn.clicked.connect(self._on_install)
        btns.addWidget(self.install_btn)

        btns.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        self._populate_list()
        if self.template_list.count() > 0:
            self.template_list.setCurrentRow(0)

    def _populate_list(self):
        self.template_list.clear()
        for tmpl in MCP_REGISTRY:
            item = QListWidgetItem(f"{tmpl.name} [{tmpl.category}]")
            item.setData(Qt.UserRole, tmpl.id)
            self.template_list.addItem(item)

    def _filter_templates(self):
        text = self.search_edit.text().strip().lower()
        cat = self.category_combo.currentText()

        self.template_list.clear()
        for tmpl in MCP_REGISTRY:
            if cat != "All Categories" and tmpl.category != cat:
                continue
            if text and (text not in tmpl.name.lower() and text not in tmpl.description.lower() and text not in tmpl.id.lower()):
                continue
            item = QListWidgetItem(f"{tmpl.name} [{tmpl.category}]")
            item.setData(Qt.UserRole, tmpl.id)
            self.template_list.addItem(item)

        if self.template_list.count() > 0:
            self.template_list.setCurrentRow(0)

    def _on_template_selected(self, row: int):
        if row < 0:
            return
        item = self.template_list.item(row)
        if not item:
            return
        tid = item.data(Qt.UserRole)
        tmpl = get_mcp_template(tid)
        if not tmpl:
            return

        self.selected_template = tmpl
        self.key_edit.setText(tmpl.id)

        # Update description
        doc_html = f"<br><a href='{tmpl.doc_url}'>Documentation</a>" if tmpl.doc_url else ""
        self.desc_label.setText(f"<b>{tmpl.name}</b> ({tmpl.category})<br>{tmpl.description}{doc_html}")

        # Clear and rebuild dynamic parameter form
        while self.param_form.rowCount() > 1:
            self.param_form.removeRow(1)

        self.param_widgets.clear()
        self.env_widgets.clear()

        if tmpl.transport_type == "remote":
            self.url_edit = QLineEdit(tmpl.url)
            self.url_edit.textChanged.connect(self._update_preview)
            self.param_form.addRow("Server URL:", self.url_edit)
        else:
            # Check for arguments like {allowed_directory} or {db_path}
            for part in tmpl.command:
                if "{" in part and "}" in part:
                    param_name = part[part.find("{") + 1 : part.find("}")]
                    p_edit = QLineEdit()
                    p_edit.textChanged.connect(self._update_preview)

                    # Add file / dir picker button if applicable
                    row_box = QHBoxLayout()
                    row_box.addWidget(p_edit, 1)
                    if "directory" in param_name or "path" in param_name or "repo" in param_name:
                        browse_btn = QPushButton("Browse...")
                        browse_btn.setFixedWidth(70)
                        browse_btn.clicked.connect(lambda _, pe=p_edit: self._browse_path(pe))
                        row_box.addWidget(browse_btn)

                    self.param_form.addRow(f"Arg ({param_name}):", row_box)
                    self.param_widgets[param_name] = p_edit

            # Env keys
            for k, placeholder in tmpl.env_keys.items():
                env_edit = QLineEdit()
                env_edit.setPlaceholderText(placeholder)
                env_edit.textChanged.connect(self._update_preview)
                self.param_form.addRow(f"Env ({k}):", env_edit)
                self.env_widgets[k] = env_edit

        self._update_preview()

    def _browse_path(self, target_edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if path:
            target_edit.setText(path)

    def _update_preview(self):
        if not self.selected_template:
            return

        key = self.key_edit.text().strip() or self.selected_template.id
        args_vals = {k: w.text().strip() for k, w in self.param_widgets.items()}
        env_vals = {k: w.text().strip() for k, w in self.env_widgets.items()}
        url_val = self.url_edit.text().strip() if self.url_edit else ""

        if self.target_mode == "openclaude":
            cfg = instantiate_openclaude_mcp(
                self.selected_template, key, args_vals, env_vals, url_val
            )
        else:
            cfg = instantiate_opencode_mcp(
                self.selected_template, key, args_vals, env_vals, url_val
            )

        self.result_server_key = key
        self.result_server_config = cfg
        self.preview_edit.setPlainText(json.dumps({key: cfg}, indent=2, ensure_ascii=False))

    def _on_install(self):
        if not self.result_server_key:
            QMessageBox.warning(self, "Error", "Server key cannot be empty.")
            return
        self.accept()
