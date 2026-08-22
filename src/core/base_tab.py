# Shared base for form-style tabs.
#
# A BaseTab bundles the small helpers that config tabs repeat: "touched"-group
# tracking (only serialize sections the user actually edited) and the
# widget<->value setters. New tabs (opencode or a future agent adapter) inherit
# this instead of copy-pasting _t/_put/_set_* into every tab.

class BaseTab(QWidget):
    """Base class for form tabs with touched-tracking and value helpers."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._touched = set()

    def _t(self, group):
        """Return a slot that marks `group` touched and flags the doc dirty."""
        def _h(*_):
            self._touched.add(group)
            self.app.mark_dirty()
        return _h

    def _put(self, d, k, val, empty):
        """Set d[k]=val, or remove the key when val equals the 'empty' sentinel."""
        if val != empty:
            d[k] = val
        else:
            d.pop(k, None)

    def _set_checked(self, cb, val):
        cb.blockSignals(True)
        cb.setChecked(bool(val))
        cb.blockSignals(False)

    def _set_spin(self, spin, val):
        spin.blockSignals(True)
        spin.setValue(int(val) if isinstance(val, int) and not isinstance(val, bool) else 0)
        spin.blockSignals(False)

    def _set_double(self, spin, val):
        spin.blockSignals(True)
        spin.setValue(float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else spin.minimum())
        spin.blockSignals(False)

    def _set_combo(self, combo, val, fallback):
        combo.blockSignals(True)
        idx = combo.findData(val)
        combo.setCurrentIndex(idx if idx >= 0 else fallback)
        combo.blockSignals(False)

    def _set_text(self, edit, val):
        """blockSignals-safe population for QLineEdit/QPlainTextEdit-like widgets."""
        text = str(val if val is not None else "")
        setter = getattr(edit, "setPlainText", None) or edit.setText
        edit.blockSignals(True)
        setter(text)
        edit.blockSignals(False)

    # --- shared table helpers (row fidelity pattern) ---
    @staticmethod
    def cell_text(table, r, c):
        """Read a table cell as stripped text ('' when missing)."""
        item = table.item(r, c)
        return item.text().strip() if item else ""

    @staticmethod
    def remove_current(table):
        """Remove the table's current row; return True when a row was removed."""
        r = table.currentRow()
        if r >= 0:
            table.removeRow(r)
            return True
        return False

    @staticmethod
    def preserve(item, data):
        """Stash a row's original dict on its name item (Qt.UserRole)."""
        item.setData(Qt.UserRole, dict(data) if isinstance(data, dict) else {})

    @staticmethod
    def preserved(item):
        """Read back the stashed original dict as a defensive copy."""
        orig = item.data(Qt.UserRole)
        return dict(orig) if isinstance(orig, dict) else {}
