# Application settings, theme and undo/redo management
class SettingsManager:
    """Handle application settings with QSettings"""

    def __init__(self):
        self.settings = QSettings(str(SETTINGS_FILE), QSettings.IniFormat)
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, default=None):
        return self.settings.value(key, default)

    def set(self, key: str, value):
        self.settings.setValue(key, value)

    def get_window_geometry(self):
        return self.get("window/geometry")

    def set_window_geometry(self, geometry):
        self.set("window/geometry", geometry)

    def get_window_state(self):
        return self.get("window/state")

    def set_window_state(self, state):
        self.set("window/state", state)

    def get_theme(self):
        return self.get("appearance/theme", "system")

    def set_theme(self, theme: str):
        self.set("appearance/theme", theme)

    def get_font_size(self):
        return int(self.get("appearance/font_size", 10))

    def set_font_size(self, size: int):
        self.set("appearance/font_size", size)

    def get_recent_files(self) -> List[str]:
        val = self.get("recent_files", [])
        if isinstance(val, str):
            return [val] if val else []
        if isinstance(val, list):
            return [str(x) for x in val]
        return []

    def add_recent_file(self, path: str):
        recent = self.get_recent_files()
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self.set("recent_files", recent[:10])

    DEFAULT_CONTEXT_TIERS = [4000, 8000, 32000, 64000, 128000, 200000, 1000000]
    DEFAULT_OUTPUT_TIERS = [1000, 4000, 8000, 32000, 128000]

    def _parse_tiers(self, val, default) -> List[int]:
        if isinstance(val, str) and val.strip():
            try:
                return sorted({int(x) for x in val.split(",") if x.strip()})
            except ValueError:
                return default
        if isinstance(val, list):
            try:
                return sorted({int(x) for x in val})
            except (ValueError, TypeError):
                return default
        return default

    def get_context_tiers(self) -> List[int]:
        return self._parse_tiers(self.get("catalog/context_tiers"), self.DEFAULT_CONTEXT_TIERS)

    def set_context_tiers(self, tiers: List[int]):
        self.set("catalog/context_tiers", ",".join(str(x) for x in sorted(set(tiers))))

    def get_output_tiers(self) -> List[int]:
        return self._parse_tiers(self.get("catalog/output_tiers"), self.DEFAULT_OUTPUT_TIERS)

    def set_output_tiers(self, tiers: List[int]):
        self.set("catalog/output_tiers", ",".join(str(x) for x in sorted(set(tiers))))

    # Persisted unknown->catalog model mappings: {"provider_key/model_id": "catalog_id"}
    def get_reference_mappings(self) -> Dict[str, str]:
        raw = self.get("catalog/reference_mappings", "{}")
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if v}
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return {}

    def set_reference_mappings(self, mappings: Dict[str, str]):
        self.set("catalog/reference_mappings", json.dumps(mappings, ensure_ascii=False))

    def add_reference_mapping(self, provider_key: str, model_id: str, catalog_id: str):
        mappings = self.get_reference_mappings()
        mappings[f"{provider_key}/{model_id}"] = catalog_id
        self.set_reference_mappings(mappings)

class ThemeManager:
    """Handle application theme switching"""

    def __init__(self, app: QApplication):
        self.app = app
        self.settings = SettingsManager()
        self._setup_theme()

    def _setup_theme(self):
        theme = self.settings.get_theme()

        if theme == "system":
            # Use system theme
            if self.app.styleHints().colorScheme() == Qt.Dark:
                self._apply_dark_theme()
            else:
                self._apply_light_theme()
        elif theme == "dark":
            self._apply_dark_theme()
        else:
            self._apply_light_theme()

    def _apply_dark_theme(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.WindowText, Qt.white)
        dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
        dark_palette.setColor(QPalette.ToolTipText, Qt.white)
        dark_palette.setColor(QPalette.Text, Qt.white)
        dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ButtonText, Qt.white)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        self.app.setPalette(dark_palette)

    def _apply_light_theme(self):
        light_palette = QPalette()
        self.app.setPalette(light_palette)

    def toggle_theme(self):
        current = self.settings.get_theme()
        if current == "dark":
            self.settings.set_theme("light")
        elif current == "light":
            self.settings.set_theme("system")
        else:
            self.settings.set_theme("dark")
        self._setup_theme()

class UndoManager:
    """Two-stack undo/redo. `current` (the live config) is supplied by the
    caller so undo/redo stay symmetric: undo() returns a prior snapshot,
    redo() returns the one you just stepped away from."""

    def __init__(self):
        self.undo_stack = deque(maxlen=UNDO_LIMIT)
        self.redo_stack = deque(maxlen=UNDO_LIMIT)

    def push(self, snapshot: dict):
        """Record a deep-copied snapshot of the state BEFORE a change."""
        self.undo_stack.append(snapshot)
        self.redo_stack.clear()

    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    def can_redo(self) -> bool:
        return bool(self.redo_stack)

    def undo(self, current: dict) -> Optional[dict]:
        """Return a deep copy of the state to revert to, or None."""
        if not self.undo_stack:
            return None
        self.redo_stack.append(copy.deepcopy(current))
        return self.undo_stack.pop()

    def redo(self, current: dict) -> Optional[dict]:
        """Return a deep copy of the state to move forward to, or None."""
        if not self.redo_stack:
            return None
        self.undo_stack.append(copy.deepcopy(current))
        return self.redo_stack.pop()

