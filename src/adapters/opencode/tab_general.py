# General tab
class GeneralTab(QWidget):
    """Enhanced general tab with validation"""

    def __init__(self, app):
        super().__init__()
        self.app = app

        layout = QFormLayout(self)

        # Schema
        self.schema_edit = MaskedLineEdit("", field_name="schema")
        self.schema_edit.edit.editingFinished.connect(self.app.mark_dirty)
        layout.addRow("$schema", self.schema_edit)

        # Autoupdate: true | false | "notify"
        self.autoupdate_combo = QComboBox()
        for label, val in [("Off (false)", False), ("On (true)", True), ("Notify (\"notify\")", "notify")]:
            self.autoupdate_combo.addItem(label, val)
        self.autoupdate_combo.currentIndexChanged.connect(self.app.mark_dirty)
        layout.addRow("Autoupdate", self.autoupdate_combo)

        # Default model
        self.model_edit = MaskedLineEdit("", field_name="model")
        self.model_edit.edit.editingFinished.connect(self.app.mark_dirty)
        layout.addRow("Default Model", self.model_edit)

        # Small model
        self.small_model_edit = MaskedLineEdit("", field_name="small_model")
        self.small_model_edit.edit.editingFinished.connect(self.app.mark_dirty)
        layout.addRow("Small Model", self.small_model_edit)

        # Default agent
        self.default_agent_edit = MaskedLineEdit("", field_name="default_agent")
        self.default_agent_edit.edit.editingFinished.connect(self.app.mark_dirty)
        layout.addRow("Default Agent", self.default_agent_edit)

        # Subagent depth
        self.subagent_depth = QSpinBox()
        self.subagent_depth.setRange(0, 100)
        self.subagent_depth.setSpecialValueText("(default)")
        self.subagent_depth.valueChanged.connect(self._depth_changed)
        layout.addRow("Subagent Depth", self.subagent_depth)
        self._depth_touched = False

        # Username
        self.username_edit = MaskedLineEdit("", field_name="username")
        self.username_edit.edit.editingFinished.connect(self.app.mark_dirty)
        layout.addRow("Username", self.username_edit)

        # Shell
        self.shell_edit = MaskedLineEdit("", field_name="shell")
        self.shell_edit.edit.editingFinished.connect(self.app.mark_dirty)
        layout.addRow("Shell", self.shell_edit)

        # Log level
        self.loglevel_combo = QComboBox()
        for label, val in [("(default)", ""), ("DEBUG", "DEBUG"), ("INFO", "INFO"),
                           ("WARN", "WARN"), ("ERROR", "ERROR")]:
            self.loglevel_combo.addItem(label, val)
        self.loglevel_combo.currentIndexChanged.connect(self.app.mark_dirty)
        layout.addRow("Log Level", self.loglevel_combo)

        # Share
        self.share_combo = QComboBox()
        for label, val in [("(default)", ""), ("true", "true"), ("false", "false")]:
            self.share_combo.addItem(label, val)
        self.share_combo.currentIndexChanged.connect(self.app.mark_dirty)
        layout.addRow("Share", self.share_combo)

        # Snapshot (experimental)
        self.snapshot_check = QCheckBox("Enable snapshot caching")
        self.snapshot_check.stateChanged.connect(self._snapshot_changed)
        layout.addRow("Snapshot", self.snapshot_check)
        self._snapshot_touched = False

        # Disabled providers
        self.disabled_providers = StringListEdit(app, ["disabled_providers"], "provider")
        layout.addRow("Disabled Providers", self.disabled_providers)

        # Enabled providers
        self.enabled_providers = StringListEdit(app, ["enabled_providers"], "provider")
        layout.addRow("Enabled Providers", self.enabled_providers)

        # Info
        info_label = QLabel(
            "Runtime, agents, commands, providers, MCP, plugins, permission and "
            "TUI settings have their own tabs. Remaining options are editable in "
            "the Raw JSON tab."
        )
        info_label.setWordWrap(True)
        layout.addRow(info_label)

    def _depth_changed(self):
        self._depth_touched = True
        self.app.mark_dirty()

    def _snapshot_changed(self):
        self._snapshot_touched = True
        self.app.mark_dirty()

    def refresh(self):
        """Refresh fields with current data (signals blocked so programmatic
        population does not mark the document dirty)."""
        data = self.app.cfg.data if self.app.cfg else {}
        self.schema_edit.set_value(data.get("$schema", ""))
        au = data.get("autoupdate")
        idx = 0 if au is False or au is None else (1 if au is True else 2)
        self.autoupdate_combo.blockSignals(True)
        self.autoupdate_combo.setCurrentIndex(idx)
        self.autoupdate_combo.blockSignals(False)
        self.model_edit.set_value(data.get("model", ""))
        self.small_model_edit.set_value(data.get("small_model", ""))
        self.default_agent_edit.set_value(data.get("default_agent", ""))
        self._depth_touched = False
        self.subagent_depth.blockSignals(True)
        self.subagent_depth.setValue(int(data["subagent_depth"]) if isinstance(data.get("subagent_depth"), int) else 0)
        self.subagent_depth.blockSignals(False)
        self.username_edit.set_value(data.get("username", ""))
        self.shell_edit.set_value(data.get("shell", ""))
        ll = data.get("logLevel", "")
        ll_idx = self.loglevel_combo.findData(ll)
        self.loglevel_combo.blockSignals(True)
        self.loglevel_combo.setCurrentIndex(ll_idx if ll_idx >= 0 else 0)
        self.loglevel_combo.blockSignals(False)
        sh = data.get("share")
        sh_idx = self.share_combo.findData("true" if sh is True else ("false" if sh is False else ""))
        self.share_combo.blockSignals(True)
        self.share_combo.setCurrentIndex(sh_idx if sh_idx >= 0 else 0)
        self.share_combo.blockSignals(False)
        self._snapshot_touched = False
        self.snapshot_check.blockSignals(True)
        self.snapshot_check.setChecked(bool(data.get("snapshot", False)))
        self.snapshot_check.blockSignals(False)
        self.disabled_providers.refresh()
        self.enabled_providers.refresh()

    def collect(self, data: dict):
        """Collect data from UI (struct-tab, so combos always round-trip)."""
        if self.schema_edit.value():
            data["$schema"] = self.schema_edit.value()

        au = self.autoupdate_combo.currentData()
        if au is False:
            data.pop("autoupdate", None)
        else:
            data["autoupdate"] = au

        for key, edit in [
            ("model", self.model_edit),
            ("small_model", self.small_model_edit),
            ("default_agent", self.default_agent_edit),
            ("username", self.username_edit),
            ("shell", self.shell_edit),
        ]:
            value = edit.value()
            if value:
                data[key] = value
            else:
                data.pop(key, None)

        if self._depth_touched:
            data["subagent_depth"] = self.subagent_depth.value()

        ll = self.loglevel_combo.currentData()
        if ll:
            data["logLevel"] = ll
        else:
            data.pop("logLevel", None)

        sh = self.share_combo.currentData()
        if sh == "true":
            data["share"] = True
        elif sh == "false":
            data["share"] = False
        else:
            data.pop("share", None)

        if self._snapshot_touched:
            if self.snapshot_check.isChecked():
                data["snapshot"] = True
            else:
                data.pop("snapshot", None)

        self.disabled_providers.collect(data)
        self.enabled_providers.collect(data)

