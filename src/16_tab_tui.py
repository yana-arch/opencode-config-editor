# TUI tab
class TuiPluginEditor(QWidget):
    """Manage the tui.json `plugin` list + `plugin_enabled` state map.

    The `plugin` list entries may be plain strings or `[name, {opts}]` tuples;
    tuple-form options are preserved verbatim. A plugin is disabled by setting
    `plugin_enabled[name] = false` (it stays in the `plugin` list, so the
    disabled state is remembered and can be re-enabled — mirroring the
    settings.json PluginsTab behaviour).
    """

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.cbs = {}
        self.state_store = TuiPluginStateStore()
        self._entry_map = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search plugins...")
        self.search_edit.textChanged.connect(self._filter)
        top.addWidget(self.search_edit)
        for text, slot in [("+ Add", self._add), ("Remove", self._remove),
                           ("Enable All", lambda: self._set_all(True)),
                           ("Disable All", lambda: self._set_all(False))]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            top.addWidget(b)
        lay.addLayout(top)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Enabled", "Plugin", "Options"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        lay.addWidget(self.table)

        self.status = QLabel("Disabled plugins stay enabled/disabled via the editor cache "
                             "(no new attribute is written into tui.json).")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: gray;")
        lay.addWidget(self.status)

    @staticmethod
    def _name_of(entry):
        if isinstance(entry, str):
            return entry
        if isinstance(entry, list) and entry and isinstance(entry[0], str):
            return entry[0]
        return ""

    @staticmethod
    def _opts_of(entry):
        if isinstance(entry, list) and len(entry) >= 2 and isinstance(entry[1], dict):
            return entry[1]
        return None

    @property
    def _data(self):
        return self.app.cfg_tui.data if self.app.cfg_tui else {}

    def _entries(self):
        plugin = self._data.get("plugin", [])
        return plugin if isinstance(plugin, list) else []

    def _cfg_path(self):
        return self.app.cfg_tui.path if self.app.cfg_tui else None

    def _active_names(self):
        return {self._name_of(e) for e in self._entries()}

    def _is_enabled(self, name):
        return name in self._active_names()

    def _migrate_file_flag(self):
        data = self._data
        path = self._cfg_path()
        if path is None or not isinstance(data.get("plugin_enabled"), dict):
            return
        flagged = {n for n, v in data["plugin_enabled"].items() if v is False}
        plugin = data.get("plugin", [])
        if flagged:
            kept = []
            for entry in plugin:
                name = self._name_of(entry)
                if name in flagged:
                    self.state_store.set_entry(path, name, entry)
                else:
                    kept.append(entry)
            if kept:
                data["plugin"] = kept
            else:
                data.pop("plugin", None)
        data.pop("plugin_enabled", None)

    def _display_entries(self):
        path = self._cfg_path()
        store = self.state_store.get_entries(path) if path else {}
        active = list(self._entries())
        active_names = {self._name_of(e) for e in active}
        for name in sorted(store.keys()):
            if name not in active_names:
                active.append(store[name])
        return active

    def refresh(self):
        self._migrate_file_flag()
        path = self._cfg_path()
        if path is not None:
            active_names = self._active_names()
            stale = [n for n in self.state_store.get_entries(path) if n in active_names]
            if stale:
                self.state_store.clear(path, stale)
        self._update_table(self._display_entries())

    def _filter(self, text):
        if not text:
            self.refresh()
            return
        text = text.lower()
        entries = [e for e in self._display_entries() if text in self._name_of(e).lower()]
        self._update_table(entries)

    def _update_table(self, entries):
        self.table.blockSignals(True)
        self.table.setRowCount(len(entries))
        self.cbs = {}
        self._entry_map = {}
        for row, entry in enumerate(entries):
            name = self._name_of(entry)
            opts = self._opts_of(entry)
            self._entry_map[name] = entry

            cb = QCheckBox()
            cb.setChecked(self._is_enabled(name))
            cb.stateChanged.connect(lambda _, n=name: self._toggle(n))
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setAlignment(Qt.AlignCenter)
            cl.addWidget(cb)
            self.table.setCellWidget(row, 0, cell)
            self.cbs[name] = cb

            self.table.setItem(row, 1, QTableWidgetItem(name))
            self.table.setItem(row, 2, QTableWidgetItem(
                "(custom options)" if opts is not None else ""))
        self.table.blockSignals(False)
        self._update_status()

    def _update_status(self):
        n = self.table.rowCount()
        en = sum(1 for cb in self.cbs.values() if cb.isChecked())
        self.status.setText(f"{n} plugins ({en} enabled)")

    def _toggle(self, name: str):
        path = self._cfg_path()
        if path is None:
            return
        self.app.snapshot_state("tui")
        entry = self._entry_map.get(name, name)
        if self.cbs[name].isChecked():
            plugin = self._data.setdefault("plugin", [])
            if not isinstance(plugin, list):
                plugin = self._data["plugin"] = []
            if all(self._name_of(e) != name for e in plugin):
                plugin.append(entry)
            self.state_store.remove_entry(path, name)
        else:
            plugin = [e for e in self._data.get("plugin", []) if self._name_of(e) != name]
            if plugin:
                self._data["plugin"] = plugin
            else:
                self._data.pop("plugin", None)
            self.state_store.set_entry(path, name, entry)
        self.app.mark_dirty("tui")
        self._update_status()

    def _set_all(self, enabled: bool):
        path = self._cfg_path()
        if path is None:
            return
        self.app.snapshot_state("tui")
        if enabled:
            store = self.state_store.get_entries(path)
            plugin = self._data.setdefault("plugin", [])
            if not isinstance(plugin, list):
                plugin = self._data["plugin"] = []
            active_names = {self._name_of(e) for e in plugin}
            for name, entry in store.items():
                if name not in active_names:
                    plugin.append(entry)
            self.state_store.clear(path)
        else:
            for entry in self._data.get("plugin", []):
                name = self._name_of(entry)
                if name:
                    self.state_store.set_entry(path, name, entry)
            self._data.pop("plugin", None)
        for cb in self.cbs.values():
            cb.blockSignals(True)
            cb.setChecked(enabled)
            cb.blockSignals(False)
        self.app.mark_dirty("tui")
        self._update_status()

    def _add(self):
        name, ok = QInputDialog.getText(self, "Add Plugin", "Plugin (npm spec):",
                                        QLineEdit.Normal, "@opencode/plugin-example")
        if not ok or not name.strip():
            return
        name = name.strip()
        all_names = {self._name_of(e) for e in self._display_entries()}
        if name in all_names:
            QMessageBox.warning(self, "Error", f"Plugin '{name}' already exists")
            return
        self.app.snapshot_state("tui")
        path = self._cfg_path()
        if path is not None:
            self.state_store.remove_entry(path, name)
        plugin = self._data.setdefault("plugin", [])
        if not isinstance(plugin, list):
            plugin = self._data["plugin"] = []
        plugin.append(name)
        self.app.mark_dirty("tui")
        self.refresh()

    def _remove(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "Remove", "Select plugins to remove first.")
            return
        if not _confirm(self, "Remove Plugins", f"Remove {len(rows)} selected plugins?"):
            return
        self.app.snapshot_state("tui")
        names = {self.table.item(r, 1).text() if self.table.item(r, 1) else "" for r in rows}
        plugin = [e for e in self._data.get("plugin", []) if self._name_of(e) not in names]
        if plugin:
            self._data["plugin"] = plugin
        else:
            self._data.pop("plugin", None)
        path = self._cfg_path()
        if path is not None:
            self.state_store.clear(path, names)
        self.app.mark_dirty("tui")
        self.refresh()

    def collect(self, data):
        data.pop("plugin_enabled", None)


class TuiTab(QWidget):
    """Editor for the tui.json schema."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._touched = set()
        form = QFormLayout(self)

        self.schema_edit = MaskedLineEdit("", field_name="schema")
        self.schema_edit.edit.editingFinished.connect(self._t("schema"))
        form.addRow("$schema", self.schema_edit)

        self.theme_edit = MaskedLineEdit("", field_name="theme")
        self.theme_edit.edit.editingFinished.connect(self._t("theme"))
        form.addRow("Theme", self.theme_edit)

        self.diff_combo = QComboBox()
        for x in ["", "auto", "stacked"]:
            self.diff_combo.addItem(x or "(auto)", x)
        self.diff_combo.currentIndexChanged.connect(self._t("diff"))
        form.addRow("Diff style", self.diff_combo)

        self.mouse = QCheckBox("Enable mouse capture")
        self.mouse.stateChanged.connect(self._t("mouse"))
        form.addRow("Mouse", self.mouse)

        self.scroll_speed = QDoubleSpinBox()
        self.scroll_speed.setRange(0.001, 1000)
        self.scroll_speed.setDecimals(3)
        self.scroll_speed.setValue(1.0)
        self.scroll_speed.valueChanged.connect(self._t("scroll"))
        form.addRow("Scroll speed", self.scroll_speed)

        self.scroll_acc = QCheckBox("Enable scroll acceleration")
        self.scroll_acc.stateChanged.connect(self._t("scroll"))
        form.addRow("Scroll acceleration", self.scroll_acc)

        self.cursor_style = QComboBox()
        for x in ["", "block", "underline", "line", "default"]:
            self.cursor_style.addItem(x or "(inherit)", x)
        self.cursor_style.currentIndexChanged.connect(self._t("cursor"))
        form.addRow("Cursor style", self.cursor_style)

        self.cursor_blink = QCheckBox("Blinking cursor")
        self.cursor_blink.stateChanged.connect(self._t("cursor"))
        form.addRow("Cursor blinking", self.cursor_blink)

        self.leader_timeout = QSpinBox()
        self.leader_timeout.setRange(0, 10**6)
        self.leader_timeout.setSpecialValueText("(unset)")
        self.leader_timeout.valueChanged.connect(self._t("leader"))
        form.addRow("Leader timeout (ms)", self.leader_timeout)

        att = QGroupBox("Attention")
        aform = QFormLayout(att)
        self.att_enabled = QCheckBox("Enabled")
        self.att_enabled.stateChanged.connect(self._t("attention"))
        aform.addRow("Enabled", self.att_enabled)
        self.att_notif = QCheckBox("Notifications")
        self.att_notif.stateChanged.connect(self._t("attention"))
        aform.addRow("Notifications", self.att_notif)
        self.att_sound = QCheckBox("Sound")
        self.att_sound.stateChanged.connect(self._t("attention"))
        aform.addRow("Sound", self.att_sound)
        self.att_volume = QDoubleSpinBox()
        self.att_volume.setRange(0, 1)
        self.att_volume.setDecimals(2)
        self.att_volume.setValue(0.4)
        self.att_volume.valueChanged.connect(self._t("attention"))
        aform.addRow("Volume", self.att_volume)
        form.addRow(att)

        self.prompt_h = QSpinBox()
        self.prompt_h.setRange(0, 10**6)
        self.prompt_h.setSpecialValueText("(unset)")
        self.prompt_h.valueChanged.connect(self._t("prompt"))
        form.addRow("Prompt max height", self.prompt_h)

        self.prompt_w = QSpinBox()
        self.prompt_w.setRange(0, 10**6)
        self.prompt_w.setSpecialValueText("(auto)")
        self.prompt_w.valueChanged.connect(self._t("prompt"))
        form.addRow("Prompt max width", self.prompt_w)

        self.plugins = TuiPluginEditor(app)
        form.addRow("Plugins", self.plugins)

        info = QLabel("The `keybinds` map is edited in the Raw JSON tab.")
        info.setWordWrap(True)
        form.addRow(info)

    def _t(self, group):
        def _h(*_):
            self._touched.add(group)
            self.app.mark_dirty("tui")
        return _h

    def _set_checked(self, cb, val):
        cb.blockSignals(True)
        cb.setChecked(bool(val))
        cb.blockSignals(False)

    def _set_combo(self, combo, val, fallback):
        combo.blockSignals(True)
        idx = combo.findData(val)
        combo.setCurrentIndex(idx if idx >= 0 else fallback)
        combo.blockSignals(False)

    def _set_spin(self, spin, val):
        spin.blockSignals(True)
        spin.setValue(int(val) if isinstance(val, int) and not isinstance(val, bool) else 0)
        spin.blockSignals(False)

    def _set_double(self, spin, val):
        spin.blockSignals(True)
        spin.setValue(float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else spin.minimum())
        spin.blockSignals(False)

    def _put(self, d, k, val, empty):
        if val != empty:
            d[k] = val
        else:
            d.pop(k, None)

    def refresh(self):
        data = self.app.cfg_tui.data if self.app.cfg_tui else {}
        self.schema_edit.set_value(data.get("$schema", ""))
        self.theme_edit.set_value(data.get("theme", ""))
        self._set_combo(self.diff_combo, data.get("diff_style", ""), 0)
        self._set_checked(self.mouse, data.get("mouse", True))
        self._set_double(self.scroll_speed, data.get("scroll_speed", 1.0))
        acc = data.get("scroll_acceleration") if isinstance(data.get("scroll_acceleration"), dict) else {}
        self._set_checked(self.scroll_acc, acc.get("enabled", False))
        cursor = data.get("cursor") if isinstance(data.get("cursor"), dict) else {}
        self._set_combo(self.cursor_style, cursor.get("style", ""), 0)
        self._set_checked(self.cursor_blink, cursor.get("blinking", False))
        self._set_spin(self.leader_timeout, data.get("leader_timeout"))
        att = data.get("attention") if isinstance(data.get("attention"), dict) else {}
        self._set_checked(self.att_enabled, att.get("enabled", False))
        self._set_checked(self.att_notif, att.get("notifications", False))
        self._set_checked(self.att_sound, att.get("sound", False))
        self._set_double(self.att_volume, att.get("volume", 0.4))
        prompt = data.get("prompt") if isinstance(data.get("prompt"), dict) else {}
        self._set_spin(self.prompt_h, prompt.get("max_height"))
        self._set_spin(self.prompt_w, prompt.get("max_width"))
        self.plugins.refresh()

    def collect(self, data):
        if "schema" in self._touched:
            v = self.schema_edit.value()
            data["$schema"] = v if v else None
            if not v:
                data.pop("$schema", None)
        if "theme" in self._touched:
            self._put(data, "theme", self.theme_edit.value(), "")
        if "diff" in self._touched:
            self._put(data, "diff_style", self.diff_combo.currentData() or "", "")
        if "mouse" in self._touched:
            data["mouse"] = self.mouse.isChecked()
        if "scroll" in self._touched:
            self._put(data, "scroll_speed", self.scroll_speed.value(), 1.0)
            self._put(data, "scroll_acceleration",
                      {"enabled": self.scroll_acc.isChecked()} if self.scroll_acc.isChecked() else None, None)
        if "cursor" in self._touched:
            cursor = data.setdefault("cursor", {})
            self._put(cursor, "style", self.cursor_style.currentData() or "", "")
            self._put(cursor, "blinking", self.cursor_blink.isChecked(), False)
            if not cursor:
                data.pop("cursor", None)
        if "leader" in self._touched:
            self._put(data, "leader_timeout", self.leader_timeout.value() or None, None)
        if "attention" in self._touched:
            att = data.setdefault("attention", {})
            self._put(att, "enabled", self.att_enabled.isChecked(), False)
            self._put(att, "notifications", self.att_notif.isChecked(), False)
            self._put(att, "sound", self.att_sound.isChecked(), False)
            self._put(att, "volume", self.att_volume.value(), 0.4)
            if not att:
                data.pop("attention", None)
        if "prompt" in self._touched:
            prompt = data.setdefault("prompt", {})
            self._put(prompt, "max_height", self.prompt_h.value() or None, None)
            self._put(prompt, "max_width", self.prompt_w.value() or None, None)
            if not prompt:
                data.pop("prompt", None)
        self.plugins.collect(data)
        self._touched.clear()


