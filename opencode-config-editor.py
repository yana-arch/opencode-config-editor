#!/usr/bin/env python3
"""
opencode-config-editor — Enhanced GUI for opencode/tui config files

Key improvements:
- Dark/light theme support with system preference detection
- Advanced model management with bulk operations
- Provider/MCP/plugin import with conflict resolution
- Schema-aware validation with detailed error reporting
- Undo/redo support for all operations
- Search/filter across all tabs
- Bulk enable/disable for plugins and MCP servers
- Model catalog with preview and filtering
- Export/backup functionality
- Keyboard shortcuts for common operations
- Responsive UI with better error handling
"""

import json
import os
import re
import copy
import shutil
import sys
import tempfile
import time
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

try:
    from PySide6.QtCore import (
        Qt, QTimer, QSize, QPoint, QSettings
    )
    from PySide6.QtGui import (
        QAction, QFont, QKeySequence, QColor, QPalette,
        QTextCharFormat, QSyntaxHighlighter
    )
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
        QFormLayout, QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QTextEdit,
        QPlainTextEdit, QTableWidget, QTableWidgetItem, QPushButton, QLabel,
        QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QSplitter,
        QComboBox, QMessageBox, QFileDialog, QDialogButtonBox, QGroupBox,
        QHeaderView, QToolBar, QToolButton, QMenu, QDialog, QFrame, QInputDialog,
        QScrollArea
    )
except ImportError:
    sys.stderr.write("PySide6 is required. Install it with: pip install PySide6\n")
    sys.exit(1)

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

# Constants
APP_NAME = "opencode-config-editor"
APP_VERSION = "4.0.0"
SCHEMA_URL = "https://opencode.ai/config.json"
TUI_SCHEMA_URL = "https://opencode.ai/tui.json"
SCHEMA_CACHE = Path.home() / ".cache" / APP_NAME / "config-schema.json"
TUI_SCHEMA_CACHE = Path.home() / ".cache" / APP_NAME / "tui-schema.json"
PLUGIN_STATE_CACHE = Path.home() / ".cache" / APP_NAME / "plugin-state.json"
SETTINGS_FILE = Path.home() / ".config" / APP_NAME / "settings.ini"
UNDO_LIMIT = 100

# Configuration keys (derived from https://opencode.ai/config.json and /tui.json)
OPENCODE_KEYS = {
    "$schema", "shell", "logLevel", "server", "command", "skills",
    "references", "reference", "watcher", "snapshot", "plugin", "share",
    "autoshare", "autoupdate", "disabled_providers", "enabled_providers",
    "model", "small_model", "default_agent", "subagent_depth", "username",
    "mode", "agent", "provider", "mcp", "formatter", "lsp", "instructions",
    "layout", "permission", "tools", "attachment", "enterprise",
    "tool_output", "compaction", "experimental",
}

TUI_KEYS = {
    "$schema", "theme", "keybinds", "plugin", "plugin_enabled",
    "leader_timeout", "attention", "prompt", "scroll_speed",
    "scroll_acceleration", "diff_style", "cursor", "mouse",
}

# Model fields that can be bulk-edited
MODEL_FIELDS = [
    "name", "attachment", "reasoning", "temperature", "tool_call",
    "cost.input", "cost.output", "cost.cache_read", "cost.cache_write",
    "limit.context", "limit.output"
]

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

class JSONHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for JSON editor"""

    def __init__(self, document):
        super().__init__(document)
        self._rules = []

        # Keywords
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569CD6"))
        keyword_format.setFontWeight(QFont.Bold)
        keywords = ["true", "false", "null"]
        self._rules += [(r'\b%s\b' % keyword, keyword_format) for keyword in keywords]

        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178"))
        self._rules.append((r'".*?"', string_format))

        # Numbers
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#B5CEA8"))
        self._rules.append((r'\b[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?\b', number_format))

        # Comments (JSON doesn't support comments, but we'll highlight them if present)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955"))
        self._rules.append((r'//[^\n]*', comment_format))
        self._rules.append((r'/\*.*?\*/', comment_format))

        # Properties
        property_format = QTextCharFormat()
        property_format.setForeground(QColor("#9CDCFE"))
        self._rules.append((r'"[^"]*"\s*(?=:)', property_format))

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            expression = re.compile(pattern)
            for match in expression.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, fmt)

class ConfigFile:
    """Enhanced config file handler with backup and validation"""

    def __init__(self, path: Path, kind: str):
        self.path = Path(path)
        self.kind = kind
        self.data = {}
        self.error = None
        self.backup_dir = Path.home() / ".cache" / APP_NAME / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def targets(cwd: Path) -> List[Tuple[str, Path, str]]:
        """Get available config file targets"""
        home = Path.home()
        proj_dir = cwd / ".opencode"
        candidates = [
            ("Global opencode.json", home / ".config" / "opencode" / "opencode.json", "opencode"),
            ("Project opencode.json", (proj_dir / "opencode.json") if (proj_dir / "opencode.json").exists()
             else (cwd / "opencode.json"), "opencode"),
            ("Global tui.json", home / ".config" / "opencode" / "tui.json", "tui"),
            ("Project tui.json", (proj_dir / "tui.json") if (proj_dir / "tui.json").exists()
             else (cwd / "tui.json"), "tui"),
        ]
        return [(label, p, kind) for label, p, kind in candidates]

    @staticmethod
    def kind_for(path: Path) -> str:
        """Determine config kind from path"""
        name = path.name.lower()
        if name == "opencode.json":
            return "opencode"
        if name == "tui.json":
            return "tui"
        return "generic"

    def load(self) -> bool:
        """Load config file with error handling"""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = f.read()
            self.data = json.loads(raw)
            self.error = None
            return True
        except FileNotFoundError:
            self.data = {}
            self.error = f"File not found: {self.path}"
            return False
        except json.JSONDecodeError as e:
            self.error = f"Invalid JSON: {e}"
            return False
        except OSError as e:
            self.error = f"Read error: {e}"
            return False

    def backup_path(self) -> Path:
        """Generate backup path with timestamp"""
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        return self.backup_dir / f"{self.path.name}.bak-{ts}"

    def create_backup(self) -> bool:
        """Create backup of current file"""
        try:
            if self.path.exists():
                shutil.copy2(self.path, self.backup_path())
            return True
        except OSError as e:
            self.error = f"Backup failed: {e}"
            return False

    def save(self, data: dict) -> Tuple[bool, str]:
        """Atomic save with backup"""
        if not isinstance(data, dict):
            return False, "Root must be a JSON object."

        try:
            content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        except (TypeError, ValueError) as e:
            return False, f"Cannot serialize config: {e}"

        try:
            # Create backup before saving
            self.create_backup()

            # Atomic write
            fd, tmp = tempfile.mkstemp(
                dir=str(self.path.parent),
                prefix=f"{self.path.name}.",
                suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, self.path)

            self.data = data
            return True, f"Saved to {self.path}"
        except OSError as e:
            return False, f"Save error: {e}"

    def export(self, path: Path) -> Tuple[bool, str]:
        """Export config to specified path"""
        try:
            content = json.dumps(self.data, indent=2, ensure_ascii=False) + "\n"
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True, f"Exported to {path}"
        except OSError as e:
            return False, f"Export error: {e}"

class Validator:
    """Enhanced validator with schema caching and detailed error reporting"""

    def __init__(self):
        self.schemas = {}  # kind -> schema dict
        self.schema_error = None
        self.last_schema_fetch = 0
        self.schema_cache_duration = 86400  # 24 hours

    def _schema_source(self, kind: str) -> Tuple[str, Path]:
        """Return (url, cache_path) for the given config kind."""
        if kind == "tui":
            return TUI_SCHEMA_URL, TUI_SCHEMA_CACHE
        return SCHEMA_URL, SCHEMA_CACHE

    def _load_schema(self, kind: str = "opencode") -> Optional[dict]:
        """Load schema (kind-aware) with caching and periodic refresh"""
        if not HAVE_JSONSCHEMA:
            return None

        url, cache_path = self._schema_source(kind)
        current_time = time.time()
        if self.schemas.get(kind) is not None and (current_time - self.last_schema_fetch) < self.schema_cache_duration:
            return self.schemas[kind]

        if self.schema_error is not None and (current_time - self.last_schema_fetch) < 3600:  # 1 hour
            return None

        data = None
        try:
            # Try cache first
            if cache_path.exists():
                data = json.loads(cache_path.read_text())
                self.schemas[kind] = data
                self.last_schema_fetch = current_time
                return data
        except Exception:
            pass

        # Fetch from network
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))

            # Save to cache
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(data))
            except OSError:
                pass

            self.schemas[kind] = data
            self.last_schema_fetch = current_time
            return data
        except Exception as e:
            self.schema_error = f"Could not fetch schema: {e}"
            self.last_schema_fetch = current_time
            return None

    def validate(self, data: dict, kind: str) -> Tuple[bool, List[str], List[str]]:
        """Validate config.

        Returns (hard_ok, hard_errors, schema_warnings).

        Hard errors are structural checks we can trust regardless of schema.
        Schema-derived findings are treated as advisory *warnings* because the
        official opencode schema is stricter/incomplete (e.g. it rejects the
        `local` MCP type that opencode actually supports), so a valid config
        would otherwise always be flagged.
        """
        if not isinstance(data, dict):
            return False, ["Root must be a JSON object."], []

        known = OPENCODE_KEYS if kind in ("opencode", "generic") else TUI_KEYS
        hard_ok, hard = self._basic_checks(data, known)
        if not hard_ok:
            return False, hard, []

        warnings: List[str] = []
        if HAVE_JSONSCHEMA:
            schema = self._load_schema(kind)
            if schema is not None:
                try:
                    for e in jsonschema.Draft7Validator(schema).iter_errors(data):
                        warnings.append(f"schema: {e.message} (path: {_path_of(e)})")
                except Exception as ex:
                    warnings.append(f"schema error: {ex}")
        return True, [], warnings

    def _basic_checks(self, data: dict, known_keys: set) -> Tuple[bool, List[str]]:
        """Basic structural validation"""
        errors = []

        if "provider" in data and not isinstance(data["provider"], dict):
            errors.append("'provider' must be an object.")

        if "mcp" in data and not isinstance(data["mcp"], dict):
            errors.append("'mcp' must be an object.")

        if "plugin" in data and not isinstance(data["plugin"], list):
            errors.append("'plugin' must be an array.")

        if "mcp" in data:
            for name, cfg in data["mcp"].items():
                if not isinstance(cfg, dict):
                    errors.append(f"mcp[{name!r}] must be an object.")
                    continue

                t = cfg.get("type")
                if t not in (None, "local", "remote"):
                    errors.append(f"mcp[{name!r}].type must be 'local' or 'remote'.")

                if t == "local" and "command" in cfg and not isinstance(cfg["command"], list):
                    errors.append(f"mcp[{name!r}].command must be an array.")

                if t == "remote" and "url" in cfg and not isinstance(cfg["url"], str):
                    errors.append(f"mcp[{name!r}].url must be a string.")

        return (len(errors) == 0), errors

def _path_of(e) -> str:
    """Get path from validation error"""
    try:
        return "/".join(str(x) for x in e.absolute_path)
    except Exception:
        return "?"

class PluginStateStore:
    """Enhanced plugin state store with persistence"""

    def __init__(self):
        self.path = PLUGIN_STATE_CACHE
        self._data = {}
        self._load()

    def _load(self):
        """Load plugin state from cache"""
        try:
            if self.path.exists():
                self._data = json.loads(self.path.read_text())
        except Exception:
            self._data = {}

    def _save(self):
        """Save plugin state to cache"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2))
        except OSError:
            pass

    def get_disabled(self, cfg_path: Path) -> set:
        """Get disabled plugins for config file"""
        return set(self._data.get(str(cfg_path), []))

    def set_disabled(self, cfg_path: Path, disabled: set):
        """Set disabled plugins for config file"""
        key = str(cfg_path)
        if disabled:
            self._data[key] = sorted(disabled)
        else:
            self._data.pop(key, None)
        self._save()

class TuiPluginStateStore:
    """Remember disabled tui plugins in the editor cache, keying each by name and
    storing its full entry so re-enabling restores tuple-form options verbatim."""

    def __init__(self):
        self.path = Path.home() / ".cache" / APP_NAME / "tui-plugin-state.json"
        self._data = {}
        self._load()

    def _load(self):
        try:
            if self.path.exists():
                self._data = json.loads(self.path.read_text())
        except Exception:
            self._data = {}

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data))
        except OSError:
            pass

    def get_entries(self, cfg_path: Path) -> dict:
        """{name: full entry} for disabled plugins of this config."""
        entries = self._data.get(str(cfg_path), {})
        return dict(entries) if isinstance(entries, dict) else {}

    def set_entry(self, cfg_path: Path, name: str, entry):
        key = str(cfg_path)
        self._data.setdefault(key, {})[name] = entry
        self._save()

    def remove_entry(self, cfg_path: Path, name: str):
        key = str(cfg_path)
        d = self._data.get(key, {})
        if name in d:
            d.pop(name, None)
            if not d:
                self._data.pop(key, None)
            self._save()

    def clear(self, cfg_path: Path, names=None):
        key = str(cfg_path)
        d = self._data.get(key, {})
        if names is None:
            d = {}
        else:
            for n in names:
                d.pop(n, None)
        if d:
            self._data[key] = d
        else:
            self._data.pop(key, None)
        self._save()

class ModelCatalog:
    """Enhanced model catalog with filtering and preview"""

    def __init__(self):
        self.raw = None
        self.by_provider = {}  # provider_id -> {model_id: spec}
        self.flat = {}         # model_id -> spec
        self.source = None
        self.last_updated = None

    def loaded(self) -> bool:
        """Check if catalog is loaded"""
        return self.raw is not None

    def load(self, path: Path):
        """Load catalog from file"""
        data = _load_json_file(path)
        self._ingest(data)
        self.source = str(path)
        self.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def load_text(self, text: str):
        """Load catalog from text"""
        data = json.loads(text)
        self._ingest(data)
        self.source = "(pasted)"
        self.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _ingest(self, data: dict):
        """Process catalog data"""
        if not isinstance(data, dict) or not data:
            raise ValueError("Catalog JSON must be a non-empty object.")

        by_provider, flat = {}, {}

        # models.dev-style dump: {providerId: {..., "models": {id: spec}}}
        if all(isinstance(v, dict) and "models" in v for v in data.values()):
            for pid, pdata in data.items():
                models = pdata.get("models", {})
                if isinstance(models, dict):
                    by_provider[pid] = models
                    for mid, spec in models.items():
                        flat.setdefault(mid, spec)

        # Single provider dump: {"id":..., "models": {...}}
        elif "models" in data and isinstance(data["models"], dict):
            pid = data.get("id") or "provider"
            by_provider[pid] = data["models"]
            flat.update(data["models"])

        # Flat map: {modelId: spec}
        elif all(isinstance(v, dict) for v in data.values()):
            flat.update(data)

        else:
            raise ValueError("Unrecognized model catalog format.")

        self.raw, self.by_provider, self.flat = data, by_provider, flat

    def models_for(self, provider_key: str, npm: str = None) -> dict:
        """Get models for provider"""
        candidates = [provider_key, npm, (npm or "").split("/")[-1]]
        for candidate in candidates:
            if candidate and candidate in self.by_provider:
                return self.by_provider[candidate]
        return self.flat

    def filter_models(self, search: str) -> dict:
        """Filter models by search string"""
        if not search:
            return self.flat

        search = search.lower()
        return {
            mid: spec for mid, spec in self.flat.items()
            if search in mid.lower() or
               (isinstance(spec.get("name"), str) and search in spec["name"].lower())
        }

def _load_json_file(path: Path) -> dict:
    """Load JSON file with error handling"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _slugify(s: str) -> str:
    """Convert string to slug"""
    s = re.sub(r"[^a-zA-Z0-9_.\-]+", "-", str(s)).strip("-")
    return s or "item"

def _looks_like_provider_cfg(v) -> bool:
    """Check if object looks like a provider config"""
    return isinstance(v, dict) and any(k in v for k in ("npm", "models", "options", "name", "id"))

def parse_provider_import(obj: dict) -> dict:
    """Parse provider import from various JSON formats"""
    if isinstance(obj, dict) and isinstance(obj.get("provider"), dict) and obj["provider"]:
        obj = obj["provider"]

    if isinstance(obj, dict) and obj and all(_looks_like_provider_cfg(v) for v in obj.values()):
        return obj

    if _looks_like_provider_cfg(obj):
        key = _slugify(obj.get("id") or obj.get("name") or "provider")
        cfg = {k: v for k, v in obj.items() if k != "id"}
        return {key: cfg}

    raise ValueError(
        "Unrecognized provider JSON. Expected a provider object, a "
        "{name: provider} map, or a full config containing 'provider'."
    )

def _looks_like_mcp_cfg(v) -> bool:
    """Check if object looks like an MCP config"""
    return isinstance(v, dict) and any(k in v for k in ("type", "command", "url", "enabled"))

def parse_mcp_import(obj: dict) -> dict:
    """Parse MCP import from various JSON formats"""
    if isinstance(obj, dict) and isinstance(obj.get("mcp"), dict) and obj["mcp"]:
        obj = obj["mcp"]

    if isinstance(obj, dict) and obj and all(_looks_like_mcp_cfg(v) for v in obj.values()):
        return obj

    if _looks_like_mcp_cfg(obj):
        key = _slugify(obj.get("name") or obj.get("id") or "server")
        cfg = {k: v for k, v in obj.items() if k not in ("name", "id")}
        return {key: cfg}

    raise ValueError(
        "Unrecognized MCP JSON. Expected a server object or a {name: server} map."
    )

def merge_dict(base: dict, incoming: dict) -> dict:
    """Merge two configs with special handling for models/options"""
    out = dict(base)
    for k, v in incoming.items():
        if k in ("models", "options") and isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out

def _extract_models_map(data) -> dict:
    """Extract models map from various formats"""
    if isinstance(data, dict):
        if isinstance(data.get("models"), dict):
            return data["models"]
        if data and all(isinstance(v, dict) for v in data.values()):
            return data

    if isinstance(data, list):
        out = {}
        for item in data:
            if isinstance(item, dict) and "id" in item:
                out[item["id"]] = {k: v for k, v in item.items() if k != "id"}
        if not out:
            raise ValueError("Array items must be objects with an 'id' field.")
        return out

    raise ValueError("Unrecognized models JSON shape.")

def _merge_model_spec(existing: dict, catalog_spec: dict, overwrite: bool) -> dict:
    """Merge model spec with catalog spec"""
    existing = dict(existing or {})
    for k, v in catalog_spec.items():
        if k in ("cost", "limit") and isinstance(v, dict):
            sub = dict(existing.get(k, {})) if isinstance(existing.get(k), dict) else {}
            for sk, sv in v.items():
                if overwrite or sk not in sub:
                    sub[sk] = sv
            existing[k] = sub
        else:
            if overwrite or k not in existing:
                existing[k] = v
    return existing

# GUI Components
class MaskedLineEdit(QWidget):
    """Line edit with optional masking for sensitive fields"""

    SECRET_HINT = re.compile(r"(key|token|secret|password|auth)", re.I)

    def __init__(self, value="", parent=None, field_name="", placeholder=""):
        super().__init__(parent)
        self.field_name = field_name
        self.is_secret = bool(self.SECRET_HINT.search(field_name))
        self._real_value = str(value) if value is not None else ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setText(self._display_value())
        layout.addWidget(self.edit)

        if self.is_secret:
            self.toggle_btn = QPushButton("👁")
            self.toggle_btn.setCheckable(True)
            self.toggle_btn.setFixedWidth(30)
            self.toggle_btn.toggled.connect(self._toggle_visibility)
            layout.addWidget(self.toggle_btn)

    def _display_value(self) -> str:
        """Get display value (masked if secret)"""
        if not self.is_secret or self.toggle_btn.isChecked():
            return self._real_value
        return _mask(self._real_value)

    def _toggle_visibility(self, checked: bool):
        """Toggle visibility of secret value"""
        self.edit.setText(self._display_value())

    def set_value(self, value):
        """Set value"""
        self._real_value = str(value) if value is not None else ""
        self.edit.setText(self._display_value())

    def value(self) -> str:
        """Get current value"""
        if self.is_secret and not self.toggle_btn.isChecked():
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

class ModelEditDialog(QDialog):
    """Enhanced model edit dialog with validation"""

    def __init__(self, parent, model_id: str = "", spec: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Model" if model_id else "Add Model")
        self.resize(500, 600)

        spec = spec or {}
        layout = QFormLayout(self)

        # Model ID
        self.id_edit = QLineEdit(model_id)
        self.id_edit.setPlaceholderText("e.g. gpt-4o")
        layout.addRow("Model ID*", self.id_edit)

        # Basic fields
        self.name_edit = QLineEdit(spec.get("name", ""))
        self.name_edit.setPlaceholderText("Human-readable name")
        layout.addRow("Name", self.name_edit)

        self.attachment_check = QCheckBox("Supports file attachments")
        self.attachment_check.setChecked(spec.get("attachment", False))
        layout.addRow("", self.attachment_check)

        self.reasoning_check = QCheckBox("Supports reasoning")
        self.reasoning_check.setChecked(spec.get("reasoning", False))
        layout.addRow("", self.reasoning_check)

        self.temperature_check = QCheckBox("Supports temperature setting")
        self.temperature_check.setChecked(spec.get("temperature", False))
        layout.addRow("", self.temperature_check)

        self.tool_call_check = QCheckBox("Supports tool calls")
        self.tool_call_check.setChecked(spec.get("tool_call", True))
        layout.addRow("", self.tool_call_check)

        # Cost fields
        cost_group = QGroupBox("Cost (per 1M tokens)")
        cost_layout = QFormLayout()

        self.cost_in_edit = QLineEdit(str(spec.get("cost", {}).get("input", "")))
        self.cost_in_edit.setPlaceholderText("e.g. 5.00")
        cost_layout.addRow("Input ($)", self.cost_in_edit)

        self.cost_out_edit = QLineEdit(str(spec.get("cost", {}).get("output", "")))
        self.cost_out_edit.setPlaceholderText("e.g. 15.00")
        cost_layout.addRow("Output ($)", self.cost_out_edit)

        self.cost_cache_read_edit = QLineEdit(str(spec.get("cost", {}).get("cache_read", "")))
        cost_layout.addRow("Cache Read ($)", self.cost_cache_read_edit)

        self.cost_cache_write_edit = QLineEdit(str(spec.get("cost", {}).get("cache_write", "")))
        cost_layout.addRow("Cache Write ($)", self.cost_cache_write_edit)

        cost_group.setLayout(cost_layout)
        layout.addRow(cost_group)

        # Limit fields
        limit_group = QGroupBox("Limits")
        limit_layout = QFormLayout()

        self.limit_ctx_edit = QLineEdit(str(spec.get("limit", {}).get("context", "")))
        self.limit_ctx_edit.setPlaceholderText("e.g. 128000")
        limit_layout.addRow("Context (tokens)", self.limit_ctx_edit)

        self.limit_out_edit = QLineEdit(str(spec.get("limit", {}).get("output", "")))
        self.limit_out_edit.setPlaceholderText("e.g. 4096")
        limit_layout.addRow("Output (tokens)", self.limit_out_edit)

        limit_group.setLayout(limit_layout)
        layout.addRow(limit_group)

        # Additional fields
        self.extra_edit = QPlainTextEdit()
        extra_data = {k: v for k, v in spec.items() if k not in {
            "name", "attachment", "reasoning", "temperature", "tool_call",
            "cost", "limit"
        }}
        self.extra_edit.setPlainText(json.dumps(extra_data, indent=2))
        layout.addRow("Additional Fields (JSON)", self.extra_edit)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        self.result_id = None
        self.result_spec = None

    def _accept(self):
        """Validate and accept dialog"""
        model_id = self.id_edit.text().strip()
        if not model_id:
            QMessageBox.warning(self, "Error", "Model ID is required")
            return

        try:
            extra_data = json.loads(self.extra_edit.toPlainText() or "{}")
            if not isinstance(extra_data, dict):
                raise ValueError("Additional fields must be a JSON object")
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Error", f"Invalid JSON in additional fields: {e}")
            return
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        # Build spec
        spec = dict(extra_data)

        if self.name_edit.text().strip():
            spec["name"] = self.name_edit.text().strip()

        spec["attachment"] = self.attachment_check.isChecked()
        spec["reasoning"] = self.reasoning_check.isChecked()
        spec["temperature"] = self.temperature_check.isChecked()
        spec["tool_call"] = self.tool_call_check.isChecked()

        # Cost
        cost = {}
        for field, edit in [
            ("input", self.cost_in_edit),
            ("output", self.cost_out_edit),
            ("cache_read", self.cost_cache_read_edit),
            ("cache_write", self.cost_cache_write_edit)
        ]:
            value = edit.text().strip()
            if value:
                try:
                    cost[field] = float(value)
                except ValueError:
                    QMessageBox.warning(self, "Error", f"Invalid cost value for {field}")
                    return
        if cost:
            spec["cost"] = cost

        # Limits
        limit = {}
        for field, edit in [
            ("context", self.limit_ctx_edit),
            ("output", self.limit_out_edit)
        ]:
            value = edit.text().strip()
            if value:
                try:
                    limit[field] = int(value)
                except ValueError:
                    QMessageBox.warning(self, "Error", f"Invalid limit value for {field}")
                    return
        if limit:
            spec["limit"] = limit

        self.result_id = model_id
        self.result_spec = spec
        self.accept()

class ModelsManagerDialog(QDialog):
    """Enhanced models manager with bulk operations"""

    def __init__(self, app, provider_key: str, provider_cfg: dict):
        super().__init__(app)
        self.app = app
        self.provider_key = provider_key
        self.provider_cfg = provider_cfg
        self.models = dict(provider_cfg.get("models", {})) if isinstance(provider_cfg.get("models"), dict) else {}
        self.setWindowTitle(f"Models - {provider_key}")
        self.resize(900, 600)

        layout = QVBoxLayout(self)

        # Search bar
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search models...")
        self.search_edit.textChanged.connect(self._filter_models)
        search_layout.addWidget(self.search_edit)

        # Buttons
        button_layout = QHBoxLayout()
        for text, slot in [
            ("+ Add", self._add_model),
            ("Edit", self._edit_model),
            ("Remove", self._remove_model),
            ("Import", self._import_models),
            ("Export", self._export_models),
            ("Apply Catalog", self._apply_catalog),
            ("Bulk Edit", self._bulk_edit)
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            button_layout.addWidget(btn)

        layout.addLayout(search_layout)
        layout.addLayout(button_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Name", "Attachment", "Reasoning", "Cost (in/out)",
            "Context/Output", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        layout.addWidget(self.table)

        # Status bar
        self.status_label = QLabel()
        layout.addWidget(self.status_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._update_table()

    def _update_table(self):
        """Update table with current models"""
        self.table.setRowCount(len(self.models))
        for row, (model_id, spec) in enumerate(sorted(self.models.items())):
            if not isinstance(spec, dict):
                spec = {}

            # ID
            self.table.setItem(row, 0, QTableWidgetItem(model_id))

            # Name
            self.table.setItem(row, 1, QTableWidgetItem(spec.get("name", "")))

            # Attachment
            self.table.setItem(row, 2, QTableWidgetItem("✓" if spec.get("attachment") else ""))

            # Reasoning
            self.table.setItem(row, 3, QTableWidgetItem("✓" if spec.get("reasoning") else ""))

            # Cost
            cost = spec.get("cost", {}) if isinstance(spec.get("cost"), dict) else {}
            cost_text = f"{cost.get('input', '')}/{cost.get('output', '')}"
            self.table.setItem(row, 4, QTableWidgetItem(cost_text))

            # Limits
            limit = spec.get("limit", {}) if isinstance(spec.get("limit"), dict) else {}
            limit_text = f"{limit.get('context', '')}/{limit.get('output', '')}"
            self.table.setItem(row, 5, QTableWidgetItem(limit_text))

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedWidth(60)
            edit_btn.clicked.connect(lambda _, m=model_id: self._edit_model(m))
            actions_layout.addWidget(edit_btn)

            remove_btn = QPushButton("Remove")
            remove_btn.setFixedWidth(60)
            remove_btn.clicked.connect(lambda _, m=model_id: self._remove_model(m))
            actions_layout.addWidget(remove_btn)

            self.table.setCellWidget(row, 6, actions_widget)

        self.status_label.setText(f"{len(self.models)} models")

    def _filter_models(self, text: str):
        """Filter models by search text"""
        if not text:
            self._update_table()
            return

        text = text.lower()
        filtered = {
            mid: spec for mid, spec in self.models.items()
            if text in mid.lower() or
               (isinstance(spec.get("name"), str) and text in spec["name"].lower())
        }

        self.table.setRowCount(len(filtered))
        for row, (model_id, spec) in enumerate(sorted(filtered.items())):
            if not isinstance(spec, dict):
                spec = {}

            self.table.setItem(row, 0, QTableWidgetItem(model_id))
            self.table.setItem(row, 1, QTableWidgetItem(spec.get("name", "")))
            self.table.setItem(row, 2, QTableWidgetItem("✓" if spec.get("attachment") else ""))
            self.table.setItem(row, 3, QTableWidgetItem("✓" if spec.get("reasoning") else ""))

            cost = spec.get("cost", {}) if isinstance(spec.get("cost"), dict) else {}
            cost_text = f"{cost.get('input', '')}/{cost.get('output', '')}"
            self.table.setItem(row, 4, QTableWidgetItem(cost_text))

            limit = spec.get("limit", {}) if isinstance(spec.get("limit"), dict) else {}
            limit_text = f"{limit.get('context', '')}/{limit.get('output', '')}"
            self.table.setItem(row, 5, QTableWidgetItem(limit_text))

            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedWidth(60)
            edit_btn.clicked.connect(lambda _, m=model_id: self._edit_model(m))
            actions_layout.addWidget(edit_btn)

            remove_btn = QPushButton("Remove")
            remove_btn.setFixedWidth(60)
            remove_btn.clicked.connect(lambda _, m=model_id: self._remove_model(m))
            actions_layout.addWidget(remove_btn)

            self.table.setCellWidget(row, 6, actions_widget)

        self.status_label.setText(f"{len(filtered)} models (filtered)")

    def _add_model(self):
        """Add new model"""
        dlg = ModelEditDialog(self)
        if dlg.exec() == QDialog.Accepted:
            if dlg.result_id in self.models:
                if not _confirm(self, "Model exists", f"Overwrite existing model '{dlg.result_id}'?"):
                    return
            self.models[dlg.result_id] = dlg.result_spec
            self._update_table()
            self.app.mark_dirty()

    def _edit_model(self, model_id: Optional[str] = None):
        """Edit existing model"""
        if model_id is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Edit", "Please select a model to edit")
                return
            model_id = selected[0].text()

        if model_id not in self.models:
            QMessageBox.warning(self, "Error", f"Model '{model_id}' not found")
            return

        dlg = ModelEditDialog(self, model_id, self.models[model_id])
        if dlg.exec() == QDialog.Accepted:
            if dlg.result_id != model_id:
                self.models.pop(model_id)
            self.models[dlg.result_id] = dlg.result_spec
            self._update_table()
            self.app.mark_dirty()

    def _remove_model(self, model_id: Optional[str] = None):
        """Remove model(s)"""
        if model_id is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Remove", "Please select models to remove")
                return

            model_ids = {selected[i].text() for i in range(0, len(selected), self.table.columnCount())}
            if not _confirm(self, "Remove Models", f"Remove {len(model_ids)} selected models?"):
                return

            for mid in model_ids:
                self.models.pop(mid, None)
        else:
            if not _confirm(self, "Remove Model", f"Remove model '{model_id}'?"):
                return
            self.models.pop(model_id, None)

        self._update_table()
        self.app.mark_dirty()

    def _import_models(self):
        """Import models from JSON"""
        dlg = JsonImportDialog(
            self, "Import Models",
            "Paste or load models JSON. Supported formats:\n"
            "- {modelId: spec} map\n"
            "- {'models': {modelId: spec}} object\n"
            "- Array of model specs with 'id' field"
        )
        if dlg.exec() != QDialog.Accepted:
            return

        try:
            models_map = _extract_models_map(dlg.result_data)
        except ValueError as e:
            QMessageBox.warning(self, "Import Error", str(e))
            return

        added = 0
        updated = 0
        for model_id, spec in models_map.items():
            if model_id in self.models:
                updated += 1
            else:
                added += 1
            self.models[model_id] = spec

        self._update_table()
        self.app.mark_dirty()
        QMessageBox.information(
            self, "Import Complete",
            f"Added {added} new models, updated {updated} existing models"
        )

    def _export_models(self):
        """Export models to JSON file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Models", f"{self.provider_key}-models.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.models, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _apply_catalog(self):
        """Apply model catalog to update existing models"""
        if not self.app.model_catalog.loaded():
            if not _confirm(self, "No Catalog", "No model catalog loaded. Load one now?"):
                return
            if not self.app.load_model_catalog():
                return

        catalog = self.app.model_catalog
        models = catalog.models_for(self.provider_key, self.provider_cfg.get("npm"))

        if not models:
            QMessageBox.information(self, "Apply Catalog", "No matching models found in catalog")
            return

        # Show preview dialog
        preview_dlg = CatalogPreviewDialog(self, models, self.models)
        if preview_dlg.exec() != QDialog.Accepted:
            return

        overwrite = preview_dlg.overwrite_checkbox.isChecked()
        updated = 0

        for model_id in preview_dlg.selected_models:
            if model_id in self.models and model_id in models:
                self.models[model_id] = _merge_model_spec(
                    self.models[model_id], models[model_id], overwrite
                )
                updated += 1

        self._update_table()
        self.app.mark_dirty()
        QMessageBox.information(
            self, "Apply Catalog",
            f"Updated {updated} models from catalog"
        )

    def _bulk_edit(self):
        """Bulk edit selected models"""
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Bulk Edit", "Please select models to edit")
            return

        model_ids = {selected[i].text() for i in range(0, len(selected), self.table.columnCount())}
        if not model_ids:
            return

        dlg = BulkEditDialog(self, self.models, model_ids)
        if dlg.exec() == QDialog.Accepted:
            for model_id in model_ids:
                if model_id in self.models:
                    self.models[model_id] = dlg.apply_to_model(self.models[model_id])
            self._update_table()
            self.app.mark_dirty()

    def result(self) -> dict:
        """Get result models"""
        return self.models

class CatalogPreviewDialog(QDialog):
    """Dialog to preview catalog application"""

    def __init__(self, parent, catalog_models: dict, existing_models: dict):
        super().__init__(parent)
        self.setWindowTitle("Apply Model Catalog")
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        # Info
        info_label = QLabel(
            f"Found {len(catalog_models)} models in catalog that match this provider.\n"
            "Select which models to update and whether to overwrite existing values."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Search
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search models...")
        self.search_edit.textChanged.connect(self._filter_models)
        search_layout.addWidget(self.search_edit)
        layout.addLayout(search_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Apply", "Model ID", "Name", "Current Values", "Catalog Values"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        # Overwrite checkbox
        self.overwrite_checkbox = QCheckBox("Overwrite existing values (otherwise only fill missing fields)")
        layout.addWidget(self.overwrite_checkbox)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Populate table
        self.catalog_models = catalog_models
        self.existing_models = existing_models
        self._update_table()

    def _update_table(self):
        """Update table with models"""
        self.table.setRowCount(len(self.catalog_models))
        for row, (model_id, catalog_spec) in enumerate(sorted(self.catalog_models.items())):
            # Apply checkbox
            apply_check = QCheckBox()
            apply_check.setChecked(model_id in self.existing_models)
            self.table.setCellWidget(row, 0, apply_check)

            # Model ID
            self.table.setItem(row, 1, QTableWidgetItem(model_id))

            # Name
            name = catalog_spec.get("name", "")
            self.table.setItem(row, 2, QTableWidgetItem(name))

            # Current values
            current_spec = self.existing_models.get(model_id, {})
            current_text = self._spec_to_text(current_spec)
            self.table.setItem(row, 3, QTableWidgetItem(current_text))

            # Catalog values
            catalog_text = self._spec_to_text(catalog_spec)
            self.table.setItem(row, 4, QTableWidgetItem(catalog_text))

    def _filter_models(self, text: str):
        """Filter models by search text"""
        if not text:
            self._update_table()
            return

        text = text.lower()
        filtered = {
            mid: spec for mid, spec in self.catalog_models.items()
            if text in mid.lower() or
               (isinstance(spec.get("name"), str) and text in spec["name"].lower())
        }

        self.table.setRowCount(len(filtered))
        for row, (model_id, catalog_spec) in enumerate(sorted(filtered.items())):
            apply_check = QCheckBox()
            apply_check.setChecked(model_id in self.existing_models)
            self.table.setCellWidget(row, 0, apply_check)

            self.table.setItem(row, 1, QTableWidgetItem(model_id))
            self.table.setItem(row, 2, QTableWidgetItem(catalog_spec.get("name", "")))

            current_spec = self.existing_models.get(model_id, {})
            current_text = self._spec_to_text(current_spec)
            self.table.setItem(row, 3, QTableWidgetItem(current_text))

            catalog_text = self._spec_to_text(catalog_spec)
            self.table.setItem(row, 4, QTableWidgetItem(catalog_text))

    def _spec_to_text(self, spec: dict) -> str:
        """Convert model spec to display text"""
        parts = []
        if "name" in spec:
            parts.append(f"name: {spec['name']}")
        if "attachment" in spec:
            parts.append(f"attachment: {spec['attachment']}")
        if "reasoning" in spec:
            parts.append(f"reasoning: {spec['reasoning']}")
        if "cost" in spec and isinstance(spec["cost"], dict):
            cost = spec["cost"]
            if "input" in cost or "output" in cost:
                parts.append(f"cost: {cost.get('input', '')}/{cost.get('output', '')}")
        if "limit" in spec and isinstance(spec["limit"], dict):
            limit = spec["limit"]
            if "context" in limit or "output" in limit:
                parts.append(f"limit: {limit.get('context', '')}/{limit.get('output', '')}")
        return ", ".join(parts)

    @property
    def selected_models(self) -> List[str]:
        """Get selected model IDs"""
        selected = []
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 0).isChecked():
                selected.append(self.table.item(row, 1).text())
        return selected

class BulkEditDialog(QDialog):
    """Dialog for bulk editing model fields"""

    def __init__(self, parent, models: dict, model_ids: set):
        super().__init__(parent)
        self.setWindowTitle("Bulk Edit Models")
        self.resize(500, 400)

        self.models = models
        self.model_ids = model_ids

        layout = QVBoxLayout(self)

        # Info
        info_label = QLabel(f"Editing {len(model_ids)} models")
        layout.addWidget(info_label)

        # Fields to edit
        self.field_combo = QComboBox()
        self.field_combo.addItems(MODEL_FIELDS)
        layout.addWidget(self.field_combo)

        # Value
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("Leave empty to remove field")
        layout.addWidget(self.value_edit)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def apply_to_model(self, model: dict) -> dict:
        """Apply bulk edit to a model"""
        field = self.field_combo.currentText()
        value = self.value_edit.text().strip()

        if not field:
            return model

        model = dict(model)

        # Handle nested fields
        if "." in field:
            parts = field.split(".")
            current = model
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
                if not isinstance(current, dict):
                    current = {}
            last_part = parts[-1]

            if value:
                try:
                    if last_part in ("input", "output", "cache_read", "cache_write"):
                        current[last_part] = float(value)
                    else:
                        current[last_part] = int(value)
                except ValueError:
                    pass
            else:
                current.pop(last_part, None)
                # Clean up empty parent objects
                for part in reversed(parts[:-1]):
                    parent = model
                    for p in parts[:parts.index(part)]:
                        parent = parent[p]
                    if not parent.get(part):
                        parent.pop(part, None)
        else:
            if value:
                if field in ("attachment", "reasoning", "temperature", "tool_call"):
                    model[field] = value.lower() in ("true", "1", "yes")
                else:
                    try:
                        model[field] = int(value)
                    except ValueError:
                        try:
                            model[field] = float(value)
                        except ValueError:
                            model[field] = value
            else:
                model.pop(field, None)

        return model

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
            self.result_data = json.loads(self.editor.toPlainText())
            self.accept()
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", str(e))

class ProvidersTab(QWidget):
    """Enhanced providers tab with search and bulk operations"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.rows = []  # (provider_name, npm_edit, name_edit)

        layout = QVBoxLayout(self)

        # Search and buttons
        top_layout = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search providers...")
        self.search_edit.textChanged.connect(self._filter_providers)
        top_layout.addWidget(self.search_edit)

        for text, slot in [
            ("+ Add", self._add_provider),
            ("Import", self._import_providers),
            ("Export", self._export_providers),
            ("Enable All", lambda: self._set_all_enabled(True)),
            ("Disable All", lambda: self._set_all_enabled(False))
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            top_layout.addWidget(btn)

        layout.addLayout(top_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Provider", "npm", "Name", "Models / Options", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        layout.addWidget(self.table)

        # Status
        self.status_label = QLabel()
        layout.addWidget(self.status_label)

    def _filter_providers(self, text: str):
        """Filter providers by search text"""
        if not text:
            self.refresh()
            return

        text = text.lower()
        providers = self.app.cfg.data.get("provider", {}) if self.app.cfg else {}
        filtered = {
            name: cfg for name, cfg in providers.items()
            if text in name.lower() or
               (isinstance(cfg.get("npm"), str) and text in cfg["npm"].lower()) or
               (isinstance(cfg.get("name"), str) and text in cfg["name"].lower())
        }

        self._update_table(filtered)

    def _update_table(self, providers: Optional[dict] = None):
        """Update table with providers"""
        if providers is None:
            providers = self.app.cfg.data.get("provider", {}) if self.app.cfg else {}

        self.table.setRowCount(len(providers))
        self.rows = []

        for row, (name, cfg) in enumerate(sorted(providers.items())):
            if not isinstance(cfg, dict):
                cfg = {}

            # Provider name
            self.table.setItem(row, 0, QTableWidgetItem(name))

            # npm
            npm_edit = MaskedLineEdit(cfg.get("npm", ""), field_name="npm")
            npm_edit.edit.editingFinished.connect(self.app.mark_dirty)
            self.table.setCellWidget(row, 1, npm_edit)

            # Name
            name_edit = MaskedLineEdit(cfg.get("name", ""), field_name="name")
            name_edit.edit.editingFinished.connect(self.app.mark_dirty)
            self.table.setCellWidget(row, 2, name_edit)

            # Models/Options
            n_models = len(cfg.get("models", {})) if isinstance(cfg.get("models"), dict) else 0
            base_url = cfg.get("options", {}).get("baseURL", "") if isinstance(cfg.get("options"), dict) else ""

            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(2, 0, 2, 0)

            summary = QLabel(f"{n_models} models  {base_url}")
            summary.setToolTip(json.dumps(cfg, ensure_ascii=False, indent=2)[:4000])
            cell_layout.addWidget(summary, 1)

            models_btn = QPushButton("Models...")
            models_btn.clicked.connect(lambda _, n=name: self._edit_models(n))
            cell_layout.addWidget(models_btn)

            options_btn = QPushButton("Options...")
            options_btn.clicked.connect(lambda _, n=name: self._edit_options(n))
            cell_layout.addWidget(options_btn)

            self.table.setCellWidget(row, 3, cell)

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedWidth(60)
            edit_btn.clicked.connect(lambda _, n=name: self._edit_provider(n))
            actions_layout.addWidget(edit_btn)

            remove_btn = QPushButton("Remove")
            remove_btn.setFixedWidth(60)
            remove_btn.clicked.connect(lambda _, n=name: self._remove_provider(n))
            actions_layout.addWidget(remove_btn)

            self.table.setCellWidget(row, 4, actions_widget)

            self.rows.append((name, npm_edit, name_edit))

        self.status_label.setText(f"{len(providers)} providers")

    def refresh(self):
        """Refresh table with current data"""
        self._update_table()

    def _add_provider(self):
        """Add new provider"""
        self.app.snapshot_state()
        name, ok = QInputDialog.getText(
            self, "Add Provider", "Provider key:",
            QLineEdit.Normal, "new-provider"
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        providers = self.app.cfg.data.setdefault("provider", {})

        if name in providers:
            QMessageBox.warning(self, "Error", f"Provider '{name}' already exists")
            return

        providers[name] = {
            "npm": "@ai-sdk/openai",
            "name": name,
            "models": {}
        }
        self.app.mark_dirty()
        self.refresh()

    def _edit_provider(self, name: Optional[str] = None):
        """Edit provider"""
        self.app.snapshot_state()
        if name is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Edit", "Please select a provider to edit")
                return
            name = selected[0].text()

        providers = self.app.cfg.data.get("provider", {})
        if name not in providers:
            QMessageBox.warning(self, "Error", f"Provider '{name}' not found")
            return

        new_name, ok = QInputDialog.getText(
            self, "Edit Provider", "New provider key:",
            QLineEdit.Normal, name
        )
        if not ok:
            return

        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Error", "Provider key cannot be empty")
            return

        if new_name != name and new_name in providers:
            QMessageBox.warning(self, "Error", f"Provider '{new_name}' already exists")
            return

        if new_name != name:
            providers[new_name] = providers.pop(name)

        self.app.mark_dirty()
        self.refresh()

    def _remove_provider(self, name: Optional[str] = None):
        """Remove provider(s)"""
        self.app.snapshot_state()
        if name is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Remove", "Please select providers to remove")
                return

            names = {selected[i].text() for i in range(0, len(selected), self.table.columnCount())}
            if not _confirm(self, "Remove Providers", f"Remove {len(names)} selected providers?"):
                return

            providers = self.app.cfg.data.get("provider", {})
            for name in names:
                providers.pop(name, None)
        else:
            if not _confirm(self, "Remove Provider", f"Remove provider '{name}'?"):
                return

            self.app.cfg.data.get("provider", {}).pop(name, None)

        self.app.mark_dirty()
        self.refresh()

    def _import_providers(self):
        """Import providers from JSON"""
        self.app.snapshot_state()
        dlg = JsonImportDialog(
            self, "Import Providers",
            "Paste or load provider JSON. Supported formats:\n"
            "- Single provider object\n"
            "- {name: provider} map\n"
            "- Full config with 'provider' key"
        )
        if dlg.exec() != QDialog.Accepted:
            return

        try:
            parsed = parse_provider_import(dlg.result_data)
        except ValueError as e:
            QMessageBox.warning(self, "Import Error", str(e))
            return

        providers = self.app.cfg.data.setdefault("provider", {})
        added = 0
        updated = 0

        for name, cfg in parsed.items():
            if name in providers:
                if _confirm(
                    self, "Provider Exists",
                    f"Provider '{name}' already exists. Merge with existing?"
                ):
                    providers[name] = merge_dict(providers[name], cfg)
                    updated += 1
            else:
                providers[name] = cfg
                added += 1

        self.app.mark_dirty()
        self.refresh()
        QMessageBox.information(
            self, "Import Complete",
            f"Added {added} new providers, updated {updated} existing providers"
        )

    def _export_providers(self):
        """Export providers to JSON file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Providers", "providers.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        providers = self.app.cfg.data.get("provider", {})
        if not providers:
            QMessageBox.information(self, "Export", "No providers to export")
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(providers, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _set_all_enabled(self, enabled: bool):
        """Enable/disable all providers"""
        # Providers don't have an enabled flag, but we can add one for UI purposes
        # This is just a placeholder for potential future functionality
        QMessageBox.information(self, "Info", "Providers don't have an enabled/disabled state")

    def _edit_models(self, name: str):
        """Edit models for provider"""
        self.app.snapshot_state()
        providers = self.app.cfg.data.get("provider", {})
        if name not in providers:
            return

        dlg = ModelsManagerDialog(self.app, name, providers[name])
        if dlg.exec() == QDialog.Accepted:
            providers[name]["models"] = dlg.result()
            self.app.mark_dirty()
            self.refresh()

    def _edit_options(self, name: str):
        """Edit options for provider"""
        self.app.snapshot_state()
        providers = self.app.cfg.data.get("provider", {})
        if name not in providers:
            return

        current = providers[name].get("options", {})
        dlg = JsonImportDialog(
            self, f"Options - {name}",
            "Edit provider options (baseURL, headers, etc.)"
        )
        dlg.editor.setPlainText(json.dumps(current, indent=2, ensure_ascii=False))

        if dlg.exec() == QDialog.Accepted:
            try:
                options = json.loads(dlg.editor.toPlainText())
                if not isinstance(options, dict):
                    raise ValueError("Options must be a JSON object")
                providers[name]["options"] = options
                self.app.mark_dirty()
                self.refresh()
            except (json.JSONDecodeError, ValueError) as e:
                QMessageBox.warning(self, "Error", str(e))

    def collect(self, data: dict):
        """Collect data from UI"""
        providers = data.setdefault("provider", {})
        seen = set()

        for row in range(self.table.rowCount()):
            old_name = self.rows[row][0]
            new_name = self.table.item(row, 0).text().strip()

            if not new_name:
                continue

            if new_name in seen:
                raise ValueError(f"Duplicate provider key: {new_name!r}")
            seen.add(new_name)

            npm_edit = self.rows[row][1]
            name_edit = self.rows[row][2]

            old_cfg = dict(providers.get(old_name, {}))
            old_cfg["npm"] = npm_edit.value()
            if name_edit.value():
                old_cfg["name"] = name_edit.value()
            else:
                old_cfg.pop("name", None)

            providers[new_name] = old_cfg

class MCPHeadersDialog(QDialog):
    """Edit the `headers` map (name -> value) of a remote MCP server.

    Used for HTTP auth headers such as `Authorization: Bearer <token>`.
    """

    def __init__(self, parent=None, headers=None):
        super().__init__(parent)
        self.setWindowTitle("MCP Headers")
        self.setMinimumSize(480, 320)
        headers = headers or {}

        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Header", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.table)

        btns = QHBoxLayout()
        add_b = QPushButton("+ Add")
        add_b.clicked.connect(self._add)
        rem_b = QPushButton("Remove")
        rem_b.clicked.connect(self._remove)
        btns.addWidget(add_b)
        btns.addWidget(rem_b)
        btns.addStretch(1)
        lay.addLayout(btns)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.table.blockSignals(True)
        for name, value in sorted(headers.items()):
            self._insert_row(str(name), str(value))
        self.table.blockSignals(False)

    def _insert_row(self, name, value):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(name))
        self.table.setItem(r, 1, QTableWidgetItem(value))

    def _add(self):
        name, ok = QInputDialog.getText(self, "Header", "Header name:")
        if ok and name.strip():
            self._insert_row(name.strip(), "")
            self.table.setCurrentCell(self.table.rowCount() - 1, 1)

    def _remove(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def headers(self) -> dict:
        out = {}
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0)
            value = self.table.item(r, 1)
            n = name.text().strip() if name else ""
            v = value.text() if value else ""
            if n:
                out[n] = v
        return out


class McpTab(QWidget):
    """Enhanced MCP tab with search and bulk operations"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.cbs = {}  # name -> QCheckBox

        layout = QVBoxLayout(self)

        # Search and buttons
        top_layout = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search servers...")
        self.search_edit.textChanged.connect(self._filter_servers)
        top_layout.addWidget(self.search_edit)

        for text, slot in [
            ("+ Add", self._add_server),
            ("Import", self._import_servers),
            ("Export", self._export_servers),
            ("Enable All", lambda: self._set_all_enabled(True)),
            ("Disable All", lambda: self._set_all_enabled(False))
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            top_layout.addWidget(btn)

        layout.addLayout(top_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Enabled", "Name", "Type", "Command / URL", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        layout.addWidget(self.table)

        # Status
        self.status_label = QLabel()
        layout.addWidget(self.status_label)

    def _filter_servers(self, text: str):
        """Filter servers by search text"""
        if not text:
            self.refresh()
            return

        text = text.lower()
        mcp = self.app.cfg.data.get("mcp", {}) if self.app.cfg else {}
        filtered = {
            name: cfg for name, cfg in mcp.items()
            if text in name.lower() or
               (isinstance(cfg.get("type"), str) and text in cfg["type"].lower()) or
               (isinstance(cfg.get("url"), str) and text in cfg["url"].lower()) or
               (isinstance(cfg.get("command"), list) and any(text in str(c).lower() for c in cfg["command"]))
        }

        self._update_table(filtered)

    def _update_table(self, servers: Optional[dict] = None):
        """Update table with servers"""
        if servers is None:
            servers = self.app.cfg.data.get("mcp", {}) if self.app.cfg else {}

        self.table.setRowCount(len(servers))
        self.cbs = {}

        for row, (name, cfg) in enumerate(sorted(servers.items())):
            if not isinstance(cfg, dict):
                cfg = {}

            # Enabled checkbox
            enabled_check = QCheckBox()
            enabled_check.setChecked(bool(cfg.get("enabled", True)))
            enabled_check.stateChanged.connect(lambda _, n=name: self._toggle_enabled(n))
            self.table.setCellWidget(row, 0, enabled_check)
            self.cbs[name] = enabled_check

            # Name
            self.table.setItem(row, 1, QTableWidgetItem(name))

            # Type
            self.table.setItem(row, 2, QTableWidgetItem(str(cfg.get("type", ""))))

            # Command/URL
            if cfg.get("type") == "local":
                cmd = " ".join(cfg.get("command", []))
            else:
                cmd = cfg.get("url", "")
            self.table.setItem(row, 3, QTableWidgetItem(cmd))

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedWidth(60)
            edit_btn.clicked.connect(lambda _, n=name: self._edit_server(n))
            actions_layout.addWidget(edit_btn)

            headers_btn = QPushButton("Headers")
            headers_btn.setFixedWidth(70)
            headers_btn.clicked.connect(lambda _, n=name: self._edit_headers(n))
            actions_layout.addWidget(headers_btn)

            remove_btn = QPushButton("Remove")
            remove_btn.setFixedWidth(60)
            remove_btn.clicked.connect(lambda _, n=name: self._remove_server(n))
            actions_layout.addWidget(remove_btn)

            self.table.setCellWidget(row, 4, actions_widget)

        self.status_label.setText(f"{len(servers)} servers")

    def refresh(self):
        """Refresh table with current data"""
        self._update_table()

    def _add_server(self):
        """Add new MCP server"""
        self.app.snapshot_state()
        name, ok = QInputDialog.getText(
            self, "Add MCP Server", "Server key:",
            QLineEdit.Normal, "new-server"
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        mcp = self.app.cfg.data.setdefault("mcp", {})

        if name in mcp:
            QMessageBox.warning(self, "Error", f"Server '{name}' already exists")
            return

        mcp[name] = {
            "type": "remote",
            "url": "https://",
            "enabled": True
        }
        self.app.mark_dirty()
        self.refresh()

    def _edit_server(self, name: Optional[str] = None):
        """Edit MCP server"""
        self.app.snapshot_state()
        if name is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Edit", "Please select a server to edit")
                return
            name = selected[0].text()

        mcp = self.app.cfg.data.get("mcp", {})
        if name not in mcp:
            QMessageBox.warning(self, "Error", f"Server '{name}' not found")
            return

        new_name, ok = QInputDialog.getText(
            self, "Edit MCP Server", "New server key:",
            QLineEdit.Normal, name
        )
        if not ok:
            return

        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Error", "Server key cannot be empty")
            return

        if new_name != name and new_name in mcp:
            QMessageBox.warning(self, "Error", f"Server '{new_name}' already exists")
            return

        if new_name != name:
            mcp[new_name] = mcp.pop(name)

        self.app.mark_dirty()
        self.refresh()

    def _edit_headers(self, name: Optional[str] = None):
        """Edit the `headers` map of a (typically remote) MCP server."""
        if name is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Headers", "Please select a server")
                return
            name = selected[0].text()

        mcp = self.app.cfg.data.get("mcp", {})
        cfg = mcp.get(name)
        if not isinstance(cfg, dict):
            QMessageBox.warning(self, "Error", f"Server '{name}' not found")
            return

        if cfg.get("type") == "local":
            QMessageBox.information(
                self, "Headers", "Headers apply to remote MCP servers only."
            )
            return

        headers = cfg.get("headers") if isinstance(cfg.get("headers"), dict) else {}
        dlg = MCPHeadersDialog(self, headers=headers)
        if dlg.exec() != QDialog.Accepted:
            return

        new_headers = dlg.headers()
        self.app.snapshot_state()
        if new_headers:
            cfg["headers"] = new_headers
        else:
            cfg.pop("headers", None)
        self.app.mark_dirty()
        self.refresh()

    def _remove_server(self, name: Optional[str] = None):
        """Remove MCP server(s)"""
        self.app.snapshot_state()
        if name is None:
            selected = self.table.selectedItems()
            if not selected:
                QMessageBox.information(self, "Remove", "Please select servers to remove")
                return

            names = {selected[i].text() for i in range(0, len(selected), self.table.columnCount())}
            if not _confirm(self, "Remove Servers", f"Remove {len(names)} selected servers?"):
                return

            mcp = self.app.cfg.data.get("mcp", {})
            for name in names:
                mcp.pop(name, None)
        else:
            if not _confirm(self, "Remove Server", f"Remove server '{name}'?"):
                return

            self.app.cfg.data.get("mcp", {}).pop(name, None)

        self.app.mark_dirty()
        self.refresh()

    def _import_servers(self):
        """Import MCP servers from JSON"""
        self.app.snapshot_state()
        dlg = JsonImportDialog(
            self, "Import MCP Servers",
            "Paste or load MCP server JSON. Supported formats:\n"
            "- Single server object\n"
            "- {name: server} map\n"
            "- Full config with 'mcp' key"
        )
        if dlg.exec() != QDialog.Accepted:
            return

        try:
            parsed = parse_mcp_import(dlg.result_data)
        except ValueError as e:
            QMessageBox.warning(self, "Import Error", str(e))
            return

        mcp = self.app.cfg.data.setdefault("mcp", {})
        added = 0
        updated = 0

        for name, cfg in parsed.items():
            if name in mcp:
                if _confirm(
                    self, "Server Exists",
                    f"Server '{name}' already exists. Overwrite?"
                ):
                    mcp[name] = cfg
                    updated += 1
            else:
                mcp[name] = cfg
                added += 1

        self.app.mark_dirty()
        self.refresh()
        QMessageBox.information(
            self, "Import Complete",
            f"Added {added} new servers, updated {updated} existing servers"
        )

    def _export_servers(self):
        """Export MCP servers to JSON file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export MCP Servers", "mcp-servers.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        mcp = self.app.cfg.data.get("mcp", {})
        if not mcp:
            QMessageBox.information(self, "Export", "No MCP servers to export")
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(mcp, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _set_all_enabled(self, enabled: bool):
        """Enable/disable all servers"""
        self.app.snapshot_state()
        mcp = self.app.cfg.data.get("mcp", {})
        for name in mcp:
            mcp[name]["enabled"] = enabled
        self.app.mark_dirty()
        self.refresh()

    def _toggle_enabled(self, name: str):
        """Toggle enabled state for server"""
        self.app.snapshot_state()
        mcp = self.app.cfg.data.get("mcp", {})
        if name in mcp:
            mcp[name]["enabled"] = self.cbs[name].isChecked()
            self.app.mark_dirty()

    def collect(self, data: dict):
        """Collect data from UI"""
        # Enabled states are already applied live
        pass

class PluginsTab(QWidget):
    """Enhanced plugins tab with search and bulk operations"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.state_store = PluginStateStore()
        self.cbs = {}  # plugin -> QCheckBox

        layout = QVBoxLayout(self)

        # Search and buttons
        top_layout = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search plugins...")
        self.search_edit.textChanged.connect(self._filter_plugins)
        top_layout.addWidget(self.search_edit)

        for text, slot in [
            ("+ Add", self._add_plugin),
            ("Import", self._import_plugins),
            ("Export", self._export_plugins),
            ("Enable All", lambda: self._set_all_enabled(True)),
            ("Disable All", lambda: self._set_all_enabled(False)),
            ("Remove Selected", self._remove_selected)
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            top_layout.addWidget(btn)

        layout.addLayout(top_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Enabled", "Plugin"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        layout.addWidget(self.table)

        # Status
        self.status_label = QLabel(
            "Disabled plugins are removed from the saved config but remembered "
            "so you can re-enable them later."
        )
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

    def _filter_plugins(self, text: str):
        """Filter plugins by search text"""
        if not text:
            self.refresh()
            return

        text = text.lower()
        plugins = self._get_plugins()
        disabled = self.state_store.get_disabled(self.app.cfg.path) if self.app.cfg else set()

        filtered = [
            (p, p not in disabled) for p in plugins
            if text in p.lower()
        ]

        self._update_table(filtered)

    def _update_table(self, plugins: Optional[List[Tuple[str, bool]]] = None):
        """Update table with plugins"""
        if plugins is None:
            plugins = self._get_plugins()
            disabled = self.state_store.get_disabled(self.app.cfg.path) if self.app.cfg else set()
            plugins = [(p, p not in disabled) for p in plugins]

        self.table.setRowCount(len(plugins))
        self.cbs = {}

        for row, (plugin, enabled) in enumerate(plugins):
            # Enabled checkbox
            enabled_check = QCheckBox()
            enabled_check.setChecked(enabled)
            enabled_check.stateChanged.connect(self.app.mark_dirty)
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setAlignment(Qt.AlignCenter)
            cell_layout.addWidget(enabled_check)
            self.table.setCellWidget(row, 0, cell)
            self.cbs[plugin] = enabled_check

            # Plugin
            self.table.setItem(row, 1, QTableWidgetItem(plugin))

    def _get_plugins(self) -> List[str]:
        """Get all plugins: active (from config) plus remembered-disabled ones,
        so disabled plugins reappear in the list and can be re-enabled."""
        plugins = self.app.cfg.data.get("plugin", []) if self.app.cfg else []
        if not isinstance(plugins, list):
            plugins = []
        active = {str(p) for p in plugins}
        if self.app.cfg is not None:
            active |= self.state_store.get_disabled(self.app.cfg.path)
        return sorted(active)

    def refresh(self):
        """Refresh table with current data"""
        self._update_table()

    def _add_plugin(self):
        """Add new plugin"""
        self.app.snapshot_state()
        plugin, ok = QInputDialog.getText(
            self, "Add Plugin", "Plugin (npm spec):",
            QLineEdit.Normal, "@opencode/plugin-example"
        )
        if not ok or not plugin.strip():
            return

        plugin = plugin.strip()
        if plugin in self.cbs:
            QMessageBox.warning(self, "Error", f"Plugin '{plugin}' already exists")
            return

        self._insert_plugin(plugin, True)
        self.app.mark_dirty()

    def _insert_plugin(self, plugin: str, enabled: bool):
        """Insert plugin into table"""
        self.table.insertRow(self.table.rowCount())
        row = self.table.rowCount() - 1

        # Enabled checkbox
        enabled_check = QCheckBox()
        enabled_check.setChecked(enabled)
        enabled_check.stateChanged.connect(self.app.mark_dirty)
        cell = QWidget()
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.setAlignment(Qt.AlignCenter)
        cell_layout.addWidget(enabled_check)
        self.table.setCellWidget(row, 0, cell)
        self.cbs[plugin] = enabled_check

        # Plugin
        self.table.setItem(row, 1, QTableWidgetItem(plugin))

    def _import_plugins(self):
        """Import plugins from JSON"""
        self.app.snapshot_state()
        dlg = JsonImportDialog(
            self, "Import Plugins",
            "Paste or load plugins JSON. Supported formats:\n"
            "- Array of plugin strings\n"
            "- {'plugin': [...]} object"
        )
        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.result_data
        if isinstance(data, dict) and "plugin" in data:
            data = data["plugin"]

        if not isinstance(data, list):
            QMessageBox.warning(self, "Import Error", "Expected a JSON array of plugin strings")
            return

        existing = set(self.cbs.keys())
        added = 0

        for item in data:
            if isinstance(item, str) and item not in existing:
                self._insert_plugin(item, True)
                added += 1

        self.app.mark_dirty()
        QMessageBox.information(self, "Import Complete", f"Added {added} new plugins")

    def _export_plugins(self):
        """Export plugins to JSON file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Plugins", "plugins.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        plugins = [p for p, cb in self.cbs.items() if cb.isChecked()]
        if not plugins:
            QMessageBox.information(self, "Export", "No plugins to export")
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(plugins, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _set_all_enabled(self, enabled: bool):
        """Enable/disable all plugins"""
        self.app.snapshot_state()
        for cb in self.cbs.values():
            cb.setChecked(enabled)
        self.app.mark_dirty()

    def _remove_selected(self):
        """Remove selected plugins"""
        self.app.snapshot_state()
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Remove", "Please select plugins to remove")
            return

        plugins = {selected[i].text() for i in range(0, len(selected), self.table.columnCount())}
        if not plugins:
            return

        if not _confirm(self, "Remove Plugins", f"Remove {len(plugins)} selected plugins?"):
            return

        for plugin in plugins:
            row = self._find_plugin_row(plugin)
            if row >= 0:
                self.table.removeRow(row)
            self.cbs.pop(plugin, None)

        self.app.mark_dirty()

    def _find_plugin_row(self, plugin: str) -> int:
        """Find row for plugin"""
        for row in range(self.table.rowCount()):
            if self.table.item(row, 1).text() == plugin:
                return row
        return -1

    def collect(self, data: dict):
        """Collect data from UI"""
        active = []
        disabled = []

        for plugin, cb in self.cbs.items():
            if cb.isChecked():
                active.append(plugin)
            else:
                disabled.append(plugin)

        data["plugin"] = active
        if self.app.cfg:
            self.state_store.set_disabled(self.app.cfg.path, set(disabled))

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

class StringListEdit(QWidget):
    """Editable list of strings backed by a nested key path in the config."""

    def __init__(self, app, data_path, placeholder="item"):
        super().__init__()
        self.app = app
        self.data_path = data_path  # e.g. ["disabled_providers"]
        self.placeholder = placeholder

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setMaximumHeight(110)
        lay.addWidget(self.list)

        btns = QHBoxLayout()
        add_b = QPushButton("+")
        add_b.setFixedWidth(28)
        add_b.clicked.connect(self._add)
        rem_b = QPushButton("-")
        rem_b.setFixedWidth(28)
        rem_b.clicked.connect(self._remove)
        btns.addWidget(add_b)
        btns.addWidget(rem_b)
        btns.addStretch(1)
        lay.addLayout(btns)

    def _node(self, data):
        node = data
        for k in self.data_path:
            if not isinstance(node, dict):
                return None
            node = node.get(k)
        return node

    def refresh(self):
        self.list.clear()
        node = self._node(self.app.cfg.data if self.app.cfg else {})
        if isinstance(node, list):
            for item in node:
                self.list.addItem(str(item))

    def collect(self, data):
        vals = [self.list.item(i).text().strip()
                for i in range(self.list.count())
                if self.list.item(i).text().strip()]
        node = data
        for k in self.data_path[:-1]:
            if not isinstance(node.get(k), dict):
                node[k] = {}
            node = node[k]
        last = self.data_path[-1]
        if vals:
            node[last] = vals
        else:
            node.pop(last, None)

    def _add(self):
        text, ok = QInputDialog.getText(self, "Add", f"New {self.placeholder}:")
        if ok and text.strip():
            self.list.addItem(text.strip())
            self.app.mark_dirty()

    def _remove(self):
        rows = sorted({self.list.row(it) for it in self.list.selectedItems()}, reverse=True)
        for r in rows:
            self.list.takeItem(r)
        if rows:
            self.app.mark_dirty()


class BoolObjectCombo(QWidget):
    """Tri-state selector for bool|object keys (formatter, lsp).
    Custom-object values are preserved verbatim (edit via Raw JSON)."""

    def __init__(self, app, key):
        super().__init__()
        self.app = app
        self.key = key
        self._loading = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.combo.addItem("Disabled (omit)", "omit")
        self.combo.addItem("Enable built-ins (true)", "true")
        self.combo.addItem("Custom object (Raw JSON)", "custom")
        self.combo.currentIndexChanged.connect(self._changed)
        lay.addWidget(self.combo, 1)
        self.note = QLabel("")
        self.note.setStyleSheet("color: gray;")
        lay.addWidget(self.note, 2)

    def _changed(self):
        if not self._loading:
            self.app.mark_dirty()

    def refresh(self):
        self._loading = True
        node = self.app.cfg.data.get(self.key) if self.app.cfg else None
        if node is True:
            self.combo.setCurrentIndex(1)
        elif node is False or node is None:
            self.combo.setCurrentIndex(0)
        else:
            self.combo.setCurrentIndex(2)
        self.note.setText("preserved as-is; edit shape in Raw JSON" if self.combo.currentIndex() == 2 else "")
        self._loading = False

    def collect(self, data):
        idx = self.combo.currentIndex()
        if idx == 0:
            data.pop(self.key, None)
        elif idx == 1:
            data[self.key] = True
        # idx == 2 (custom): leave the existing base value untouched


class BoolMapEditor(QWidget):
    """Editable map<string,bool> backed by a nested key path (e.g. tools)."""

    def __init__(self, app, data_path):
        super().__init__()
        self.app = app
        self.data_path = data_path
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Item", "Enabled"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMaximumHeight(140)
        lay.addWidget(self.table)
        btns = QHBoxLayout()
        addb = QPushButton("+")
        addb.setFixedWidth(28)
        addb.clicked.connect(self._add)
        remb = QPushButton("-")
        remb.setFixedWidth(28)
        remb.clicked.connect(self._remove)
        btns.addWidget(addb)
        btns.addWidget(remb)
        btns.addStretch(1)
        lay.addLayout(btns)

    def _node(self, data):
        node = data
        for k in self.data_path:
            if not isinstance(node, dict):
                return None
            node = node.get(k)
        return node

    def refresh(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        node = self._node(self.app.cfg.data if self.app.cfg else {})
        if isinstance(node, dict):
            for name, enabled in sorted(node.items()):
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(str(name)))
                cb = QCheckBox()
                cb.setChecked(bool(enabled))
                self.table.setCellWidget(r, 1, cb)
                cb.stateChanged.connect(lambda *_: self._changed())
        self.table.blockSignals(False)

    def collect(self, data):
        node = data
        for k in self.data_path[:-1]:
            if not isinstance(node.get(k), dict):
                node[k] = {}
            node = node[k]
        last = self.data_path[-1]
        out = {}
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0)
            if not name or not name.text().strip():
                continue
            cb = self.table.cellWidget(r, 1)
            out[name.text().strip()] = bool(cb.isChecked())
        if out:
            node[last] = out
        else:
            node.pop(last, None)

    def _changed(self):
        self.app.mark_dirty()

    def _add(self):
        text, ok = QInputDialog.getText(self, "Add", "Item name:")
        if ok and text.strip():
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(text.strip()))
            cb = QCheckBox()
            cb.setChecked(True)
            self.table.setCellWidget(r, 1, cb)
            self.app.mark_dirty()

    def _remove(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        if rows:
            self.app.mark_dirty()


class RuntimeTab(QWidget):
    """Server, session, attachment, advanced and experimental settings."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._touched = set()

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        container = QWidget()
        scroll.setWidget(container)
        lay = QVBoxLayout(container)

        # ---- Server ----
        server_box = QGroupBox("Server (opencode serve / web)")
        sform = QFormLayout(server_box)
        self.server_port = self._spin(0)
        sform.addRow("Port", self.server_port)
        self.server_host = MaskedLineEdit("", field_name="hostname", placeholder="0.0.0.0")
        self.server_host.edit.editingFinished.connect(self._t("server"))
        sform.addRow("Hostname", self.server_host)
        self.server_mdns = QCheckBox("Enable mDNS discovery")
        self.server_mdns.stateChanged.connect(self._t("server"))
        sform.addRow("mDNS", self.server_mdns)
        self.server_mdns_domain = MaskedLineEdit("", field_name="mdnsDomain", placeholder="opencode.local")
        self.server_mdns_domain.edit.editingFinished.connect(self._t("server"))
        sform.addRow("mDNS Domain", self.server_mdns_domain)
        self.server_cors = StringListEdit(app, ["cors"], "origin")
        sform.addRow("CORS origins", self.server_cors)
        lay.addWidget(server_box)

        # ---- Session ----
        session_box = QGroupBox("Session (compaction / tool output)")
        sform = QFormLayout(session_box)
        self.comp_auto = QCheckBox("Auto-compact when context is full")
        self.comp_auto.stateChanged.connect(self._t("compaction"))
        sform.addRow("Compaction auto", self.comp_auto)
        self.comp_prune = QCheckBox("Prune old tool outputs")
        self.comp_prune.stateChanged.connect(self._t("compaction"))
        sform.addRow("Compaction prune", self.comp_prune)
        self.comp_reserved = self._spin(0)
        sform.addRow("Compaction reserved", self.comp_reserved)
        self.comp_tail = self._spin(0)
        sform.addRow("Compaction tail turns", self.comp_tail)
        self.comp_preserve = self._spin(0)
        sform.addRow("Preserve recent tokens", self.comp_preserve)
        self.tool_lines = self._spin(0)
        sform.addRow("Tool output max lines", self.tool_lines)
        self.tool_bytes = self._spin(0)
        sform.addRow("Tool output max bytes", self.tool_bytes)
        lay.addWidget(session_box)

        # ---- Attachment ----
        att_box = QGroupBox("Image attachments")
        aform = QFormLayout(att_box)
        self.att_resize = QCheckBox("Auto-resize oversized images")
        self.att_resize.stateChanged.connect(self._t("attachment"))
        aform.addRow("Auto resize", self.att_resize)
        self.att_w = self._spin(0)
        aform.addRow("Max width", self.att_w)
        self.att_h = self._spin(0)
        aform.addRow("Max height", self.att_h)
        self.att_bytes = self._spin(0)
        aform.addRow("Max base64 bytes", self.att_bytes)
        lay.addWidget(att_box)

        # ---- Advanced ----
        adv_box = QGroupBox("Advanced")
        aform = QFormLayout(adv_box)
        self.formatter = BoolObjectCombo(app, "formatter")
        self.formatter.combo.currentIndexChanged.connect(self._t("formatter"))
        aform.addRow("Formatter", self.formatter)
        self.lsp = BoolObjectCombo(app, "lsp")
        self.lsp.combo.currentIndexChanged.connect(self._t("lsp"))
        aform.addRow("LSP", self.lsp)
        self.watcher_ignore = StringListEdit(app, ["watcher", "ignore"], "glob")
        aform.addRow("Watcher ignore", self.watcher_ignore)
        self.instructions = StringListEdit(app, ["instructions"], "path/glob")
        aform.addRow("Instructions", self.instructions)
        self.skills_paths = StringListEdit(app, ["skills", "paths"], "path")
        aform.addRow("Skill paths", self.skills_paths)
        self.skills_urls = StringListEdit(app, ["skills", "urls"], "url")
        aform.addRow("Skill URLs", self.skills_urls)
        self.tools = BoolMapEditor(app, ["tools"])
        aform.addRow("Tools", self.tools)
        lay.addWidget(adv_box)

        # ---- Experimental ----
        exp_box = QGroupBox("Experimental")
        eform = QFormLayout(exp_box)
        self.exp_disable_paste = QCheckBox("Disable paste summary")
        self.exp_disable_paste.stateChanged.connect(self._t("experimental"))
        eform.addRow("Disable paste summary", self.exp_disable_paste)
        self.exp_batch = QCheckBox("Enable batch tool")
        self.exp_batch.stateChanged.connect(self._t("experimental"))
        eform.addRow("Batch tool", self.exp_batch)
        self.exp_otel = QCheckBox("Enable OpenTelemetry spans")
        self.exp_otel.stateChanged.connect(self._t("experimental"))
        eform.addRow("OpenTelemetry", self.exp_otel)
        self.exp_loop = QCheckBox("Continue loop on deny")
        self.exp_loop.stateChanged.connect(self._t("experimental"))
        eform.addRow("Continue loop on deny", self.exp_loop)
        self.exp_mcp_timeout = self._spin(0)
        eform.addRow("MCP timeout (ms)", self.exp_mcp_timeout)
        self.exp_primary_tools = StringListEdit(app, ["experimental", "primary_tools"], "tool")
        eform.addRow("Primary-only tools", self.exp_primary_tools)
        eform.addRow("Policies", self._build_policies_table())
        lay.addWidget(exp_box)
        lay.addStretch(1)

    # --- helpers ---
    def _spin(self, lo=0):
        s = QSpinBox()
        s.setRange(lo, 2**31 - 1)
        s.setSpecialValueText("(unset)")
        s.valueChanged.connect(lambda *_: self.app.mark_dirty())
        return s

    def _t(self, group):
        def _h(*_):
            self._touched.add(group)
            self.app.mark_dirty()
        return _h

    def _set_checked(self, cb, val):
        cb.blockSignals(True)
        cb.setChecked(bool(val))
        cb.blockSignals(False)

    def _set_spin(self, spin, val):
        spin.blockSignals(True)
        spin.setValue(int(val) if isinstance(val, int) and not isinstance(val, bool) else 0)
        spin.blockSignals(False)

    def _put(self, d, k, val, empty):
        if val != empty:
            d[k] = val
        else:
            d.pop(k, None)

    def _build_policies_table(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.policies = QTableWidget(0, 3)
        self.policies.setHorizontalHeaderLabels(["Effect", "Action", "Resource"])
        self.policies.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.policies.itemChanged.connect(lambda *_: self._t("experimental")())
        lay.addWidget(self.policies)
        btns = QHBoxLayout()
        addb = QPushButton("+")
        addb.setFixedWidth(28)
        addb.clicked.connect(self._add_policy)
        remb = QPushButton("-")
        remb.setFixedWidth(28)
        remb.clicked.connect(self._remove_policy)
        btns.addWidget(addb)
        btns.addWidget(remb)
        btns.addStretch(1)
        lay.addLayout(btns)
        return w

    def _add_policy(self):
        r = self.policies.rowCount()
        self.policies.insertRow(r)
        self.policies.setItem(r, 0, QTableWidgetItem("allow"))
        self.policies.setItem(r, 1, QTableWidgetItem("provider.use"))
        self.policies.setItem(r, 2, QTableWidgetItem(""))
        self._t("experimental")()

    def _remove_policy(self):
        rows = sorted({i.row() for i in self.policies.selectedItems()}, reverse=True)
        for r in rows:
            self.policies.removeRow(r)
        if rows:
            self._t("experimental")()

    # --- refresh ---
    def refresh(self):
        data = self.app.cfg.data if self.app.cfg else {}
        server = data.get("server") if isinstance(data.get("server"), dict) else {}
        self._set_spin(self.server_port, server.get("port"))
        self.server_host.set_value(server.get("hostname", ""))
        self._set_checked(self.server_mdns, server.get("mdns", False))
        self.server_mdns_domain.set_value(server.get("mdnsDomain", ""))
        self.server_cors.refresh()

        comp = data.get("compaction") if isinstance(data.get("compaction"), dict) else {}
        self._set_checked(self.comp_auto, comp.get("auto", True))
        self._set_checked(self.comp_prune, comp.get("prune", False))
        self._set_spin(self.comp_reserved, comp.get("reserved"))
        self._set_spin(self.comp_tail, comp.get("tail_turns"))
        self._set_spin(self.comp_preserve, comp.get("preserve_recent_tokens"))

        toolo = data.get("tool_output") if isinstance(data.get("tool_output"), dict) else {}
        self._set_spin(self.tool_lines, toolo.get("max_lines"))
        self._set_spin(self.tool_bytes, toolo.get("max_bytes"))

        att = data.get("attachment", {}).get("image") if isinstance(data.get("attachment"), dict) else None
        att = att if isinstance(att, dict) else {}
        self._set_checked(self.att_resize, att.get("auto_resize", True))
        self._set_spin(self.att_w, att.get("max_width"))
        self._set_spin(self.att_h, att.get("max_height"))
        self._set_spin(self.att_bytes, att.get("max_base64_bytes"))

        self.formatter.refresh()
        self.lsp.refresh()
        self.watcher_ignore.refresh()
        self.instructions.refresh()
        self.skills_paths.refresh()
        self.skills_urls.refresh()
        self.tools.refresh()

        exp = data.get("experimental") if isinstance(data.get("experimental"), dict) else {}
        self._set_checked(self.exp_disable_paste, exp.get("disable_paste_summary", False))
        self._set_checked(self.exp_batch, exp.get("batch_tool", False))
        self._set_checked(self.exp_otel, exp.get("openTelemetry", False))
        self._set_checked(self.exp_loop, exp.get("continue_loop_on_deny", False))
        self._set_spin(self.exp_mcp_timeout, exp.get("mcp_timeout"))
        self.exp_primary_tools.refresh()
        self.policies.blockSignals(True)
        self.policies.setRowCount(0)
        for pol in exp.get("policies", []) if isinstance(exp.get("policies"), list) else []:
            if not isinstance(pol, dict):
                continue
            r = self.policies.rowCount()
            self.policies.insertRow(r)
            self.policies.setItem(r, 0, QTableWidgetItem(str(pol.get("effect", ""))))
            self.policies.setItem(r, 1, QTableWidgetItem(str(pol.get("action", ""))))
            self.policies.setItem(r, 2, QTableWidgetItem(str(pol.get("resource", ""))))
        self.policies.blockSignals(False)

    # --- collect ---
    def collect(self, data):
        if "server" in self._touched:
            srv = data.setdefault("server", {})
            if not isinstance(srv, dict):
                data["server"] = srv = {}
            self._put(srv, "port", self.server_port.value() or None, None)
            self._put(srv, "hostname", self.server_host.value(), "")
            self._put(srv, "mdns", self.server_mdns.isChecked(), None)
            self._put(srv, "mdnsDomain", self.server_mdns_domain.value(), "")
            self.server_cors.collect(srv)
            if not srv:
                data.pop("server", None)

        if "compaction" in self._touched:
            comp = data.setdefault("compaction", {})
            self._put(comp, "auto", self.comp_auto.isChecked(), True)
            self._put(comp, "prune", self.comp_prune.isChecked(), False)
            self._put(comp, "reserved", self.comp_reserved.value() or None, None)
            self._put(comp, "tail_turns", self.comp_tail.value() or None, None)
            self._put(comp, "preserve_recent_tokens", self.comp_preserve.value() or None, None)
            if not comp:
                data.pop("compaction", None)

        if "tool_output" in self._touched or "compaction" in self._touched:
            toolo = data.setdefault("tool_output", {})
            self._put(toolo, "max_lines", self.tool_lines.value() or None, None)
            self._put(toolo, "max_bytes", self.tool_bytes.value() or None, None)
            if not toolo:
                data.pop("tool_output", None)

        if "attachment" in self._touched:
            att = data.setdefault("attachment", {}).setdefault("image", {})
            self._put(att, "auto_resize", self.att_resize.isChecked(), True)
            self._put(att, "max_width", self.att_w.value() or None, None)
            self._put(att, "max_height", self.att_h.value() or None, None)
            self._put(att, "max_base64_bytes", self.att_bytes.value() or None, None)
            if not att:
                data.get("attachment", {}).pop("image", None)
            if not data.get("attachment", {}):
                data.pop("attachment", None)

        if "formatter" in self._touched:
            self.formatter.collect(data)
        if "lsp" in self._touched:
            self.lsp.collect(data)

        if "watcher" in self._touched or "instructions" in self._touched \
                or "skills" in self._touched or "tools" in self._touched:
            self.watcher_ignore.collect(data.setdefault("watcher", {}))
            self.instructions.collect(data)
            self.skills_paths.collect(data.setdefault("skills", {}))
            self.skills_urls.collect(data.setdefault("skills", {}))
            self.tools.collect(data)

        if "experimental" in self._touched:
            exp = data.setdefault("experimental", {})
            self._put(exp, "disable_paste_summary", self.exp_disable_paste.isChecked(), False)
            self._put(exp, "batch_tool", self.exp_batch.isChecked(), False)
            self._put(exp, "openTelemetry", self.exp_otel.isChecked(), False)
            self._put(exp, "continue_loop_on_deny", self.exp_loop.isChecked(), False)
            self._put(exp, "mcp_timeout", self.exp_mcp_timeout.value() or None, None)
            self.exp_primary_tools.collect(exp)
            pols = []
            for r in range(self.policies.rowCount()):
                eff = self.policies.item(r, 0).text() if self.policies.item(r, 0) else ""
                act = self.policies.item(r, 1).text() if self.policies.item(r, 1) else ""
                res = self.policies.item(r, 2).text() if self.policies.item(r, 2) else ""
                if act and res:
                    pols.append({"effect": eff, "action": act, "resource": res})
            self._put(exp, "policies", pols, [])
            if not exp:
                data.pop("experimental", None)

        self._touched.clear()


class AgentEditDialog(QDialog):
    """Add/edit a custom agent."""

    def __init__(self, parent=None, name="", cfg=None):
        super().__init__(parent)
        self.setWindowTitle("Agent")
        self.setMinimumWidth(460)
        cfg = cfg or {}

        form = QFormLayout(self)
        self.name_edit = QLineEdit(name)
        form.addRow("Name", self.name_edit)
        self.desc_edit = QLineEdit(cfg.get("description", ""))
        form.addRow("Description", self.desc_edit)
        self.model_edit = QLineEdit(cfg.get("model", "") or "")
        form.addRow("Model", self.model_edit)
        self.mode_combo = QComboBox()
        for m in ["", "primary", "subagent", "all"]:
            self.mode_combo.addItem(m or "(inherit)", m)
        idx = self.mode_combo.findData(cfg.get("mode", ""))
        self.mode_combo.setCurrentIndex(max(0, idx))
        form.addRow("Mode", self.mode_combo)
        self.prompt_edit = QPlainTextEdit(cfg.get("prompt", "") or "")
        self.prompt_edit.setMaximumHeight(120)
        form.addRow("Prompt", self.prompt_edit)
        self.temp = self._double(-1000)
        if isinstance(cfg.get("temperature"), (int, float)):
            self.temp.setValue(cfg["temperature"])
        form.addRow("Temperature", self.temp)
        self.top_p = self._double(-1000)
        if isinstance(cfg.get("top_p"), (int, float)):
            self.top_p.setValue(cfg["top_p"])
        form.addRow("Top P", self.top_p)
        self.steps = QSpinBox()
        self.steps.setRange(-1, 10**6)
        self.steps.setSpecialValueText("(inherit)")
        if isinstance(cfg.get("steps"), int):
            self.steps.setValue(cfg["steps"])
        form.addRow("Steps", self.steps)
        self.hidden = QCheckBox("Hidden from @ menu")
        self.hidden.setChecked(bool(cfg.get("hidden", False)))
        form.addRow("Hidden", self.hidden)
        self.disable = QCheckBox("Disabled")
        self.disable.setChecked(bool(cfg.get("disable", False)))
        form.addRow("Disable", self.disable)
        self.color_edit = QLineEdit(cfg.get("color", "") or "")
        form.addRow("Color", self.color_edit)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _double(self, sentinel):
        d = QDoubleSpinBox()
        d.setRange(-1000, 1000)
        d.setDecimals(3)
        d.setValue(sentinel)
        d.setSpecialValueText("(inherit)")
        return d

    def values(self) -> dict:
        out = {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.text(),
            "model": self.model_edit.text().strip(),
            "mode": self.mode_combo.currentData() or "",
            "prompt": self.prompt_edit.toPlainText(),
            "hidden": self.hidden.isChecked(),
            "disable": self.disable.isChecked(),
            "color": self.color_edit.text().strip(),
        }
        if self.temp.value() != -1000:
            out["temperature"] = self.temp.value()
        if self.top_p.value() != -1000:
            out["top_p"] = self.top_p.value()
        if self.steps.value() != -1:
            out["steps"] = self.steps.value()
        return out


class AgentsTab(QWidget):
    """Manage `agent` definitions (custom + overrides of built-ins)."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search agents...")
        self.search_edit.textChanged.connect(self._filter)
        top.addWidget(self.search_edit)
        for text, slot in [("+ Add", self._add), ("Edit", self._edit), ("Remove", self._remove)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            top.addWidget(b)
        lay.addLayout(top)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Description", "Mode", "Model", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self.table)
        self.status = QLabel()
        lay.addWidget(self.status)

    def _agents(self):
        return self.app.cfg.data.get("agent", {}) if self.app.cfg else {}

    def refresh(self):
        self._update_table(self._agents())

    def _filter(self, t):
        if not t:
            self.refresh()
            return
        t = t.lower()
        self._update_table({n: c for n, c in self._agents().items() if t in n.lower()})

    def _update_table(self, agents):
        self.table.setRowCount(len(agents))
        for row, (name, cfg) in enumerate(sorted(agents.items())):
            if not isinstance(cfg, dict):
                cfg = {}
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(cfg.get("description", "")))
            self.table.setItem(row, 2, QTableWidgetItem(cfg.get("mode", "")))
            self.table.setItem(row, 3, QTableWidgetItem(cfg.get("model", "") or ""))
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0)
            eb = QPushButton("Edit")
            eb.setFixedWidth(60)
            eb.clicked.connect(lambda _, n=name: self._edit(n))
            rb = QPushButton("Remove")
            rb.setFixedWidth(70)
            rb.clicked.connect(lambda _, n=name: self._remove(n))
            l.addWidget(eb)
            l.addWidget(rb)
            self.table.setCellWidget(row, 4, w)
        self.status.setText(f"{len(agents)} agents")

    def _selected_name(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "Select", "Select an agent first.")
            return None
        return self.table.item(sel[0].row(), 0).text()

    def _add(self):
        dlg = AgentEditDialog(self)
        if dlg.exec() and dlg.values()["name"]:
            v = dlg.values()
            name = v.pop("name")
            self.app.snapshot_state()
            agents = self.app.cfg.data.setdefault("agent", {})
            agents[name] = {k: val for k, val in v.items() if val not in (None, "")}
            self.app.mark_dirty()
            self.refresh()

    def _edit(self, name=None):
        if name is None:
            name = self._selected_name()
            if not name:
                return
        cfg = dict(self._agents().get(name, {}))
        dlg = AgentEditDialog(self, name=name, cfg=cfg)
        if dlg.exec():
            v = dlg.values()
            newname = v.pop("name") or name
            self.app.snapshot_state()
            agents = self.app.cfg.data.setdefault("agent", {})
            merged = dict(cfg)  # preserve unknown keys (permission, options, tools, ...)
            for k, val in v.items():
                if val in (None, ""):
                    merged.pop(k, None)
                else:
                    merged[k] = val
            if newname != name:
                agents.pop(name, None)
            agents[newname] = merged
            self.app.mark_dirty()
            self.refresh()

    def _remove(self, name=None):
        if name is None:
            name = self._selected_name()
            if not name:
                return
        self.app.snapshot_state()
        agents = self.app.cfg.data.setdefault("agent", {})
        agents.pop(name, None)
        if not agents:
            self.app.cfg.data.pop("agent", None)
        self.app.mark_dirty()
        self.refresh()

    def collect(self, data):
        pass  # mutations applied live to cfg.data


class CommandEditDialog(QDialog):
    """Add/edit a custom command."""

    def __init__(self, parent=None, name="", cfg=None):
        super().__init__(parent)
        self.setWindowTitle("Command")
        self.setMinimumWidth(460)
        cfg = cfg or {}
        form = QFormLayout(self)
        self.name_edit = QLineEdit(name)
        form.addRow("Name", self.name_edit)
        self.desc_edit = QLineEdit(cfg.get("description", ""))
        form.addRow("Description", self.desc_edit)
        self.agent_edit = QLineEdit(cfg.get("agent", ""))
        form.addRow("Agent", self.agent_edit)
        self.model_edit = QLineEdit(cfg.get("model", "") or "")
        form.addRow("Model", self.model_edit)
        self.variant_edit = QLineEdit(cfg.get("variant", ""))
        form.addRow("Variant", self.variant_edit)
        self.subtask = QCheckBox("Run as subtask")
        self.subtask.setChecked(bool(cfg.get("subtask", False)))
        form.addRow("Subtask", self.subtask)
        self.template_edit = QPlainTextEdit(cfg.get("template", "") or "")
        self.template_edit.setMaximumHeight(150)
        form.addRow("Template", self.template_edit)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.text(),
            "agent": self.agent_edit.text().strip(),
            "model": self.model_edit.text().strip(),
            "variant": self.variant_edit.text().strip(),
            "subtask": self.subtask.isChecked(),
            "template": self.template_edit.toPlainText(),
        }


class CommandsTab(QWidget):
    """Manage `command` definitions (reusable slash commands)."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search commands...")
        self.search_edit.textChanged.connect(self._filter)
        top.addWidget(self.search_edit)
        for text, slot in [("+ Add", self._add), ("Edit", self._edit), ("Remove", self._remove)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            top.addWidget(b)
        lay.addLayout(top)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Description", "Agent", "Model"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self.table)
        self.status = QLabel()
        lay.addWidget(self.status)

    def _commands(self):
        return self.app.cfg.data.get("command", {}) if self.app.cfg else {}

    def refresh(self):
        self._update_table(self._commands())

    def _filter(self, t):
        if not t:
            self.refresh()
            return
        t = t.lower()
        self._update_table({n: c for n, c in self._commands().items() if t in n.lower()})

    def _update_table(self, commands):
        self.table.setRowCount(len(commands))
        for row, (name, cfg) in enumerate(sorted(commands.items())):
            if not isinstance(cfg, dict):
                cfg = {}
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(cfg.get("description", "")))
            self.table.setItem(row, 2, QTableWidgetItem(cfg.get("agent", "")))
            self.table.setItem(row, 3, QTableWidgetItem(cfg.get("model", "") or ""))
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0)
            eb = QPushButton("Edit")
            eb.setFixedWidth(60)
            eb.clicked.connect(lambda _, n=name: self._edit(n))
            rb = QPushButton("Remove")
            rb.setFixedWidth(70)
            rb.clicked.connect(lambda _, n=name: self._remove(n))
            l.addWidget(eb)
            l.addWidget(rb)
            self.table.setCellWidget(row, 4, w)
        self.status.setText(f"{len(commands)} commands")

    def _selected_name(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "Select", "Select a command first.")
            return None
        return self.table.item(sel[0].row(), 0).text()

    def _add(self):
        dlg = CommandEditDialog(self)
        if dlg.exec() and dlg.values()["name"] and dlg.values()["template"]:
            v = dlg.values()
            name = v.pop("name")
            self.app.snapshot_state()
            commands = self.app.cfg.data.setdefault("command", {})
            commands[name] = {k: val for k, val in v.items() if val not in (None, "")}
            self.app.mark_dirty()
            self.refresh()

    def _edit(self, name=None):
        if name is None:
            name = self._selected_name()
            if not name:
                return
        cfg = dict(self._commands().get(name, {}))
        dlg = CommandEditDialog(self, name=name, cfg=cfg)
        if dlg.exec() and dlg.values()["template"]:
            v = dlg.values()
            newname = v.pop("name") or name
            self.app.snapshot_state()
            commands = self.app.cfg.data.setdefault("command", {})
            merged = {k: val for k, val in v.items() if val not in (None, "")}
            if newname != name:
                commands.pop(name, None)
            commands[newname] = merged
            self.app.mark_dirty()
            self.refresh()

    def _remove(self, name=None):
        if name is None:
            name = self._selected_name()
            if not name:
                return
        self.app.snapshot_state()
        commands = self.app.cfg.data.setdefault("command", {})
        commands.pop(name, None)
        if not commands:
            self.app.cfg.data.pop("command", None)
        self.app.mark_dirty()
        self.refresh()

    def collect(self, data):
        pass  # mutations applied live to cfg.data


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

class RawJsonTab(QWidget):
    """Enhanced raw JSON editor with validation and formatting"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._raw_kind = "opencode"

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.file_combo = QComboBox()
        self.file_combo.addItem("opencode.json", "opencode")
        self.file_combo.addItem("tui.json", "tui")
        self.file_combo.currentIndexChanged.connect(self._switch_file)
        toolbar.addWidget(QLabel(" Raw: "))
        toolbar.addWidget(self.file_combo)

        format_btn = QPushButton("Pretty Print")
        format_btn.clicked.connect(self._format_json)
        toolbar.addWidget(format_btn)

        validate_btn = QPushButton("Validate")
        validate_btn.clicked.connect(self._validate)
        toolbar.addWidget(validate_btn)

        toolbar.addStretch()

        self.status_label = QLabel()
        toolbar.addWidget(self.status_label)

        layout.addLayout(toolbar)

        self.editor = QPlainTextEdit()
        font = QFont("Monospace")
        font.setStyleHint(QFont.Monospace)
        self.editor.setFont(font)
        self.highlighter = JSONHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._debounced_validate)
        self._modified = False
        layout.addWidget(self.editor)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._validate)

    @property
    def _modified(self):
        return self.__modified

    @_modified.setter
    def _modified(self, val):
        self.__modified = val

    def _switch_file(self):
        self.app._raw_kind = self.file_combo.currentData()
        self.refresh()

    def _debounced_validate(self):
        self._modified = True
        self.app.mark_dirty(self.app._raw_kind)
        self._timer.start()

    def _format_json(self):
        """Format JSON with pretty printing"""
        try:
            data = json.loads(self.editor.toPlainText())
            self.editor.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
            self._validate()
        except json.JSONDecodeError as e:
            self._set_status(f"Invalid JSON: {e}", "red")

    def _validate(self):
        text = self.editor.toPlainText()
        if not text.strip():
            self._set_status("Empty document", "gray")
            return
        kind = self.app._raw_kind
        cfg = self.app.cfg_tui if kind == "tui" else self.app.cfg_oc
        if cfg is None:
            self._set_status("No file loaded", "gray")
            return
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            self._set_status(f"Invalid JSON: {e}", "red")
            return
        hard_ok, hard, warnings = self.app.validate(text, kind)
        if not hard_ok:
            self._set_status(f"{len(hard)} issue(s)", "red")
            self.editor.setToolTip("\n".join(hard[:10]))
        elif warnings:
            self._set_status(f"Valid ✓ ({len(warnings)} schema notes)", "orange")
            self.editor.setToolTip("\n".join(warnings[:10]))
        else:
            self._set_status("Valid ✓", "green")
            self.editor.setToolTip("")

    def _set_status(self, text: str, color: str):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def refresh(self):
        kind = self.app._raw_kind
        cfg = self.app.cfg_tui if kind == "tui" else self.app.cfg_oc
        if cfg is None:
            self.editor.blockSignals(True)
            self.editor.setPlainText("")
            self.editor.blockSignals(False)
            self._modified = False
            return
        self.file_combo.blockSignals(True)
        idx = self.file_combo.findData(kind)
        self.file_combo.setCurrentIndex(max(0, idx))
        self.file_combo.blockSignals(False)
        self.editor.blockSignals(True)
        self.editor.setPlainText(json.dumps(cfg.data, indent=2, ensure_ascii=False))
        self.editor.blockSignals(False)
        self._modified = False
        self._validate()

    def collect(self, data: dict):
        try:
            parsed = json.loads(self.editor.toPlainText())
            data.clear()
            data.update(parsed)
        except json.JSONDecodeError:
            pass

def _confirm(parent, title: str, text: str) -> bool:
    """Show confirmation dialog"""
    return QMessageBox.question(
        parent, title, text,
        QMessageBox.Yes | QMessageBox.No
    ) == QMessageBox.Yes

class MainWindow(QMainWindow):
    """Enhanced main window with undo/redo, themes, and better UX"""

    def __init__(self, cwd: Path):
        super().__init__()
        self.cwd = Path(cwd)
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
        """Build main tabs"""
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setMovable(True)

        self.tab_general = GeneralTab(self)
        self.tab_runtime = RuntimeTab(self)
        self.tab_agents = AgentsTab(self)
        self.tab_commands = CommandsTab(self)
        self.tab_providers = ProvidersTab(self)
        self.tab_mcp = McpTab(self)
        self.tab_plugins = PluginsTab(self)
        self.tab_permission = PermissionTab(self)
        self.tab_tui = TuiTab(self)
        self.tab_raw = RawJsonTab(self)

        self.tabs.addTab(self.tab_general, "General")
        self.tabs.addTab(self.tab_runtime, "Runtime")
        self.tabs.addTab(self.tab_agents, "Agents")
        self.tabs.addTab(self.tab_commands, "Commands")
        self.tabs.addTab(self.tab_providers, "Providers")
        self.tabs.addTab(self.tab_mcp, "MCP Servers")
        self.tabs.addTab(self.tab_plugins, "Plugins")
        self.tabs.addTab(self.tab_permission, "Permissions")
        self.tabs.addTab(self.tab_tui, "TUI")
        self.tabs.addTab(self.tab_raw, "Raw JSON")

        self._oc_tabs = [self.tab_general, self.tab_runtime, self.tab_agents,
                         self.tab_commands, self.tab_providers, self.tab_mcp,
                         self.tab_plugins, self.tab_permission]
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
        return self.validator.validate(data, kind)

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

def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    # Set application style
    app.setStyle("Fusion")

    # Set default font size
    settings = SettingsManager()
    font = QApplication.font()
    font.setPointSize(settings.get_font_size())
    QApplication.setFont(font)

    # Create and show main window
    cwd = Path(os.getcwd())
    win = MainWindow(cwd)
    win.show()

    # Run application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
