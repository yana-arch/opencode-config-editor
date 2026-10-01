# Shared GUI components and generic import dialogs
# GUI Components
def _esc_html(s) -> str:
    return html.escape(str(s), quote=True)

class MaskedLineEdit(QWidget):
    """Line edit with optional masking for sensitive fields"""

    SECRET_HINT = re.compile(r"(key|token|secret|password|auth)", re.I)
    textChanged = Signal()          # emitted on any edit-text change

    def __init__(self, value="", parent=None, field_name="", placeholder="", secret=None):
        super().__init__(parent)
        self.field_name = field_name
        # secret=None infers from the field name; pass True/False to override
        # (e.g. env/headers cells whose VALUES may carry API keys).
        self.is_secret = bool(self.SECRET_HINT.search(field_name)) if secret is None else bool(secret)
        self._real_value = str(value) if value is not None else ""
        # What we last pushed into the line edit; lets _user_modified() tell an
        # untouched secret apart from a user edit without re-deriving the mask.
        self._rendered = ""
        self.toggle_btn = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self._rendered = self._display_value()
        self.edit.setText(self._rendered)
        # QLineEdit.textChanged carries a str, but our own textChanged is
        # declared arg-less, so it must NOT be used as the slot directly:
        # PySide6 raises "textChanged() only accepts 0 argument(s), 1 given!"
        # inside the emit and the signal never reaches downstream slots (the
        # dirty flag then stays False and the edit is silently dropped on save).
        self.edit.textChanged.connect(self._relay_text_changed)
        layout.addWidget(self.edit)

        if self.is_secret:
            self.toggle_btn = QPushButton("👁")
            self.toggle_btn.setCheckable(True)
            self.toggle_btn.setFixedWidth(30)
            self.toggle_btn.toggled.connect(self._toggle_visibility)
            layout.addWidget(self.toggle_btn)

    def _relay_text_changed(self, _text=""):
        """Re-emit QLineEdit's str-carrying textChanged as our arg-less one."""
        self.textChanged.emit()

    def _revealed(self) -> bool:
        return self.toggle_btn is not None and self.toggle_btn.isChecked()

    def _user_modified(self) -> bool:
        """True when the visible text differs from the last value rendering.

        Tracking the rendering explicitly (rather than recomputing it) is what
        makes toggling reliable: the eye state has already flipped by the time
        _toggle_visibility runs, so a recomputed display would compare the text
        against the wrong side of the toggle.
        """
        return self.edit.text() != self._rendered

    def _display_value(self) -> str:
        """Get display value (masked if secret)"""
        if not self.is_secret or self._revealed():
            return self._real_value
        return _mask(self._real_value)

    def _toggle_visibility(self, checked: bool):
        """Show/hide the secret without losing a typed edit in either direction.

        The eye state has already flipped when this runs, so _user_modified()
        compares against the *previous* rendering, and the text the user typed
        (masked or not) becomes the new value to protect.
        """
        if self._user_modified():
            self._real_value = self.edit.text()
        self._render()

    def _render(self):
        """Push the current value into the line edit for the current eye state."""
        self._rendered = self._display_value()
        self.edit.setText(self._rendered)

    def set_value(self, value):
        """Set value"""
        self._real_value = str(value) if value is not None else ""
        self._render()

    def value(self) -> str:
        """Get current value: the stored secret while the (untouched) display is
        still masked, otherwise what the user typed - masked edits included."""
        if self.is_secret and not self._revealed() and not self._user_modified():
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
            self.result_data = loads_jsonc(self.editor.toPlainText())
            self.accept()
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", str(e))
        except Exception as e:
            QMessageBox.warning(self, "Invalid Data", str(e))


class PluginOptionsDialog(QDialog):
    """Dialog to edit/view JSON options for a plugin."""

    def __init__(self, parent, plugin_name: str, options: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Plugin Options: {plugin_name}")
        self.resize(600, 420)
        self.result_options = None

        layout = QVBoxLayout(self)

        hint = QLabel(f"Configure custom options for <b>{_esc_html(plugin_name)}</b> in JSON format:")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Toolbar
        tb_layout = QHBoxLayout()
        format_btn = QPushButton("Format JSON")
        format_btn.clicked.connect(self._format_json)
        clear_btn = QPushButton("Clear Options")
        clear_btn.clicked.connect(self._clear_options)
        tb_layout.addWidget(format_btn)
        tb_layout.addWidget(clear_btn)
        tb_layout.addStretch()
        layout.addLayout(tb_layout)

        # Editor
        self.editor = QPlainTextEdit()
        font = QFont("Monospace")
        font.setStyleHint(QFont.Monospace)
        self.editor.setFont(font)
        self.highlighter = JSONHighlighter(self.editor.document())

        initial_text = json.dumps(options, indent=2, ensure_ascii=False) if options else "{\n  \n}"
        self.editor.setPlainText(initial_text)
        layout.addWidget(self.editor)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _format_json(self):
        text = self.editor.toPlainText().strip()
        if not text:
            return
        try:
            parsed = loads_jsonc(text)
            self.editor.setPlainText(json.dumps(parsed, indent=2, ensure_ascii=False))
        except Exception as e:
            QMessageBox.warning(self, "Invalid JSON", f"Cannot format invalid JSON: {e}")

    def _clear_options(self):
        self.editor.setPlainText("")

    def _accept(self):
        text = self.editor.toPlainText().strip()
        if not text or text == "{}":
            self.result_options = None
            self.accept()
            return

        try:
            parsed = loads_jsonc(text)
            if not isinstance(parsed, dict):
                QMessageBox.warning(self, "Invalid Type", "Plugin options must be a JSON object ({...}) or empty.")
                return
            self.result_options = parsed if parsed else None
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Invalid JSON", f"Error parsing JSON options: {e}")


class AddPluginDialog(QDialog):
    """Dialog to add a new plugin with name and optional initial options."""

    def __init__(self, parent, default_name: str = "@opencode/plugin-example"):
        super().__init__(parent)
        self.setWindowTitle("Add Plugin")
        self.resize(550, 380)
        self.plugin_name = ""
        self.plugin_options = None

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Plugin specifier (npm package or local path):"))
        self.name_edit = QLineEdit(default_name)
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("Options (JSON object, optional):"))
        self.options_edit = QPlainTextEdit()
        font = QFont("Monospace")
        font.setStyleHint(QFont.Monospace)
        self.options_edit.setFont(font)
        self.options_edit.setPlaceholderText('{\n  "key": "value"\n}')
        self.highlighter = JSONHighlighter(self.options_edit.document())
        layout.addWidget(self.options_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Plugin specifier cannot be empty.")
            return

        opts_text = self.options_edit.toPlainText().strip()
        opts = None
        if opts_text and opts_text != "{}":
            try:
                parsed = loads_jsonc(opts_text)
                if not isinstance(parsed, dict):
                    QMessageBox.warning(self, "Invalid Options", "Options must be a JSON object ({...}).")
                    return
                opts = parsed
            except Exception as e:
                QMessageBox.warning(self, "Invalid JSON", f"Error parsing options JSON: {e}")
                return

        self.plugin_name = name
        self.plugin_options = opts
        self.accept()


