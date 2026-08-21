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
