# Permissions tab
class PermissionTab(QWidget):
    """Enhanced permission tab with search"""

    def __init__(self, app):
        super().__init__()
        self.app = app

        layout = QVBoxLayout(self)

        # Search
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search permissions...")
        self.search_edit.textChanged.connect(self._filter_permissions)
        layout.addWidget(self.search_edit)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Category", "Path", "Level"])
        self.tree.setColumnCount(3)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        layout.addWidget(self.tree)

        # Buttons
        button_layout = QHBoxLayout()
        add_btn = QPushButton("+ Add Rule")
        add_btn.clicked.connect(self._add_rule)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        button_layout.addWidget(add_btn)
        button_layout.addWidget(remove_btn)
        layout.addLayout(button_layout)

    def _filter_permissions(self, text: str):
        """Filter permissions by search text"""
        if not text:
            self.refresh()
            return

        text = text.lower()
        perm = self.app.cfg.data.get("permission", {}) if self.app.cfg else {}
        filtered = {}

        for category, rules in perm.items():
            if not isinstance(rules, dict):
                continue

            matching_rules = {
                path: level for path, level in rules.items()
                if text in category.lower() or text in path.lower() or text in str(level).lower()
            }

            if matching_rules:
                filtered[category] = matching_rules

        self._update_tree(filtered)

    def _update_tree(self, permissions: Optional[dict] = None):
        """Update tree with permissions"""
        if permissions is None:
            permissions = self.app.cfg.data.get("permission", {}) if self.app.cfg else {}

        self.tree.clear()

        for category, rules in permissions.items():
            if not isinstance(rules, dict):
                continue

            category_item = QTreeWidgetItem(self.tree)
            category_item.setText(0, category)
            category_item.setFlags(category_item.flags() | Qt.ItemIsEditable)

            for path, level in rules.items():
                rule_item = QTreeWidgetItem(category_item)
                rule_item.setText(1, path)
                rule_item.setText(2, str(level))
                rule_item.setFlags(rule_item.flags() | Qt.ItemIsEditable)

        self.tree.expandAll()

    def refresh(self):
        """Refresh tree with current data"""
        self._update_tree()

    def _add_rule(self):
        """Add new permission rule"""
        self.app.snapshot_state()
        category, ok = QInputDialog.getText(
            self, "Add Permission Rule", "Category:",
            QLineEdit.Normal, "filesystem"
        )
        if not ok or not category.strip():
            return

        path, ok = QInputDialog.getText(
            self, "Add Permission Rule", "Path:",
            QLineEdit.Normal, "/tmp/*"
        )
        if not ok or not path.strip():
            return

        level, ok = QInputDialog.getItem(
            self, "Add Permission Rule", "Level:",
            ["read", "write", "execute", "none"], 0, False
        )
        if not ok:
            return

        perm = self.app.cfg.data.setdefault("permission", {})
        if category not in perm:
            perm[category] = {}

        perm[category][path] = level
        self.app.mark_dirty()
        self.refresh()

    def _remove_selected(self):
        """Remove selected permission rules"""
        self.app.snapshot_state()
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.information(self, "Remove", "Please select rules to remove")
            return

        perm = self.app.cfg.data.get("permission", {})
        removed = 0

        for item in selected:
            if item.parent() is None:
                # Category
                category = item.text(0)
                if category in perm:
                    removed += len(perm[category])
                    perm.pop(category)
            else:
                # Rule
                category = item.parent().text(0)
                path = item.text(1)
                if category in perm and path in perm[category]:
                    removed += 1
                    perm[category].pop(path)
                    if not perm[category]:
                        perm.pop(category)

        self.app.mark_dirty()
        self.refresh()
        QMessageBox.information(self, "Remove", f"Removed {removed} permission rules")

    def collect(self, data: dict):
        """Collect data from UI"""
        # Permissions are edited directly in the config
        pass

