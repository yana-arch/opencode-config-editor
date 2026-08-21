class MainWindow(QMainWindow):
    """Enhanced main window with undo/redo, themes, and better UX"""

    def __init__(self, cwd: Path, adapter=None):
        super().__init__()
        self.cwd = Path(cwd)
        self.adapter = adapter or default_adapter()
        self.cfg_oc = None
        self.cfg_tui = None
        self.validator = Validator()
        self.model_catalog = ModelCatalog()
        self.undo_oc = UndoManager()
        self.undo_tui = UndoManager()
        self.settings = SettingsManager()
        self.theme_manager = None
        self.dirty_oc = False
        self.dirty_tui = False
        self.recent_files = []
        self._snap_oc = False
        self._snap_tui = False
        self.mode = None
        self.project_path = None
        self._raw_kind = "opencode"

        self._restore_window_state()

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1200, 800)

        self._setup_theme()

        self._build_tabs()
        self._setup_recent_files()
        self._build_menu()
        self._build_toolbar()
        self._build_status_bar()

        self._load_global()

    def _setup_theme(self):
        """Setup application theme"""
        self.theme_manager = ThemeManager(QApplication.instance())
        self._apply_theme()

    def _apply_theme(self):
        """Apply current theme"""
        theme = self.settings.get_theme()
        if theme == "dark":
            self.setStyleSheet("""
                QToolTip {
                    background-color: #353535;
                    color: white;
                    border: 1px solid #555555;
                }
            """)
        else:
            self.setStyleSheet("")

    def _restore_window_state(self):
        """Restore window geometry and state"""
        geometry = self.settings.get_window_geometry()
        if geometry:
            self.restoreGeometry(geometry)

        state = self.settings.get_window_state()
        if state:
            self.restoreState(state)

    def _save_window_state(self):
        """Save window geometry and state"""
        self.settings.set_window_geometry(self.saveGeometry())
        self.settings.set_window_state(self.saveState())

    def _build_menu(self):
        """Build application menu"""
        mb = self.menuBar()

        # File menu
        mfile = mb.addMenu("&File")

        self.act_open = QAction("&Open...", self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(self._browse)
        mfile.addAction(self.act_open)

        self.act_recent = mfile.addMenu("Open &Recent")
        self._update_recent_files_menu()

        self.act_save = QAction("&Save", self)
        self.act_save.setShortcut(QKeySequence.Save)
        self.act_save.triggered.connect(self._save)
        mfile.addAction(self.act_save)

        self.act_save_as = QAction("Save &As...", self)
        self.act_save_as.triggered.connect(self._save_as)
        mfile.addAction(self.act_save_as)

        self.act_export = QAction("&Export...", self)
        self.act_export.triggered.connect(self._export)
        mfile.addAction(self.act_export)

        mfile.addSeparator()

        self.act_reload = QAction("&Reload", self)
        self.act_reload.setShortcut(QKeySequence.Refresh)
        self.act_reload.triggered.connect(self._reload)
        mfile.addAction(self.act_reload)

        mfile.addSeparator()

        self.act_close = QAction("&Close", self)
        self.act_close.setShortcut(QKeySequence.Close)
        self.act_close.triggered.connect(self.close)
        mfile.addAction(self.act_close)

        # Edit menu
        medit = mb.addMenu("&Edit")

        self.act_undo = QAction("&Undo", self)
        self.act_undo.setShortcut(QKeySequence.Undo)
        self.act_undo.triggered.connect(self._undo)
        self.act_undo.setEnabled(False)
        medit.addAction(self.act_undo)

        self.act_redo = QAction("&Redo", self)
        self.act_redo.setShortcut(QKeySequence.Redo)
        self.act_redo.triggered.connect(self._redo)
        self.act_redo.setEnabled(False)
        medit.addAction(self.act_redo)

        medit.addSeparator()

        self.act_cut = QAction("Cu&t", self)
        self.act_cut.setShortcut(QKeySequence.Cut)
        self.act_cut.triggered.connect(self._cut)
        medit.addAction(self.act_cut)

        self.act_copy = QAction("&Copy", self)
        self.act_copy.setShortcut(QKeySequence.Copy)
        self.act_copy.triggered.connect(self._copy)
        medit.addAction(self.act_copy)

        self.act_paste = QAction("&Paste", self)
        self.act_paste.setShortcut(QKeySequence.Paste)
        self.act_paste.triggered.connect(self._paste)
        medit.addAction(self.act_paste)

        self.act_select_all = QAction("Select &All", self)
        self.act_select_all.setShortcut(QKeySequence.SelectAll)
        self.act_select_all.triggered.connect(self._select_all)
        medit.addAction(self.act_select_all)

        # Tools menu
        mtools = mb.addMenu("&Tools")

        self.act_catalog = QAction("Load Model &Catalog...", self)
        self.act_catalog.triggered.connect(self.load_model_catalog)
        mtools.addAction(self.act_catalog)

        self.act_browse_catalog = QAction("&Browse Model Catalog...", self)
        self.act_browse_catalog.triggered.connect(self._browse_model_catalog)
        mtools.addAction(self.act_browse_catalog)

        self.act_apply_catalog = QAction("&Match & Format Models from Catalog...", self)
        self.act_apply_catalog.triggered.connect(self._apply_model_catalog)
        mtools.addAction(self.act_apply_catalog)

        mtools.addSeparator()

        self.act_imp_provider = QAction("Import &Providers...", self)
        self.act_imp_provider.triggered.connect(self.tab_providers._import_providers)
        mtools.addAction(self.act_imp_provider)

        self.act_imp_mcp = QAction("Import &MCP Servers...", self)
        self.act_imp_mcp.triggered.connect(self.tab_mcp._import_servers)
        mtools.addAction(self.act_imp_mcp)

        self.act_imp_plugin = QAction("Import &Plugins...", self)
        self.act_imp_plugin.triggered.connect(self.tab_plugins._import_plugins)
        mtools.addAction(self.act_imp_plugin)

        # View menu
        mview = mb.addMenu("&View")

        self.act_toggle_theme = QAction("Toggle &Theme", self)
        self.act_toggle_theme.setShortcut("Ctrl+T")
        self.act_toggle_theme.triggered.connect(self._toggle_theme)
        mview.addAction(self.act_toggle_theme)

        self.act_increase_font = QAction("&Increase Font Size", self)
        self.act_increase_font.setShortcut("Ctrl++")
        self.act_increase_font.triggered.connect(self._increase_font_size)
        mview.addAction(self.act_increase_font)

        self.act_decrease_font = QAction("&Decrease Font Size", self)
        self.act_decrease_font.setShortcut("Ctrl+-")
        self.act_decrease_font.triggered.connect(self._decrease_font_size)
        mview.addAction(self.act_decrease_font)

        # Help menu
        mhelp = mb.addMenu("&Help")

        self.act_about = QAction("&About", self)
        self.act_about.triggered.connect(self._show_about)
        mhelp.addAction(self.act_about)

        self.act_about_qt = QAction("About &Qt", self)
        self.act_about_qt.triggered.connect(QApplication.aboutQt)
        mhelp.addAction(self.act_about_qt)

    def _build_toolbar(self):
        """Build application toolbar"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addWidget(QLabel(" Mode: "))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Global")
        self.mode_combo.addItem("Local project…")
        self.mode_combo.setMinimumWidth(180)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        toolbar.addWidget(self.mode_combo)

        self.project_btn = QPushButton("Browse…")
        self.project_btn.clicked.connect(self._browse_project)
        toolbar.addWidget(self.project_btn)
        self.project_label = QLabel("(no project)")
        self.project_label.setStyleSheet("color: gray;")
        toolbar.addWidget(self.project_label)

        toolbar.addSeparator()

        for action in [self.act_save, self.act_reload, self.act_undo, self.act_redo]:
            toolbar.addAction(action)

        toolbar.addSeparator()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search...")
        self.search_edit.setMaximumWidth(200)
        self.search_edit.textChanged.connect(self._search)
        toolbar.addWidget(self.search_edit)

    def _build_tabs(self):
        """Build main tabs from the active adapter."""
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setMovable(True)

        for tab, title, _kind in self.adapter.make_tabs(self):
            self.tabs.addTab(tab, title)

        self.setCentralWidget(self.tabs)

    def _build_status_bar(self):
        """Build status bar"""
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready")

        # Add permanent widgets
        self.catalog_status = QLabel()
        self.status_bar.addPermanentWidget(self.catalog_status)
        self._update_catalog_status()

    def _setup_recent_files(self):
        """Setup recent files menu"""
        self.recent_files = self.settings.get_recent_files()

    def _update_recent_files_menu(self):
        """Update recent files menu"""
        if not hasattr(self, "act_recent"):
            return
        self.act_recent.clear()
        for path in self.recent_files:
            action = QAction(path, self)
            action.triggered.connect(lambda _, p=path: self._open_recent(Path(p)))
            self.act_recent.addAction(action)

        self.act_recent.setEnabled(bool(self.recent_files))

    def _on_mode_changed(self, idx: int):
        if idx == 0:
            self._load_global()
        elif idx == 1:
            if self.project_path is None:
                self._browse_project()
            else:
                self._load_local(self.project_path)

    def _browse_project(self):
        start = self.project_path or self.cwd or Path.home()
        path = QFileDialog.getExistingDirectory(
            self, "Select Project Folder", str(start))
        if path:
            self.project_path = Path(path)
            self.project_label.setText(str(self.project_path))
            self._load_local(self.project_path)

    def _paths_for_mode(self, mode: str, project: Path = None) -> tuple:
        home = Path.home()
        if mode == "global":
            oc = home / ".config" / "opencode" / "opencode.json"
            tui = home / ".config" / "opencode" / "tui.json"
        else:
            proj = project or self.cwd
            dot_oc = proj / ".opencode"
            oc = (dot_oc / "opencode.json") if (dot_oc / "opencode.json").exists() else (proj / "opencode.json")
            tui = (dot_oc / "tui.json") if (dot_oc / "tui.json").exists() else (proj / "tui.json")
        return oc, tui

    def _load_global(self):
        self.mode = "global"
        self.project_label.setText("(global)")
        oc_path, tui_path = self._paths_for_mode("global")
        self._load_pair(oc_path, tui_path)

    def _load_local(self, project: Path):
        self.mode = "local"
        self.project_path = project
        oc_path, tui_path = self._paths_for_mode("local", project)
        self._load_pair(oc_path, tui_path)

    def _load_pair(self, oc_path: Path, tui_path: Path):
        if self.dirty_oc or self.dirty_tui:
            if not _confirm(self, "Unsaved Changes",
                            "You have unsaved changes. Discard and switch?"):
                self.mode_combo.blockSignals(True)
                self.mode_combo.setCurrentIndex(0 if self.mode == "global" else 1)
                self.mode_combo.blockSignals(False)
                return

        self.cfg_oc = ConfigFile(oc_path, "opencode")
        self.cfg_tui = ConfigFile(tui_path, "tui")
        self.cfg_oc.load()
        self.cfg_tui.load()

        self.dirty_oc = False
        self.dirty_tui = False
        self._snap_oc = False
        self._snap_tui = False
        self.undo_oc = UndoManager()
        self.undo_tui = UndoManager()

        oc_exists = oc_path.exists()
        tui_exists = tui_path.exists()
        self.status_bar.showMessage(
            f"opencode.json [{'✓' if oc_exists else '✗'}]  "
            f"tui.json [{'✓' if tui_exists else '✗'}]"
        )
        self.refresh_tabs()

    def _update_catalog_status(self):
        """Update model catalog status"""
        if self.model_catalog.loaded():
            self.catalog_status.setText(
                f"Catalog: {self.model_catalog.source} "
                f"({len(self.model_catalog.flat)} models)"
            )
        else:
            self.catalog_status.setText("No model catalog loaded")

    def _search(self, text: str):
        """Search across all tabs"""
        current_tab = self.tabs.currentWidget()

        if current_tab is self.tab_providers:
            self.tab_providers.search_edit.setText(text)
        elif current_tab is self.tab_mcp:
            self.tab_mcp.search_edit.setText(text)
        elif current_tab is self.tab_plugins:
            self.tab_plugins.search_edit.setText(text)
        elif current_tab is self.tab_permission:
            self.tab_permission.search_edit.setText(text)
        elif current_tab is self.tab_agents:
            self.tab_agents.search_edit.setText(text)
        elif current_tab is self.tab_commands:
            self.tab_commands.search_edit.setText(text)

    def _browse(self):
        """Browse for a single config file (loads it into the matching slot)"""
        start = self.cwd if self.cwd.exists() else Path.home()
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Config File", str(start),
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return
        kind = ConfigFile.kind_for(Path(path))
        if kind == "opencode":
            self.cfg_oc = ConfigFile(Path(path), kind)
            self.cfg_oc.load()
            self.dirty_oc = False
            self._snap_oc = False
            self.undo_oc = UndoManager()
        elif kind == "tui":
            self.cfg_tui = ConfigFile(Path(path), kind)
            self.cfg_tui.load()
            self.dirty_tui = False
            self._snap_tui = False
            self.undo_tui = UndoManager()
        else:
            QMessageBox.information(self, "Open", f"File kind '{kind}' opened as opencode.json")
            self.cfg_oc = ConfigFile(Path(path), "opencode")
            self.cfg_oc.load()
            self.dirty_oc = False
            self._snap_oc = False
            self.undo_oc = UndoManager()
        self.refresh_tabs()

    def refresh_tabs(self):
        """Refresh all tabs — opencode tabs from cfg_oc, tui tab from cfg_tui."""
        if self.cfg_oc:
            for tab in self._oc_tabs:
                tab.refresh()
        if self.cfg_tui:
            self.tab_tui.refresh()
        self.tab_raw.refresh()
        self.act_undo.setEnabled(self.undo_oc.can_undo() or self.undo_tui.can_undo())
        self.act_redo.setEnabled(self.undo_oc.can_redo() or self.undo_tui.can_redo())

    @property
    def cfg(self):
        return self.cfg_oc

    @property
    def dirty(self):
        return self.dirty_oc or self.dirty_tui

    def mark_dirty(self, kind="auto"):
        """Mark the given config (or the active-tab kind) as dirty."""
        k = kind
        if k == "auto":
            k = self._kind_of_active_tab()
        if k == "tui":
            if self.cfg_tui is not None and not self._snap_tui:
                self.undo_tui.push(copy.deepcopy(self.cfg_tui.data))
                self._snap_tui = True
            self.dirty_tui = True
        else:
            if self.cfg_oc is not None and not self._snap_oc:
                self.undo_oc.push(copy.deepcopy(self.cfg_oc.data))
                self._snap_oc = True
            self.dirty_oc = True
        self.status_bar.showMessage("Unsaved changes…")

    def _kind_of_active_tab(self):
        w = self.tabs.currentWidget()
        if w is self.tab_tui:
            return "tui"
        return "opencode"

    def _collect_oc(self) -> dict:
        if self.tab_raw._modified and self._raw_kind == "opencode":
            try:
                base = json.loads(self.tab_raw.editor.toPlainText())
                if isinstance(base, dict):
                    data = base
                else:
                    data = dict(self.cfg_oc.data) if isinstance(self.cfg_oc.data, dict) else {}
            except json.JSONDecodeError:
                data = dict(self.cfg_oc.data) if isinstance(self.cfg_oc.data, dict) else {}
        else:
            data = dict(self.cfg_oc.data) if isinstance(self.cfg_oc.data, dict) else {}
        for tab in self._oc_tabs:
            try:
                tab.collect(data)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"{type(tab).__name__}: {e}")
        return data

    def _collect_tui(self) -> dict:
        if self.tab_raw._modified and self._raw_kind == "tui":
            try:
                base = json.loads(self.tab_raw.editor.toPlainText())
                if isinstance(base, dict):
                    data = base
                else:
                    data = dict(self.cfg_tui.data) if isinstance(self.cfg_tui.data, dict) else {}
            except json.JSONDecodeError:
                data = dict(self.cfg_tui.data) if isinstance(self.cfg_tui.data, dict) else {}
        else:
            data = dict(self.cfg_tui.data) if isinstance(self.cfg_tui.data, dict) else {}
        self.tab_tui.collect(data)
        return data

    def validate(self, text: str, kind: str = "opencode") -> Tuple[bool, List[str], List[str]]:
        """Validate JSON text. Returns (hard_ok, hard_errors, schema_warnings)."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return False, [f"Line {e.lineno}: {e.msg}"], []
        known = self.adapter.known_keys_for(kind) if self.adapter else None
        return self.validator.validate(data, kind, known_keys=known)

    def _save_state(self, kind="auto"):
        k = kind
        if k == "auto":
            k = self._kind_of_active_tab()
        if k == "tui":
            if self.cfg_tui:
                self.undo_tui.push(copy.deepcopy(self.cfg_tui.data))
                self._snap_tui = True
        else:
            if self.cfg_oc:
                self.undo_oc.push(copy.deepcopy(self.cfg_oc.data))
                self._snap_oc = True

    def snapshot_state(self, kind="auto"):
        k = kind
        if k == "auto":
            k = self._kind_of_active_tab()
        if k == "tui":
            if self.cfg_tui is not None:
                self.undo_tui.push(copy.deepcopy(self.cfg_tui.data))
                self._snap_tui = True
        else:
            if self.cfg_oc is not None:
                self.undo_oc.push(copy.deepcopy(self.cfg_oc.data))
                self._snap_oc = True

    def _undo(self):
        w = self.tabs.currentWidget()
        if w is self.tab_tui:
            if self.cfg_tui and self.undo_tui.can_undo():
                state = self.undo_tui.undo(self.cfg_tui.data)
                if state is not None:
                    self.cfg_tui.data = state
                    self.dirty_tui = True
                    self._snap_tui = False
                    self.refresh_tabs()
                    self.status_bar.showMessage("Undo (tui)")
        else:
            if self.cfg_oc and self.undo_oc.can_undo():
                state = self.undo_oc.undo(self.cfg_oc.data)
                if state is not None:
                    self.cfg_oc.data = state
                    self.dirty_oc = True
                    self._snap_oc = False
                    self.refresh_tabs()
                    self.status_bar.showMessage("Undo (opencode)")

    def _redo(self):
        w = self.tabs.currentWidget()
        if w is self.tab_tui:
            if self.cfg_tui and self.undo_tui.can_redo():
                state = self.undo_tui.redo(self.cfg_tui.data)
                if state is not None:
                    self.cfg_tui.data = state
                    self.dirty_tui = True
                    self._snap_tui = False
                    self.refresh_tabs()
                    self.status_bar.showMessage("Redo (tui)")
        else:
            if self.cfg_oc and self.undo_oc.can_redo():
                state = self.undo_oc.redo(self.cfg_oc.data)
                if state is not None:
                    self.cfg_oc.data = state
                    self.dirty_oc = True
                    self._snap_oc = False
                    self.refresh_tabs()
                    self.status_bar.showMessage("Redo (opencode)")

    def _cut(self):
        """Cut text"""
        current_tab = self.tabs.currentWidget()
        if current_tab is self.tab_raw:
            self.tab_raw.editor.cut()

    def _copy(self):
        """Copy text"""
        current_tab = self.tabs.currentWidget()
        if current_tab is self.tab_raw:
            self.tab_raw.editor.copy()
        elif hasattr(current_tab, "table"):
            selected = current_tab.table.selectedItems()
            if selected:
                text = "\n".join(item.text() for item in selected)
                QApplication.clipboard().setText(text)

    def _paste(self):
        """Paste text"""
        current_tab = self.tabs.currentWidget()
        if current_tab is self.tab_raw:
            self.tab_raw.editor.paste()

    def _select_all(self):
        """Select all text"""
        current_tab = self.tabs.currentWidget()
        if current_tab is self.tab_raw:
            self.tab_raw.editor.selectAll()
        elif hasattr(current_tab, "table"):
            current_tab.table.selectAll()

    def _save(self):
        if self.cfg_oc is None and self.cfg_tui is None:
            QMessageBox.information(self, "Save", "No file is currently open")
            return

        oc_data = self._collect_oc() if self.cfg_oc else None
        tui_data = self._collect_tui() if self.cfg_tui else None

        for label, cfg, data, kind in [
            ("opencode.json", self.cfg_oc, oc_data, "opencode"),
            ("tui.json", self.cfg_tui, tui_data, "tui"),
        ]:
            if cfg is None or data is None:
                continue
            hard_ok, hard, warnings = self.validator.validate(data, kind)
            if not hard_ok and not _confirm(
                self, f"Validation: {label}",
                "\n".join(hard[:10]) + "\n\nSave anyway?"
            ):
                return

        if self.cfg_oc and oc_data is not None:
            self._save_state("opencode")
            ok, msg = self.cfg_oc.save(oc_data)
            if ok:
                self.dirty_oc = False
                self._snap_oc = False
                self.status_bar.showMessage(f"opencode.json: {msg}")
            else:
                QMessageBox.critical(self, "Save Error (opencode.json)", msg)
                return

        if self.cfg_tui and tui_data is not None:
            self._save_state("tui")
            ok, msg = self.cfg_tui.save(tui_data)
            if ok:
                self.dirty_tui = False
                self._snap_tui = False
                self.status_bar.showMessage(f"tui.json: {msg}")
            else:
                QMessageBox.critical(self, "Save Error (tui.json)", msg)
                return

        self.refresh_tabs()

    def _save_as(self):
        if self.cfg_oc is None and self.cfg_tui is None:
            QMessageBox.information(self, "Save As", "No file is currently open")
            return

        for label, cfg, kind in [("opencode.json", self.cfg_oc, "opencode"),
                                 ("tui.json", self.cfg_tui, "tui")]:
            if cfg is None:
                continue
            path, _ = QFileDialog.getSaveFileName(
                self, f"Save {label} As…", str(cfg.path),
                "JSON files (*.json);;All files (*)"
            )
            if not path:
                continue
            new_cfg = ConfigFile(Path(path), kind)
            data = self._collect_oc() if kind == "opencode" else self._collect_tui()
            ok, msg = new_cfg.save(data)
            if ok:
                if kind == "opencode":
                    self.cfg_oc = new_cfg
                    self.dirty_oc = False
                    self._snap_oc = False
                else:
                    self.cfg_tui = new_cfg
                    self.dirty_tui = False
                    self._snap_tui = False
                self.settings.add_recent_file(str(path))
                self._update_recent_files_menu()
            else:
                QMessageBox.critical(self, f"Save As Error ({label})", msg)
        self.refresh_tabs()

    def _export(self):
        if self.cfg_oc is None and self.cfg_tui is None:
            QMessageBox.information(self, "Export", "No file is currently open")
            return
        for label, cfg in [("opencode", self.cfg_oc), ("tui", self.cfg_tui)]:
            if cfg is None:
                continue
            path, _ = QFileDialog.getSaveFileName(
                self, f"Export {label}", f"{label}-export.json",
                "JSON files (*.json);;All files (*)"
            )
            if not path:
                continue
            ok, msg = cfg.export(Path(path))
            if ok:
                QMessageBox.information(self, "Export Complete", msg)
            else:
                QMessageBox.warning(self, "Export Error", msg)

    def _reload(self):
        if self.cfg_oc is None and self.cfg_tui is None:
            return
        if (self.dirty_oc or self.dirty_tui) and not _confirm(
            self, "Reload", "Discard unsaved changes and reload?"
        ):
            return
        if self.cfg_oc and not self.cfg_oc.load():
            QMessageBox.warning(self, "Reload Error", self.cfg_oc.error or "Failed to reload opencode.json")
        if self.cfg_tui and not self.cfg_tui.load():
            QMessageBox.warning(self, "Reload Error", self.cfg_tui.error or "Failed to reload tui.json")
        self.dirty_oc = False
        self.dirty_tui = False
        self._snap_oc = False
        self._snap_tui = False
        self.undo_oc = UndoManager()
        self.undo_tui = UndoManager()
        self.refresh_tabs()
        self.status_bar.showMessage("Reloaded both files")

    def load_model_catalog(self) -> bool:
        """Load model catalog from file or clipboard"""
        ret = QMessageBox.question(
            self, "Load Model Catalog",
            "Load catalog from a file? (No = paste JSON instead)",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
        )

        if ret == QMessageBox.Cancel:
            return False

        try:
            if ret == QMessageBox.Yes:
                path, _ = QFileDialog.getOpenFileName(
                    self, "Load Model Catalog", str(Path.home()),
                    "JSON files (*.json);;All files (*)"
                )
                if not path:
                    return False
                self.model_catalog.load(Path(path))
            else:
                dlg = JsonImportDialog(
                    self, "Paste Model Catalog",
                    "Paste model catalog JSON. Supported formats:\n"
                    "- models.dev-style dump ({provider: {models: {...}}})\n"
                    "- Single provider dump ({'models': {...}})\n"
                    "- Flat map ({modelId: spec})"
                )
                if dlg.exec() != QDialog.Accepted:
                    return False
                self.model_catalog.load_text(json.dumps(dlg.result_data))

            self._update_catalog_status()
            self.status_bar.showMessage(
                f"Model catalog loaded: {self.model_catalog.source}"
            )
            return True
        except (OSError, ValueError, json.JSONDecodeError) as e:
            QMessageBox.warning(self, "Load Error", f"Failed to load catalog: {e}")
            return False

    def _ensure_catalog(self) -> bool:
        """Load the bundled models.dev catalog if present, else ask the user."""
        bundled = Path(__file__).resolve().parent / "models" / "models.dev.catalog.json"
        if bundled.exists():
            try:
                self.model_catalog.load(bundled)
                self._update_catalog_status()
                self.status_bar.showMessage(f"Loaded bundled catalog: {bundled.name}")
                return True
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, "Catalog Error", f"Failed to load bundled catalog: {e}")
        return self.load_model_catalog()

    def _browse_model_catalog(self):
        """Open the full-catalog browse dialog."""
        if not self.model_catalog.loaded():
            if not self._ensure_catalog():
                return
        dlg = ModelCatalogDialog(self, self.model_catalog)
        dlg.exec()

    def _apply_model_catalog(self):
        """Match configured models against the catalog and apply normalized format."""
        if not self.model_catalog.loaded():
            if not self._ensure_catalog():
                return
        if not self.cfg_oc:
            QMessageBox.information(self, "Match & Format", "Open a config file first.")
            return

        providers = section(self.cfg_oc.data, "provider")
        if not providers:
            QMessageBox.information(
                self, "Match & Format", "No providers found in the current config."
            )
            return

        self.snapshot_state("opencode")
        dlg = ApplyCatalogDialog(self, self.model_catalog, providers)
        if dlg.exec() != QDialog.Accepted:
            return

        report = dlg.apply()
        if report.any_changes():
            self.mark_dirty("opencode")
            self.refresh_tabs()
            self.status_bar.showMessage(
                f"Catalog apply: {len(report.filled)} filled, "
                f"{len(report.added)} added, {len(report.unknown)} unknown"
            )
            QMessageBox.information(
                self, "Apply Complete",
                f"Filled/updated: {len(report.filled)}\n"
                f"Added: {len(report.added)}\n"
                f"Unchanged: {len(report.unchanged)}\n"
                f"Unknown: {len(report.unknown)}\n"
                f"Ambiguous: {len(report.ambiguous)}"
            )
        else:
            QMessageBox.information(self, "Apply", "No changes were applied.")

    def _toggle_theme(self):
        """Toggle between light/dark/system theme"""
        self.theme_manager.toggle_theme()
        self._apply_theme()

    def _increase_font_size(self):
        """Increase font size"""
        current = self.settings.get_font_size()
        self.settings.set_font_size(current + 1)
        self._update_font_size()

    def _decrease_font_size(self):
        """Decrease font size"""
        current = self.settings.get_font_size()
        if current > 6:
            self.settings.set_font_size(current - 1)
            self._update_font_size()

    def _update_font_size(self):
        """Update font size for all components"""
        size = self.settings.get_font_size()
        font = QApplication.font()
        font.setPointSize(size)
        QApplication.setFont(font)

    def _show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self, "About opencode-config-editor",
            f"""<h2>{APP_NAME} v{APP_VERSION}</h2>
            <p>A GUI editor for opencode configuration files.</p>
            <p>Features:
            <ul>
                <li>Edit providers, MCP servers, plugins, and permissions</li>
                <li>Import/export functionality</li>
                <li>Model catalog support</li>
                <li>Undo/redo support</li>
                <li>Dark/light theme support</li>
                <li>Schema validation</li>
            </ul>
            </p>
            <p>Copyright © 2023 opencode.ai</p>"""
        )

    def closeEvent(self, event):
        if self.dirty_oc or self.dirty_tui:
            ret = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            if ret == QMessageBox.Save:
                self._save()
                if self.dirty:
                    event.ignore()
                    return
            elif ret == QMessageBox.Cancel:
                event.ignore()
                return
        self._save_window_state()
        event.accept()

