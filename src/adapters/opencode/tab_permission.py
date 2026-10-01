# Permissions tab
class PermissionTab(QWidget):
    """Enhanced permission tab with search"""

    # Categories the schema restricts to a bare action string
    # (PermissionActionConfig) — a path/level map is invalid for these.
    ACTION_ONLY = ("todowrite", "question", "webfetch", "websearch", "doom_loop")

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

    def _perm(self):
        """Raw `permission` value, or {} when there is no config."""
        return self.app.cfg.data.get("permission") if self.app.cfg else None

    def _rules(self, perm):
        """`permission` as a dict of categories; {} for the string form.

        The schema allows a bare action string ("allow"/"ask"/"deny") as the
        whole permission block, which has no .items().
        """
        return perm if isinstance(perm, dict) else {}

    def _filter_permissions(self, text: str):
        """Filter permissions by search text"""
        if not text:
            self.refresh()
            return

        text = text.lower()
        raw = self._perm()
        if isinstance(raw, str):
            # whole-block action string: a single implicit row
            self._update_tree({"": raw} if text in raw.lower() else {})
            return

        perm = self._rules(raw)
        filtered = {}

        for category, rules in perm.items():
            if not isinstance(rules, dict):
                # action-only category, e.g. {"edit": "ask"}
                if text in category.lower() or text in str(rules).lower():
                    filtered[category] = rules
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
            raw = self._perm()
            # the whole block may be a single action string
            permissions = {"": raw} if isinstance(raw, str) else self._rules(raw)

        self.tree.clear()

        for category, rules in permissions.items():
            if category == "" and isinstance(rules, str):
                # the whole block is a single action string
                root = QTreeWidgetItem(self.tree)
                root.setText(0, "permission")
                root.setText(2, rules)
                root.setData(0, Qt.UserRole, "block")
                continue

            category_item = QTreeWidgetItem(self.tree)
            category_item.setText(0, category)
            category_item.setData(0, Qt.UserRole, "cat")

            if not isinstance(rules, dict):
                # action-only category: no path level
                category_item.setText(2, str(rules))
                continue

            for path, level in rules.items():
                rule_item = QTreeWidgetItem(category_item)
                rule_item.setText(1, path)
                rule_item.setText(2, str(level))
                rule_item.setData(0, Qt.UserRole, "rule")

        self.tree.expandAll()

    def refresh(self):
        """Refresh tree with current data"""
        self._update_tree()

    def _add_rule(self):
        """Add new permission rule"""
        raw = self._perm()
        if raw is not None and not isinstance(raw, dict):
            QMessageBox.information(
                self, "Add Permission Rule",
                'This config sets "permission" to a single action string.\n'
                "Turn it into an object in the Raw JSON tab before adding rules.",
            )
            return
        self.app.snapshot_state()
        category, ok = QInputDialog.getText(
            self, "Add Permission Rule", "Category:",
            QLineEdit.Normal, "read"
        )
        if not ok or not category.strip():
            return
        category = category.strip()

        action_only = category in self.ACTION_ONLY
        path = ""
        if not action_only:
            path, ok = QInputDialog.getText(
                self, "Add Permission Rule", "Path:",
                QLineEdit.Normal, "*"
            )
            if not ok or not path.strip():
                return
            path = path.strip()

        level, ok = QInputDialog.getItem(
            self, "Add Permission Rule", "Level:",
            ["ask", "allow", "deny"], 0, False
        )
        if not ok:
            return

        perm = self.app.cfg.data.setdefault("permission", {})
        if not isinstance(perm, dict):
            return
        if action_only:
            perm[category] = level
        else:
            # A category may already hold a bare action string ({"bash":"ask"});
            # keep it as the catch-all "*" rule instead of discarding it.
            old = perm.get(category)
            if isinstance(old, str):
                perm[category] = {"*": old}
            elif isinstance(old, dict):
                perm[category] = old
            else:
                perm[category] = {}
            perm[category][path] = level
        self.app.mark_dirty()
        self.refresh()

    def _remove_selected(self):
        """Remove selected permission rules"""
        raw = self._perm()
        if isinstance(raw, str):
            QMessageBox.information(
                self, "Remove", "Nothing to remove: permission is a single action string.")
            return
        perm = self._rules(raw)
        self.app.snapshot_state()
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.information(self, "Remove", "Please select rules to remove")
            return

        removed = 0

        for item in selected:
            if item.parent() is None:
                # Category
                category = item.text(0)
                if category in perm:
                    removed += max(1, len(perm[category]) if isinstance(perm[category], dict) else 1)
                    perm.pop(category)
            else:
                # Rule
                category = item.parent().text(0)
                path = item.text(1)
                if isinstance(perm.get(category), dict) and path in perm[category]:
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
