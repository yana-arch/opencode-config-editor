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

import fnmatch
import json
import os
import re
import copy
import shutil
import sys
import tempfile
import time
import urllib.request
import urllib.parse
import ipaddress
import socket
import html
import csv
import shlex
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from PySide6.QtCore import (
        Qt, QTimer, QSettings, QThread, Signal
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
        QHeaderView, QToolBar, QDialog, QFrame, QInputDialog,
        QScrollArea, QGridLayout, QProgressBar
    )
    HAS_QT = True
except ImportError as _e:
    HAS_QT = False
    sys.stderr.write(f"PySide6 not available ({_e}) - GUI disabled, core tests still run\n")

    class _DummyMeta(type):
        def __getattr__(cls, name): return 0
        def __call__(cls, *a, **kw): return super().__call__(*a, **kw)

    class _DummyQt(metaclass=_DummyMeta):
        def __init__(self, *a, **kw): pass
        def __getattr__(self, name): return lambda *a, **kw: None

    # Signal is used as class attribute descriptor (Signal(str) etc.)
    def _dummy_signal(*a, **kw):
        return _DummyQt()

    Qt = QTimer = QSettings = QThread = _DummyQt
    Signal = _dummy_signal
    QAction = QFont = QKeySequence = QColor = QPalette = QTextCharFormat = QSyntaxHighlighter = _DummyQt
    QApplication = QMainWindow = QWidget = QTabWidget = QVBoxLayout = QHBoxLayout = _DummyQt
    QFormLayout = QLineEdit = QCheckBox = QSpinBox = QDoubleSpinBox = QTextEdit = _DummyQt
    QPlainTextEdit = QTableWidget = QTableWidgetItem = QPushButton = QLabel = _DummyQt
    QListWidget = QListWidgetItem = QTreeWidget = QTreeWidgetItem = QSplitter = _DummyQt
    QComboBox = QMessageBox = QFileDialog = QDialogButtonBox = QGroupBox = _DummyQt
    QHeaderView = QToolBar = QDialog = QFrame = QInputDialog = QScrollArea = _DummyQt
    QGridLayout = QProgressBar = _DummyQt

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

# Constants
APP_NAME = "opencode-config-editor"
APP_VERSION = "4.4.1"
USER_CONFIG_DIR = Path.home() / ".config" / APP_NAME
SCHEMA_URL = "https://opencode.ai/config.json"
TUI_SCHEMA_URL = "https://opencode.ai/tui.json"
SCHEMA_CACHE = USER_CONFIG_DIR / "config-schema.json"
TUI_SCHEMA_CACHE = USER_CONFIG_DIR / "tui-schema.json"
PLUGIN_STATE_CACHE = USER_CONFIG_DIR / "plugin-state.json"
# Soft-deleted providers (opencode + openclaude), kept OUT of the agent config:
# {str(config_path): {provider_key: entry}}. Holds API keys; written 0600.
PROVIDER_TRASH_FILE = USER_CONFIG_DIR / "deleted-providers.json"
SETTINGS_FILE = USER_CONFIG_DIR / "settings.ini"
CATALOG_CACHE = USER_CONFIG_DIR / "catalog.json"
CUSTOM_MODELS_FILE = USER_CONFIG_DIR / "custom_models.json"
PATTERN_RULES_FILE = USER_CONFIG_DIR / "pattern_rules.json"
DEFAULT_CATALOG_URL = "https://models.dev/api.json"
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

    def get_catalog_url(self) -> str:
        return str(self.get("catalog/url", DEFAULT_CATALOG_URL))

    def set_catalog_url(self, url: str):
        self.set("catalog/url", str(url).strip())

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

# Config file model, validation and state stores
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

def strip_jsonc(text: str) -> str:
    """Strip JavaScript-style comments (//... and /*...*/) and trailing commas
    from a JSON string without breaking string literals.

    A trailing comma is dropped only when the next significant character
    (outside strings and comments) is `}` or `]`, so anything json.loads
    accepts round-trips to the same value.
    """
    if not text:
        return ""
    out = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    # Index in out[] holding a ',' that may turn out to be a trailing comma.
    pending_comma = -1

    def drop_pending_comma():
        nonlocal pending_comma
        if pending_comma >= 0:
            out[pending_comma] = " "
            pending_comma = -1

    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if escape:
                escape = False
            elif c == '\\':
                escape = True
            elif c == '"':
                in_string = False
            i += 1
        else:
            if c == '"':
                in_string = True
                pending_comma = -1  # a string value confirms the comma is not trailing
                out.append(c)
                i += 1
            elif c == '/' and i + 1 < n and text[i + 1] == '/':
                i += 2
                while i < n and text[i] != '\n':
                    i += 1
            elif c == '/' and i + 1 < n and text[i + 1] == '*':
                i += 2
                while i + 1 < n and not (text[i] == '*' and text[i + 1] == '/'):
                    i += 1
                i += 2
            elif c == ',':
                out.append(c)
                pending_comma = len(out) - 1
                i += 1
            elif c in ' \t\r\n':
                # Whitespace can never confirm a trailing comma on its own.
                out.append(c)
                i += 1
            else:
                if c in '}]':
                    drop_pending_comma()
                else:
                    pending_comma = -1
                out.append(c)
                i += 1

    return "".join(out)


def loads_jsonc(text: str):
    """Parse a JSON or JSONC string, accepting a leading BOM, comments and
    trailing commas."""
    if not isinstance(text, str):
        raise TypeError(f"Expected string, got {type(text)}")
    if text.startswith("\ufeff"):
        text = text[1:]
    return json.loads(strip_jsonc(text))




def section(cfg_data, key: str) -> dict:
    """Return cfg_data[key] when it is a dict, else an empty dict."""
    v = cfg_data.get(key) if isinstance(cfg_data, dict) else None
    return v if isinstance(v, dict) else {}


def deep_merge(base: dict, incoming: dict) -> dict:
    """Recursively merge `incoming` into a copy of `base` (later wins).

    Nested dicts are merged key-by-key; any non-dict value replaces wholesale.
    Generic building block for layered configs (e.g. openclaude's
    user -> project -> local settings.json chain).
    """
    out = dict(base) if isinstance(base, dict) else {}
    for k, v in (incoming or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def merge_layers(layers) -> dict:
    """Merge an ordered iterable of config dicts; later layers override earlier."""
    result: dict = {}
    for layer in layers:
        if isinstance(layer, dict):
            result = deep_merge(result, layer)
    return result


def atomic_write_json(path, content: str) -> None:
    """Write text to `path` atomically via mkstemp + os.replace.

    Raises OSError on failure; the temp file is always cleaned up.
    """
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def config_home(default_dir, env_vars=()) -> Path:
    """Resolve a config directory, honoring env overrides (first set wins).

    e.g. config_home("~/.openclaude", ("OPENCLAUDE_CONFIG_DIR", "CLAUDE_CONFIG_DIR")).
    """
    for name in env_vars:
        val = os.environ.get(name)
        if val:
            return Path(val).expanduser()
    return Path(default_dir).expanduser()


class ConfigFile:
    """Enhanced config file handler with backup and validation"""

    def __init__(self, path: Path, kind: str):
        self.path = Path(path)
        self.kind = kind
        self.data = {}
        self.error = None
        self.backup_dir = USER_CONFIG_DIR / "backups"
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
            # utf-8-sig: a UTF-8 BOM (common from Windows editors) must still load.
            with open(self.path, "r", encoding="utf-8-sig") as f:
                raw = f.read()
            self.data = loads_jsonc(raw)
            self.error = None
            return True
        except FileNotFoundError:
            self.data = {}
            self.error = f"File not found: {self.path}"
            return False
        except json.JSONDecodeError as e:
            self.error = f"Invalid JSON: {e}"
            return False
        except UnicodeDecodeError as e:
            self.error = f"Not a UTF-8 text file: {e}"
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
            atomic_write_json(self.path, content)

            self.data = data
            if self.kind == "opencode":
                self._prune_provider_trash(data)
            return True, f"Saved to {self.path}"
        except OSError as e:
            return False, f"Save error: {e}"

    def _prune_provider_trash(self, data: dict):
        """Drop trash entries for providers present in the just-saved file
        (restored, or re-added). Best-effort: never changes the save result."""
        present = section(data, "provider").keys()
        if not present:
            return
        try:
            ProviderTrashStore().prune(self.path, present)
        except Exception:
            pass

    def export(self, path: Path) -> Tuple[bool, str]:
        """Export config to specified path"""
        try:
            content = json.dumps(self.data, indent=2, ensure_ascii=False) + "\n"
            atomic_write_json(path, content)
            return True, f"Exported to {path}"
        except OSError as e:
            return False, f"Export error: {e}"

class Validator:
    """Enhanced validator with schema caching and detailed error reporting"""

    def __init__(self):
        self.schemas = {}  # kind -> schema dict
        self.last_schema_fetch = {}  # kind -> timestamp of last successful load
        self.schema_cache_duration = 86400  # 24 hours
        self.schema_errors = {}  # kind -> error message
        self.last_fetch_attempt = {}  # kind -> timestamp of last fetch attempt

    def _schema_source(self, kind: str) -> Tuple[str, Path]:
        """Return (url, cache_path) for the given config kind."""
        if kind == "tui":
            return TUI_SCHEMA_URL, TUI_SCHEMA_CACHE
        return SCHEMA_URL, SCHEMA_CACHE

    def _load_schema(self, kind: str = "opencode") -> Optional[dict]:
        """Load schema (kind-aware) with caching and periodic refresh"""
        url, cache_path = self._schema_source(kind)
        return self.schema_from(url, cache_path, kind)

    def schema_from(self, url: str, cache_path: Path, kind: str) -> Optional[dict]:
        """Load any JSON Schema by url, cached in memory and on disk.

        Adapters pass their own schema here so core stays agent-agnostic.
        """
        if not HAVE_JSONSCHEMA:
            return None

        current_time = time.time()
        # Per-kind timestamps: a failed tui fetch must not suppress a valid
        # cached opencode schema, and vice versa.
        last_ok = self.last_schema_fetch.get(kind, 0)
        last_try = self.last_fetch_attempt.get(kind, 0)

        if self.schemas.get(kind) is not None and (current_time - last_ok) < self.schema_cache_duration:
            return self.schemas[kind]

        # Try the on-disk cache. It is always usable; it is only *authoritative*
        # while fresh, so a stale cache still keeps validating when a fetch fails.
        cached = None
        try:
            if cache_path.exists():
                cached = json.loads(cache_path.read_text())
                if not (isinstance(cached, dict) and cached):
                    cached = None
        except Exception:
            cached = None

        # Avoid hammering a failed endpoint, but keep serving the last valid
        # disk cache during the backoff window.
        if self.schema_errors.get(kind) and (current_time - last_try) < 3600:
            return cached

        if cached is not None and (current_time - cache_path.stat().st_mtime) < self.schema_cache_duration:
            self.schemas[kind] = cached
            self.last_schema_fetch[kind] = current_time
            self.schema_errors.pop(kind, None)
            return cached

        # Fetch from network
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
            with urllib.request.urlopen(req, timeout=10) as r:
                fetched = json.loads(r.read().decode("utf-8"))

            # Accept both ordinary object schemas and the real opencode schema,
            # whose root delegates through $ref/$defs and has no root `type`.
            is_schema = (isinstance(fetched, dict) and bool(fetched) and
                         (fetched.get("type") == "object" or "$ref" in fetched or "$defs" in fetched))
            if not is_schema:
                raise ValueError("response is not a JSON Schema object")

            # Save to cache
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(fetched))
            except OSError:
                pass

            self.schemas[kind] = fetched
            self.last_schema_fetch[kind] = current_time
            self.schema_errors.pop(kind, None)
            return fetched
        except Exception as e:
            self.schema_errors[kind] = f"Could not fetch schema: {e}"
            self.last_fetch_attempt[kind] = current_time
            # Keep serving the last good schema rather than dropping validation.
            return cached

    def validate(self, data: dict, kind: str, known_keys: set = None) -> Tuple[bool, List[str], List[str]]:
        """Validate config.

        Returns (hard_ok, hard_errors, schema_warnings).

        Hard errors are structural checks we can trust regardless of schema.
        Schema-derived findings are treated as advisory *warnings* because the
        official opencode schema is stricter/incomplete (e.g. it rejects the
        `local` MCP type that opencode actually supports), so a valid config
        would otherwise always be flagged.

        `known_keys` may be injected by the active adapter; when omitted we fall
        back to the built-in opencode/tui key sets.
        """
        if not isinstance(data, dict):
            return False, ["Root must be a JSON object."], []

        if known_keys is None:
            known_keys = OPENCODE_KEYS if kind in ("opencode", "generic") else TUI_KEYS
        hard_ok, hard = self._basic_checks(data, known_keys)
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
            # Non-dict 'mcp' is already a hard error; iterating it would raise.
            return False, errors

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


def _merge_legacy_plugin_state(new_path: Path, legacy_name: str) -> None:
    """Fold the v4.4.0 ~/.cache plugin-state file into the current store.

    Entries already present in `new_path` win. The legacy file is renamed to
    `<name>.migrated` (never deleted) so the merge is idempotent and a failure
    leaves the original data in place. Best-effort: never raises.
    """
    legacy = Path.home() / ".cache" / APP_NAME / legacy_name
    try:
        if not legacy.is_file():
            return
        old = loads_jsonc(legacy.read_text(encoding="utf-8"))
        current = (loads_jsonc(new_path.read_text(encoding="utf-8"))
                   if new_path.is_file() else {})
        if not isinstance(old, dict) or not isinstance(current, dict):
            return
        merged = dict(current)
        changed = False
        for cfg_path, bucket in old.items():
            if not isinstance(bucket, dict):
                continue
            target = merged.get(cfg_path)
            if not isinstance(target, dict):
                merged[cfg_path] = dict(bucket)
                changed = True
                continue
            for name, entry in bucket.items():
                if name not in target:
                    target[name] = entry
                    changed = True
        if changed:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                new_path, json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
        legacy.replace(legacy.with_name(legacy.name + ".migrated"))
    except Exception:
        pass


class PluginStateStore:
    """Remember disabled opencode plugins in the editor cache, keying each by name and
    storing its full entry so re-enabling restores tuple-form options verbatim."""

    def __init__(self):
        self.path = PLUGIN_STATE_CACHE
        self._data = {}
        _merge_legacy_plugin_state(self.path, "plugin-state.json")
        self._load()

    def _load(self):
        """Load plugin state from cache"""
        try:
            if self.path.exists():
                self._data = loads_jsonc(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._data = {}

    def _save(self):
        """Save plugin state to cache"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def get_entries(self, cfg_path: Path) -> dict:
        """Get dict of {plugin_name: full_entry} for disabled plugins for config file."""
        raw = self._data.get(str(cfg_path), {})
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, list):
            out = {}
            for item in raw:
                if isinstance(item, str):
                    out[item] = item
                elif isinstance(item, (list, tuple)) and item and isinstance(item[0], str):
                    out[item[0]] = item
            return out
        return {}

    def get_disabled(self, cfg_path: Path) -> set:
        """Get set of disabled plugin names for backward compatibility."""
        return set(self.get_entries(cfg_path).keys())

    def set_entry(self, cfg_path: Path, name: str, entry):
        key = str(cfg_path)
        if key not in self._data or not isinstance(self._data[key], dict):
            self._data[key] = {}
        self._data[key][name] = entry
        self._save()

    def remove_entry(self, cfg_path: Path, name: str):
        key = str(cfg_path)
        d = self._data.get(key)
        if isinstance(d, dict) and name in d:
            d.pop(name, None)
            if not d:
                self._data.pop(key, None)
            self._save()

    def clear(self, cfg_path: Path, names=None):
        key = str(cfg_path)
        d = self._data.get(key)
        if isinstance(d, dict):
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

    def set_disabled(self, cfg_path: Path, disabled):
        """Set disabled plugins (accepts set/list of names or dict of {name: entry})."""
        key = str(cfg_path)
        if not disabled:
            self._data.pop(key, None)
            self._save()
            return
        if isinstance(disabled, dict):
            self._data[key] = disabled
        elif isinstance(disabled, (set, list, tuple)):
            d = {}
            for item in disabled:
                if isinstance(item, str):
                    d[item] = item
                elif isinstance(item, (list, tuple)) and item and isinstance(item[0], str):
                    d[item[0]] = item
            self._data[key] = d
        self._save()

class ProviderTrashStore:
    """Soft-deleted providers, kept in the editor's own app-data dir instead of
    the agent config: {str(config_path): {provider_key: entry}}.

    Unlike PluginStateStore this file is the ONLY copy of deleted provider data
    (API keys included), so: it is re-read on every operation (two windows
    never clobber each other), written atomically via mkstemp (mode 0600), and
    write errors raise OSError. An unreadable/invalid file reads as empty but
    every mutation raises and leaves it untouched; it is never overwritten.
    """

    def __init__(self, path=None):
        self.path = Path(path) if path else PROVIDER_TRASH_FILE

    def _read(self) -> dict:
        """Whole store; {} when absent. Raises OSError when unreadable/invalid."""
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError as e:     # JSONDecodeError / UnicodeDecodeError
            raise OSError(f"Invalid trash file {self.path}: {e}") from e
        if not isinstance(data, dict):
            raise OSError(f"Invalid trash file {self.path}: root is not a JSON object")
        return data

    def _write(self, data: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def entries(self, cfg_path) -> dict:
        """Deep copy of {key: entry} for one config file ({} on any read problem)."""
        try:
            bucket = self._read().get(str(cfg_path))
        except OSError:
            return {}
        return copy.deepcopy(bucket) if isinstance(bucket, dict) else {}

    def put(self, cfg_path, key: str, entry):
        data = self._read()
        bucket = data.setdefault(str(cfg_path), {})
        if not isinstance(bucket, dict):
            raise OSError(f"Invalid trash file {self.path}: entry for {cfg_path} is not an object")
        bucket[key] = entry
        self._write(data)

    def discard(self, cfg_path, key: str):
        data = self._read()
        bucket = data.get(str(cfg_path))
        if not isinstance(bucket, dict) or key not in bucket:
            return
        del bucket[key]
        if not bucket:
            del data[str(cfg_path)]
        self._write(data)

    def prune(self, cfg_path, present_keys) -> int:
        """Drop entries whose key is in `present_keys`; write only on change."""
        data = self._read()
        bucket = data.get(str(cfg_path))
        if not isinstance(bucket, dict):
            return 0
        present = set(present_keys)
        stale = [k for k in bucket if k in present]
        if not stale:
            return 0
        for k in stale:
            del bucket[k]
        if not bucket:
            del data[str(cfg_path)]
        self._write(data)
        return len(stale)

class TuiPluginStateStore:
    """Remember disabled tui plugins in the editor cache, keying each by name and
    storing its full entry so re-enabling restores tuple-form options verbatim."""

    def __init__(self):
        self.path = USER_CONFIG_DIR / "tui-plugin-state.json"
        self._data = {}
        _merge_legacy_plugin_state(self.path, "tui-plugin-state.json")
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

# JSON parsing / import helpers for providers, MCP servers and models
def _load_json_file(path: Path) -> dict:
    """Load JSON with error handling"""
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


def _is_opencode_mcp_cfg(v) -> bool:
    """True for an entry already in opencode's own mcp shape.

    opencode uses type:local with an argv list, or type:remote with a url.
    Claude Desktop / Cursor instead use a bare 'command' string plus 'args'
    (and 'env'), or a bare 'url' with no type, which opencode does not accept.
    """
    if not _looks_like_mcp_cfg(v):
        return False
    if v.get("type") in ("local", "remote"):
        return True
    if "command" in v or "url" in v or "args" in v:
        return False
    return True   # toggle-only entry, e.g. {"enabled": false}


def parse_mcp_import(obj: dict) -> dict:
    """Parse MCP import from various JSON formats.

    Accepts opencode entries as-is, and converts Claude Desktop / Cursor
    entries (bare 'command' + 'args' + 'env', or a bare 'url') through
    claude_mcp_to_opencode_mcp so the result always matches opencode's schema.
    """
    if isinstance(obj, dict) and isinstance(obj.get("mcpServers"), dict) and obj["mcpServers"]:
        obj = obj["mcpServers"]
    elif isinstance(obj, dict) and isinstance(obj.get("mcp"), dict) and obj["mcp"]:
        obj = obj["mcp"]

    if isinstance(obj, dict) and obj and all(isinstance(v, dict) for v in obj.values()):
        converted = {}
        for name, entry in obj.items():
            if _is_opencode_mcp_cfg(entry):
                converted[name] = entry
            else:
                item = claude_mcp_to_opencode_mcp({name: entry})
                if name not in item:
                    raise ValueError(f"Unrecognized MCP server entry: {name}")
                converted[name] = item[name]
        return converted

    if _looks_like_mcp_cfg(obj):
        if _is_opencode_mcp_cfg(obj):
            key = _slugify(obj.get("name") or obj.get("id") or "server")
            cfg = {k: v for k, v in obj.items() if k not in ("name", "id")}
            return {key: cfg}
        converted = claude_mcp_to_opencode_mcp({"server": obj})
        if converted:
            key = _slugify(obj.get("name") or obj.get("id") or "server")
            return {key: converted["server"]}

    raise ValueError(
        "Unrecognized MCP JSON. Expected a server object, a {name: server} "
        "map, a 'mcpServers' wrapper, or a full config with 'mcp'."
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

# Model catalog, normalized model formats, matching and fallback logic
class ModelCatalog:
    """Enhanced model catalog with custom models, pattern rules, filtering, and preview"""

    def __init__(self):
        self.raw = None
        self.by_provider = {}        # provider_id -> {model_id: spec}
        self.flat = {}               # model_id -> spec
        self.custom_models = {}      # model_id -> spec
        self.custom_by_provider = {} # provider_id -> {model_id: spec}
        self.pattern_rules = []      # list of rule dicts
        self.source = None
        self.last_updated = None
        self._formats_cache = None
        self._model_index = {}       # model_id -> [provider_id, ...]
        self.normalized_index = {}   # normalized_id -> [model_id, ...]
        self._load_custom_models()
        self._load_pattern_rules()

    def loaded(self) -> bool:
        """Check if a base catalog (file, cache, bundle or pasted text) is loaded.

        Custom models alone do not count: they overlay whatever base catalog is
        active, and every lazy-load guard must still pull in the base catalog.
        """
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

    def _load_custom_models(self):
        """Load user-defined custom models from CUSTOM_MODELS_FILE."""
        try:
            if CUSTOM_MODELS_FILE.exists():
                data = loads_jsonc(CUSTOM_MODELS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    if self.raw is None:
                        # No base catalog: the indexes hold nothing but custom
                        # entries, so rebuild them instead of overlaying twice.
                        self.by_provider = {}
                        self.flat = {}
                        self._model_index = {}
                        self.normalized_index = {}
                    self._apply_custom_models_dict(data)
        except Exception:
            pass

    def _apply_custom_models_dict(self, data: dict):
        """Merge custom models dict with high priority into catalog.

        Entries are classified one by one: a `{provider: {"models": {...}}}`
        group, a top-level `{"id":..., "models": {...}}` group and a flat
        `{model_id: spec}` entry can coexist in the same file. Non-object values
        are skipped instead of disabling every custom model.
        """
        self.custom_models = {}
        self.custom_by_provider = {}

        flat_custom = {}
        by_prov = {}

        top_models = data.get("models")
        if isinstance(top_models, dict):
            pid = data.get("id") if isinstance(data.get("id"), str) else "custom"
            for mid, spec in top_models.items():
                if isinstance(spec, dict):
                    by_prov.setdefault(pid, {})[mid] = spec
                    flat_custom[mid] = spec

        for mid, value in data.items():
            if mid == "models":
                continue
            if not isinstance(value, dict):
                continue
            inner = value.get("models")
            if isinstance(inner, dict):
                pid = str(mid)
                for sub_id, sub_spec in inner.items():
                    if isinstance(sub_spec, dict):
                        by_prov.setdefault(pid, {})[sub_id] = sub_spec
                        flat_custom[sub_id] = sub_spec
                continue
            pid = value.get("provider") if isinstance(value.get("provider"), str) else "custom"
            by_prov.setdefault(pid, {})[mid] = value
            flat_custom[mid] = value

        self.custom_models = flat_custom
        self.custom_by_provider = by_prov

        # Overlay on active index
        self._overlay_custom_models()

    def _overlay_custom_models(self):
        """Overlay the current custom models onto the active catalog indexes."""
        for pid, models in self.custom_by_provider.items():
            if pid not in self.by_provider:
                self.by_provider[pid] = {}
            for mid, spec in models.items():
                self.by_provider[pid][mid] = spec
                self.flat[mid] = spec
                if mid not in self._model_index:
                    self._model_index[mid] = []
                if pid not in self._model_index[mid]:
                    self._model_index[mid].insert(0, pid)
                norm_id = _normalize_model_id(mid)
                if norm_id:
                    self.normalized_index.setdefault(norm_id, []).insert(0, mid)
                if isinstance(spec, dict) and "aliases" in spec:
                    for alias in spec["aliases"]:
                        self._model_index.setdefault(alias, []).insert(0, pid)
                        norm_alias = _normalize_model_id(alias)
                        if norm_alias:
                            self.normalized_index.setdefault(norm_alias, []).insert(0, mid)

        self._formats_cache = None

    def _reload_after_custom_change(self):
        """Rebuild the indexes after custom models were added/removed on disk."""
        if self.raw is not None:
            self._ingest(self.raw)
            return
        # No base catalog: rebuild from scratch out of the file on disk, so a
        # deleted or renamed model leaves no stale index entry behind.
        self.by_provider = {}
        self.flat = {}
        self._model_index = {}
        self.normalized_index = {}
        self._load_custom_models()

    def _load_pattern_rules(self):
        """Load pattern rules from PATTERN_RULES_FILE."""
        try:
            if PATTERN_RULES_FILE.exists():
                data = loads_jsonc(PATTERN_RULES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.pattern_rules = [r for r in data if isinstance(r, dict)]
        except Exception:
            self.pattern_rules = []

    def save_custom_model(self, model_id: str, spec: dict, provider: str = "custom") -> bool:
        """Save/update a custom model spec in CUSTOM_MODELS_FILE."""
        model_id = str(model_id).strip()
        if not model_id:
            return False
        try:
            current = self.get_all_custom_models()
        except ValueError:
            return False
        spec_copy = dict(spec)
        spec_copy["provider"] = provider
        current[model_id] = spec_copy

        try:
            CUSTOM_MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                CUSTOM_MODELS_FILE,
                json.dumps(current, indent=2, ensure_ascii=False),
            )
            self._reload_after_custom_change()
            return True
        except (OSError, ValueError):
            return False

    def delete_custom_model(self, model_id: str) -> bool:
        """Delete a custom model from CUSTOM_MODELS_FILE."""
        try:
            current = self.get_all_custom_models()
        except ValueError:
            return False
        if model_id in current:
            current.pop(model_id, None)
            try:
                atomic_write_json(
                    CUSTOM_MODELS_FILE,
                    json.dumps(current, indent=2, ensure_ascii=False),
                )
                self._reload_after_custom_change()
                return True
            except (OSError, ValueError):
                return False
        return False

    def get_all_custom_models(self) -> Dict[str, dict]:
        """Get dict of all saved custom models.

        Raises ValueError when the file exists but cannot be parsed, so callers
        never silently write back a truncated dataset and destroy the models
        they could not read.
        """
        if CUSTOM_MODELS_FILE.exists():
            data = loads_jsonc(CUSTOM_MODELS_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(
                    f"{CUSTOM_MODELS_FILE.name} must contain a JSON object."
                )
            return data
        return dict(self.custom_models)

    def save_pattern_rules(self, rules: List[dict]) -> bool:
        """Save list of pattern rules to PATTERN_RULES_FILE."""
        self.pattern_rules = [r for r in rules if isinstance(r, dict) and r.get("pattern")]
        try:
            PATTERN_RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
            PATTERN_RULES_FILE.write_text(json.dumps(self.pattern_rules, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except OSError:
            return False

    def get_all_pattern_rules(self) -> List[dict]:
        """Get list of all pattern rules."""
        if not self.pattern_rules:
            self._load_pattern_rules()
        return list(self.pattern_rules)

    def fetch_online(self, url: Optional[str] = None) -> Tuple[bool, str, int]:
        """Download latest catalog from online source, update cache, and reload.

        The download is fully validated before anything is replaced: a failed
        request, unparseable body or unrecognized catalog shape leaves both the
        in-memory catalog and the on-disk cache untouched.
        """
        catalog_url = (url or SettingsManager().get_catalog_url() or DEFAULT_CATALOG_URL).strip()
        try:
            req = urllib.request.Request(
                catalog_url,
                headers={"User-Agent": f"opencode-config-editor/{APP_VERSION}"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
            data = loads_jsonc(raw)
            if not isinstance(data, dict) or not data:
                return False, "Downloaded catalog is empty or invalid JSON.", 0

            # Validate the shape on a throwaway catalog first: only a catalog
            # that ingests cleanly is allowed to overwrite the cache.
            try:
                _validate_catalog_data(data)
            except ValueError as e:
                return False, f"Downloaded catalog is invalid: {e}", 0

            CATALOG_CACHE.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                CATALOG_CACHE,
                json.dumps(data, indent=2, ensure_ascii=False),
            )
            self.load(CATALOG_CACHE)
            return True, f"Catalog updated successfully from {catalog_url}!", len(self.flat)
        except Exception as e:
            return False, f"Failed to fetch catalog: {e}", 0

    def _ingest(self, data: dict):
        """Process catalog data and overlay custom models."""
        by_provider, flat = _parse_catalog_data(data)

        self.raw, self.by_provider, self.flat = data, by_provider, flat
        self._formats_cache = None
        self._model_index = {}
        self.normalized_index = {}
        for pid, models in by_provider.items():
            for mid, spec in models.items():
                self._model_index.setdefault(mid, []).append(pid)
                # Phase 2: Aliases
                if isinstance(spec, dict) and "aliases" in spec:
                    for alias in spec["aliases"]:
                        self._model_index.setdefault(alias, []).append(pid)

        for mid in list(self.flat.keys()):
            norm_id = _normalize_model_id(mid)
            if norm_id:
                self.normalized_index.setdefault(norm_id, []).append(mid)

            # Phase 2: Aliases in normalized index
            spec = self.flat[mid]
            if isinstance(spec, dict) and "aliases" in spec:
                for alias in spec["aliases"]:
                    norm_alias = _normalize_model_id(alias)
                    if norm_alias:
                        self.normalized_index.setdefault(norm_alias, []).append(mid)

        # Overlay custom models & load pattern rules
        self._load_custom_models()
        self._load_pattern_rules()

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

    def formats(self) -> Dict[str, Dict[str, "ModelFormat"]]:
        """Lazily build normalized formats: provider -> model_id -> ModelFormat."""
        if getattr(self, "_formats_cache", None) is not None:
            return self._formats_cache
        cache = {}
        for pid, models in self.by_provider.items():
            pmap = {}
            for mid, spec in models.items():
                pmap[mid] = ModelFormat.from_spec(pid, mid, spec)
            cache[pid] = pmap
        self._formats_cache = cache
        return cache

    def all_formats(self) -> List["ModelFormat"]:
        """Flatten all formats across providers."""
        return [fmt for pmap in self.formats().values() for fmt in pmap.values()]

    def find_model(self, model_id: str) -> List["ModelFormat"]:
        """Match a model id across the catalog, custom models, and pattern rules.

        An id that exists in the catalog resolves to that entry (and nothing
        else); otherwise the normalized bucket is searched. Ordering is
        deterministic, so repeated runs pick the same match.

        `_seen_refs` guards pattern-rule reference lookups against re-entering
        the rule that is currently being applied.
        """
        return self._find_model(model_id, _seen_refs=frozenset())

    def _find_model(self, model_id: str, _seen_refs: frozenset) -> List["ModelFormat"]:
        # Insertion-ordered dict: a deterministic stand-in for a set.
        matches = {}

        # 1. Exact match wins outright: never widen an id that exists.
        # `_model_index` also holds alias keys, which have no format of their
        # own, so only a real model id short-circuits here.
        if model_id in self.flat:
            matches[model_id] = None
        # 2. Full normalized match (most precise).
        full = _normalize_model_id(model_id)
        if not matches and full in self.normalized_index:
            for original_id in self.normalized_index[full]:
                matches[original_id] = None

        # 3. Fallback: version-stripped variants
        if not matches:
            for key in _normalized_match_keys(model_id):
                if key == full:
                    continue
                if key in self.normalized_index:
                    for original_id in self.normalized_index[key]:
                        matches[original_id] = None

        # 4. Pattern rules match
        if not matches and self.pattern_rules:
            for rule in self.pattern_rules:
                pat = str(rule.get("pattern", "")).strip()
                if not pat:
                    continue
                matched = False
                if pat.startswith("regex:"):
                    try:
                        matched = bool(re.search(pat[6:], model_id, re.IGNORECASE))
                    except re.error:
                        matched = False
                else:
                    matched = fnmatch.fnmatch(model_id.lower(), pat.lower())

                if matched:
                    ref_prov = rule.get("reference_provider")
                    ref_mod = rule.get("reference_model")
                    ref_fmt = None
                    if ref_mod and ref_mod not in _seen_refs:
                        mod_matches = self._find_model(
                            ref_mod, _seen_refs | {ref_mod, model_id}
                        )
                        if mod_matches:
                            ref_fmt = mod_matches[0]
                    if ref_fmt is None and ref_prov:
                        ref_fmt = _find_fallback(model_id, ref_prov, self)
                    if ref_fmt is not None:
                        derived_fmt = ModelFormat(
                            provider=ref_prov or ref_fmt.provider,
                            model_id=model_id,
                            name=humanize_model_id(model_id),
                            context=ref_fmt.context,
                            output=ref_fmt.output,
                            cost_in=ref_fmt.cost_in,
                            cost_out=ref_fmt.cost_out,
                            cost_cache_read=ref_fmt.cost_cache_read,
                            cost_cache_write=ref_fmt.cost_cache_write,
                            modalities=ref_fmt.modalities,
                            attachment=ref_fmt.attachment,
                            reasoning=ref_fmt.reasoning,
                            tools=ref_fmt.tools,
                            temperature=ref_fmt.temperature,
                        )
                        return [derived_fmt]

        if not matches:
            return []

        # Collect all unique ModelFormat objects
        found_formats = {}
        fmts = self.formats()
        for mid in matches:
            providers = self._model_index.get(mid, [])
            for p in providers:
                if mid in fmts.get(p, {}):
                    fmt = fmts[p][mid]
                    found_formats[(fmt.provider, fmt.model_id)] = fmt

        return list(found_formats.values())

def try_load_bundled_catalog(catalog) -> bool:
    """Silently load the bundled models.dev catalog into `catalog` if present.

    Never prompts or raises; returns True when the catalog was loaded."""
    if catalog is None or catalog.loaded():
        return catalog is not None and catalog.loaded()
    try:
        # 1. User config dir (~/.config/opencode-config-editor/catalog.json)
        if CATALOG_CACHE.exists():
            catalog.load(CATALOG_CACHE)
            return True
        # 2. Local bundled relative to main script
        bundled = Path(__file__).resolve().parent / "models" / "models.dev.catalog.json"
        if bundled.exists():
            catalog.load(bundled)
            return True
    except (OSError, ValueError):
        pass
    return False

def _merge_model_spec(existing, catalog_spec: dict, overwrite: bool) -> dict:
    """Merge model spec with catalog spec"""
    if not isinstance(existing, dict):
        existing = {}
    existing = dict(existing)
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


# ---------------------------------------------------------------------------
# Model Format normalization
# ---------------------------------------------------------------------------

# Flexible key aliases so new providers/schemas only need a map entry.
SPEC_ALIASES = {
    "context": ["limit.context", "context_window", "max_input_tokens", "context_length"],
    "output": ["limit.output", "max_output_tokens", "output_tokens", "max_tokens"],
    "modalities": ["modalities", "input_modalities", "supported_media"],
    "cost_in": ["cost.input", "cost_in", "input_cost"],
    "cost_out": ["cost.output", "cost_out", "output_cost"],
    "cost_cache_read": ["cost.cache_read", "cache_read"],
    "cost_cache_write": ["cost.cache_write", "cache_write"],
}


def _deep_get(spec: dict, dotted: str):
    """Resolve a dotted path ('limit.context') in a dict."""
    cur = spec
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _first_value(spec: dict, aliases) -> Optional[object]:
    for key in aliases:
        v = _deep_get(spec, key)
        if v is not None:
            return v
    return None


def _as_bool(v) -> bool:
    return bool(v) if v is not None else False


@dataclass
class Modalities:
    """Normalized input/output modalities of a model."""
    input_mods: List[str] = field(default_factory=lambda: ["text"])
    output_mods: List[str] = field(default_factory=lambda: ["text"])
    inferred: bool = False

    @property
    def has_image_input(self) -> bool:
        return any(m in ("image", "vision") for m in self.input_mods)

    @property
    def has_pdf_input(self) -> bool:
        return "pdf" in self.input_mods

    @property
    def supports_text_input(self) -> bool:
        return "text" in self.input_mods or not self.input_mods

    @property
    def supports_text_output(self) -> bool:
        return "text" in self.output_mods or not self.output_mods

    def label(self) -> str:
        in_str = "+".join(self.input_mods) if self.input_mods else "?"
        out_str = "+".join(self.output_mods) if self.output_mods else "?"
        mark = "~" if self.inferred else ""
        return f"in:{in_str}{mark} / out:{out_str}"


@dataclass
class ModelFormat:
    """Normalized description of a model across any provider."""
    provider: str
    model_id: str
    name: str
    context: Optional[int] = None
    output: Optional[int] = None
    modalities: Modalities = field(default_factory=Modalities)
    attachment: bool = False
    reasoning: bool = False
    tools: bool = False
    temperature: bool = False
    cost_in: Optional[float] = None
    cost_out: Optional[float] = None
    cost_cache_read: Optional[float] = None
    cost_cache_write: Optional[float] = None

    def context_k(self) -> str:
        return _fmt_tokens(self.context)

    def output_k(self) -> str:
        return _fmt_tokens(self.output)

    def cost_in_label(self) -> str:
        return _fmt_cost(self.cost_in)

    def cost_out_label(self) -> str:
        return _fmt_cost(self.cost_out)

    @classmethod
    def from_spec(cls, provider: str, model_id: str, spec: dict) -> "ModelFormat":
        spec = spec or {}

        context = _first_value(spec, SPEC_ALIASES["context"])
        output = _first_value(spec, SPEC_ALIASES["output"])

        mods = _parse_modalities(spec)

        attachment = _as_bool(spec.get("attachment"))
        reasoning = _as_bool(spec.get("reasoning"))
        tools = _as_bool(spec.get("tool_call") or spec.get("tools"))
        temperature = _as_bool(spec.get("temperature"))

        cost_in = _first_value(spec, SPEC_ALIASES["cost_in"])
        cost_out = _first_value(spec, SPEC_ALIASES["cost_out"])
        cache_read = _first_value(spec, SPEC_ALIASES["cost_cache_read"])
        cache_write = _first_value(spec, SPEC_ALIASES["cost_cache_write"])

        return cls(
            provider=provider,
            model_id=model_id,
            name=str(spec.get("name") or humanize_model_id(model_id)),
            context=_as_int(context),
            output=_as_int(output),
            modalities=mods,
            attachment=attachment,
            reasoning=reasoning,
            tools=tools,
            temperature=temperature,
            cost_in=_as_float(cost_in),
            cost_out=_as_float(cost_out),
            cost_cache_read=_as_float(cache_read),
            cost_cache_write=_as_float(cache_write),
        )


def _parse_modalities(spec: dict) -> Modalities:
    """Parse modalities, inferring from attachment when missing."""
    raw = _first_value(spec, SPEC_ALIASES["modalities"])

    if isinstance(raw, dict):
        in_mods = raw.get("input")
        out_mods = raw.get("output")
        inferred = False
    elif isinstance(raw, list):
        in_mods, out_mods = raw, ["text"]
        inferred = True
    else:
        in_mods, out_mods = None, None
        inferred = True

    in_list = [str(m) for m in in_mods] if in_mods else None
    out_list = [str(m) for m in out_mods] if out_mods else None

    # Fallback: attachment implies image input
    if not in_list and _as_bool(spec.get("attachment")):
        in_list = ["text", "image"]
    elif not in_list:
        in_list = ["text"]

    if not out_list:
        out_list = ["text"]

    return Modalities(input_mods=in_list, output_mods=out_list, inferred=inferred)


def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_tokens(v) -> str:
    if v is None:
        return "?"
    if v >= 1000000:
        return f"{v / 1000000:.1f}M"
    if v >= 1000:
        return f"{v / 1000:.0f}k"
    return str(v)


def _fmt_cost(v) -> str:
    if v is None:
        return "?"
    return f"${v:.4f}"


# Tokens rendered as uppercase acronyms in derived display names.
_NAME_ACRONYMS = {
    "gpt": "GPT", "api": "API", "url": "URL", "http": "HTTP", "https": "HTTPS",
    "ai": "AI", "ml": "ML", "llm": "LLM", "ui": "UI", "cli": "CLI", "json": "JSON",
    "xml": "XML", "html": "HTML", "css": "CSS", "js": "JS", "ts": "TS",
    "db": "DB", "id": "ID", "qa": "QA", "v": "v", "glm": "GLM", "dbrx": "DBRX",
    "qwen": "Qwen", "deepseek": "DeepSeek", "llama": "Llama", "mistral": "Mistral",
    "claude": "Claude", "gemini": "Gemini", "phi": "Phi", "gemma": "Gemma",
    "yi": "Yi", "r1": "R1", "v3": "V3", "v2": "V2", "v1": "V1",
}


def humanize_model_id(model_id: str) -> str:
    """Derive a readable label from a model id, e.g.
    ``glm-5.3-flash`` -> ``GLM 5.3 Flash``,
    ``claude-opus-4.8-thinking`` -> ``Claude Opus 4.8 Thinking``.

    Used when creating or formatting a model spec so that the model's display name
    is derived directly from its own model ID rather than inheriting an outdated
    or mismatched name from a fallback/matched catalog entry.
    """
    if not model_id:
        return model_id
    s = _NAMESPACE_RE.sub("", str(model_id).strip())
    parts = re.split(r"[-_/:]", s)
    out = []
    for p in parts:
        if not p:
            continue
        low = p.lower()
        if low in _NAME_ACRONYMS:
            out.append(_NAME_ACRONYMS[low])
        elif re.fullmatch(r"\d+(\.\d+)*", p) or re.fullmatch(r"\d{6,8}", p):
            out.append(p)
        elif re.fullmatch(r"\d+[xX]\d+[bBmMkK]|\d+[bBmMkK]", p):
            out.append(p.upper())
        else:
            out.append(p[:1].upper() + p[1:].lower())
    return " ".join(out)


def build_spec_from_format(fmt: ModelFormat, model_id: Optional[str] = None) -> dict:
    """Convert a normalized ModelFormat back into a config-shaped spec.

    When `model_id` is supplied, the spec name is set according to `model_id`
    (e.g. humanized name derived from `model_id`) to ensure models like
    `glm-5.3-flash` get `GLM 5.3 Flash` instead of the name of the matched entry.
    """
    spec = {}
    if model_id is not None:
        if fmt.model_id == model_id and fmt.name and fmt.name != fmt.model_id:
            spec["name"] = fmt.name
        else:
            spec["name"] = humanize_model_id(model_id)
    elif fmt.name and fmt.name != fmt.model_id:
        spec["name"] = fmt.name

    limit = {}
    if fmt.context is not None:
        limit["context"] = fmt.context
    if fmt.output is not None:
        limit["output"] = fmt.output
    if limit:
        spec["limit"] = limit

    cost = {}
    if fmt.cost_in is not None:
        cost["input"] = fmt.cost_in
    if fmt.cost_out is not None:
        cost["output"] = fmt.cost_out
    if fmt.cost_cache_read is not None:
        cost["cache_read"] = fmt.cost_cache_read
    if fmt.cost_cache_write is not None:
        cost["cache_write"] = fmt.cost_cache_write
    if cost:
        spec["cost"] = cost

    if not fmt.modalities.inferred:
        spec["modalities"] = {
            "input": list(fmt.modalities.input_mods),
            "output": list(fmt.modalities.output_mods),
        }

    if fmt.attachment:
        spec["attachment"] = True
    if fmt.reasoning:
        spec["reasoning"] = True
    if fmt.tools:
        spec["tool_call"] = True
    if fmt.temperature:
        spec["temperature"] = True
    return spec


@dataclass
class ApplyReport:
    """Result of applying catalog specs to a config's providers."""
    matched: List[str] = field(default_factory=list)
    filled: List[str] = field(default_factory=list)
    added: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)
    ambiguous: List[tuple] = field(default_factory=list)

    def any_changes(self) -> bool:
        return bool(self.matched or self.filled or self.added)


def apply_catalog_to_config(catalog, config_providers: dict, *,
                            overwrite: bool = False,
                            add_new: bool = False,
                            resolve_fn=None) -> ApplyReport:
    """Match each configured model id against the catalog and merge specs."""
    report = ApplyReport()
    formats = catalog.formats()

    for prov_name, prov_cfg in list((config_providers or {}).items()):
        if not isinstance(prov_cfg, dict):
            continue
        models = prov_cfg.get("models")
        if models is None:
            # Only create an empty models map if we'll actually add something.
            has_new = add_new and bool(formats.get(prov_name))
            models = prov_cfg.setdefault("models", {}) if has_new else {}
        if not isinstance(models, dict):
            continue

        for mid, spec in list(models.items()):
            matches = catalog.find_model(mid)
            if not matches:
                report.unknown.append(f"{prov_name}/{mid}")
                continue

            chosen = _resolve_match(matches, prov_name, mid, resolve_fn)
            if chosen is None:
                report.ambiguous.append((prov_name, mid, matches))
                continue

            merged = _merge_model_spec(spec, build_spec_from_format(chosen, mid), overwrite)
            changed = merged != (spec or {})
            if changed:
                models[mid] = merged
                report.filled.append(f"{prov_name}/{mid}")
            else:
                report.unchanged.append(f"{prov_name}/{mid}")

        if add_new:
            known_ids = set(models.keys())
            for fmt in formats.get(prov_name, {}).values():
                if fmt.model_id not in known_ids:
                    models[fmt.model_id] = build_spec_from_format(fmt)
                    report.added.append(f"{prov_name}/{fmt.model_id}")
                    known_ids.add(fmt.model_id)

    return report


def _resolve_match(matches, prov_name, mid=None, resolve_fn=None):
    """Pick a match: prefer same provider name, else ask resolve_fn, else first."""
    if len(matches) == 1:
        return matches[0]
    for m in matches:
        if m.provider == prov_name:
            return m
    if resolve_fn is not None:
        return resolve_fn(prov_name, mid, matches)
    return None


def _format_completeness(fmt: ModelFormat) -> int:
    """Count how much metadata a format carries (used to rank matches)."""
    score = 0
    for v in (fmt.context, fmt.output, fmt.cost_in, fmt.cost_out,
              fmt.cost_cache_read, fmt.cost_cache_write):
        if v is not None:
            score += 1
    if not fmt.modalities.inferred:
        score += 1
    if fmt.name and fmt.name != fmt.model_id:
        score += 1
    return score


def _sort_matches(matches, prov_name):
    """Order matches: same provider name first, then by completeness (desc)."""
    return sorted(
        matches,
        key=lambda m: (m.provider != prov_name, -_format_completeness(m)),
    )


_VERSION_SUFFIX = re.compile(
    r'[-_](\d{4}[-_]\d{2}[-_]\d{2}'                   # YYYY-MM-DD
    r'|\d{4}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])'     # YYYYMMDD
    r'|(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])'          # MMDD (common for preview models)
    r'|v\d+(\.\d+)*|latest|preview|stable)$',
    re.IGNORECASE)

# Prefixes and suffixes to strip during normalization. Order matters for suffixes.
_NORM_PREFIXES = ("google/", "google:", "anthropic.", "openai:", "zh-", "en-")

# A leading "namespace" token followed by '/', e.g. "df/", "anthropic/",
# "opencode-provider/". Stripped so that "df/claude-opus-4.8" collapses to
# "claude-opus-4.8" and matches catalog entries stored under any other (or no)
# namespace.
#
# Only a '/' introduces a namespace. A ':' must be kept: in Ollama, Bedrock and
# OpenRouter ids it separates a model name from a tag or size
# ("deepseek-r1:free", "amazon.nova-micro-v1:0", "qwen2.5-coder:32b"), and
# stripping it collapses unrelated families onto the same key.
_NAMESPACE_RE = re.compile(r'^[^/]+/')

# Same idea for display names: only the path part is a namespace.

# A trailing dotted version (e.g. "4.8", "2.1", "3.5.2") reduced to its major,
# so "claude-opus-4.8" -> "claude-opus-4" and matches "claude-opus-4".
_DOTTED_VERSION_RE = re.compile(r'(-\d+)(?:\.\d+)+$')
_NORM_SUFFIXES = (
    "-thinking",
    "-online",
    "-tool-use", "-tool_use", "-tools",
    "-preview", "-rc", "-beta", "-alpha", "-canary",
    "-latest", "-stable",
    "-chat", "-instruct", "-completions", "-completion",
    "-code", "-text",
    "-with-vision", "-vision", "-with",
)


def _normalize_model_id(mid: str) -> str:
    """Normalize a model id for fuzzy matching: lowercase, hyphens,
    a leading namespace token, and trailing version/date/general suffixes stripped."""
    s = str(mid).strip().lower().replace("_", "-")

    # Strip leading path namespaces ("df/anthropic/claude" -> "claude").
    # A trailing ':tag' is part of the model id and is deliberately kept.
    while _NAMESPACE_RE.match(s):
        s = _NAMESPACE_RE.sub("", s, count=1)

    # Strip curated prefixes
    for prefix in _NORM_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break

    # Iteratively strip version/date and general suffixes
    changed = True
    while changed:
        changed = False
        # Try version/date regex first
        new_s = _VERSION_SUFFIX.sub("", s)
        if new_s != s:
            s = new_s
            changed = True
            continue
        # Try general suffixes
        for suffix in _NORM_SUFFIXES:
            if s.endswith(suffix):
                s = s[:-len(suffix)]
                changed = True
                break

    return s.strip("-") or str(mid).strip().lower()


def _normalized_match_keys(model_id: str) -> List[str]:
    """Candidate normalized keys for matching, most specific first.

    Starts from the fully-normalized id, then progressively drops trailing
    version/date segments so that e.g. ``df/claude-opus-4.8`` can also match a
    catalog entry stored as ``anthropic/claude-opus-4`` or ``claude-opus``.
    """
    base = _normalize_model_id(model_id)
    if not base:
        return []
    keys = [base]
    cur = base
    while True:
        new = None
        # 1) Reduce a trailing "N.M" dotted version to its major "N".
        red = _DOTTED_VERSION_RE.sub(r"\1", cur)
        if red != cur and red:
            new = red
        # 2) Drop a trailing version/date token (vN, dates, latest, ...).
        if new is None:
            red = _VERSION_SUFFIX.sub("", cur)
            if red != cur and red:
                new = red
        # 3) Drop a bare trailing "-N" or "-N.M" version.
        if new is None:
            m = re.search(r'-\d+(?:\.\d+)*$', cur)
            if m:
                red = cur[:m.start()]
                if red:
                    new = red
        if new is None or new in keys:
            break
        keys.append(new)
        cur = new
    return keys




def _find_fallback(mid: str, reference_provider: Optional[str], catalog):
    """Try to find a catalog format for an unmatched model id.

    Order: (a) exact id within the reference provider, (b) normalized-id
    match within the reference provider, (c) normalized-id match anywhere,
    (d) version-stripped variants, (e) longest shared prefix within the
    reference provider.
    Returns a ModelFormat or None. Never raises on a missing catalog.

    Normalized lookups go through the catalog's `normalized_index` instead of
    re-normalizing every catalog id: `find_model` has already missed this id
    there, so a full rescan cannot find anything new.
    """
    if catalog is None or not getattr(catalog, "loaded", lambda: False)():
        return None
    formats = catalog.formats()

    # (a) exact id within reference provider
    if reference_provider:
        fmt = formats.get(reference_provider, {}).get(mid)
        if fmt is not None:
            return fmt

    normalized = _normalize_model_id(mid)
    if not normalized:
        return None

    normalized_index = getattr(catalog, "normalized_index", None)

    def _lookup(key, provider=None):
        """First catalog format whose id (or alias) normalizes to `key`."""
        if normalized_index is not None:
            for cand_id in normalized_index.get(key, []):
                for pid in catalog._model_index.get(cand_id, []):
                    if provider is not None and pid != provider:
                        continue
                    fmt = formats.get(pid, {}).get(cand_id)
                    if fmt is not None:
                        return fmt
            return None
        # Duck-typed catalogs without an index: fall back to a scan.
        for pid, pmap in formats.items():
            if provider is not None and pid != provider:
                continue
            for cand_id, fmt in pmap.items():
                if _normalize_model_id(cand_id) == key:
                    return fmt
        return None

    # (b) full normalized match within the reference provider first.
    fmt = _lookup(normalized, reference_provider) if reference_provider else None
    if fmt is not None:
        return fmt


    # (c) full normalized match anywhere in the catalog.
    fmt = _lookup(normalized)
    if fmt is not None:
        return fmt

    # (d) version-stripped variants, most specific key first.
    for key in _normalized_match_keys(mid):
        if key == normalized:
            continue
        fmt = _lookup(key)
        if fmt is not None:
            return fmt

    # (e) longest shared prefix within the reference provider
    if reference_provider:
        pmap = formats.get(reference_provider, {})
        best, best_len = None, 0
        for cand_id, fmt in pmap.items():
            cand_norm = _normalize_model_id(cand_id)
            if not cand_norm:
                continue
            common = 0
            for a, b in zip(normalized, cand_norm):
                if a != b:
                    break
                common += 1
            # Require a meaningful prefix and a remaining "family" shape.
            if common > best_len and common >= min(len(normalized), len(cand_norm)) - 4 \
                    and common >= 4:
                best, best_len = fmt, common
        return best

    return None


def _parse_catalog_data(data: dict):
    """Split raw catalog JSON into `(by_provider, flat)` model maps.

    Raises ValueError for an empty object or an unrecognized shape, so callers
    can validate a download before replacing a good cache with it.
    """
    if not isinstance(data, dict) or not data:
        raise ValueError("Catalog JSON must be a non-empty object.")

    by_provider, flat = {}, {}

    # models.dev-style dump: {providerId: {..., "models": {id: spec}}}
    if all(isinstance(v, dict) and "models" in v for v in data.values()):
        for pid, pdata in data.items():
            models = pdata.get("models", {})
            if isinstance(models, dict):
                by_provider[pid] = dict(models)
                for mid, spec in models.items():
                    flat.setdefault(mid, spec)

    # Single provider dump: {"id":..., "models": {...}}
    elif "models" in data and isinstance(data["models"], dict):
        pid = data.get("id") or "provider"
        by_provider[pid] = dict(data["models"])
        flat.update(data["models"])

    # Flat map: {modelId: spec}
    elif all(isinstance(v, dict) for v in data.values()):
        flat.update(data)
        # Provide a synthetic provider so the normalized formats still work.
        by_provider["provider"] = dict(data)

    else:
        raise ValueError("Unrecognized model catalog format.")

    if not by_provider or not flat:
        raise ValueError("Catalog contains no models.")
    return by_provider, flat


def _validate_catalog_data(data: dict) -> None:
    """Raise ValueError unless `data` is a catalog this app can index."""
    _parse_catalog_data(data)


# Provider model-list fetching (adapters, SSRF guard, response parsing)
# ---------------------------------------------------------------------------
# Provider model fetching (import a new provider by fetching its model list)
# ---------------------------------------------------------------------------

class FetchError(Exception):
    """Raised when fetching or parsing a provider's model list fails."""


@dataclass
class ProviderFetchSpec:
    """Describes how to fetch a model list from a provider API."""
    base_url: str
    adapter: str = "openai"           # openai | anthropic | gemini | models_dev | generic
    api_key: str = ""
    extra_headers: Dict[str, str] = field(default_factory=dict)
    # Generic adapter only:
    items_path: str = ""              # dotted path to the array, e.g. "data" or "result.models"
    id_field: str = ""                # field within each item holding the model id
    name_field: str = ""              # field within each item holding the display name
    allow_local: bool = False         # permit localhost / private IPs (Ollama, LM Studio)
    timeout: int = 15


# Well-known adapter presets: (endpoint suffix, auth mode, items_path, id_field).
FETCH_ADAPTERS = {
    "openai": {
        "label": "OpenAI-compatible (/models)",
        "suffix": "/models",
        "auth": "bearer",
        "items_path": "data",
        "id_field": "id",
        "name_field": "id",
    },
    "anthropic": {
        "label": "Anthropic / Claude (/v1/models)",
        "suffix": "/v1/models",
        "auth": "x-api-key",
        "items_path": "data",
        "id_field": "id",
        "name_field": "display_name",
    },
    "gemini": {
        "label": "Google Gemini (/v1beta/models)",
        "suffix": "/v1beta/models",
        "auth": "query-key",
        "items_path": "models",
        "id_field": "name",
        "name_field": "displayName",
    },
    "models_dev": {
        "label": "models.dev catalog (api.json)",
        "suffix": "",
        "auth": "none",
        "items_path": "",   # handled specially (catalog dump)
        "id_field": "id",
        "name_field": "name",
    },
    "generic": {
        "label": "Generic JSON (custom path)",
        "suffix": "",
        "auth": "bearer",
        "items_path": "data",
        "id_field": "id",
        "name_field": "name",
    },
}


def stale_configured_models(existing_models, fetched_ids):
    """Configured model ids that the API no longer lists (sorted)."""
    if not isinstance(existing_models, dict):
        return []
    fetched = set(fetched_ids)
    return sorted(m for m in existing_models if m not in fetched)


def npm_for_fetch(adapter: str, base_url: str) -> str:
    """Best AI-SDK npm package for a provider fetched from base_url.

    The "openai" fetch format also serves OpenAI-compatible gateways
    (OpenRouter, LiteLLM, vLLM...), which need @ai-sdk/openai-compatible;
    only openai.com itself gets the dedicated package.
    """
    host = ""
    if base_url:
        host = (urllib.parse.urlparse(base_url).hostname or "").lower()
    if adapter == "anthropic":
        return "@ai-sdk/anthropic"
    if adapter == "gemini":
        return "@ai-sdk/google"
    if adapter == "openai" and (host == "openai.com" or host.endswith(".openai.com")):
        return "@ai-sdk/openai"
    return "@ai-sdk/openai-compatible"


def apply_fetched_provider(providers, key, selected, base_url="", api_key="",
                           save_api_key=True, npm="@ai-sdk/openai",
                           remove_missing=False):
    """Merge fetched models into providers[key], persisting the endpoint config.

    - creates the entry with `npm` when missing (an existing npm is kept)
    - writes options.baseURL from the URL the models were fetched from; an
      empty base_url (list/catalog formats) never writes and never clears an
      existing options.baseURL
    - writes options.apiKey only when save_api_key is true and a key was given;
      an existing apiKey is never deleted
    - existing model specs are never overwritten (API listings carry id/name
      only; the catalog auto-match enriches specs separately)
    - remove_missing=True also drops configured models absent from the fetch
      result (opt-in sync; default keeps them)

    Returns (provider_dict, summary) where summary has added/kept/removed ids.
    """
    prov = providers.get(key)
    if not isinstance(prov, dict):
        prov = {"npm": npm, "name": key, "models": {}}
        providers[key] = prov
    if not isinstance(prov.get("models"), dict):
        prov["models"] = {}
    added, kept = [], []
    for mid, spec in selected.items():
        if mid in prov["models"]:
            kept.append(mid)
        else:
            added.append(mid)
        prov["models"].setdefault(mid, dict(spec))
    removed = []
    if remove_missing:
        for mid in sorted(prov["models"]):
            if mid not in selected:
                del prov["models"][mid]
                removed.append(mid)
    if base_url or (save_api_key and api_key):
        opts = prov.get("options")
        if not isinstance(opts, dict):
            opts = {}
            prov["options"] = opts
        if base_url:
            opts["baseURL"] = base_url
        if save_api_key and api_key:
            opts["apiKey"] = api_key
    return prov, {"added": sorted(added), "kept": sorted(kept), "removed": removed}

def api_base_url_for(adapter: str, base_url: str) -> str:
    """The options.baseURL to persist for a fetch, or '' for list formats.

    List/catalog formats (models.dev, generic) fetched a listing URL that is
    *not* an API base, so nothing is persisted for them. Every API-style
    format persists its base; for anthropic/gemini the version segment is
    part of the base the AI SDK expects (Anthropic normalises a bare host,
    Google does not), so it is added when missing.
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return ""
    preset = FETCH_ADAPTERS.get(adapter, FETCH_ADAPTERS["generic"])
    if adapter in ("models_dev", "generic"):
        return ""
    version = _version_segment(preset["suffix"]) if preset.get("suffix") else ""
    if not version or _has_version_segment(base, version):
        return base
    return f"{base}/{version}"


def _version_segment(suffix: str) -> str:
    """'v1/models' -> 'v1'; '' when the suffix carries no version segment."""
    first = (suffix or "").strip("/").split("/")[0]
    return first if re.fullmatch(r"v\d+[a-z0-9]*", first or "") else ""


def _has_version_segment(base: str, version: str) -> bool:
    """True when the last path segment of base already is the version."""
    path = urllib.parse.urlparse(base).path.rstrip("/")
    return path.rsplit("/", 1)[-1] == version


def _join_fetch_suffix(base: str, suffix: str) -> str:
    """Append an adapter suffix without duplicating the version segment.

    An SDK base may already carry its version ('https://api.x/v1', '.../v1beta');
    joining 'v1/models' onto it must yield '.../v1/models', not '.../v1/v1/models'.
    """
    base = (base or "").strip().rstrip("/")
    suffix = (suffix or "").strip().strip("/")
    if not suffix:
        return base
    if base.endswith(suffix):
        return base
    version = _version_segment(suffix)
    if version and _has_version_segment(base, version):
        return f"{base}/{suffix.split('/', 1)[1]}"
    return f"{base}/{suffix}"


def _is_local_host(host: str) -> bool:
    """True if host is localhost or resolves to a private/loopback address."""
    if not host:
        return True
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass
    # Resolve hostname; if any resolved address is private, treat as local.
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return True
            except ValueError:
                continue
    except (socket.gaierror, OSError):
        # Cannot resolve; let the request itself fail rather than blocking.
        return False
    return False


def _validate_fetch_url(url: str, allow_local: bool):
    """Basic SSRF guard: require http(s) and block private hosts unless allowed."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("URL must use http:// or https://")
    if not parsed.hostname:
        raise FetchError("URL has no host")
    if not allow_local and _is_local_host(parsed.hostname):
        raise FetchError(
            f"Refusing to fetch from local/private host '{parsed.hostname}'. "
            "Enable 'Allow local URL' for Ollama/LM Studio.")
    return parsed


def _build_fetch_url(spec: ProviderFetchSpec) -> str:
    """Combine base_url + adapter suffix (+ query key for Gemini).

    The join is version-aware: a base that already ends in the adapter's
    version segment ('/v1', '/v1beta') is not doubled.
    """
    preset = FETCH_ADAPTERS.get(spec.adapter, FETCH_ADAPTERS["generic"])
    url = _join_fetch_suffix(spec.base_url, preset["suffix"])
    if preset["auth"] == "query-key" and spec.api_key:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}key={urllib.parse.quote(spec.api_key)}"
    return url


def _build_fetch_headers(spec: ProviderFetchSpec) -> Dict[str, str]:
    preset = FETCH_ADAPTERS.get(spec.adapter, FETCH_ADAPTERS["generic"])
    headers = {"User-Agent": f"{APP_NAME}/{APP_VERSION}", "Accept": "application/json"}
    auth = preset["auth"]
    if spec.api_key and auth == "bearer":
        headers["Authorization"] = f"Bearer {spec.api_key}"
    elif spec.api_key and auth == "x-api-key":
        headers["x-api-key"] = spec.api_key
        headers["anthropic-version"] = "2023-06-01"
    headers.update(spec.extra_headers or {})
    return headers


def _extract_by_path(data, dotted: str):
    """Follow a dotted path; empty path returns data unchanged."""
    if not dotted:
        return data
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _gemini_model_id(raw_id: str) -> str:
    """Gemini ids come as 'models/gemini-1.5-pro'; strip the prefix."""
    if isinstance(raw_id, str) and raw_id.startswith("models/"):
        return raw_id[len("models/"):]
    return raw_id


def parse_fetched_models(data, spec: ProviderFetchSpec) -> dict:
    """Normalize a fetched API response into a {model_id: spec} map."""
    preset = FETCH_ADAPTERS.get(spec.adapter, FETCH_ADAPTERS["generic"])

    # models.dev returns a full catalog dump; flatten across providers.
    if spec.adapter == "models_dev":
        flat = {}
        if isinstance(data, dict):
            for _pid, pdata in data.items():
                if isinstance(pdata, dict) and isinstance(pdata.get("models"), dict):
                    for mid, mspec in pdata["models"].items():
                        flat.setdefault(mid, mspec)
        if not flat:
            raise FetchError("models.dev response contained no models.")
        return flat

    items_path = spec.items_path or preset["items_path"]
    id_field = spec.id_field or preset["id_field"]
    name_field = spec.name_field or preset["name_field"]

    items = _extract_by_path(data, items_path)
    # Some APIs return the array at the top level.
    if items is None and isinstance(data, list):
        items = data
    if not isinstance(items, list):
        raise FetchError(
            f"Could not find a model array at path '{items_path or '(root)'}'. "
            "Check the format / path.")

    out = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get(id_field)
        if not raw_id:
            continue
        mid = _gemini_model_id(raw_id) if spec.adapter == "gemini" else str(raw_id)
        model_spec = {}
        display = item.get(name_field)
        if display and str(display) != mid:
            model_spec["name"] = str(display)
        out[mid] = model_spec
    if not out:
        raise FetchError("No models with a valid id were found in the response.")
    return out


MAX_FETCH_PAGES = 20


class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-runs the SSRF guard on every redirect target.

    urllib follows 30x to any host and would replay the Authorization /
    x-api-key headers. Each hop is re-validated with the same guard, and
    credentials are stripped when the origin changes.
    """

    def __init__(self, allow_local: bool):
        super().__init__()
        self.allow_local = allow_local

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_fetch_url(newurl, self.allow_local)
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        old = urllib.parse.urlparse(req.full_url)
        target = urllib.parse.urlparse(newurl)
        if (old.scheme, old.hostname) != (target.scheme, target.hostname):
            sensitive = {"authorization", "x-api-key", "proxy-authorization", "cookie"}
            for key in list(new.headers):
                if key.lower() in sensitive:
                    new.headers.pop(key, None)
        return new


def _guarded_opener(allow_local: bool):
    """An opener that applies _GuardedRedirectHandler to every request."""
    return urllib.request.build_opener(_GuardedRedirectHandler(allow_local))


def _next_page_url(data, spec: ProviderFetchSpec, current_url: str) -> str:
    """URL of the next page, or '' when this was the last one."""
    if not isinstance(data, dict):
        return ""
    parts = urllib.parse.urlsplit(current_url)
    if spec.adapter == "anthropic":
        if not data.get("has_more"):
            return ""
        token = data.get("last_id") or data.get("after_id")
        if not token:
            return ""
        query = {"before_id": "", "after_id": str(token)}
    elif spec.adapter == "gemini":
        token = data.get("nextPageToken")
        if not token:
            return ""
        query = {"pageToken": str(token)}
    else:
        return ""
    params = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    params.update({k: v for k, v in query.items() if v})
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(params),
         parts.fragment))


def _read_page(url, headers, spec, opener):
    """One HTTP(S) request, through the injected opener or the guarded one."""
    if opener is not None:
        raw = opener(url, headers, spec.timeout)
    else:
        req = urllib.request.Request(url, headers=headers)
        try:
            with _guarded_opener(spec.allow_local).open(req, timeout=spec.timeout) as r:
                raw = r.read()
        except FetchError:
            raise
        except Exception as e:  # urllib raises many subclasses; surface uniformly
            raise FetchError(f"Request failed: {e}") from e
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise FetchError(f"Response was not valid JSON: {e}") from e


def fetch_provider_models(spec: ProviderFetchSpec, *, opener=None) -> dict:
    """Fetch and normalize a provider's model list. Returns {model_id: spec}.

    Follows Anthropic (has_more/last_id) and Gemini (nextPageToken)
    pagination up to MAX_FETCH_PAGES.

    `opener` is an optional callable(url, headers, timeout) -> bytes, injected
    for testing so no real network call is made.
    """
    url = _build_fetch_url(spec)
    _validate_fetch_url(url, spec.allow_local)
    headers = _build_fetch_headers(spec)

    merged: dict = {}
    for _page in range(MAX_FETCH_PAGES):
        data = _read_page(url, headers, spec, opener)
        merged.update(parse_fetched_models(data, spec))
        next_url = _next_page_url(data, spec, url)
        if not next_url:
            return merged
        _validate_fetch_url(next_url, spec.allow_local)
        url = next_url
    return merged


# Connectivity and Health Check module for Provider APIs
# ---------------------------------------------------------------------------


@dataclass
class ConnectionTestResult:
    """Result of testing connectivity to a model provider API."""
    success: bool
    latency_ms: float = 0.0
    status_code: int = 0
    message: str = ""
    model_count: Optional[int] = None
    models: List[str] = field(default_factory=list)
    raw_error: str = ""

    def summary(self) -> str:
        if self.success:
            count_str = f" ({self.model_count} models found)" if self.model_count is not None else ""
            return f"✓ Connected in {self.latency_ms:.0f}ms{count_str}"
        return f"✗ Failed: {self.message}"



# opencode config variables: '{env:VAR}' and '{file:path}'
# https://opencode.ai/docs/config/#variables
_PLACEHOLDER_RE = re.compile(r"\{(env|file):([^{}]*)\}")


def _resolve_one_placeholder(kind: str, arg: str, config_dir: Optional[Path]) -> str:
    if kind == "env":
        return os.environ.get(arg, "")
    path = Path(arg.strip()).expanduser()
    if not path.is_absolute():
        path = Path(config_dir) / path
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def resolve_config_placeholders(value: str, config_dir: Optional[Path] = None) -> str:
    """Expand opencode's {env:VAR} / {file:path} config variables in a string.

    An unset variable or an unreadable file expands to an empty string, as
    opencode does. Relative {file:} paths resolve against the config file's
    directory (config_dir); '~' and absolute paths are used as-is.
    """
    if not isinstance(value, str) or "{" not in value:
        return value
    return _PLACEHOLDER_RE.sub(
        lambda m: _resolve_one_placeholder(m.group(1), m.group(2), config_dir), value
    )


def _redact_url_secrets(url: str) -> str:
    """Mask credentials carried in the query string (e.g. Gemini's ?key=)."""
    return re.sub(r"([?&](?:key|api_key|apikey|token|access_token)=)[^&]*",
                  r"\1***", url or "")



def _sanitize_secret(text: str, secret: str) -> str:
    """Strip the configured key out of text that is shown in the UI.

    urllib echoes the request line and the header block back in its errors (a
    base URL with a space, a key with a newline), so a bare str(e) can leak
    the credential into the Diagnostic Log. The key is masked both literally
    and in the repr-escaped form urllib prints for invalid header values.
    """
    out = _redact_url_secrets(text or "")
    if not secret:
        return out
    out = out.replace(secret, "***")
    for line in secret.splitlines():
        stripped = line.strip()
        if len(stripped) >= 4:
            out = out.replace(stripped, "***")
    return out


def test_provider_connection(
    base_url: str,
    api_key: str = "",
    adapter: str = "openai",
    timeout: int = 10,
    allow_local: bool = True,
    opener=None,
) -> ConnectionTestResult:
    """Send a lightweight test request to verify API endpoint connectivity and authentication.

    Measures latency and extracts model list when possible.
    """
    if not base_url or not base_url.strip():
        return ConnectionTestResult(
            success=False,
            message="Base URL is empty.",
            raw_error="Empty URL",
        )

    clean_url = base_url.strip()
    spec = ProviderFetchSpec(
        base_url=clean_url,
        adapter=adapter,
        api_key=api_key.strip() if api_key else "",
        allow_local=allow_local,
        timeout=timeout,
    )

    t0 = time.perf_counter()
    url = ""
    try:
        url = _build_fetch_url(spec)
        _validate_fetch_url(url, spec.allow_local)
        headers = _build_fetch_headers(spec)

        if opener is not None:
            raw = opener(url, headers, spec.timeout)
            status_code = 200
        else:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=spec.timeout) as r:
                raw = r.read()
                status_code = getattr(r, "status", 200)

        latency_ms = (time.perf_counter() - t0) * 1000.0

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        data = json.loads(raw)
        models_dict = parse_fetched_models(data, spec)
        model_keys = sorted(models_dict.keys())

        return ConnectionTestResult(
            success=True,
            latency_ms=latency_ms,
            status_code=status_code,
            message="Connection successful",
            model_count=len(model_keys),
            models=model_keys[:50],
        )

    except FetchError as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        text = _sanitize_secret(str(e), spec.api_key)
        return ConnectionTestResult(
            success=False,
            latency_ms=latency_ms,
            message=text,
            raw_error=text,
        )
    except urllib.error.HTTPError as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        msg = f"HTTP {e.code}: {e.reason}"
        if e.code == 401:
            msg = "HTTP 401: Unauthorized (Invalid or missing API key)"
        elif e.code == 403:
            msg = "HTTP 403: Forbidden (Access denied or insufficient permissions)"
        elif e.code == 404:
            msg = f"HTTP 404: Endpoint not found ({_redact_url_secrets(url)})"
        elif e.code == 429:
            msg = "HTTP 429: Rate limited or quota exhausted"
        return ConnectionTestResult(
            success=False,
            latency_ms=latency_ms,
            status_code=e.code,
            message=_sanitize_secret(msg, spec.api_key),
            raw_error=_sanitize_secret(str(e), spec.api_key),
        )
    except urllib.error.URLError as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        reason = str(e.reason)
        if "Connection refused" in reason:
            reason = "Connection refused (Check if local server like Ollama/vLLM is running)"
        return ConnectionTestResult(
            success=False,
            latency_ms=latency_ms,
            message=_sanitize_secret(f"Network error: {reason}", spec.api_key),
            raw_error=_sanitize_secret(str(e), spec.api_key),
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ConnectionTestResult(
            success=False,
            latency_ms=latency_ms,
            message=_sanitize_secret(f"Error: {e}", spec.api_key),
            raw_error=_sanitize_secret(str(e), spec.api_key),
        )
# MCP Server Templates and Hub Catalog
# ---------------------------------------------------------------------------


@dataclass
class MCPTemplate:
    id: str
    name: str
    category: str  # "Memory & Context", "System & Files", "Developer Tools", "Data & Web", "Database"
    description: str
    transport_type: str  # "local" | "remote"
    command: List[str] = field(default_factory=list)
    url: str = ""
    env_keys: Dict[str, str] = field(default_factory=dict)  # key -> placeholder/hint
    default_args: List[str] = field(default_factory=list)
    doc_url: str = ""


MCP_REGISTRY: List[MCPTemplate] = [
    MCPTemplate(
        id="memory",
        name="Memory (Knowledge Graph)",
        category="Memory & Context",
        description="Persistent memory and knowledge graph storage across AI sessions using official MCP memory server.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-memory"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/memory",
    ),
    MCPTemplate(
        id="filesystem",
        name="Filesystem Access",
        category="System & Files",
        description="Secure file system access to read, write, and list files within specified directories.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "{allowed_directory}"],
        default_args=["/path/to/allowed/directory"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
    ),
    MCPTemplate(
        id="github",
        name="GitHub Integration",
        category="Developer Tools",
        description="Search repositories, view code, inspect pull requests, and manage issues directly on GitHub.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-github"],
        env_keys={"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxxxxxxxxxx"},
        doc_url="https://github.com/modelcontextprotocol/servers-archived/tree/main/src/github",
    ),
    MCPTemplate(
        id="brave-search",
        name="Brave Search",
        category="Data & Web",
        description="Web search and local business search via Brave Search API for live internet knowledge.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-brave-search"],
        env_keys={"BRAVE_API_KEY": "BSAxxxxxxxxxxxx"},
        doc_url="https://github.com/modelcontextprotocol/servers-archived/tree/main/src/brave-search",
    ),
    MCPTemplate(
        id="fetch",
        name="Web Page Fetcher",
        category="Data & Web",
        description="Fetch web pages, extract content, and convert HTML to clean markdown for reading.",
        transport_type="local",
        command=["uvx", "mcp-server-fetch"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/fetch",
    ),
    MCPTemplate(
        id="postgres",
        name="PostgreSQL Inspector",
        category="Database",
        description="Read-only or read/write schema inspection and querying for PostgreSQL databases.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-postgres", "{connection_string}"],
        default_args=["postgresql://user:password@localhost:5432/my_database"],
        doc_url="https://github.com/modelcontextprotocol/servers-archived/tree/main/src/postgres",
    ),
    MCPTemplate(
        id="sqlite",
        name="SQLite Explorer",
        category="Database",
        description="Inspect tables, query schemas, and run SQL on local SQLite database files.",
        transport_type="local",
        command=["uvx", "mcp-server-sqlite", "--db-path", "{db_path}"],
        default_args=["/path/to/database.db"],
        doc_url="https://github.com/modelcontextprotocol/servers-archived/tree/main/src/sqlite",
    ),
    MCPTemplate(
        id="puppeteer",
        name="Puppeteer Browser",
        category="Data & Web",
        description="Headless browser automation to interact with dynamic web pages, take screenshots, and execute JavaScript.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-puppeteer"],
        doc_url="https://github.com/modelcontextprotocol/servers-archived/tree/main/src/puppeteer",
    ),
    MCPTemplate(
        id="git",
        name="Git Tools",
        category="Developer Tools",
        description="Query repository status, commit history, diffs, and inspect branches.",
        transport_type="local",
        command=["uvx", "mcp-server-git", "--repository", "{repo_path}"],
        default_args=["/path/to/repo"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/git",
    ),
    MCPTemplate(
        id="sequential-thinking",
        name="Sequential Thinking",
        category="Memory & Context",
        description="Dynamic, multi-step structured reasoning tool for complex problem solving and debugging.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-sequential-thinking"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking",
    ),
    MCPTemplate(
        id="context7",
        name="Context7 Docs & Libraries",
        category="Developer Tools",
        description="Up-to-date documentation and API reference lookup engine for popular libraries.",
        transport_type="local",
        command=["npx", "-y", "@upstash/context7-mcp"],
        doc_url="https://context7.com",
    ),
    MCPTemplate(
        id="remote-sse",
        name="Generic Remote MCP (SSE/HTTP)",
        category="Custom & Remote",
        description="Connect to any remote or hosted MCP server via Server-Sent Events (SSE) or HTTP endpoint.",
        transport_type="remote",
        url="https://mcp.example.com/sse",
        doc_url="https://modelcontextprotocol.io",
    ),
]


def get_mcp_template(template_id: str) -> Optional[MCPTemplate]:
    """Retrieve template by its ID."""
    for tmpl in MCP_REGISTRY:
        if tmpl.id == template_id:
            return tmpl
    return None


def instantiate_opencode_mcp(
    template: MCPTemplate,
    server_key: str,
    args_values: Optional[Dict[str, str]] = None,
    env_values: Optional[Dict[str, str]] = None,
    url_value: str = "",
) -> Dict[str, Any]:
    """Create OpenCode format config for an MCP server."""
    args_values = args_values or {}
    env_values = env_values or {}

    if template.transport_type == "remote":
        res: Dict[str, Any] = {
            "type": "remote",
            "url": url_value.strip(),
            "enabled": True,
        }
        return res

    cmd_list = []
    for part in template.command:
        formatted = part
        for k, v in args_values.items():
            formatted = formatted.replace(f"{{{k}}}", v.strip())
        cmd_list.append(formatted)

    config: Dict[str, Any] = {
        "type": "local",
        "command": cmd_list,
        "enabled": True,
    }
    clean_env = {k: v.strip() for k, v in env_values.items() if v.strip()}
    if clean_env:
        # opencode's McpLocalConfig names this field "environment" (the live
        # schema at https://opencode.ai/config.json sets additionalProperties:
        # false, so "env" is dropped silently).
        config["environment"] = clean_env

    return config


def instantiate_openclaude_mcp(
    template: MCPTemplate,
    server_key: str,
    args_values: Optional[Dict[str, str]] = None,
    env_values: Optional[Dict[str, str]] = None,
    url_value: str = "",
) -> Dict[str, Any]:
    """Create OpenClaude / Claude Code format config for an MCP server (mcpServers entry)."""
    args_values = args_values or {}
    env_values = env_values or {}

    if template.transport_type == "remote":
        return {
            "type": "sse",
            "url": url_value.strip(),
        }

    cmd_list = []
    for part in template.command:
        formatted = part
        for k, v in args_values.items():
            formatted = formatted.replace(f"{{{k}}}", v.strip())
        cmd_list.append(formatted)

    if not cmd_list:
        return {}

    command = cmd_list[0]
    args = cmd_list[1:]

    config: Dict[str, Any] = {
        "command": command,
        "args": args,
    }
    clean_env = {k: v.strip() for k, v in env_values.items() if v.strip()}
    if clean_env:
        config["env"] = clean_env

    return config
# Universal Config Converter & Cross-Import/Export Engine
# (OpenCode <-> OpenClaude <-> OMP v1 <-> Claude Desktop / Cursor)
# ---------------------------------------------------------------------------

def detect_config_format(data: dict) -> str:
    """Identify the config format of the given dictionary."""
    if not isinstance(data, dict):
        return "unknown"

    if data.get("format") == "omp/v1" or ("$schema" in data and "omp" in str(data["$schema"])):
        return "omp"

    # opencode.json (and tui.json) markers win over the OpenClaude settings keys,
    # which overlap (env, model, ...) with other formats.
    if "provider" in data or "tui" in data or "plugin" in data or "mcp" in data:
        return "opencode"

    if "providerProfiles" in data or "activeProviderProfileId" in data:
        return "openclaude_global"

    _SETTINGS_KEYS = (
        "permissions", "modelLimits", "statusLine", "env", "hooks", "model",
        "includeCoAuthoredBy", "forceLoginMethod", "cleanupPeriodDays",
    )
    if any(k in data for k in _SETTINGS_KEYS):
        return "openclaude_settings"

    if "mcpServers" in data:
        if len(data) == 1:
            return "claude_desktop"
        return "openclaude_global"

    return "generic"


# ---------------------------------------------------------------------------
# OpenCode <-> OpenClaude converters
# ---------------------------------------------------------------------------

def opencode_mcp_to_claude_mcp(opencode_mcp: dict) -> dict:
    """Convert OpenCode `mcp` dictionary to Claude `mcpServers` dictionary."""
    out = {}
    if not isinstance(opencode_mcp, dict):
        return out

    for name, cfg in opencode_mcp.items():
        if not isinstance(cfg, dict):
            continue
        stype = cfg.get("type", "local")
        if cfg.get("enabled") is False:
            continue
        entry = {}
        if stype == "remote":
            # opencode carries no transport hint; streamable HTTP is the modern default
            entry["type"] = "http"
            entry["url"] = cfg.get("url", "")
            if "headers" in cfg and isinstance(cfg["headers"], dict):
                entry["headers"] = dict(cfg["headers"])
        else:
            cmd = cfg.get("command", [])
            if isinstance(cmd, list) and cmd:
                entry["command"] = str(cmd[0])
                if len(cmd) > 1:
                    entry["args"] = [str(x) for x in cmd[1:]]
            elif isinstance(cmd, str) and cmd:
                parts = cmd.split()
                entry["command"] = parts[0]
                if len(parts) > 1:
                    entry["args"] = parts[1:]
            if isinstance(cfg.get("cwd"), str) and cfg["cwd"]:
                entry["cwd"] = cfg["cwd"]
        env = cfg.get("environment")
        if not isinstance(env, dict):
            env = cfg.get("env")
        if isinstance(env, dict):
            entry["env"] = {str(k): str(v) for k, v in env.items()}
        out[name] = entry
    return out


def claude_mcp_to_opencode_mcp(claude_mcp: dict) -> dict:
    """Convert Claude `mcpServers` dictionary to OpenCode `mcp` dictionary."""
    out = {}
    if not isinstance(claude_mcp, dict):
        return out

    for name, cfg in claude_mcp.items():
        if not isinstance(cfg, dict):
            continue
        stype = cfg.get("type", "stdio")
        if stype in ("sse", "remote", "http") or "url" in cfg:
            entry = {
                "type": "remote",
                "url": cfg.get("url", ""),
                "enabled": bool(cfg.get("enabled", True)),
            }
            if "headers" in cfg and isinstance(cfg["headers"], dict):
                entry["headers"] = dict(cfg["headers"])
        else:
            cmd_parts = []
            if "command" in cfg and cfg["command"]:
                cmd_parts.append(str(cfg["command"]))
            if "args" in cfg and isinstance(cfg["args"], list):
                cmd_parts.extend([str(a) for a in cfg["args"]])
            entry = {
                "type": "local",
                "command": cmd_parts,
                "enabled": bool(cfg.get("enabled", True)),
            }
            if isinstance(cfg.get("cwd"), str) and cfg["cwd"]:
                entry["cwd"] = cfg["cwd"]
        env = cfg.get("env")
        if isinstance(env, dict):
            entry["environment"] = {str(k): str(v) for k, v in env.items()}
        out[name] = entry
    return out


_OC_TOOL_TO_CLAUDE_RULE = {
    "read": "Read",
    "edit": "Edit",
    "write": "Write",
    "glob": "Glob",
    "grep": "Grep",
    "list": "LS",
    "bash": "Bash",
    "task": "Task",
    "todowrite": "TodoWrite",
    "webfetch": "WebFetch",
    "websearch": "WebSearch",
    "lsp": "LSP",
    "external_directory": "Read",
}
_CLAUDE_RULE_TO_OC_TOOL = {
    "read": "read",
    "edit": "edit",
    "write": "edit",
    "glob": "glob",
    "grep": "grep",
    "ls": "list",
    "bash": "bash",
    "task": "task",
    "todowrite": "todowrite",
    "webfetch": "webfetch",
    "websearch": "websearch",
}
_PERM_ACTIONS = {
    "allow": "allow",
    "true": "allow",
    "deny": "deny",
    "false": "deny",
    "block": "deny",
    "ask": "ask",
    "prompt": "ask",
}


def _opencode_rule_to_claude(tool: str, pattern, action: str) -> str:
    base = _OC_TOOL_TO_CLAUDE_RULE.get(str(tool).lower(), str(tool))
    if pattern is None:
        return base
    return f"{base}({pattern})"


def opencode_permissions_to_claude(perms: dict) -> dict:
    """Convert OpenCode permissions to OpenClaude permissions format.

    Handles both flat actions ("bash": "allow") and per-pattern rule objects
    ("bash": {"npm run *": "allow"}).
    """
    out = {"allow": [], "deny": [], "ask": []}
    if not isinstance(perms, dict):
        return out

    def _add(rule: str, action: str):
        bucket = _PERM_ACTIONS.get(str(action).lower())
        if bucket:
            out[bucket].append(rule)

    for tool, value in perms.items():
        if isinstance(value, dict):
            for pattern, action in value.items():
                _add(_opencode_rule_to_claude(tool, pattern, action), action)
        else:
            _add(_opencode_rule_to_claude(tool, None, value), value)
    for rules in out.values():
        rules.sort()
    return {k: v for k, v in out.items() if v}


def _claude_rule_to_opencode(rule: str):
    """Split a Claude rule into (tool, pattern or None)."""
    rule = str(rule).strip()
    if "(" in rule and rule.endswith(")"):
        base, pattern = rule.split("(", 1)
        return base.strip(), pattern[:-1]
    return rule, None


def claude_permissions_to_opencode(perms: dict) -> dict:
    """Convert OpenClaude permissions to OpenCode dictionary format.

    deny takes precedence over ask, which takes precedence over allow
    (Claude Code evaluates rules in that order).
    """
    out: Dict[str, Any] = {}
    if not isinstance(perms, dict):
        return out
    # Claude evaluates deny, then ask, then allow: write in that order and keep
    # the strongest action per rule so deny is never downgraded to ask/allow.
    for bucket in ("deny", "ask", "allow"):
        rules = perms.get(bucket, [])
        if isinstance(rules, str) or not isinstance(rules, (list, tuple)):
            continue
        for rule in rules:
            base, pattern = _claude_rule_to_opencode(rule)
            tool = _CLAUDE_RULE_TO_OC_TOOL.get(base.lower())
            if tool is None:
                tool = base
            if pattern is None:
                if not isinstance(out.get(tool), dict):
                    out[tool] = bucket
            else:
                nested = out.get(tool)
                if not isinstance(nested, dict):
                    if nested in ("allow", "ask", "deny"):
                        # keep the tool-wide rule and add the narrower pattern
                        nested = {"*": nested}
                    else:
                        nested = {}
                    out[tool] = nested
                nested.setdefault(pattern, bucket)
    return out


# ---------------------------------------------------------------------------
# OMP (Open Multi-Platform) Schema v1
# ---------------------------------------------------------------------------

def export_to_omp(
    opencode_cfg: Optional[dict] = None,
    openclaude_global: Optional[dict] = None,
    openclaude_settings: Optional[dict] = None,
    name: str = "My AI Development Profile",
    description: str = "",
) -> dict:
    """Export configs from OpenCode and/or OpenClaude into a unified OMP v1 bundle."""
    bundle: Dict[str, Any] = {
        "$schema": "https://opencode.ai/schemas/omp-v1.json",
        "format": "omp/v1",
        "metadata": {
            "name": name,
            "description": description,
            "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "generator": "opencode-config-editor",
        },
        "providers": {},
        "mcp_servers": {},
        "plugins": [],
        "permissions": {},
        "prompts": {},
        "settings": {},
    }

    # Extract from OpenCode
    if isinstance(opencode_cfg, dict):
        if "provider" in opencode_cfg and isinstance(opencode_cfg["provider"], dict):
            bundle["providers"] = json.loads(json.dumps(opencode_cfg["provider"]))
        if "mcp" in opencode_cfg and isinstance(opencode_cfg["mcp"], dict):
            bundle["mcp_servers"] = json.loads(json.dumps(opencode_cfg["mcp"]))
        if "plugin" in opencode_cfg:
            bundle["plugins"] = json.loads(json.dumps(opencode_cfg["plugin"]))
        if "permission" in opencode_cfg and isinstance(opencode_cfg["permission"], dict):
            bundle["permissions"] = json.loads(json.dumps(opencode_cfg["permission"]))
        if "instructions" in opencode_cfg:
            bundle["prompts"]["instructions"] = opencode_cfg["instructions"]
        if "tui" in opencode_cfg:
            bundle["settings"]["tui"] = json.loads(json.dumps(opencode_cfg["tui"]))

    # Merge/augment from OpenClaude
    if isinstance(openclaude_global, dict):
        if "mcpServers" in openclaude_global and isinstance(openclaude_global["mcpServers"], dict):
            converted = claude_mcp_to_opencode_mcp(openclaude_global["mcpServers"])
            for k, v in converted.items():
                bundle["mcp_servers"].setdefault(k, v)
        if "providerProfiles" in openclaude_global:
            bundle["settings"]["claude_provider_profiles"] = json.loads(
                json.dumps(openclaude_global["providerProfiles"])
            )

    if isinstance(openclaude_settings, dict):
        if "permissions" in openclaude_settings and isinstance(openclaude_settings["permissions"], dict):
            conv_perms = claude_permissions_to_opencode(openclaude_settings["permissions"])
            for k, v in conv_perms.items():
                bundle["permissions"].setdefault(k, v)
        if "env" in openclaude_settings and isinstance(openclaude_settings["env"], dict):
            bundle["settings"]["env"] = json.loads(json.dumps(openclaude_settings["env"]))

    return bundle


def import_from_omp(
    omp_data: dict,
    target: str = "opencode",  # "opencode" | "openclaude_settings" | "openclaude_global"
    selected_components: Optional[List[str]] = None,
) -> dict:
    """Import an OMP v1 bundle into the target config dictionary structure."""
    if not isinstance(omp_data, dict):
        return {}

    if selected_components is None:
        comps = {"providers", "mcp_servers", "plugins", "permissions", "prompts", "settings"}
    else:
        comps = set(selected_components)
    result: Dict[str, Any] = {}

    def _has(key: str) -> bool:
        """A selected component is transferred only when the bundle carries data for it."""
        if key not in comps:
            return False
        val = omp_data.get(key)
        if isinstance(val, (dict, list, str)):
            return bool(val)
        return val is not None
    if target == "opencode":
        if _has("providers") and isinstance(omp_data["providers"], dict):
            result["provider"] = json.loads(json.dumps(omp_data["providers"]))
        if _has("mcp_servers") and isinstance(omp_data["mcp_servers"], dict):
            result["mcp"] = json.loads(json.dumps(omp_data["mcp_servers"]))
        if _has("plugins"):
            result["plugin"] = json.loads(json.dumps(omp_data["plugins"]))
        if _has("permissions") and isinstance(omp_data["permissions"], dict):
            result["permission"] = json.loads(json.dumps(omp_data["permissions"]))
        if _has("prompts") and isinstance(omp_data["prompts"], dict):
            if "instructions" in omp_data["prompts"]:
                result["instructions"] = omp_data["prompts"]["instructions"]
        if _has("settings") and isinstance(omp_data["settings"], dict):
            if "tui" in omp_data["settings"]:
                result["tui"] = json.loads(json.dumps(omp_data["settings"]["tui"]))

    elif target == "openclaude_global":
        if _has("mcp_servers") and isinstance(omp_data["mcp_servers"], dict):
            servers = opencode_mcp_to_claude_mcp(omp_data["mcp_servers"])
            if servers:
                result["mcpServers"] = servers
        if _has("settings") and isinstance(omp_data["settings"], dict):
            if "claude_provider_profiles" in omp_data["settings"]:
                result["providerProfiles"] = json.loads(json.dumps(omp_data["settings"]["claude_provider_profiles"]))

    elif target == "openclaude_settings":
        if _has("permissions") and isinstance(omp_data["permissions"], dict):
            perms = opencode_permissions_to_claude(omp_data["permissions"])
            if perms:
                result["permissions"] = perms
        if _has("settings") and isinstance(omp_data["settings"], dict):
            if "env" in omp_data["settings"]:
                result["env"] = json.loads(json.dumps(omp_data["settings"]["env"]))

    return result


def extract_external_mcp_servers(raw_data: dict) -> dict:
    """Extract MCP servers from Claude Desktop (`claude_desktop_config.json`) or Cursor (`mcp.json`)."""
    if not isinstance(raw_data, dict):
        return {}
    if "mcpServers" in raw_data and isinstance(raw_data["mcpServers"], dict):
        return raw_data["mcpServers"]
    if "mcp" in raw_data and isinstance(raw_data["mcp"], dict):
        return opencode_mcp_to_claude_mcp(raw_data["mcp"])
    likely_mcp = {}
    for k, v in raw_data.items():
        if isinstance(v, dict) and ("command" in v or "url" in v or "type" in v):
            likely_mcp[k] = v
    return likely_mcp
# Agent adapter spec + registry.
#
# An AdapterSpec describes ONE agent CLI's config surface (file locations,
# known keys, which tabs to show) so the editor can be extended to a new CLI
# (opencode, openclaude, ...) by registering an adapter instead of editing the
# core. This is the seam that keeps `core` generic and each agent's specifics
# isolated in its own adapter module.

@dataclass
class AdapterSpec:
    name: str                                  # unique id, e.g. "opencode"
    app_title: str                             # window title base
    version: str
    kinds: List[str]                           # config kinds, e.g. ["opencode", "tui"]
    known_keys: Dict[str, set]                 # kind -> allowed top-level keys
    raw_files: List[Tuple[str, str]]           # [(label, kind)] for the Raw JSON combo
    targets_fn: Callable                       # (cwd) -> [(label, Path, kind)]
    make_tabs_fn: Callable                     # (window) -> [(tab_widget, title, kind|None)]
    capabilities: set = field(default_factory=set)
    # Optional session hooks. When None, MainWindow uses its built-in opencode
    # behavior; an adapter with a different config topology (e.g. openclaude's
    # layered settings) provides these to take over load/refresh/save.
    initial_load_fn: Optional[Callable] = None   # (window) -> None
    refresh_fn: Optional[Callable] = None        # (window) -> None
    save_fn: Optional[Callable] = None           # (window) -> None

    def targets(self, cwd):
        return self.targets_fn(cwd)

    def make_tabs(self, window):
        return self.make_tabs_fn(window)

    def known_keys_for(self, kind: str) -> set:
        if kind in self.known_keys:
            return self.known_keys[kind]
        # fall back to the first/primary kind's keys
        return self.known_keys.get(self.kinds[0], set()) if self.kinds else set()

    def has(self, capability: str) -> bool:
        return capability in self.capabilities


_REGISTRY: Dict[str, AdapterSpec] = {}
_DEFAULT: List[str] = []  # holds the name of the first-registered adapter


def register_adapter(spec: AdapterSpec) -> AdapterSpec:
    """Register an adapter; the first one registered becomes the default."""
    _REGISTRY[spec.name] = spec
    if not _DEFAULT:
        _DEFAULT.append(spec.name)
    return spec


def get_adapter(name: str) -> Optional[AdapterSpec]:
    return _REGISTRY.get(name)


def list_adapters() -> List[str]:
    return sorted(_REGISTRY)


def default_adapter() -> Optional[AdapterSpec]:
    return _REGISTRY.get(_DEFAULT[0]) if _DEFAULT else None
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
# Model editing and management dialogs (Models Manager and friends)
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
        for fname, edit in [
            ("input", self.cost_in_edit),
            ("output", self.cost_out_edit),
            ("cache_read", self.cost_cache_read_edit),
            ("cache_write", self.cost_cache_write_edit)
        ]:
            value = edit.text().strip()
            if value:
                try:
                    cost[fname] = float(value)
                except ValueError:
                    QMessageBox.warning(self, "Error", f"Invalid cost value for {fname}")
                    return
        if cost:
            spec["cost"] = cost

        # Limits
        limit = {}
        for fname, edit in [
            ("context", self.limit_ctx_edit),
            ("output", self.limit_out_edit)
        ]:
            value = edit.text().strip()
            if value:
                try:
                    limit[fname] = int(value)
                except ValueError:
                    QMessageBox.warning(self, "Error", f"Invalid limit value for {fname}")
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
        # Options staged by a Fetch from API, committed only on accept.
        self._pending_options = None
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
            ("Fetch from API", self._fetch_from_api),
            ("+ Add", self._add_model),
            ("Edit", self._edit_model),
            ("Remove", self._remove_model),
            ("Import", self._import_models),
            ("Export", self._export_models),
            ("Apply Catalog", self._apply_catalog),
            ("Match from Catalog", self._match_catalog),
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

    def accept(self):
        """Commit the working copy: models plus any staged endpoint options."""
        if self._pending_options is not None:
            if self._pending_options:
                self.provider_cfg["options"] = copy.deepcopy(self._pending_options)
            else:
                self.provider_cfg.pop("options", None)
            self._pending_options = None
        super().accept()

    def _fetch_from_api(self):
        """Fetch this provider's model list from its live API endpoint.

        Nothing here touches the live provider: the fetch runs against a deep
        copy so that cancelling this dialog (or the Models dialog itself)
        leaves cfg.data exactly as it was. The result is folded back into
        self.models, which the Models dialog commits on accept.
        """
        self.app.snapshot_state()
        # Pending in-dialog edits are what the user sees, so the fetch scope
        # starts from the working copy, not the last committed one.
        scope = {self.provider_key: copy.deepcopy(self.provider_cfg)}
        scope[self.provider_key]["models"] = dict(self.models)

        dlg = FetchProviderModelsDialog(self, catalog=self.app.model_catalog,
                                        provider_key=self.provider_key,
                                        providers=scope,
                                        lock_key=True)
        if dlg.exec() != QDialog.Accepted:
            return

        selected = dlg.selected_models
        if not selected:
            QMessageBox.information(self, "Fetch", "No models selected.")
            return

        # The dialog owns the policy: a list/catalog format yields '' so
        # nothing is persisted, and an SDK-style base comes back normalised.
        base_url = dlg.api_base_url()
        prov, summary = apply_fetched_provider(
            scope, self.provider_key, selected,
            base_url=base_url,
            api_key=dlg.apikey_edit.text().strip(),
            save_api_key=dlg.save_apikey_check.isChecked(),
            npm=npm_for_fetch(dlg._current_adapter(), dlg.url_edit.text().strip()))

        removed = []
        if dlg.sync_check.isChecked():
            stale = stale_configured_models(
                dict(self.models), set(dlg.fetched_models))
            if stale:
                shown = ", ".join(stale[:8])
                if len(stale) > 8:
                    shown += f", ... (+{len(stale) - 8} more)"
                if _confirm(self, "Sync Models",
                            f"Remove {len(stale)} configured model(s) the API no "
                            f"longer lists?\n{shown}"):
                    for mid in stale:
                        prov["models"].pop(mid, None)
                    removed = stale

        # The endpoint config is staged on the dialog and committed in accept();
        # until then the live provider is untouched, so Cancel reverts it all.
        self._pending_options = copy.deepcopy(prov.get("options", {}))
        self.models = dict(prov["models"])
        self._update_table()

        if summary["added"]:
            self._match_models(set(summary["added"]))
        note = f", removed {len(removed)} stale" if removed else ""
        QMessageBox.information(
            self, "Fetch Complete",
            f"'{self.provider_key}': added {len(summary['added'])} new "
            f"model(s), kept {len(summary['kept'])}{note}.")

    def _update_table(self):
        """Update table with current models"""
        self.table.setRowCount(len(self.models))
        for row, (model_id, spec) in enumerate(sorted(self.models.items())):
            if not isinstance(spec, dict):
                spec = {}

            # ID
            self.table.setItem(row, 0, QTableWidgetItem(model_id))

            # Name
            self.table.setItem(row, 1, QTableWidgetItem(spec.get("name") or humanize_model_id(model_id)))

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

            match_btn = QPushButton("Match")
            match_btn.setFixedWidth(60)
            match_btn.clicked.connect(lambda _, m=model_id: self._match_single(m))
            actions_layout.addWidget(match_btn)

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
            self.table.setItem(row, 1, QTableWidgetItem(spec.get("name") or humanize_model_id(model_id)))
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

            match_btn = QPushButton("Match")
            match_btn.setFixedWidth(60)
            match_btn.clicked.connect(lambda _, m=model_id: self._match_single(m))
            actions_layout.addWidget(match_btn)

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
            if hasattr(self.app, "_ensure_catalog"):
                if not self.app._ensure_catalog():
                    return
            else:
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

    def _match_catalog(self):
        """Match & format all models in this provider against the catalog."""
        self._match_models(set(self.models.keys()))

    def _match_single(self, model_id: str):
        """Match & format a single model against the catalog."""
        self._match_models({model_id})

    def _match_models(self, model_ids):
        """Preview and apply matched catalog format for the given models."""
        if not self.app.model_catalog.loaded():
            if hasattr(self.app, "_ensure_catalog"):
                if not self.app._ensure_catalog():
                    return
            else:
                if not _confirm(self, "No Catalog", "No model catalog loaded. Load one now?"):
                    return
                if not self.app.load_model_catalog():
                    return

        catalog = self.app.model_catalog
        scope = set(model_ids)

        entries = []  # (model_id, old_spec, new_spec, status)
        ambiguous_data = {}
        for mid in sorted(scope):
            if mid not in self.models:
                continue
            matches = catalog.find_model(mid)
            if not matches:
                entries.append((mid, dict(self.models[mid]), None, "unknown"))
                continue
            chosen = _resolve_match(matches, self.provider_key, mid)
            if chosen is None:
                entries.append((mid, dict(self.models[mid]), None, "ambiguous"))
                ambiguous_data[mid] = (self.provider_key, matches)
                continue
            merged = _merge_model_spec(
                self.models[mid], build_spec_from_format(chosen, mid), overwrite=False)
            status = "matched" if merged != (self.models[mid] or {}) else "unchanged"
            entries.append((mid, dict(self.models[mid]), merged, status))

        if not any(e[2] is not None or e[3] == "ambiguous" for e in entries):
            QMessageBox.information(
                self, "Match from Catalog",
                "No models matched. Check the model ids against the catalog."
            )
            return

        dlg = MatchFormatPreviewDialog(
            self, entries, ambiguous_data, catalog=self.app.model_catalog)
        if dlg.exec() != QDialog.Accepted:
            return

        overwrite = dlg.overwrite_checkbox.isChecked()
        applied = 0
        for mid, old_spec, new_spec, status in dlg.selected_entries:
            # Use the provider picked in the combo for ambiguous entries.
            if status == "ambiguous":
                new_spec = dlg.resolved_specs.get(mid, new_spec)
            elif status == "mapped":
                new_spec = dlg.mapped_specs.get(mid, new_spec)
            if new_spec is None:
                continue
            self.models[mid] = _merge_model_spec(
                self.models[mid], new_spec, overwrite=overwrite)
            applied += 1

        self._update_table()
        self.app.mark_dirty()
        if applied:
            QMessageBox.information(
                self, "Match from Catalog", f"Updated {applied} model(s) from catalog")
        else:
            QMessageBox.information(self, "Match from Catalog", "No changes were applied.")

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

# Catalog dialogs: preview/match, browse, apply, fetch and format card
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

class CatalogModelPickerDialog(QDialog):
    """Searchable picker over catalog formats (used to map unknown models)."""

    def __init__(self, parent, catalog, initial_filter: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Map to Catalog Model")
        self.resize(520, 520)
        self._formats = list(catalog.all_formats()) if catalog is not None else []
        self.selected_format = None

        layout = QVBoxLayout(self)
        self.search = QLineEdit(initial_filter)
        self.search.setPlaceholderText("Filter by provider, model id or name...")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self._accept())
        layout.addWidget(self.list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._filter()

    def _filter(self):
        text = self.search.text().lower()
        self.list.clear()
        shown = 0
        for fmt in self._formats:
            label = f"{fmt.provider} · {fmt.model_id}"
            if text and text not in label.lower() and text not in (fmt.name or "").lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, fmt)
            self.list.addItem(item)
            shown += 1
            if shown >= 400:  # keep the list snappy on huge catalogs
                break

    def _accept(self):
        item = self.list.currentItem()
        if item is not None:
            self.selected_format = item.data(Qt.UserRole)
        if self.selected_format is not None:
            self.accept()


class MatchFormatPreviewDialog(QDialog):
    """Preview old vs new model config after matching against the catalog."""

    def __init__(self, parent, entries, ambiguous_data=None,
                 fallback_data=None, catalog=None):
        super().__init__(parent)
        self.setWindowTitle("Preview Matched Models")
        self.resize(900, 600)
        # entries: list of (model_id, old_spec, new_spec|None, status)
        self.entries = entries
        self.resolved_specs = {}
        self._ambiguous_data = ambiguous_data or {}
        self.fallback_data = fallback_data or {}   # {model_id: ModelFormat}
        self.mapped_specs = {}                     # {model_id: spec}
        self.mapped_ids = {}                       # {model_id: catalog model_id}
        self.catalog = catalog

        layout = QVBoxLayout(self)

        info = QLabel(
            "Review each model below. 'Old' is your current config, 'New' is the "
            "matched catalog format. Check the ones you want to apply."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.overwrite_checkbox = QCheckBox("Overwrite existing values (otherwise only fill missing fields)")
        layout.addWidget(self.overwrite_checkbox)

        # Bulk resolve bar: set every ambiguous row to one provider at once.
        self.bulk_bar = QWidget()
        bulk_layout = QHBoxLayout(self.bulk_bar)
        bulk_layout.setContentsMargins(0, 0, 0, 0)
        bulk_layout.addWidget(QLabel("Set all ambiguous to:"))
        self.bulk_combo = QComboBox()
        self.bulk_combo.setMinimumWidth(220)
        bulk_layout.addWidget(self.bulk_combo)
        bulk_btn = QPushButton("Apply to all")
        bulk_btn.clicked.connect(self._bulk_resolve)
        bulk_layout.addWidget(bulk_btn)
        self.apply_fallback_check = QCheckBox("Apply fallback")
        self.apply_fallback_check.setChecked(True)
        self.apply_fallback_check.toggled.connect(self._on_fallback_toggle)
        bulk_layout.addWidget(self.apply_fallback_check)
        bulk_layout.addStretch()
        layout.addWidget(self.bulk_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Apply", "Model ID", "Status", "Old Config", "New Config", "Catalog Provider"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self._show_diff)

        # Diff panel: side-by-side visual old -> new for the selected row.
        self.diff_title = QLabel("Select a row to preview the change")
        self.diff_title.setStyleSheet("font-weight: bold;")
        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setMinimumHeight(180)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.table)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.diff_title)
        rl.addWidget(self.diff_view)
        splitter.addWidget(right)
        splitter.setSizes([360, 220])
        layout.addWidget(splitter)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate()

    def _flat(self, d, prefix=""):
        """Flatten a nested dict into (path, value) leaves."""
        out = []
        if not isinstance(d, dict):
            return [(prefix, d)]
        for k, v in d.items():
            p = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out.extend(self._flat(v, p))
            else:
                out.append((p, v))
        return out

    def _show_diff(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.diff_title.setText("Select a row to preview the change")
            self.diff_view.clear()
            return
        row = rows[0].row()
        if not (0 <= row < len(self.entries)):
            return
        mid, old_spec, new_spec, status = self.entries[row]
        if status == "ambiguous":
            new_spec = self.resolved_specs.get(mid, new_spec)
        self.diff_title.setText(
            f"{mid} — {status}"
            + (" (ambiguous: pick a catalog provider)" if status == "ambiguous" else ""))
        self.diff_view.setHtml(self._diff_html(old_spec or {}, new_spec))

    def _diff_html(self, old, new) -> str:
        """Render an HTML table comparing old vs new field-by-field."""
        if new is None:
            return "<b>No catalog match for this model.</b>"
        old_flat = dict(self._flat(old))
        new_flat = dict(self._flat(new))
        keys = sorted(set(old_flat) | set(new_flat))

        def esc(v):
            return _esc_html(json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)

        rows_html = []
        for k in keys:
            o = old_flat.get(k)
            n = new_flat.get(k)
            if o is None and n is None:
                continue
            if o == n:
                rows_html.append(
                    f"<tr><td class='k'>{_esc_html(k)}</td>"
                    f"<td class='same'>{esc(n)}</td></tr>")
            elif o is None:
                rows_html.append(
                    f"<tr><td class='k'>{_esc_html(k)}</td>"
                    f"<td class='add' style='color:#1a7f37'>+ {esc(n)}</td></tr>")
            elif n is None:
                rows_html.append(
                    f"<tr><td class='k'>{_esc_html(k)}</td>"
                    f"<td class='del' style='color:#d1242f; text-decoration:line-through'>- {esc(o)}</td></tr>")
            else:
                rows_html.append(
                    f"<tr><td class='k'>{_esc_html(k)}</td>"
                    f"<td class='chg' style='color:#9a6700'>{esc(o)} → {esc(n)}</td></tr>")

        return (
            "<style>table{border-collapse:collapse;width:100%;font-family:monospace;font-size:12px}"
            ".k{color:#57606a;padding:2px 10px 2px 0;vertical-align:top;white-space:nowrap}</style>"
            "<table>" + "".join(rows_html) + "</table>"
        ) if rows_html else "<i>No changes</i>"

    def _populate(self):
        self.table.setRowCount(len(self.entries))
        for row, (mid, old_spec, new_spec, status) in enumerate(self.entries):
            apply_check = QCheckBox()
            # Ambiguous rows are pre-checked too: their combo already defaults
            # to the best provider (same-name first, then most complete).
            apply_check.setChecked(
                (new_spec is not None and status != "unchanged") or status == "ambiguous")
            self.table.setCellWidget(row, 0, apply_check)

            self.table.setItem(row, 1, QTableWidgetItem(mid))
            status_item = QTableWidgetItem(status)
            if status.startswith("fallback:"):
                status_item.setForeground(QColor("#0969da"))
            elif status == "mapped":
                status_item.setForeground(QColor("#8250df"))
            self.table.setItem(row, 2, status_item)

            old_text = json.dumps(old_spec, ensure_ascii=False) if old_spec else "(empty)"
            if new_spec is not None:
                new_text = json.dumps(new_spec, ensure_ascii=False)
            elif status == "ambiguous":
                new_text = "choose a provider"
            else:
                new_text = "no match"
            self.table.setItem(row, 3, QTableWidgetItem(old_text))
            self.table.setItem(row, 4, QTableWidgetItem(new_text))

            # Resolve column: combo box listing catalog providers matching this id.
            resolve_widget = QWidget()
            resolve_layout = QHBoxLayout(resolve_widget)
            resolve_layout.setContentsMargins(2, 0, 2, 0)
            combo = QComboBox()
            provider_key, matches = self._ambiguous_data.get(mid, (None, []))
            if status == "ambiguous" and matches:
                # Same-name provider first, then the most complete formats,
                # so the pre-selection is a sensible default.
                for m in _sort_matches(matches, provider_key):
                    combo.addItem(m.provider, m)
                combo.setCurrentIndex(0)
                combo.currentIndexChanged.connect(
                    lambda _, r=row, mm=mid: self._on_combo_change(r, mm))
                # reflect the default selection now
                self.resolved_specs[mid] = build_spec_from_format(combo.currentData(), mid)
                self._refresh_new_cell(row, mid)
            else:
                combo.setEnabled(False)
                combo.addItem("—")
                # Unknown rows can be mapped to a catalog model manually.
                if status == "unknown" and self.catalog is not None:
                    map_btn = QPushButton("Map…")
                    map_btn.clicked.connect(
                        lambda _, r=row, mm=mid: self._map_unknown(r, mm))
                    resolve_layout.addWidget(map_btn)
            resolve_layout.addWidget(combo, 1)
            self.table.setCellWidget(row, 5, resolve_widget)

        self._fill_bulk_combo()
        self.table.resizeColumnsToContents()

    def _fill_bulk_combo(self):
        """List providers across ambiguous rows, most frequent first."""
        counts = {}
        for mid, (_pk, matches) in self._ambiguous_data.items():
            entry = next((e for e in self.entries if e[0] == mid), None)
            if entry is None or entry[3] != "ambiguous":
                continue
            for m in matches:
                counts[m.provider] = counts.get(m.provider, 0) + 1
            self.bulk_combo.clear()
        for prov, _n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            self.bulk_combo.addItem(prov)
        n_ambiguous = sum(1 for e in self.entries if e[3] == "ambiguous")
        has_fallback = any(e[3].startswith("fallback:") for e in self.entries)
        self.bulk_bar.setVisible(
            (self.bulk_combo.count() > 0 and n_ambiguous > 1) or has_fallback)

    def _on_fallback_toggle(self, checked: bool):
        """Check/uncheck every fallback row according to the Apply fallback box."""
        for row, (mid, _old, _new, status) in enumerate(self.entries):
            if not status.startswith("fallback:"):
                continue
            check = self.table.cellWidget(row, 0)
            if check is not None:
                check.setChecked(checked)

    def _map_unknown(self, row, mid):
        """Manually map an unknown model to a catalog format."""
        if self.catalog is None:
            return
        old_spec = self.entries[row][1] or {}
        dlg = CatalogModelPickerDialog(self, self.catalog, initial_filter=mid)
        if dlg.exec() != QDialog.Accepted or dlg.selected_format is None:
            return
        fmt = dlg.selected_format
        spec = build_spec_from_format(fmt, mid)
        self.mapped_specs[mid] = spec
        self.mapped_ids[mid] = fmt.model_id
        # Update the entry in place so selected_entries carries the new spec.
        self.entries[row] = (mid, old_spec, spec, "mapped")
        status_item = QTableWidgetItem("mapped")
        status_item.setForeground(QColor("#8250df"))
        self.table.setItem(row, 2, status_item)
        self.table.setItem(row, 4, QTableWidgetItem(json.dumps(spec, ensure_ascii=False)))
        check = self.table.cellWidget(row, 0)
        if check is not None:
            check.setChecked(True)
        self._show_diff()

    def _bulk_resolve(self):
        """Point every ambiguous row's combo at the chosen provider where possible."""
        provider = self.bulk_combo.currentText()
        if not provider:
            return
        for row, (mid, _old, _new, status) in enumerate(self.entries):
            if status != "ambiguous":
                continue
            combo = self.table.cellWidget(row, 5).findChild(QComboBox)
            if combo is None:
                continue
            idx = combo.findText(provider)
            if idx >= 0 and combo.currentIndex() != idx:
                combo.setCurrentIndex(idx)  # triggers _on_combo_change

    def _on_combo_change(self, row, mid):
        combo = self.table.cellWidget(row, 5).findChild(QComboBox)
        fmt = combo.currentData()
        if fmt is not None:
            self.resolved_specs[mid] = build_spec_from_format(fmt, mid)
            self._refresh_new_cell(row, mid)
            check = self.table.cellWidget(row, 0)
            if check is not None:
                check.setChecked(True)
            self._show_diff()

    def _refresh_new_cell(self, row, mid):
        spec = self.resolved_specs.get(mid)
        self.table.setItem(row, 4, QTableWidgetItem(
            json.dumps(spec, ensure_ascii=False) if spec else "choose a provider"))
        self.table.setItem(row, 2, QTableWidgetItem("matched" if spec else "ambiguous"))
        self.table.resizeColumnsToContents()

    @property
    def selected_entries(self):
        out = []
        for row in range(self.table.rowCount()):
            check = self.table.cellWidget(row, 0)
            if check is not None and check.isChecked():
                out.append(self.entries[row])
        return out

# Default base URL per fetch adapter. Gemini's API lives under /v1beta.
_FETCH_BASE_URL_DEFAULTS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "models_dev": "https://models.dev/api.json",
    "generic": "",
}


_APIKEY_PLACEHOLDER_RE = re.compile(r"\{(?:env|file):[^{}]*\}")


def _has_placeholder(value: str) -> bool:
    """True if `value` uses opencode's {env:VAR} / {file:path} references."""
    return isinstance(value, str) and bool(_APIKEY_PLACEHOLDER_RE.search(value))

class _ModelFetchWorker(QThread):
    """Runs fetch_provider_models off the UI thread."""
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, spec):
        super().__init__()
        self.spec = spec

    def run(self):
        try:
            models = fetch_provider_models(self.spec)
            self.finished_ok.emit(models)
        except Exception as e:  # FetchError and anything unexpected
            self.failed.emit(str(e))


class _CatalogSyncWorker(QThread):
    """Runs ModelCatalog.fetch_online off the UI thread.

    Downloading, JSONC-stripping and re-parsing a multi-megabyte catalog all
    take long enough to freeze the window, so the download never runs on the
    GUI thread. Reuse this worker from anywhere else that updates the catalog.
    """
    finished_ok = Signal(str, int)   # message, model count
    failed = Signal(str)             # error message

    def __init__(self, catalog, url=None):
        super().__init__()
        self.catalog = catalog
        self.url = url

    def run(self):
        try:
            ok, msg, count = self.catalog.fetch_online(self.url)
        except Exception as e:
            self.failed.emit(str(e))
            return
        if ok:
            self.finished_ok.emit(msg, count)
        else:
            self.failed.emit(msg)


class FetchProviderModelsDialog(QDialog):
    """Fetch a provider's model list from its API and preview the results."""
    def __init__(self, parent, provider_key: str = "new-provider", catalog=None,
                 providers=None, lock_key: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Fetch Provider Models from API")
        self.resize(720, 560)
        self.fetched_models = {}   # {model_id: spec}
        self.provider_key = provider_key
        self.providers = providers  # full provider map, for existing-status display
        self._worker = None
        self._lock_key = lock_key
        self._fetched_signature = None  # (url, api key, adapter) the table matches
        self._auto_base_url = ""   # last base URL we auto-filled from a default
        self._closed = False

        # Silently load the bundled catalog so the Reference combo can be filled.
        self.catalog = catalog
        try_load_bundled_catalog(self.catalog)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.key_edit = QLineEdit(provider_key)
        # The fetch is always for this provider; letting the key be edited only
        # mislabels the Status column, since the result is applied to
        # provider_key regardless (F11).
        self.key_edit.setReadOnly(lock_key)
        self.key_edit.textChanged.connect(self._apply_status)
        form.addRow("Provider key:", self.key_edit)

        self.format_combo = QComboBox()
        for adapter, preset in FETCH_ADAPTERS.items():
            self.format_combo.addItem(preset["label"], adapter)
        self.format_combo.currentIndexChanged.connect(self._on_format_change)
        form.addRow("API format:", self.format_combo)

        # Optional provider used as a fallback source for models not in the catalog.
        self.reference_combo = QComboBox()
        self.reference_combo.addItem("Auto (exact match only)", "")
        if self.catalog is not None and self.catalog.loaded():
            for pid in sorted(self.catalog.by_provider.keys()):
                self.reference_combo.addItem(pid, pid)
        self.reference_combo.setToolTip(
            "Models not found in the catalog will borrow their format from this "
            "provider (fill-missing only). Manual 'Map…' overrides still win.")
        form.addRow("Reference provider:", self.reference_combo)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://api.openai.com/v1")
        self.url_edit.textChanged.connect(self._invalidate_fetch)
        form.addRow("Base URL:", self.url_edit)

        self.apikey_edit = QLineEdit()
        self.apikey_edit.setEchoMode(QLineEdit.Password)
        self.apikey_edit.setPlaceholderText("(sent as a header to fetch the model list)")
        self.apikey_edit.textChanged.connect(self._invalidate_fetch)
        self.apikey_edit.setReadOnly(lock_key)
        if lock_key:
            self.apikey_edit.setToolTip(
                "This provider already has an API key configured; it is reused as-is.")
        form.addRow("API key:", self.apikey_edit)

        # Saving a reference like "{env:OPENAI_API_KEY}" would freeze the
        # variable name into the config; the checkbox default is set in
        # _prefill_from_provider once the stored key is known.
        self.save_apikey_check = QCheckBox("Save API key to config (options.apiKey)")
        self.save_apikey_check.setChecked(True)
        self.save_apikey_check.setToolTip(
            "Writes the key into opencode.json (provider options.apiKey), opencode's "
            "documented mechanism. Uncheck to keep it out of the config file.")
        form.addRow("", self.save_apikey_check)

        layout.addLayout(form)

        # Generic-only advanced fields
        self.generic_box = QGroupBox("Generic JSON options")
        gform = QFormLayout(self.generic_box)
        self.items_path_edit = QLineEdit()
        self.items_path_edit.setPlaceholderText("data  (dotted path to the array)")
        self.id_field_edit = QLineEdit()
        self.id_field_edit.setPlaceholderText("id")
        self.name_field_edit = QLineEdit()
        self.name_field_edit.setPlaceholderText("name")
        gform.addRow("Items path:", self.items_path_edit)
        gform.addRow("ID field:", self.id_field_edit)
        gform.addRow("Name field:", self.name_field_edit)
        layout.addWidget(self.generic_box)

        self.allow_local_check = QCheckBox("Allow local URL (Ollama / LM Studio / localhost)")
        layout.addWidget(self.allow_local_check)

        self.sync_check = QCheckBox(
            "Sync: also remove configured models that the API no longer lists")
        self.sync_check.setToolTip(
            "Only affects a provider key that already exists. Off = add-only, "
            "every configured model is kept.")
        self.sync_check.setVisible(providers is not None)
        layout.addWidget(self.sync_check)

        # Fetch controls
        fetch_row = QHBoxLayout()
        self.fetch_btn = QPushButton("Fetch models")
        self.fetch_btn.clicked.connect(self._fetch)
        fetch_row.addWidget(self.fetch_btn)
        self.status_label = QLabel("")
        fetch_row.addWidget(self.status_label, 1)
        layout.addLayout(fetch_row)

        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Add", "Model ID", "Name", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        select_row = QHBoxLayout()
        all_btn = QPushButton("Select all")
        all_btn.clicked.connect(lambda: self._set_all(True))
        none_btn = QPushButton("Select none")
        none_btn.clicked.connect(lambda: self._set_all(False))
        select_row.addWidget(all_btn)
        select_row.addWidget(none_btn)
        select_row.addStretch()
        layout.addLayout(select_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Add Selected")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._on_format_change()
        self._prefill_from_provider()
        # Re-apply the adapter-dependent state now that the stored URL/key are
        # in place (a locked key needs a non-empty value to stay usable).
        self._on_format_change()

    # Providers whose npm package determines the API shape even before the
    # stored options are read: guessing the format first stops an Anthropic
    # key from being sent to an OpenAI endpoint.
    _NPM_ADAPTER = {
        "@ai-sdk/anthropic": "anthropic",
        "@ai-sdk/google": "gemini",
        "@ai-sdk/openai": "openai",
    }
    _PROVIDER_ID_ADAPTER = {
        "anthropic": "anthropic",
        "google": "gemini",
        "gemini": "gemini",
        "openai": "openai",
        "google-generative-ai": "gemini",
    }

    def _infer_adapter_from_provider(self) -> str:
        """Best-guess API format from the provider's npm package or id."""
        if not isinstance(self.providers, dict):
            return ""
        prov = self.providers.get(self.provider_key)
        if not isinstance(prov, dict):
            return ""
        npm = prov.get("npm")
        if isinstance(npm, str) and npm in self._NPM_ADAPTER:
            return self._NPM_ADAPTER[npm]
        pid = str(self.provider_key or "").lower()
        return self._PROVIDER_ID_ADAPTER.get(pid, "")

    def _select_adapter(self, adapter: str):
        idx = self.format_combo.findData(adapter)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)

    def _prefill_from_provider(self):
        """Pre-fill URL/key from the target provider's saved options, so
        re-fetching an existing provider starts from its real endpoint."""
        # Infer the format before reading the stored options: prefilling first
        # would send an Anthropic key to the default OpenAI URL.
        inferred = self._infer_adapter_from_provider()
        if inferred:
            self._select_adapter(inferred)

        if not isinstance(self.providers, dict):
            return
        prov = self.providers.get(self.provider_key)
        opts = prov.get("options") if isinstance(prov, dict) else None
        if not isinstance(opts, dict):
            return
        if opts.get("baseURL"):
            self.url_edit.setText(str(opts["baseURL"]))
        key = opts.get("apiKey")
        if isinstance(key, str) and key:
            # Keep "{env:…}"/"{file:…}" verbatim so Save writes it back
            # unchanged; it is only resolved when building the request.
            self.apikey_edit.setText(key)
            self.save_apikey_check.setChecked(not _has_placeholder(key))

    def _current_adapter(self) -> str:
        return self.format_combo.currentData()

    @property
    def reference_provider(self):
        """Selected fallback provider name, or None for Auto."""
        data = self.reference_combo.currentData()
        return data or None

    def _on_format_change(self):
        adapter = self._current_adapter()
        self.generic_box.setVisible(adapter == "generic")
        # Replace the URL only while it is still the default we last applied, so
        # switching format never clobbers a URL the user typed.
        if not self.url_edit.text().strip() or self.url_edit.text() == self._auto_base_url:
            self.url_edit.setText(_FETCH_BASE_URL_DEFAULTS.get(adapter, ""))
        self._auto_base_url = self.url_edit.text()
        # A locked key stays usable (it is the provider's existing key); only
        # *editing* it is blocked.
        self.apikey_edit.setEnabled(
            adapter != "models_dev" and (not self._lock_key or bool(self.apikey_edit.text())))
        self._invalidate_fetch()

    def _request_signature(self):
        """What the current table contents were fetched with."""
        return (self.url_edit.text().strip(),
                self.apikey_edit.text(),
                self._current_adapter())

    def _invalidate_fetch(self, *_):
        """Changing the endpoint, key or format makes the table stale."""
        if self._fetched_signature is None:
            return
        if self._request_signature() == self._fetched_signature:
            return
        self._fetched_signature = None
        self.fetched_models = {}
        self.table.setRowCount(0)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.status_label.setText("Settings changed — fetch again")

    def api_base_url(self) -> str:
        """The URL to store as the fetched provider's ``options.baseURL``.

        API-style formats keep their base URL, normalised with the version
        segment the AI SDK expects; list/catalog formats (models.dev, generic
        JSON) store nothing. The policy lives in api_base_url_for.
        """
        return api_base_url_for(self._current_adapter(),
                                self.url_edit.text().strip())

    def _build_spec(self) -> ProviderFetchSpec:
        return ProviderFetchSpec(
            base_url=self.url_edit.text().strip(),
            adapter=self._current_adapter(),
            # Only the outgoing request resolves {env:}/{file:} references;
            # the field itself keeps the reference text for Save.
            api_key=resolve_config_placeholders(self.apikey_edit.text()),
            items_path=self.items_path_edit.text().strip(),
            id_field=self.id_field_edit.text().strip(),
            name_field=self.name_field_edit.text().strip(),
            allow_local=self.allow_local_check.isChecked(),
        )

    def _fetch(self):
        if not self.url_edit.text().strip():
            QMessageBox.warning(self, "Fetch", "Please enter a base URL.")
            return
        self.fetch_btn.setEnabled(False)
        self.status_label.setText("Fetching…")
        self._worker = _ModelFetchWorker(self._build_spec())
        self._worker.finished_ok.connect(self._on_fetched)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_fetched(self, models: dict):
        # The dialog may have been closed (or the settings changed) while the
        # request was in flight; that result is no longer wanted.
        if self._closed:
            return
        self.fetched_models = models
        self._fetched_signature = self._request_signature()
        self.fetch_btn.setEnabled(True)
        self.status_label.setText(f"Fetched {len(models)} models")
        self._populate(models)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(models))

    def _on_failed(self, msg: str):
        if self._closed:
            return
        self.fetch_btn.setEnabled(True)
        self.status_label.setText("Fetch failed")
        QMessageBox.warning(self, "Fetch Error", msg)

    def closeEvent(self, event):
        self._closed = True
        super().closeEvent(event)

    def _populate(self, models: dict):
        self.table.setRowCount(len(models))
        for row, (mid, spec) in enumerate(sorted(models.items())):
            check = QCheckBox()
            check.setChecked(True)
            self.table.setCellWidget(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(mid))
            self.table.setItem(row, 2, QTableWidgetItem(spec.get("name", "")))
        self._apply_status()

    def _existing_model_ids(self) -> set:
        if not isinstance(self.providers, dict):
            return set()
        prov = self.providers.get(self.key_edit.text().strip())
        models = prov.get("models") if isinstance(prov, dict) else None
        return set(models.keys()) if isinstance(models, dict) else set()

    def _apply_status(self, *_):
        existing = self._existing_model_ids()
        for row in range(self.table.rowCount()):
            mid_item = self.table.item(row, 1)
            if mid_item is None:
                continue
            status = "existing" if mid_item.text() in existing else "new"
            self.table.setItem(row, 3, QTableWidgetItem(status))

    def _set_all(self, checked: bool):
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            if w is not None:
                w.setChecked(checked)

    @property
    def selected_models(self) -> dict:
        """Return {model_id: spec} for checked rows."""
        out = {}
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            if w is not None and w.isChecked():
                mid = self.table.item(row, 1).text()
                out[mid] = self.fetched_models.get(mid, {})
        return out



class ModelFormatCard(QFrame):
    """Card showing normalized details of a single model format."""

    def __init__(self, fmt: Optional[ModelFormat] = None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumWidth(280)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)

        self.title_label = QLabel("Select a model")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        self.title_label.setFont(title_font)
        self.title_label.setWordWrap(True)
        self._layout.addWidget(self.title_label)

        self.sub_label = QLabel("")
        self.sub_label.setStyleSheet("color: gray;")
        self.sub_label.setWordWrap(True)
        self._layout.addWidget(self.sub_label)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self._layout.addWidget(self.info_label)

        self.set_format(fmt)

    def set_format(self, fmt: Optional[ModelFormat]):
        if fmt is None:
            self.title_label.setText("No model selected")
            self.sub_label.setText("")
            self.info_label.setText("Click a row in the table to see its normalized format.")
            return

        self.title_label.setText(f"{fmt.provider} · {fmt.model_id}")
        self.sub_label.setText(fmt.name)
        lines = [
            f"Context: {fmt.context_k()}",
            f"Output: {fmt.output_k()}",
            f"Modalities: {fmt.modalities.label()}",
            f"Cost in/out: {fmt.cost_in_label()} / {fmt.cost_out_label()}",
            f"Cache read/write: {_fmt_cost(fmt.cost_cache_read)} / {_fmt_cost(fmt.cost_cache_write)}",
        ]
        caps = []
        if fmt.attachment:
            caps.append("attachment")
        if fmt.reasoning:
            caps.append("reasoning")
        if fmt.tools:
            caps.append("tool_call")
        if fmt.temperature:
            caps.append("temperature")
        if caps:
            lines.append("Capabilities: " + ", ".join(caps))
        if fmt.modalities.inferred:
            lines.append("(modalities inferred)")
        self.info_label.setText("\n".join(lines))


class TierSettingsDialog(QDialog):
    """Dialog to edit configurable context/output tiers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Catalog Tier Settings")
        self.resize(400, 320)
        self.settings = SettingsManager()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Enter tier thresholds in thousands of tokens (e.g. 4, 8, 32, 128, 200).\n"
            "Separate by commas. Used to bucket models by context / output size."
        ))

        form = QFormLayout()
        self.context_edit = QLineEdit()
        self.output_edit = QLineEdit()
        form.addRow("Context tiers (k):", self.context_edit)
        form.addRow("Output tiers (k):", self.output_edit)
        layout.addLayout(form)

        self.context_edit.setText(",".join(str(x // 1000 if x >= 1000 else x)
                                            for x in self.settings.get_context_tiers()))
        self.output_edit.setText(",".join(str(x // 1000 if x >= 1000 else x)
                                          for x in self.settings.get_output_tiers()))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _parse_k(self, text: str, fallback) -> List[int]:
        vals = []
        for tok in text.replace(",", " ").split():
            try:
                vals.append(int(float(tok) * 1000))
            except ValueError:
                continue
        return vals or list(fallback)

    def _accept(self):
        self.settings.set_context_tiers(
            self._parse_k(self.context_edit.text(), SettingsManager.DEFAULT_CONTEXT_TIERS))
        self.settings.set_output_tiers(
            self._parse_k(self.output_edit.text(), SettingsManager.DEFAULT_OUTPUT_TIERS))
        self.accept()


class ModelCatalogDialog(QDialog):
    """Browse the whole model catalog with filters and format detail."""

    COLUMNS = ["Provider", "Model ID", "Name", "Context", "Output", "Modalities", "Cost in/out"]

    def __init__(self, parent, catalog):
        super().__init__(parent)
        self.setWindowTitle("Browse Model Catalog")
        self.resize(960, 600)
        self.catalog = catalog
        self.settings = SettingsManager()

        layout = QVBoxLayout(self)

        # Filter bar
        filters = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search model / name...")
        self.search_edit.textChanged.connect(self._refresh)
        filters.addWidget(self.search_edit)

        self.provider_combo = QComboBox()
        self.provider_combo.addItem("All providers")
        for pid in sorted(catalog.by_provider.keys()):
            self.provider_combo.addItem(pid)
        self.provider_combo.currentTextChanged.connect(self._refresh)
        filters.addWidget(self.provider_combo)

        self.context_combo = QComboBox()
        self._fill_tier_combo(self.context_combo, "context")
        self.context_combo.currentIndexChanged.connect(self._refresh)
        filters.addWidget(QLabel("Context ≥"))
        filters.addWidget(self.context_combo)

        self.output_combo = QComboBox()
        self._fill_tier_combo(self.output_combo, "output")
        self.output_combo.currentIndexChanged.connect(self._refresh)
        filters.addWidget(QLabel("Output ≥"))
        filters.addWidget(self.output_combo)
        filters.addStretch()
        layout.addLayout(filters)

        mod_filters = QHBoxLayout()
        self.image_check = QCheckBox("Image input")
        self.pdf_check = QCheckBox("PDF input")
        self.tools_check = QCheckBox("Tools")
        self.reasoning_check = QCheckBox("Reasoning")
        for cb in (self.image_check, self.pdf_check, self.tools_check, self.reasoning_check):
            cb.stateChanged.connect(self._refresh)
            mod_filters.addWidget(cb)
        mod_filters.addStretch()
        layout.addLayout(mod_filters)

        # Splitter: table + card
        splitter = QSplitter()
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_select)
        splitter.addWidget(self.table)

        self.card = ModelFormatCard()
        splitter.addWidget(self.card)
        splitter.setSizes([680, 280])
        layout.addWidget(splitter)

        # Status + buttons
        bottom = QHBoxLayout()
        self.status_label = QLabel("")
        bottom.addWidget(self.status_label)
        bottom.addStretch()

        tiers_btn = QPushButton("Tiers…")
        tiers_btn.clicked.connect(self._edit_tiers)
        bottom.addWidget(tiers_btn)

        export_btn = QPushButton("Export…")
        export_btn.clicked.connect(self._export)
        bottom.addWidget(export_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        self._refresh()

    def _fill_tier_combo(self, combo: QComboBox, attr: str):
        combo.addItem("any")
        tiers = (self.settings.get_context_tiers() if attr == "context"
                 else self.settings.get_output_tiers())
        for t in tiers:
            combo.addItem(f"{_fmt_tokens(t)}")

    def _refresh(self):
        search = self.search_edit.text().lower()
        provider = self.provider_combo.currentText()
        ctx_min = self._tier_value(self.context_combo)
        out_min = self._tier_value(self.output_combo)

        rows = []
        for fmt in self.catalog.all_formats():
            if provider != "All providers" and fmt.provider != provider:
                continue
            if search and search not in fmt.model_id.lower() and search not in fmt.name.lower():
                continue
            if ctx_min and (fmt.context is None or fmt.context < ctx_min):
                continue
            if out_min and (fmt.output is None or fmt.output < out_min):
                continue
            if self.image_check.isChecked() and not fmt.modalities.has_image_input:
                continue
            if self.pdf_check.isChecked() and not fmt.modalities.has_pdf_input:
                continue
            if self.tools_check.isChecked() and not fmt.tools:
                continue
            if self.reasoning_check.isChecked() and not fmt.reasoning:
                continue
            rows.append(fmt)

        self.table.setRowCount(len(rows))
        self._row_formats = []
        for r, fmt in enumerate(rows):
            self._row_formats.append(fmt)
            vals = [
                fmt.provider, fmt.model_id, fmt.name, fmt.context_k(), fmt.output_k(),
                fmt.modalities.label(), f"{fmt.cost_in_label()}/{fmt.cost_out_label()}",
            ]
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.status_label.setText(f"{len(rows)} models")

    def _tier_value(self, combo: QComboBox):
        txt = combo.currentText()
        if not txt or txt == "any":
            return 0
        if txt.endswith("M"):
            return int(float(txt[:-1]) * 1000000)
        if txt.endswith("k"):
            return int(float(txt[:-1]) * 1000)
        try:
            return int(txt)
        except ValueError:
            return 0

    def _on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows or not getattr(self, "_row_formats", None):
            self.card.set_format(None)
            return
        idx = rows[0].row()
        if 0 <= idx < len(self._row_formats):
            self.card.set_format(self._row_formats[idx])

    def _edit_tiers(self):
        dlg = TierSettingsDialog(self)
        dlg.exec()
        self.context_combo.clear()
        self.output_combo.clear()
        self._fill_tier_combo(self.context_combo, "context")
        self._fill_tier_combo(self.output_combo, "output")
        self._refresh()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Models", "models.csv",
            "CSV files (*.csv);;JSON files (*.json);;All files (*)"
        )
        if not path:
            return
        rows = [self._row_formats[r] for r in range(self.table.rowCount())
                if 0 <= r < len(getattr(self, "_row_formats", []))]
        try:
            if path.endswith(".json"):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump([build_spec_from_format(f) | {"provider": f.provider,
                                                            "model_id": f.model_id}
                               for f in rows], f, indent=2, ensure_ascii=False)
            else:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["provider", "model_id", "name", "context",
                                     "output", "cost_in", "cost_out"])
                    for fm in rows:
                        writer.writerow([fm.provider, fm.model_id, fm.name,
                                         fm.context or "", fm.output or "",
                                         fm.cost_in or "", fm.cost_out or ""])
            QMessageBox.information(self, "Export Complete", f"Exported {len(rows)} models")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))


class ApplyCatalogDialog(QDialog):
    """Match configured models against the catalog and apply normalized format."""

    def __init__(self, parent, catalog, config_providers):
        super().__init__(parent)
        self.setWindowTitle("Match & Format Models from Catalog")
        self.resize(980, 620)
        self.catalog = catalog
        self.config_providers = config_providers

        layout = QVBoxLayout(self)
        info = QLabel(
            "Matches the models already configured in your config against the model catalog, "
            "then fills in normalized format (context, output, modalities, cost).\n"
            "Models with an id present in the catalog but missing from config can also be added."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Controls
        ctrl = QHBoxLayout()
        self.overwrite_check = QCheckBox("Overwrite existing values")
        self.add_new_check = QCheckBox("Add new models from catalog")
        self.add_new_check.setChecked(True)
        ctrl.addWidget(self.overwrite_check)
        ctrl.addWidget(self.add_new_check)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Model ID", "Provider (config)", "Catalog source", "Status",
            "Context", "Modalities"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemDoubleClicked.connect(self._resolve_ambiguous)
        layout.addWidget(self.table)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Apply to Config")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.overwrite_check.stateChanged.connect(lambda _: self._scan())
        self.add_new_check.stateChanged.connect(lambda _: self._scan())
        self._picks = {}
        self._scan()

    def _scan(self):
        self.rows = []
        self.fmt_cache = self.catalog.formats()
        overwrite = self.overwrite_check.isChecked()

        for prov_name, prov_cfg in (self.config_providers or {}).items():
            if not isinstance(prov_cfg, dict):
                continue
            models = prov_cfg.get("models")
            if not isinstance(models, dict):
                continue
            for mid in models:
                matches = self.catalog.find_model(mid)
                if not matches:
                    self.rows.append([mid, prov_name, "", "unknown", "", ""])
                    continue
                chosen = _resolve_match(matches, prov_name, mid,
                                        self._pick_provider)
                if chosen is None:
                    self.rows.append([mid, prov_name,
                                      ", ".join(m.provider for m in matches),
                                      "ambiguous", "", ""])
                    continue
                spec = build_spec_from_format(chosen, mid)
                merged = _merge_model_spec(models[mid], spec, overwrite)
                status = "matched" if merged != (models[mid] or {}) else "unchanged"
                self.rows.append([mid, prov_name, chosen.provider, status,
                                  chosen.context_k(), chosen.modalities.label()])

        if self.add_new_check.isChecked():
            for prov_name, prov_cfg in (self.config_providers or {}).items():
                if not isinstance(prov_cfg, dict):
                    continue
                existing = set(prov_cfg.get("models", {})) if isinstance(prov_cfg.get("models"), dict) else set()
                for fmt in self.fmt_cache.get(prov_name, {}).values():
                    if fmt.model_id not in existing:
                        self.rows.append([fmt.model_id, prov_name, prov_name, "added",
                                          fmt.context_k(), fmt.modalities.label()])

        self._populate()

    def _populate(self):
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            for c, val in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(val))
        counts = {"matched": 0, "filled": 0, "unchanged": 0, "unknown": 0,
                  "ambiguous": 0, "added": 0}
        for row in self.rows:
            counts[row[3]] = counts.get(row[3], 0) + 1
        parts = [f"{k}: {v}" for k, v in counts.items() if v]
        self.status_label.setText("  ".join(parts))

    def _pick_provider(self, prov_name, mid, matches):
        """Return the user's chosen provider for an ambiguous match, else None."""
        key = (prov_name, mid)
        picked = self._picks.get(key)
        if picked is not None:
            return next((m for m in matches if m.provider == picked), matches[0])
        return None

    def _resolve_ambiguous(self, item):
        row = item.row()
        if self.rows[row][3] != "ambiguous":
            return
        mid, prov = self.rows[row][0], self.rows[row][1]
        matches = self.catalog.find_model(mid)
        providers = [m.provider for m in matches]
        choice, ok = QInputDialog.getItem(
            self, "Choose Catalog Source",
            f"Model '{mid}' matches multiple providers. Choose one:",
            providers, 0, False
        )
        if ok and choice:
            self._picks[(prov, mid)] = choice
            fmt = next((m for m in matches if m.provider == choice), matches[0])
            self.rows[row][2] = choice
            self.rows[row][3] = "matched"
            self.rows[row][4] = fmt.context_k()
            self.rows[row][5] = fmt.modalities.label()
            self._populate()

    def apply(self) -> ApplyReport:
        """Apply the current choices to the live config providers."""
        report = apply_catalog_to_config(
            self.catalog,
            self.config_providers,
            overwrite=self.overwrite_check.isChecked(),
            add_new=self.add_new_check.isChecked(),
            resolve_fn=self._pick_provider,
        )
        return report


class EditCustomModelDialog(QDialog):
    """Dialog to add or edit a custom model spec in the catalog."""

    def __init__(self, parent, model_id: str = "", spec: Optional[dict] = None, provider: str = "custom"):
        super().__init__(parent)
        self.setWindowTitle("Edit Custom Model" if model_id else "Add Custom Model")
        self.resize(560, 480)
        self.result_model_id = ""
        self.result_provider = ""
        self.result_spec = {}
        # Fields the dialog does not expose (cost, aliases, extra modalities,
        # ...) are carried over untouched when the spec is rebuilt.
        self._original_spec = dict(spec or {})

        spec = dict(self._original_spec)
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Model ID
        self.id_edit = QLineEdit(model_id)
        self.id_edit.setPlaceholderText("e.g. glm-5.3-flash, custom-gpt-5")
        form.addRow("Model ID *:", self.id_edit)

        # Name
        init_name = spec.get("name") or (humanize_model_id(model_id) if model_id else "")
        self.name_edit = QLineEdit(init_name)
        self.name_edit.setPlaceholderText("e.g. GLM 5.3 Flash")
        form.addRow("Display Name:", self.name_edit)

        self.id_edit.textChanged.connect(self._on_id_changed)

        # Provider
        init_prov = spec.get("provider") or provider or "custom"
        self.prov_edit = QLineEdit(init_prov)
        self.prov_edit.setPlaceholderText("e.g. custom, zhipu, openai")
        form.addRow("Provider Key:", self.prov_edit)

        # Context limit
        limit = spec.get("limit", {}) if isinstance(spec.get("limit"), dict) else {}
        self.ctx_spin = QSpinBox()
        self.ctx_spin.setRange(0, 10000000)
        self.ctx_spin.setSingleStep(4000)
        self.ctx_spin.setValue(int(limit["context"]) if isinstance(limit.get("context"), (int, float)) else 128000)
        form.addRow("Context Window (tokens):", self.ctx_spin)

        # Output limit
        self.out_spin = QSpinBox()
        self.out_spin.setRange(0, 1000000)
        self.out_spin.setSingleStep(1000)
        self.out_spin.setValue(int(limit["output"]) if isinstance(limit.get("output"), (int, float)) else 8192)
        form.addRow("Max Output Tokens:", self.out_spin)

        # Features
        feat_box = QGroupBox("Capabilities & Features")
        feat_layout = QGridLayout(feat_box)
        self.att_cb = QCheckBox("Attachment (Images/Files)")
        self.att_cb.setChecked(bool(spec.get("attachment", True)))
        self.reas_cb = QCheckBox("Reasoning / Thinking")
        self.reas_cb.setChecked(bool(spec.get("reasoning", False)))
        self.tools_cb = QCheckBox("Tool Calling")
        self.tools_cb.setChecked(bool(spec.get("tool_call", True)))
        self.temp_cb = QCheckBox("Temperature Control")
        self.temp_cb.setChecked(bool(spec.get("temperature", True)))
        # Flags absent from the stored spec are only written when the user
        # actually toggles them, so an unedited OK never invents them.
        self._initial_feature_state = {
            key: box.isChecked()
            for key, box in (("attachment", self.att_cb), ("reasoning", self.reas_cb),
                             ("tool_call", self.tools_cb), ("temperature", self.temp_cb))
        }

        feat_layout.addWidget(self.att_cb, 0, 0)
        feat_layout.addWidget(self.reas_cb, 0, 1)
        feat_layout.addWidget(self.tools_cb, 1, 0)
        feat_layout.addWidget(self.temp_cb, 1, 1)
        form.addRow(feat_box)

        # Modalities
        mods = spec.get("modalities", {}) if isinstance(spec.get("modalities"), dict) else {}
        in_mods = set(mods.get("input", ["text", "image"]))
        out_mods = set(mods.get("output", ["text"]))

        mod_box = QGroupBox("Modalities")
        mod_layout = QHBoxLayout(mod_box)
        self.mod_in_image = QCheckBox("Input Image")
        self.mod_in_image.setChecked("image" in in_mods)
        self.mod_in_audio = QCheckBox("Input Audio")
        self.mod_in_audio.setChecked("audio" in in_mods)
        self.mod_out_image = QCheckBox("Output Image")
        self.mod_out_image.setChecked("image" in out_mods)

        mod_layout.addWidget(self.mod_in_image)
        mod_layout.addWidget(self.mod_in_audio)
        mod_layout.addWidget(self.mod_out_image)
        form.addRow(mod_box)

        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_id_changed(self, text: str):
        prev = self.id_edit.property("_prev_id") or ""
        if not self.name_edit.text() or self.name_edit.text() == humanize_model_id(prev):
            self.name_edit.setText(humanize_model_id(text))
        self.id_edit.setProperty("_prev_id", text)

    def _accept(self):
        mid = self.id_edit.text().strip()
        if not mid:
            QMessageBox.warning(self, "Missing Model ID", "Please specify a Model ID.")
            return

        name = self.name_edit.text().strip() or humanize_model_id(mid)
        prov = self.prov_edit.text().strip() or "custom"

        # Start from the stored spec so fields this dialog does not show
        # (cost, aliases, extra modalities, ...) survive an unedited OK.
        spec = dict(self._original_spec)

        limit = dict(spec["limit"]) if isinstance(spec.get("limit"), dict) else {}
        limit["context"] = self.ctx_spin.value()
        limit["output"] = self.out_spin.value()
        spec["limit"] = limit

        spec["name"] = name
        spec["provider"] = prov

        # Booleans: keep stored flags as they are, and only introduce a flag
        # the user actually toggled (never flip "absent" into "true").
        for key, box in (("attachment", self.att_cb),
                         ("reasoning", self.reas_cb),
                         ("tool_call", self.tools_cb),
                         ("temperature", self.temp_cb)):
            if key in spec:
                spec[key] = box.isChecked()
            elif box.isChecked() != self._initial_feature_state[key]:
                spec[key] = box.isChecked()

        mods = dict(spec["modalities"]) if isinstance(spec.get("modalities"), dict) else {}
        known_in = {"text", "image", "audio"}
        known_out = {"text", "image"}
        in_mods = [m for m in mods.get("input", []) if m not in known_in]
        out_mods = [m for m in mods.get("output", []) if m not in known_out]
        in_mods.insert(0, "text")
        if self.mod_in_image.isChecked():
            in_mods.insert(1, "image")
        if self.mod_in_audio.isChecked() and "audio" not in in_mods:
            in_mods.append("audio")
        out_mods.insert(0, "text")
        if self.mod_out_image.isChecked() and "image" not in out_mods:
            out_mods.append("image")
        if "modalities" in spec:
            spec["modalities"] = {"input": in_mods, "output": out_mods}

        self.result_model_id = mid
        self.result_provider = prov
        self.result_spec = spec
        self.accept()


class EditPatternRuleDialog(QDialog):
    """Dialog to create or edit a pattern mapping rule."""

    def __init__(self, parent, rule: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Pattern Mapping Rule" if rule else "Add Pattern Mapping Rule")
        self.resize(500, 320)
        self.result_rule = {}

        rule = rule or {}
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.pat_edit = QLineEdit(rule.get("pattern", ""))
        self.pat_edit.setPlaceholderText("e.g. glm-*, deepseek-*, or regex:^my-proxy/.*")
        form.addRow("Pattern (wildcard/regex) *:", self.pat_edit)

        self.prov_edit = QLineEdit(rule.get("reference_provider", ""))
        self.prov_edit.setPlaceholderText("e.g. zhipu, openai, google, anthropic")
        form.addRow("Reference Provider *:", self.prov_edit)

        self.model_edit = QLineEdit(rule.get("reference_model", ""))
        self.model_edit.setPlaceholderText("e.g. glm-4-flash, gpt-4o (optional)")
        form.addRow("Reference Model (optional):", self.model_edit)

        self.desc_edit = QLineEdit(rule.get("description", ""))
        self.desc_edit.setPlaceholderText("e.g. Map all GLM models to Zhipu capabilities")
        form.addRow("Description:", self.desc_edit)

        layout.addLayout(form)

        hint = QLabel(
            "<small><b>Examples:</b><br>"
            "• <code>glm-*</code> with provider <code>zhipu</code>: any model like <code>glm-5.3-flash</code> gets Zhipu features.<br>"
            "• <code>my-proxy/*</code> with provider <code>openai</code> and model <code>gpt-4o</code>: matches proxy models to GPT-4o spec."
            "</small>"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _accept(self):
        pat = self.pat_edit.text().strip()
        prov = self.prov_edit.text().strip()
        if not pat or not prov:
            QMessageBox.warning(self, "Missing Fields", "Pattern and Reference Provider are required.")
            return

        self.result_rule = {
            "pattern": pat,
            "reference_provider": prov,
            "reference_model": self.model_edit.text().strip(),
            "description": self.desc_edit.text().strip(),
        }
        self.accept()


class CustomCatalogManagerDialog(QDialog):
    """Comprehensive dialog to manage custom model specs, pattern rules, and online catalog updates."""

    def __init__(self, parent, catalog: ModelCatalog):
        super().__init__(parent)
        self.setWindowTitle("Model Catalog & Matching Rules Manager")
        self.resize(900, 600)
        self.catalog = catalog
        self.settings = SettingsManager()
        self._sync_worker = None
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Custom Models
        self.custom_tab = QWidget()
        self._setup_custom_models_tab()
        self.tabs.addTab(self.custom_tab, "Custom Model Specs")

        # Tab 2: Pattern Rules
        self.rules_tab = QWidget()
        self._setup_pattern_rules_tab()
        self.tabs.addTab(self.rules_tab, "Pattern Mapping Rules")

        # Tab 3: Online Sync & Sources
        self.sync_tab = QWidget()
        self._setup_sync_tab()
        self.tabs.addTab(self.sync_tab, "Catalog Sources & Update")

        # Bottom Close button
        btn_layout = QHBoxLayout()
        self.status_lbl = QLabel()
        self._refresh_status()
        btn_layout.addWidget(self.status_lbl)
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _setup_custom_models_tab(self):
        lay = QVBoxLayout(self.custom_tab)

        tb = QHBoxLayout()
        self.custom_search = QLineEdit()
        self.custom_search.setPlaceholderText("Search custom models...")
        self.custom_search.textChanged.connect(self._filter_custom_models)
        tb.addWidget(self.custom_search)

        for text, slot in [
            ("+ Add Model", self._add_custom_model),
            ("Edit", self._edit_selected_custom_model),
            ("Delete", self._delete_selected_custom_model),
            ("Import JSON", self._import_custom_models),
            ("Export JSON", self._export_custom_models),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            tb.addWidget(b)
        lay.addLayout(tb)

        self.custom_table = QTableWidget(0, 6)
        self.custom_table.setHorizontalHeaderLabels([
            "Model ID", "Name", "Provider", "Context", "Output", "Features"
        ])
        self.custom_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.custom_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.custom_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.custom_table.cellDoubleClicked.connect(lambda row, col: self._edit_selected_custom_model())
        lay.addWidget(self.custom_table)

        self._refresh_custom_models_table()

    def _read_custom_models(self, warn: bool = False) -> dict:
        """Read the custom-model file; an unparseable file yields an empty map
        plus a warning instead of raising through the dialog's UI paths."""
        try:
            return self.catalog.get_all_custom_models()
        except ValueError as e:
            if warn:
                QMessageBox.warning(self, "Custom Models File Error", str(e))
            return {}

    def _refresh_custom_models_table(self):
        models = self._read_custom_models(warn=True)
        self._populate_custom_models_table(models)

    def _populate_custom_models_table(self, models: dict):
        self.custom_table.setRowCount(len(models))
        for row, (mid, spec) in enumerate(sorted(models.items())):
            spec = spec if isinstance(spec, dict) else {}
            self.custom_table.setItem(row, 0, QTableWidgetItem(mid))
            self.custom_table.setItem(row, 1, QTableWidgetItem(spec.get("name") or humanize_model_id(mid)))
            self.custom_table.setItem(row, 2, QTableWidgetItem(spec.get("provider", "custom")))
            limit = spec.get("limit", {}) if isinstance(spec.get("limit"), dict) else {}
            ctx = limit.get("context")
            out = limit.get("output")
            self.custom_table.setItem(row, 3, QTableWidgetItem(f"{ctx:,}" if ctx else "—"))
            self.custom_table.setItem(row, 4, QTableWidgetItem(f"{out:,}" if out else "—"))

            feats = []
            if spec.get("attachment"):
                feats.append("Attachment")
            if spec.get("reasoning"):
                feats.append("Reasoning")
            if spec.get("tool_call"):
                feats.append("Tools")
            self.custom_table.setItem(row, 5, QTableWidgetItem(", ".join(feats) if feats else "—"))

    def _filter_custom_models(self, text: str):
        all_models = self._read_custom_models()
        if not text:
            self._populate_custom_models_table(all_models)
            return
        text = text.lower()
        filtered = {
            mid: spec for mid, spec in all_models.items()
            if text in mid.lower() or text in str(spec.get("name", "")).lower() or text in str(spec.get("provider", "")).lower()
        }
        self._populate_custom_models_table(filtered)

    def _add_custom_model(self):
        dlg = EditCustomModelDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.result_model_id:
            self.catalog.save_custom_model(dlg.result_model_id, dlg.result_spec, dlg.result_provider)
            self._refresh_custom_models_table()
            self._refresh_status()

    def _edit_selected_custom_model(self):
        selected = self.custom_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        mid_item = self.custom_table.item(row, 0)
        if not mid_item:
            return
        mid = mid_item.text()
        all_models = self._read_custom_models()
        spec = all_models.get(mid, {})
        dlg = EditCustomModelDialog(self, mid, spec, spec.get("provider", "custom"))
        if dlg.exec() == QDialog.Accepted and dlg.result_model_id:
            if dlg.result_model_id != mid:
                self.catalog.delete_custom_model(mid)
            self.catalog.save_custom_model(dlg.result_model_id, dlg.result_spec, dlg.result_provider)
            self._refresh_custom_models_table()
            self._refresh_status()

    def _delete_selected_custom_model(self):
        selected = self.custom_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        mid = self.custom_table.item(row, 0).text()
        if _confirm(self, "Delete Custom Model", f"Delete custom model spec '{mid}'?"):
            self.catalog.delete_custom_model(mid)
            self._refresh_custom_models_table()
            self._refresh_status()

    def _import_custom_models(self):
        dlg = JsonImportDialog(
            self, "Import Custom Models",
            "Paste or load custom models JSON. Supported format: { \"model_id\": { \"name\": \"...\", ... } }"
        )
        if dlg.exec() == QDialog.Accepted and dlg.result_data:
            data = dlg.result_data
            if not isinstance(data, dict):
                QMessageBox.warning(self, "Import Error",
                                    "Custom models JSON must be an object.")
                return
            # Reject anything that is not `{model_id: {spec}}` before writing:
            # a stray "$schema" string would be saved and then break the loader.
            invalid = [k for k, v in data.items() if not isinstance(v, dict)]
            if invalid:
                QMessageBox.warning(
                    self, "Import Error",
                    "These entries are not model objects and were not imported: "
                    + ", ".join(sorted(map(str, invalid))[:10]),
                )
                return
            if not data:
                QMessageBox.warning(self, "Import Error", "No custom models found.")
                return
            try:
                current = self.catalog.get_all_custom_models()
            except ValueError as e:
                QMessageBox.warning(self, "Import Error", str(e))
                return
            current.update(data)
            try:
                CUSTOM_MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(
                    CUSTOM_MODELS_FILE,
                    json.dumps(current, indent=2, ensure_ascii=False),
                )
                self.catalog._reload_after_custom_change()
                self._refresh_custom_models_table()
                self._refresh_status()
                QMessageBox.information(self, "Import", f"Imported {len(data)} custom model(s).")
            except Exception as e:
                QMessageBox.warning(self, "Import Error", str(e))

    def _export_custom_models(self):
        models = self._read_custom_models()
        if not models:
            QMessageBox.information(self, "Export", "No custom models to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Custom Models", "custom_models.json",
            "JSON files (*.json);;All files (*)"
        )
        if path:
            try:
                Path(path).write_text(json.dumps(models, indent=2, ensure_ascii=False), encoding="utf-8")
                QMessageBox.information(self, "Export Complete", f"Exported to {path}")
            except OSError as e:
                QMessageBox.warning(self, "Export Error", str(e))

    def _setup_pattern_rules_tab(self):
        lay = QVBoxLayout(self.rules_tab)

        tb = QHBoxLayout()
        for text, slot in [
            ("+ Add Rule", self._add_pattern_rule),
            ("Edit", self._edit_selected_pattern_rule),
            ("Delete", self._delete_selected_pattern_rule),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            tb.addWidget(b)
        tb.addStretch()
        lay.addLayout(tb)

        self.rules_table = QTableWidget(0, 4)
        self.rules_table.setHorizontalHeaderLabels([
            "Pattern", "Reference Provider", "Reference Model", "Description"
        ])
        self.rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.rules_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.rules_table.cellDoubleClicked.connect(lambda row, col: self._edit_selected_pattern_rule())
        lay.addWidget(self.rules_table)

        # Interactive Tester Box
        test_box = QGroupBox("Interactive Pattern Rule Tester")
        test_lay = QHBoxLayout(test_box)
        self.test_input = QLineEdit()
        self.test_input.setPlaceholderText("Type a model ID to test pattern matching, e.g. glm-5.3-flash...")
        self.test_input.textChanged.connect(self._test_pattern_match)
        test_lay.addWidget(self.test_input, 2)
        self.test_result = QLabel("Enter a model ID above to test")
        self.test_result.setStyleSheet("color: #0969da; font-weight: bold;")
        test_lay.addWidget(self.test_result, 3)
        lay.addWidget(test_box)

        self._refresh_pattern_rules_table()

    def _refresh_pattern_rules_table(self):
        rules = self.catalog.get_all_pattern_rules()
        self.rules_table.setRowCount(len(rules))
        for row, rule in enumerate(rules):
            self.rules_table.setItem(row, 0, QTableWidgetItem(rule.get("pattern", "")))
            self.rules_table.setItem(row, 1, QTableWidgetItem(rule.get("reference_provider", "")))
            self.rules_table.setItem(row, 2, QTableWidgetItem(rule.get("reference_model", "")))
            self.rules_table.setItem(row, 3, QTableWidgetItem(rule.get("description", "")))

    def _add_pattern_rule(self):
        dlg = EditPatternRuleDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.result_rule:
            rules = self.catalog.get_all_pattern_rules()
            rules.append(dlg.result_rule)
            self.catalog.save_pattern_rules(rules)
            self._refresh_pattern_rules_table()
            self._refresh_status()

    def _edit_selected_pattern_rule(self):
        selected = self.rules_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        rules = self.catalog.get_all_pattern_rules()
        if row < len(rules):
            dlg = EditPatternRuleDialog(self, rules[row])
            if dlg.exec() == QDialog.Accepted and dlg.result_rule:
                rules[row] = dlg.result_rule
                self.catalog.save_pattern_rules(rules)
                self._refresh_pattern_rules_table()
                self._refresh_status()

    def _delete_selected_pattern_rule(self):
        selected = self.rules_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        rules = self.catalog.get_all_pattern_rules()
        if row < len(rules) and _confirm(self, "Delete Rule", f"Delete rule for pattern '{rules[row].get('pattern')}'?"):
            rules.pop(row)
            self.catalog.save_pattern_rules(rules)
            self._refresh_pattern_rules_table()
            self._refresh_status()

    def _test_pattern_match(self, text: str):
        mid = text.strip()
        if not mid:
            self.test_result.setText("Enter a model ID above to test")
            return
        matches = self.catalog.find_model(mid)
        if matches:
            fmt = matches[0]
            self.test_result.setText(
                f"✓ Matches! Provider: {fmt.provider} | Name: {fmt.name or humanize_model_id(mid)} | Context: {fmt.context_k()}"
            )
        else:
            self.test_result.setText("✗ No match found in catalog or pattern rules")

    def _setup_sync_tab(self):
        lay = QVBoxLayout(self.sync_tab)

        form = QFormLayout()
        self.url_edit = QLineEdit(self.settings.get_catalog_url())
        reset_btn = QPushButton("Reset URL")
        reset_btn.clicked.connect(lambda: self.url_edit.setText(DEFAULT_CATALOG_URL))
        url_lay = QHBoxLayout()
        url_lay.addWidget(self.url_edit, 1)
        url_lay.addWidget(reset_btn)
        form.addRow("Online Catalog URL:", url_lay)
        lay.addLayout(form)

        btn_row = QHBoxLayout()
        self.sync_btn = QPushButton("🔄 Update Catalog Online Now")
        self.sync_btn.setStyleSheet("padding: 8px 16px; font-weight: bold;")
        self.sync_btn.clicked.connect(self._sync_online)
        btn_row.addWidget(self.sync_btn)

        load_file_btn = QPushButton("Load Catalog from Local JSON...")
        load_file_btn.clicked.connect(self._load_local_catalog)
        btn_row.addWidget(load_file_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self.sync_info = QLabel()
        self.sync_info.setWordWrap(True)
        self.sync_info.setStyleSheet("background: palette(window); padding: 12px; border-radius: 6px;")
        lay.addWidget(self.sync_info)
        lay.addStretch()
        self._update_sync_info()

    def _update_sync_info(self):
        src = self.catalog.source or "None"
        cnt = len(self.catalog.flat)
        try:
            custom_cnt = len(self.catalog.get_all_custom_models())
        except ValueError:
            custom_cnt = -1
        rules_cnt = len(self.catalog.get_all_pattern_rules())
        last = self.catalog.last_updated or "Never"
        custom_label = "unreadable — fix or delete custom_models.json" if custom_cnt < 0 \
            else f"{custom_cnt:,}"
        self.sync_info.setText(
            f"<b>Active Catalog Source:</b> {src}<br>"
            f"<b>Total Catalog Models:</b> {cnt:,}<br>"
            f"<b>User Custom Models:</b> {custom_label}<br>"
            f"<b>Active Pattern Rules:</b> {rules_cnt:,}<br>"
            f"<b>Last Loaded / Updated:</b> {last}"
        )

    def _sync_online(self):
        """Start the online catalog update on a worker thread."""
        url = self.url_edit.text().strip()
        self.settings.set_catalog_url(url)
        self.sync_btn.setEnabled(False)
        self.sync_btn.setText("Updating...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self._sync_worker = _CatalogSyncWorker(self.catalog, url)
        self._sync_worker.finished_ok.connect(self._on_sync_ok)
        self._sync_worker.failed.connect(self._on_sync_failed)
        self._sync_worker.start()

    def _on_sync_ok(self, msg: str, count: int):
        QApplication.restoreOverrideCursor()
        self.sync_btn.setEnabled(True)
        self.sync_btn.setText("🔄 Update Catalog Online Now")
        QMessageBox.information(self, "Catalog Update", msg)
        self._update_sync_info()
        self._refresh_status()

    def _on_sync_failed(self, msg: str):
        QApplication.restoreOverrideCursor()
        self.sync_btn.setEnabled(True)
        self.sync_btn.setText("🔄 Update Catalog Online Now")
        QMessageBox.warning(self, "Catalog Update Error", msg)

    def _load_local_catalog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Catalog JSON", str(Path.home()),
            "JSON files (*.json);;All files (*)"
        )
        if path:
            try:
                self.catalog.load(Path(path))
                self._update_sync_info()
                self._refresh_status()
                QMessageBox.information(self, "Catalog Loaded", f"Successfully loaded {len(self.catalog.flat)} models.")
            except Exception as e:
                QMessageBox.warning(self, "Load Error", str(e))

    def _refresh_status(self):
        cnt = len(self.catalog.flat)
        try:
            custom_cnt = len(self.catalog.get_all_custom_models())
        except ValueError:
            custom_cnt = "error"
        rules_cnt = len(self.catalog.get_all_pattern_rules())
        self.status_lbl.setText(
            f"Catalog: {cnt:,} models | Custom: {custom_cnt} | Pattern Rules: {rules_cnt}"
        )


# Connectivity & Health Check GUI Components
# ---------------------------------------------------------------------------

# Exact npm packages whose endpoints can be tested with an API key, and the
# matching fetch adapter. Package names are matched whole (not by substring) so
# e.g. '@ai-sdk/google-vertex' is never probed against AI Studio.
_KNOWN_PROVIDER_PACKAGES = {
    "@ai-sdk/anthropic": "anthropic",
    "@ai-sdk/openai": "openai",
    "@ai-sdk/openai-compatible": "openai",
    "@ai-sdk/google": "gemini",
}

# Default endpoint per first-party package, keyed by npm name (not by adapter)
# so '@ai-sdk/openai-compatible' can be excluded.
_PACKAGE_DEFAULT_URLS = {
    "@ai-sdk/anthropic": "https://api.anthropic.com",
    "@ai-sdk/openai": "https://api.openai.com/v1",
    "@ai-sdk/google": "https://generativelanguage.googleapis.com",
}

# Default endpoint per adapter, for providers that are configured with just a
# key (the docs' own 'provider.anthropic.options.apiKey' example has no npm
# and no baseURL). The key is the provider id opencode ships under.
_BUILTIN_PROVIDERS = {
    "anthropic": ("anthropic", "https://api.anthropic.com"),
    "openai": ("openai", "https://api.openai.com/v1"),
    "google": ("gemini", "https://generativelanguage.googleapis.com"),
}


def resolve_provider_target(key: str, pdata: dict, config_dir: Optional[Path] = None):
    """Work out which endpoint and adapter to test for one provider entry.

    Returns (adapter, base_url, api_key, error). 'error' is non-empty when the
    provider cannot be tested at all (no endpoint and no known package); the
    placeholder variables in options are expanded here.
    """
    opts = pdata.get("options") if isinstance(pdata.get("options"), dict) else {}
    base_url = resolve_config_placeholders(opts.get("baseURL", ""), config_dir)
    api_key = resolve_config_placeholders(opts.get("apiKey", ""), config_dir)
    npm = pdata.get("npm", "") or ""
    if not isinstance(npm, str):
        npm = ""

    adapter = _KNOWN_PROVIDER_PACKAGES.get(npm)
    if adapter is None and npm not in ("", None):
        # Unknown package: only test it if it configures its own baseURL.
        return "openai", base_url, api_key, ""

    if adapter is None:
        builtin = _BUILTIN_PROVIDERS.get(key)
        if builtin is None:
            return "openai", base_url, api_key, ""
        adapter, default_url = builtin
        return adapter, base_url or default_url, api_key, ""

    # Only the first-party packages get a default endpoint. openai-compatible
    # is excluded on purpose: it fronts other vendors (OpenRouter, Ollama,
    # vLLM), so defaulting it to api.openai.com would ship the user's key to
    # the wrong vendor. It must configure its own baseURL.
    default_url = _PACKAGE_DEFAULT_URLS.get(npm)
    return adapter, base_url or (default_url or ""), api_key, ""


class ProviderPingWorker(QThread):
    """Background worker to test a provider connection without freezing the GUI."""
    finished_one = Signal(str, object)  # provider_key, ConnectionTestResult

    def __init__(self, providers_to_test: Dict[str, dict], config_dir: Optional[Path] = None):
        super().__init__()
        self.providers_to_test = providers_to_test
        self.config_dir = config_dir

    def run(self):
        for key, pdata in self.providers_to_test.items():
            if self.isInterruptionRequested():
                return
            if not isinstance(pdata, dict):
                continue

            adapter, base_url, api_key, error = resolve_provider_target(
                key, pdata, self.config_dir
            )

            if error:
                res = ConnectionTestResult(success=False, message=error)
            elif not base_url:
                npm = pdata.get("npm", "") or ""
                if npm:
                    msg = (f"'{npm}' cannot be tested: configure options.baseURL "
                           "in the provider to test this endpoint.")
                else:
                    msg = "No baseURL configured for this provider."
                res = ConnectionTestResult(success=False, message=msg)
            else:
                res = test_provider_connection(
                    base_url=base_url,
                    api_key=api_key,
                    adapter=adapter,
                    timeout=12,
                    allow_local=True,
                )
            self.finished_one.emit(key, res)


class ProviderHealthCheckDialog(QDialog):
    """Dialog to run live health checks on all configured providers."""

    def __init__(self, parent=None, providers: Optional[dict] = None, auto_run: bool = True,
                 config_path: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("⚡ Provider Connectivity & Health Check")
        self.setMinimumSize(780, 520)
        self.providers = providers or {}
        self.results: Dict[str, ConnectionTestResult] = {}
        self.worker: Optional[ProviderPingWorker] = None
        # {file:} paths resolve relative to the config file being edited; the
        # default is the global opencode config dir.
        if config_path:
            self.config_dir = Path(config_path).expanduser().parent
        else:
            self.config_dir = Path.home() / ".config" / "opencode"

        layout = QVBoxLayout(self)

        # Header description
        info = QLabel(
            "Test endpoint reachability, response latency, authentication keys, and discovered models for your configured providers."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; margin-bottom: 6px;")
        layout.addWidget(info)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        layout.addWidget(self.progress)

        # Splitter: Left table, right details
        splitter = QSplitter(Qt.Horizontal)

        # Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Provider", "Status", "Latency", "Models"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.table)

        # Right side: Detail box
        right_box = QGroupBox("Health Diagnostic Details")
        right_lay = QVBoxLayout(right_box)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("Select a provider row to view detailed response and model list...")
        right_lay.addWidget(self.detail_text)
        splitter.addWidget(right_box)
        splitter.setSizes([450, 330])

        layout.addWidget(splitter, 1)

        # Buttons
        btns = QHBoxLayout()
        self.run_btn = QPushButton("▶ Run All Tests")
        self.run_btn.clicked.connect(self.run_tests)
        btns.addWidget(self.run_btn)

        self.retest_sel_btn = QPushButton("↺ Test Selected")
        self.retest_sel_btn.clicked.connect(self._test_selected)
        btns.addWidget(self.retest_sel_btn)

        btns.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

        self._populate_table()
        if auto_run and self.providers:
            self.run_tests()

    def _stop_worker(self):
        """Stop the running worker cooperatively and wait for it to unwind.

        QThread.terminate() is never used: killing a thread mid-request can
        deadlock the interpreter's own locks and freeze the editor.
        """
        worker = self.worker
        if not worker or not worker.isRunning():
            self.worker = None
            return
        # Parent the thread to the dialog so Qt keeps it alive while it drains.
        worker.setParent(self)
        worker.requestInterruption()
        try:
            worker.finished_one.disconnect()
        except (RuntimeError, TypeError):
            pass
        if worker.wait(3000):
            # Fully unwound: safe to drop the last reference.
            self.worker = None
        # else: a request is still blocked (DNS, dropped SYN, silent server).
        # Keep the reference and let _on_all_finished clear it, otherwise the
        # QThread is destroyed while running and the process aborts.

    def _busy(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def _set_running(self, running: bool):
        """Keep both start buttons disabled for the whole run."""
        self.run_btn.setEnabled(not running)
        self.retest_sel_btn.setEnabled(not running)
        if running:
            self.progress.show()
        else:
            self.progress.hide()

    def closeEvent(self, event):
        self._stop_worker()
        super().closeEvent(event)

    def reject(self):
        self._stop_worker()
        super().reject()

    def accept(self):
        self._stop_worker()
        super().accept()

    def _populate_table(self):
        self.table.setRowCount(0)
        for key in sorted(self.providers.keys()):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(key))
            self.table.setItem(r, 1, QTableWidgetItem("Ready"))
            self.table.setItem(r, 2, QTableWidgetItem("-"))
            self.table.setItem(r, 3, QTableWidgetItem("-"))

    def run_tests(self):
        if not self.providers:
            QMessageBox.information(self, "No Providers", "No providers configured to test.")
            return
        if self._busy():
            return

        self._set_running(True)
        self.progress.setRange(0, len(self.providers))
        self.progress.setValue(0)

        for r in range(self.table.rowCount()):
            self.table.setItem(r, 1, QTableWidgetItem("Testing..."))
            self.table.setItem(r, 2, QTableWidgetItem("-"))
            self.table.setItem(r, 3, QTableWidgetItem("-"))

        self.worker = ProviderPingWorker(self.providers, self.config_dir)
        self.worker.finished_one.connect(self._on_provider_tested)
        self.worker.finished.connect(self._on_all_finished)
        self.worker.start()

    def _test_selected(self):
        selected_rows = sorted({i.row() for i in self.table.selectedItems()})
        if not selected_rows:
            QMessageBox.information(self, "Selection", "Please select a provider row to test.")
            return
        if self._busy():
            return

        subset = {}
        for r in selected_rows:
            key = self.table.item(r, 0).text()
            if key in self.providers:
                subset[key] = self.providers[key]
                self.table.setItem(r, 1, QTableWidgetItem("Testing..."))

        self._set_running(True)
        self.worker = ProviderPingWorker(subset, self.config_dir)
        self.worker.finished_one.connect(self._on_provider_tested)
        self.worker.finished.connect(self._on_all_finished)
        self.worker.start()

    def _on_provider_tested(self, key: str, res: ConnectionTestResult):
        self.results[key] = res
        self.progress.setValue(self.progress.value() + 1)

        # Find row
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).text() == key:
                if res.success:
                    status_item = QTableWidgetItem("✓ OK")
                    status_item.setForeground(Qt.darkGreen)
                    lat_item = QTableWidgetItem(f"{res.latency_ms:.0f} ms")
                    mod_item = QTableWidgetItem(str(res.model_count or 0))
                else:
                    status_item = QTableWidgetItem("✗ Error")
                    status_item.setForeground(Qt.red)
                    lat_item = QTableWidgetItem(f"{res.latency_ms:.0f} ms" if res.latency_ms else "-")
                    mod_item = QTableWidgetItem("-")

                self.table.setItem(r, 1, status_item)
                self.table.setItem(r, 2, lat_item)
                self.table.setItem(r, 3, mod_item)
                break

        self._on_selection_changed()

    def _on_all_finished(self):
        self.worker = None
        self._set_running(False)

    def _on_selection_changed(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        key = self.table.item(row, 0).text()
        res = self.results.get(key)
        if not res:
            self.detail_text.setHtml(
                f"<h3>{html.escape(key)}</h3><p>Testing or not yet run...</p>"
            )
            return

        # Escape every provider-controlled value: raw errors look like
        # '<urlopen error ...>', which setHtml() would swallow as a tag.
        esc_key = html.escape(key)
        color = "green" if res.success else "red"
        out = f"<h3>Provider: <span style='color:{color}'>{esc_key}</span></h3>"
        out += f"<p><b>Status:</b> {'SUCCESS' if res.success else 'FAILED'}</p>"
        out += f"<p><b>Latency:</b> {res.latency_ms:.1f} ms</p>"
        out += f"<p><b>Message:</b> {html.escape(res.message)}</p>"

        if res.models:
            out += f"<h4>Discovered Models ({len(res.models)}):</h4><ul>"
            for m in res.models:
                out += f"<li><code>{html.escape(str(m))}</code></li>"
            out += "</ul>"
        elif res.raw_error:
            out += ("<h4>Diagnostic Log:</h4>"
                    f"<pre style='background:#f5f5f5; padding:6px;'>{html.escape(res.raw_error)}</pre>")

        self.detail_text.setHtml(out)
# MCP Template Hub GUI Dialog
# ---------------------------------------------------------------------------


class MCPTemplateHubDialog(QDialog):
    """Visual App Store / Hub for browsing and 1-click installing MCP Servers."""

    def __init__(self, parent=None, target_mode: str = "opencode"):
        super().__init__(parent)
        self.setWindowTitle("🧩 MCP Server Hub & Templates")
        self.setMinimumSize(860, 560)
        self.target_mode = target_mode  # "opencode" or "openclaude"
        self.selected_template: Optional[MCPTemplate] = None
        self.result_server_key: str = ""
        self.result_server_config: dict = {}

        layout = QVBoxLayout(self)

        # Header description
        info = QLabel(
            "Browse curated Model Context Protocol (MCP) servers and install them directly into your configuration."
        )
        info.setStyleSheet("color: #666; margin-bottom: 4px;")
        layout.addWidget(info)

        # Filter bar
        filter_bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search MCP servers...")
        self.search_edit.textChanged.connect(self._filter_templates)
        filter_bar.addWidget(self.search_edit, 2)

        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories")
        cats = sorted({t.category for t in MCP_REGISTRY})
        for c in cats:
            self.category_combo.addItem(c)
        self.category_combo.currentIndexChanged.connect(self._filter_templates)
        filter_bar.addWidget(self.category_combo, 1)

        layout.addLayout(filter_bar)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left: List of templates
        self.template_list = QListWidget()
        self.template_list.currentRowChanged.connect(self._on_template_selected)
        splitter.addWidget(self.template_list)

        # Right: Configurator & preview
        right_panel = QWidget()
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(0, 0, 0, 0)

        # Template Header / Description
        self.desc_group = QGroupBox("Server Info")
        desc_lay = QVBoxLayout(self.desc_group)
        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        desc_lay.addWidget(self.desc_label)
        right_lay.addWidget(self.desc_group)

        # Parameters Form
        self.param_group = QGroupBox("Configuration Parameters")
        self.param_form = QFormLayout(self.param_group)
        self.key_edit = QLineEdit()
        self.key_edit.textChanged.connect(self._update_preview)
        self.param_form.addRow("Server Key:", self.key_edit)

        self.param_widgets: Dict[str, QLineEdit] = {}
        self.env_widgets: Dict[str, MaskedLineEdit] = {}
        self.url_edit: Optional[QLineEdit] = None

        right_lay.addWidget(self.param_group)

        # Preview box
        self.preview_group = QGroupBox(f"Configuration Preview ({target_mode.capitalize()})")
        prev_lay = QVBoxLayout(self.preview_group)
        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setMaximumHeight(140)
        prev_lay.addWidget(self.preview_edit)
        right_lay.addWidget(self.preview_group)

        splitter.addWidget(right_panel)
        splitter.setSizes([320, 540])
        layout.addWidget(splitter, 1)

        # Bottom buttons
        btns = QHBoxLayout()
        self.install_btn = QPushButton(f"✓ Install into {target_mode.capitalize()}")
        self.install_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.install_btn.clicked.connect(self._on_install)
        btns.addWidget(self.install_btn)

        btns.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        self._populate_list()
        if self.template_list.count() > 0:
            self.template_list.setCurrentRow(0)

    def _populate_list(self):
        self.template_list.clear()
        for tmpl in MCP_REGISTRY:
            item = QListWidgetItem(f"{tmpl.name} [{tmpl.category}]")
            item.setData(Qt.UserRole, tmpl.id)
            self.template_list.addItem(item)

    def _filter_templates(self):
        text = self.search_edit.text().strip().lower()
        cat = self.category_combo.currentText()

        self.template_list.clear()
        for tmpl in MCP_REGISTRY:
            if cat != "All Categories" and tmpl.category != cat:
                continue
            if text and (text not in tmpl.name.lower() and text not in tmpl.description.lower() and text not in tmpl.id.lower()):
                continue
            item = QListWidgetItem(f"{tmpl.name} [{tmpl.category}]")
            item.setData(Qt.UserRole, tmpl.id)
            self.template_list.addItem(item)

        if self.template_list.count() > 0:
            self.template_list.setCurrentRow(0)
        else:
            # Nothing can be selected, so nothing may stay installable.
            self.selected_template = None
            self._clear_result()

    def _on_template_selected(self, row: int):
        if row < 0:
            return
        item = self.template_list.item(row)
        if not item:
            return
        tid = item.data(Qt.UserRole)
        tmpl = get_mcp_template(tid)
        if not tmpl:
            return

        self.selected_template = tmpl
        # Block the signal: key_edit's textChanged would otherwise preview the
        # previous template's params (or a deleted widget) mid-rebuild.
        self.key_edit.blockSignals(True)
        self.key_edit.setText(tmpl.id)
        self.key_edit.blockSignals(False)

        # Update description
        doc_html = f"<br><a href='{tmpl.doc_url}'>Documentation</a>" if tmpl.doc_url else ""
        self.desc_label.setText(f"<b>{tmpl.name}</b> ({tmpl.category})<br>{tmpl.description}{doc_html}")
        self.desc_label.setOpenExternalLinks(True)

        # Clear and rebuild dynamic parameter form
        while self.param_form.rowCount() > 1:
            self.param_form.removeRow(1)

        self.param_widgets.clear()
        self.env_widgets.clear()
        self.url_edit = None  # the previous remote row's QLineEdit is deleted below

        if tmpl.transport_type == "remote":
            # Example URL as a hint only: a prefilled example would pass the
            # blank check and install a server pointing at a dummy endpoint.
            self.url_edit = QLineEdit()
            self.url_edit.setPlaceholderText(tmpl.url)
            self.url_edit.textChanged.connect(self._update_preview)
            self.param_form.addRow("Server URL:", self.url_edit)
        else:
            # Check for arguments like {allowed_directory} or {db_path}
            for part in tmpl.command:
                if "{" in part and "}" in part:
                    param_name = part[part.find("{") + 1 : part.find("}")]
                    p_edit = QLineEdit()
                    if tmpl.default_args:
                        p_edit.setPlaceholderText(tmpl.default_args[0])
                    p_edit.textChanged.connect(self._update_preview)

                    # Add file / dir picker button if applicable
                    row_box = QHBoxLayout()
                    row_box.addWidget(p_edit, 1)
                    if "directory" in param_name or "path" in param_name or "repo" in param_name:
                        browse_btn = QPushButton("Browse...")
                        browse_btn.setFixedWidth(70)
                        browse_btn.setProperty(
                            "picker_mode", "file" if param_name.endswith("db_path") else "dir"
                        )
                        browse_btn.clicked.connect(lambda _, pe=p_edit, b=browse_btn: self._browse_path(pe, b.property("picker_mode")))
                        row_box.addWidget(browse_btn)

                    self.param_form.addRow(f"Arg ({param_name}):", row_box)
                    self.param_widgets[param_name] = p_edit

            # Env keys (masked: these carry API tokens)
            for k, placeholder in tmpl.env_keys.items():
                env_edit = MaskedLineEdit(field_name=k, placeholder=placeholder, secret=True)
                env_edit.textChanged.connect(self._update_preview)
                self.param_form.addRow(f"Env ({k}):", env_edit)
                self.env_widgets[k] = env_edit

        self._update_preview()

    def _browse_path(self, target_edit: QLineEdit, mode: str = "dir"):
        if mode == "file":
            # Only a path is chosen (an existing db or a new file); nothing is
            # written here, so skip the misleading "overwrite?" prompt.
            path, _ = QFileDialog.getSaveFileName(
                self, "Select File", target_edit.text(),
                options=QFileDialog.Option.DontConfirmOverwrite)
        else:
            path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if path:
            target_edit.setText(path)

    def _update_preview(self):
        if not self.selected_template:
            return

        key = self.key_edit.text().strip() or self.selected_template.id
        args_vals = {k: w.text().strip() for k, w in self.param_widgets.items()}
        env_vals = {k: w.value().strip() for k, w in self.env_widgets.items()}
        url_val = self.url_edit.text().strip() if self.url_edit else ""

        if self.target_mode == "openclaude":
            cfg = instantiate_openclaude_mcp(
                self.selected_template, key, args_vals, env_vals, url_val
            )
        else:
            cfg = instantiate_opencode_mcp(
                self.selected_template, key, args_vals, env_vals, url_val
            )

        self.result_server_key = key
        self.result_server_config = cfg
        # Redact secrets in the preview only; the result keeps the real values.
        # This covers env values, URL query tokens, and credentials embedded in
        # DSNs such as postgresql://user:password@host/db.
        secret_values = [
            widget.text().strip()
            for name, widget in self.param_widgets.items()
            if MaskedLineEdit.SECRET_HINT.search(name) and widget.text().strip()
        ]

        def redact(value):
            if isinstance(value, str):
                value = re.sub(
                    r"(?i)([a-z][a-z0-9+.-]*://[^:/@\s]+:)([^@\s]+)(@)",
                    r"\1***\3", value)
                value = re.sub(
                    r"([?&](?:key|api_key|apikey|token|access_token|password|secret)=)[^&]*",
                    r"\1***", value, flags=re.I)
                for secret in secret_values:
                    value = value.replace(secret, "***")
                return value
            if isinstance(value, dict):
                return {k: redact(v) for k, v in value.items()}
            if isinstance(value, list):
                return [redact(v) for v in value]
            return value

        shown = redact(cfg)
        for env_key in ("env", "environment"):
            if env_key in shown:
                shown[env_key] = {
                    k: _mask(v) if (self.env_widgets.get(k) and self.env_widgets[k].is_secret) else v
                    for k, v in shown[env_key].items()
                }
        self.preview_edit.setPlainText(
            json.dumps({key: shown}, indent=2, ensure_ascii=False))
        self.install_btn.setEnabled(True)

    def _blank_required(self) -> Optional[str]:
        """Label of the first required field left blank, else None."""
        if self.selected_template and self.selected_template.transport_type == "remote":
            return None if (self.url_edit and self.url_edit.text().strip()) else "Server URL"
        for name, w in self.param_widgets.items():
            if not w.text().strip():
                return f"Arg ({name})"
        return None

    def _clear_result(self):
        self.result_server_key = ""
        self.result_server_config = {}
        self.install_btn.setEnabled(False)
        self.preview_edit.clear()

    def _on_install(self):
        missing = self._blank_required()
        if missing:
            QMessageBox.warning(self, "Error", f"{missing} cannot be empty.")
            return
        if not self.result_server_key:
            QMessageBox.warning(self, "Error", "Server key cannot be empty.")
            return
        self.accept()
# Universal Cross-Config Converter GUI Dialog
# ---------------------------------------------------------------------------


_OMP_COMPONENTS = ("providers", "mcp_servers", "plugins", "permissions", "prompts", "settings")


class CrossConfigConverterDialog(QDialog):
    """Dialog to convert and transfer configurations across OpenCode, OpenClaude, OMP v1, Claude Desktop, and Cursor."""

    def __init__(self, parent=None, app_context=None):
        super().__init__(parent)
        self.setWindowTitle("🔄 Universal AI Config Converter & Importer/Exporter")
        self.setMinimumSize(920, 620)
        self.app_context = app_context
        self.source_data: Dict[str, Any] = {}
        self.source_valid = False
        self.unmapped_keys: List[str] = []
        self.converted_data: Dict[str, Any] = {}

        layout = QVBoxLayout(self)

        # Header description
        info = QLabel(
            "Convert, migrate, or bundle configurations seamlessly between OpenCode, OpenClaude, OMP v1, Cursor, and Claude Desktop."
        )
        info.setStyleSheet("color: #666; margin-bottom: 6px;")
        layout.addWidget(info)

        # Splitter: Source & Options on Left, Target & Preview on Right
        splitter = QSplitter(Qt.Horizontal)

        # Left Panel: Source & Selections
        left_panel = QWidget()
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)

        # Source Selection Group
        src_group = QGroupBox("1. Source Configuration")
        src_lay = QVBoxLayout(src_group)

        src_top = QHBoxLayout()
        self.src_type_combo = QComboBox()
        self.src_type_combo.addItem("Current Active OpenCode Config", "active_opencode")
        self.src_type_combo.addItem("Current Active OpenClaude Config", "active_openclaude")
        self.src_type_combo.addItem("Load from File...", "file")
        self.src_type_combo.addItem("Paste Custom JSON", "custom")
        self.src_type_combo.currentIndexChanged.connect(self._on_source_type_changed)
        src_top.addWidget(self.src_type_combo, 1)

        self.load_file_btn = QPushButton("Browse...")
        self.load_file_btn.clicked.connect(self._load_source_file)
        self.load_file_btn.hide()
        src_top.addWidget(self.load_file_btn)
        src_lay.addLayout(src_top)

        self.src_editor = QTextEdit()
        self.src_editor.setPlaceholderText("Source JSON will appear here...")
        self.src_editor.textChanged.connect(self._on_source_text_changed)
        src_lay.addWidget(self.src_editor)
        left_lay.addWidget(src_group, 2)

        # Component Filters Group
        comp_group = QGroupBox("2. Select Components to Transfer")
        comp_lay = QVBoxLayout(comp_group)

        self.comp_checks = {
            "providers": QCheckBox("Providers & Models"),
            "mcp_servers": QCheckBox("MCP Servers"),
            "plugins": QCheckBox("Plugins"),
            "permissions": QCheckBox("Permissions (allow / deny / ask)"),
            "prompts": QCheckBox("Instructions / Prompts"),
            "settings": QCheckBox("Environment & TUI Settings"),
        }
        for chk in self.comp_checks.values():
            chk.setChecked(True)
            chk.stateChanged.connect(self._run_conversion)
            comp_lay.addWidget(chk)

        left_lay.addWidget(comp_group, 1)
        splitter.addWidget(left_panel)

        # Right Panel: Target & Output Preview
        right_panel = QWidget()
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(0, 0, 0, 0)

        # Target Selection Group
        tgt_group = QGroupBox("3. Target Format")
        tgt_lay = QVBoxLayout(tgt_group)

        self.tgt_format_combo = QComboBox()
        self.tgt_format_combo.addItem("OpenCode Config (opencode.json)", "opencode")
        self.tgt_format_combo.addItem("OpenClaude Global (~/.openclaude.json / .mcp.json)", "openclaude_global")
        self.tgt_format_combo.addItem("OpenClaude Settings (settings.json)", "openclaude_settings")
        self.tgt_format_combo.addItem("OMP v1 Universal Bundle (omp.json)", "omp")
        self.tgt_format_combo.addItem("Claude Desktop / Cursor MCP (mcpServers)", "claude_desktop")
        self.tgt_format_combo.currentIndexChanged.connect(self._run_conversion)
        tgt_lay.addWidget(self.tgt_format_combo)
        right_lay.addWidget(tgt_group)

        # Output Preview Group
        out_group = QGroupBox("4. Resulting Output Preview")
        out_lay = QVBoxLayout(out_group)
        self.out_editor = QTextEdit()
        self.out_editor.setReadOnly(True)
        out_lay.addWidget(self.out_editor)
        self.unmapped_label = QLabel("")
        self.unmapped_label.setWordWrap(True)
        self.unmapped_label.setStyleSheet("color: #b26a00;")
        self.unmapped_label.setVisible(False)
        out_lay.addWidget(self.unmapped_label)

        out_btns = QHBoxLayout()
        copy_btn = QPushButton("📋 Copy Result")
        copy_btn.clicked.connect(self._copy_result)
        out_btns.addWidget(copy_btn)

        save_btn = QPushButton("💾 Save to File...")
        save_btn.clicked.connect(self._save_to_file)
        out_btns.addWidget(save_btn)
        out_lay.addLayout(out_btns)

        right_lay.addWidget(out_group, 1)
        splitter.addWidget(right_panel)
        splitter.setSizes([430, 490])
        layout.addWidget(splitter, 1)

        # Bottom Actions
        bottom_bar = QHBoxLayout()
        self.apply_btn = QPushButton("⚡ Apply Directly to Active Config")
        self.apply_btn.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.apply_btn.clicked.connect(self._apply_to_active)
        bottom_bar.addWidget(self.apply_btn)

        bottom_bar.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom_bar.addWidget(close_btn)
        layout.addLayout(bottom_bar)

        # Initial source load
        self._on_source_type_changed(0)

    def _on_source_type_changed(self, idx: int):
        src_type = self.src_type_combo.currentData()
        self.load_file_btn.setVisible(src_type == "file")

        if src_type == "active_opencode":
            if self.app_context and getattr(self.app_context, "cfg", None):
                self.source_data = dict(self.app_context.cfg.data)
                self.src_editor.setPlainText(json.dumps(self.source_data, indent=2, ensure_ascii=False))
            else:
                self.src_editor.setPlainText("{\n  \"provider\": {}\n}")
        elif src_type == "active_openclaude":
            layered = getattr(self.app_context, "oc_layered", None) if self.app_context else None
            if layered is not None:
                combined = dict(layered.global_data or {})
                for key, val in (layered.effective() or {}).items():
                    combined.setdefault(key, val)
                # .mcp.json holds {"mcpServers": {...}}; merge just the servers,
                # or they end up double-nested under mcpServers.mcpServers.
                project_servers = (layered.project_mcp or {}).get("mcpServers")
                if isinstance(project_servers, dict) and project_servers:
                    existing = combined.get("mcpServers")
                    combined["mcpServers"] = (
                        {**existing, **project_servers} if isinstance(existing, dict) else dict(project_servers)
                    )
                self.src_editor.setPlainText(json.dumps(combined, indent=2, ensure_ascii=False))
            else:
                self.src_editor.setPlainText("{\n  \"mcpServers\": {}\n}")
        elif src_type == "file":
            self.src_editor.setPlaceholderText("Click 'Browse...' to select a config file to import.")
        elif src_type == "custom":
            self.src_editor.setPlaceholderText("Paste any JSON config here...")

    def _load_source_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Config File to Import", "",
            "JSON files (*.json *.jsonc);;All files (*)"
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
            data = loads_jsonc(content)
            self.src_editor.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Failed to load file: {e}")

    def _on_source_text_changed(self):
        text = self.src_editor.toPlainText().strip()
        if not text:
            self.source_data = {}
            self.converted_data = {}
            self.source_valid = False
            self.out_editor.clear()
            return
        try:
            data = loads_jsonc(text)
        except Exception:
            self.source_valid = False
            self.source_data = {}
            self.converted_data = {}
            self.out_editor.setPlainText("// Invalid JSON input in source editor")
            return
        if not isinstance(data, dict):
            self.source_valid = False
            self.source_data = {}
            self.converted_data = {}
            self.out_editor.setPlainText("// Source JSON must be an object")
            return
        self.source_valid = True
        self.source_data = data
        self._run_conversion()

    def _get_selected_components(self) -> List[str]:
        return [k for k, chk in self.comp_checks.items() if chk.isChecked()]

    def _run_conversion(self):
        if not self.source_data:
            self.converted_data = {}
            self.unmapped_keys = []
            self.out_editor.clear()
            self.unmapped_label.setText("")
            self.unmapped_label.setVisible(False)
            return

        target_fmt = self.tgt_format_combo.currentData()
        comps = self._get_selected_components()
        src_fmt = detect_config_format(self.source_data)

        # 1. Normalize source to OMP bundle first as intermediate universal format
        if src_fmt == "omp":
            omp_bundle = self.source_data
        elif src_fmt == "openclaude_global":
            omp_bundle = export_to_omp(openclaude_global=self.source_data)
        elif src_fmt == "openclaude_settings":
            omp_bundle = export_to_omp(openclaude_settings=self.source_data)
        elif src_fmt == "claude_desktop":
            omp_bundle = export_to_omp(openclaude_global=self.source_data)
        else:
            # Assume opencode
            omp_bundle = export_to_omp(opencode_cfg=self.source_data)

        # 2. Convert OMP bundle to target format
        if target_fmt == "omp":
            # OMP is the intermediate format itself: honour the component filter
            omp_bundle = {k: v for k, v in omp_bundle.items() if k not in _OMP_COMPONENTS or k in comps}
            self.converted_data = omp_bundle
        elif target_fmt == "claude_desktop":
            mcp_data = import_from_omp(omp_bundle, "openclaude_global", comps)
            self.converted_data = {"mcpServers": mcp_data.get("mcpServers", {})}
        else:
            self.converted_data = import_from_omp(omp_bundle, target_fmt, comps)

        self.unmapped_keys = self._find_unmapped_keys(src_fmt)
        if self.unmapped_keys:
            self.unmapped_label.setText(
                "Not transferred (no mapping for this target): " + ", ".join(self.unmapped_keys)
            )
            self.unmapped_label.setVisible(True)
        else:
            self.unmapped_label.setText("")
            self.unmapped_label.setVisible(False)
        self.out_editor.setPlainText(json.dumps(self.converted_data, indent=2, ensure_ascii=False))

    def _find_unmapped_keys(self, src_fmt: str) -> List[str]:
        """Top-level source keys the conversion has no mapping for."""
        handled = {
            "opencode": {"provider", "mcp", "plugin", "permission", "instructions", "tui"},
            "openclaude_global": {"mcpServers", "providerProfiles"},
            "openclaude_settings": {"permissions", "env"},
            "claude_desktop": {"mcpServers"},
        }.get(src_fmt, set())
        if src_fmt == "omp":
            handled = set(_OMP_COMPONENTS)
        return sorted(str(k) for k in self.source_data if str(k) not in handled)

    def _copy_result(self):
        text = self.out_editor.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            QMessageBox.information(self, "Copied", "Converted configuration copied to clipboard.")

    def _save_to_file(self):
        if not self.source_valid or not self.converted_data:
            QMessageBox.warning(self, "No Data", "Nothing to save: fix the source JSON first.")
            return
        target_fmt = self.tgt_format_combo.currentData()
        default_name = f"{target_fmt}-config.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Converted Config", default_name,
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return
        target = Path(path)
        try:
            payload = json.loads(json.dumps(self.converted_data))
            # Merge into an existing file so unrelated keys (app state, other
            # sections) survive; only keys the conversion produced are written.
            if target.is_file():
                existing = loads_jsonc(target.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    payload = deep_merge(existing, copy.deepcopy(payload))
            atomic_write_json(target, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            QMessageBox.information(self, "Saved", f"Exported successfully to {path}")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save file: {e}")

    def _apply_to_active(self):
        if not self.source_valid:
            QMessageBox.warning(self, "No Data", "Fix the source JSON before applying.")
            return
        if not self.converted_data:
            QMessageBox.warning(self, "No Data", "No converted data to apply.")
            return

        if not self.app_context:
            QMessageBox.warning(self, "Error", "No active editor instance found.")
            return
        target_fmt = self.tgt_format_combo.currentData()

        # Apply merges into in-memory data (or writes straight to disk for OpenClaude) and
        # then reloads the tabs. Any pending form/Raw edit lives only in the tab widgets
        # until Save, so refresh would silently drop it. Settle those edits first.
        if target_fmt == "opencode":
            unsaved = (
                bool(getattr(self.app_context, "dirty_oc", False))
                or bool(getattr(self.app_context, "dirty_tui", False))
                or bool(getattr(getattr(self.app_context, "tab_raw", None), "_modified", False))
            )
        else:
            unsaved = (
                bool(getattr(self.app_context, "oc_form_dirty", False))
                or bool(getattr(getattr(self.app_context, "_agent_raw_tab", None), "_modified", False))
            )
        if unsaved:
            action = _confirm_unsaved(self.app_context, "apply the converted configuration")
            if action == "cancel":
                return
            if action == "save":
                self.app_context._save()

        if target_fmt == "opencode" and getattr(self.app_context, "cfg", None):
            if not _confirm(self, "Apply Config", "Merge converted settings into current OpenCode configuration?"):
                return
            self.app_context.snapshot_state("opencode")
            self.app_context.cfg.data = deep_merge(
                self.app_context.cfg.data, copy.deepcopy(self.converted_data)
            )
            self.app_context.mark_dirty("opencode")
            self.app_context.refresh_tabs()
            QMessageBox.information(self, "Success", "Applied converted settings to OpenCode configuration.")
            self.accept()

        elif "openclaude" in target_fmt:
            layered = getattr(self.app_context, "oc_layered", None)
            if layered is None:
                QMessageBox.information(
                    self, "Format Mismatch",
                    f"Please export to file or copy result to use with {target_fmt}.",
                )
                return
            if not _confirm(self, "Apply Config", "Apply converted settings into current OpenClaude configuration?"):
                return
            if target_fmt == "openclaude_global":
                merged = deep_merge(dict(layered.global_data or {}), copy.deepcopy(self.converted_data))
                ok, msg = layered.save_global(merged)
            else:
                merged = deep_merge(dict(layered.layer("user") or {}), copy.deepcopy(self.converted_data))
                ok, msg = layered.save_layer("user", merged)
            if not ok:
                QMessageBox.warning(self, "Save Error", msg)
                return
            self.app_context.refresh_tabs()
            QMessageBox.information(self, "Success", "Applied converted settings to OpenClaude configuration.")
            self.accept()
        else:
            QMessageBox.information(self, "Format Mismatch", f"Please export to file or copy result to use with {target_fmt}.")
def match_models_against_catalog(key, models_dict, catalog, reference_provider=None):
    """Build a list of potential catalog matches for the given models.
    Returns (entries, ambiguous_data, fallback_data).
    """
    settings = SettingsManager()
    mappings = settings.get_reference_mappings()
    entries = []       # (model_id, old_spec, new_spec|None, status)
    ambiguous_data = {}
    fallback_data = {}  # {model_id: ModelFormat}

    for mid in sorted(models_dict):
        matches = catalog.find_model(mid)
        if not matches:
            fmt = None
            # 1. Previously persisted manual/auto mapping wins.
            saved = mappings.get(f"{key}/{mid}")
            if saved:
                saved_matches = catalog.find_model(saved)
                if saved_matches:
                    fmt = _sort_matches(saved_matches, reference_provider or key)[0]
            # 2. Reference provider / normalized-id / prefix fallback.
            if fmt is None:
                fmt = _find_fallback(mid, reference_provider, catalog)
            if fmt is not None:
                merged = _merge_model_spec(
                    models_dict[mid], build_spec_from_format(fmt, mid), overwrite=False)
                entries.append((mid, dict(models_dict[mid]), merged,
                                f"fallback:{fmt.provider}"))
                fallback_data[mid] = fmt
            else:
                entries.append((mid, dict(models_dict[mid]), None, "unknown"))
            continue
        chosen = _resolve_match(matches, key, mid)
        if chosen is None:
            entries.append((mid, dict(models_dict[mid]), None, "ambiguous"))
            ambiguous_data[mid] = (key, matches)
            continue
        merged = _merge_model_spec(
            models_dict[mid], build_spec_from_format(chosen, mid), overwrite=False)
        status = "matched" if merged != (models_dict[mid] or {}) else "unchanged"
        entries.append((mid, dict(models_dict[mid]), merged, status))
    return entries, ambiguous_data, fallback_data


# Providers tab
class ProvidersTab(QWidget):
    """Providers tab: search, inline edits, soft delete via the trash file."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.rows = []  # live rows only: (provider_key, npm_edit, name_edit)

        layout = QVBoxLayout(self)

        # Search and buttons
        top_layout = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search providers...")
        self.search_edit.textChanged.connect(self._filter_providers)
        top_layout.addWidget(self.search_edit)

        self.show_trash_chk = QCheckBox("Show deleted")
        self.show_trash_chk.setToolTip(f"Removed providers are kept in {PROVIDER_TRASH_FILE}")
        self.show_trash_chk.toggled.connect(lambda _: self._update_table())
        top_layout.addWidget(self.show_trash_chk)

        for text, slot in [
            ("+ Add", self._add_provider),
            ("+ Fetch from API", self._fetch_new_provider),
            ("⚡ Health Check", self._health_check_providers),
            ("Import", self._import_providers),
            ("Export", self._export_providers),
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
        # Editing a live row's key cell renames the provider immediately.
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        # Status
        self.status_label = QLabel()
        layout.addWidget(self.status_label)

    # --- data helpers ---
    def _providers(self) -> dict:
        return section(self.app.cfg.data, "provider") if self.app.cfg else {}

    def _cfg_path(self):
        """Path of the loaded config file; None (no file) means no trash."""
        return getattr(self.app.cfg, "path", None)

    def _trashed(self) -> dict:
        """Trash entries of this config file whose key is not a live provider.
        Derived, so undoing a remove hides its entry again."""
        path = self._cfg_path()
        if path is None:
            return {}
        live = self._providers()
        return {k: v for k, v in ProviderTrashStore().entries(path).items() if k not in live}

    @staticmethod
    def _matches(key, cfg, text: str) -> bool:
        if not text:
            return True
        if text in key.lower():
            return True
        if not isinstance(cfg, dict):
            return False
        return any(isinstance(cfg.get(f), str) and text in cfg[f].lower()
                   for f in ("npm", "name"))

    @staticmethod
    def _summary(cfg) -> str:
        cfg = cfg if isinstance(cfg, dict) else {}
        n_models = len(cfg["models"]) if isinstance(cfg.get("models"), dict) else 0
        base_url = cfg["options"].get("baseURL", "") if isinstance(cfg.get("options"), dict) else ""
        return f"{n_models} models  {base_url}"

    def _filter_providers(self, text: str = ""):
        """Filter providers by search text (the table reads the search box)."""
        self._update_table()

    def _update_table(self):
        """Rebuild the table: live rows (search-filtered) first, then the
        deleted ones when "Show deleted" is checked."""
        text = self.search_edit.text().lower()
        providers = self._providers()
        trashed = self._trashed()
        live = [(k, v) for k, v in sorted(providers.items()) if self._matches(k, v, text)]
        dead = ([(k, v) for k, v in sorted(trashed.items()) if self._matches(k, v, text)]
                if self.show_trash_chk.isChecked() else [])

        prev = self.table.blockSignals(True)   # a rebuild is never an edit
        try:
            self.rows = []
            self.table.setRowCount(0)
            self.table.setRowCount(len(live) + len(dead))
            for row, (key, cfg) in enumerate(live):
                self._fill_live_row(row, key, cfg)
            for row, (key, entry) in enumerate(dead, start=len(live)):
                self._fill_trash_row(row, key, entry)
        finally:
            self.table.blockSignals(prev)
        self._update_status(len(providers), len(trashed))

    def _update_status(self, n_live=None, n_trashed=None):
        n_live = len(self._providers()) if n_live is None else n_live
        n_trashed = len(self._trashed()) if n_trashed is None else n_trashed
        text = f"{n_live} providers"
        if n_trashed:
            text += f" · {n_trashed} deleted"
        self.status_label.setText(text)

    def _fill_live_row(self, row, key, cfg):
        valid = isinstance(cfg, dict)   # non-dict entries are fixed in Raw JSON
        cfg = cfg if valid else {}
        self.table.setItem(row, 0, QTableWidgetItem(key))

        npm_edit = MaskedLineEdit(cfg.get("npm", ""), field_name="npm")
        npm_edit.edit.editingFinished.connect(
            lambda r=row, w=npm_edit: self._commit_inline(r, "npm", w))
        npm_edit.setEnabled(valid)
        self.table.setCellWidget(row, 1, npm_edit)

        name_edit = MaskedLineEdit(cfg.get("name", ""), field_name="name")
        name_edit.edit.editingFinished.connect(
            lambda r=row, w=name_edit: self._commit_inline(r, "name", w))
        name_edit.setEnabled(valid)
        self.table.setCellWidget(row, 2, name_edit)

        cell = QWidget()
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(2, 0, 2, 0)
        summary = QLabel(self._summary(cfg))
        summary.setToolTip(self._tooltip_json(cfg))
        cell_layout.addWidget(summary, 1)
        # Buttons resolve the key at click time: the key cell renames in place.
        for text, slot in (("Models...", self._edit_models), ("Options...", self._edit_options)):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, r=row, s=slot: s(self._row_key(r)))
            btn.setEnabled(valid)
            cell_layout.addWidget(btn)
        self.table.setCellWidget(row, 3, cell)

        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        for text, slot in (("Edit", self._edit_provider), ("Remove", self._remove_provider)):
            btn = QPushButton(text)
            btn.setFixedWidth(60)
            btn.clicked.connect(lambda _, r=row, s=slot: s(self._row_key(r)))
            actions_layout.addWidget(btn)
        self.table.setCellWidget(row, 4, actions_widget)

        self.rows.append((key, npm_edit, name_edit))

    @staticmethod
    def _tooltip_json(cfg):
        """Provider JSON for the summary tooltip, with the API key masked."""
        if not isinstance(cfg, dict):
            return ""
        shown = dict(cfg)
        options = shown.get("options")
        if isinstance(options, dict) and options.get("apiKey"):
            options = dict(options)
            options["apiKey"] = _mask(str(options["apiKey"]))
            shown["options"] = options
        return json.dumps(shown, ensure_ascii=False, indent=2)[:4000]

    def _fill_trash_row(self, row, key, entry):
        """Display-only row for a deleted provider: Restore / Delete permanently."""
        cfg = entry if isinstance(entry, dict) else {}
        for col, text in enumerate((key, cfg.get("npm", ""), cfg.get("name", ""),
                                    self._summary(cfg))):
            item = QTableWidgetItem(str(text))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
            item.setForeground(Qt.gray)
            self.table.setItem(row, col, item)

        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        restore_btn = QPushButton("Restore")
        restore_btn.clicked.connect(lambda _, k=key: self._restore_provider(k))
        actions_layout.addWidget(restore_btn)
        purge_btn = QPushButton("Delete permanently")
        purge_btn.clicked.connect(lambda _, k=key: self._hard_delete_provider(k))
        actions_layout.addWidget(purge_btn)
        self.table.setCellWidget(row, 4, actions_widget)

    def _row_key(self, row):
        return self.rows[row][0] if 0 <= row < len(self.rows) else None

    def _row_of(self, key):
        return next((i for i, r in enumerate(self.rows) if r[0] == key), None)

    def _set_key_cell(self, item, text):
        prev = self.table.blockSignals(True)
        item.setText(text)
        self.table.blockSignals(prev)

    def _on_item_changed(self, item):
        """Write-through rename from a live row's key cell."""
        row = item.row()
        if item.column() != 0 or not 0 <= row < len(self.rows):
            return  # deleted rows are display-only and never collected
        old = self.rows[row][0]
        new = item.text().strip()
        if new == old:
            if item.text() != old:
                self._set_key_cell(item, old)
            return
        providers = self._providers()
        if old not in providers:
            self._set_key_cell(item, old)
            return
        if not new or new in providers:
            self._set_key_cell(item, old)
            QMessageBox.warning(self, "Rename Provider",
                                "Provider key cannot be empty" if not new
                                else f"Provider '{new}' already exists")
            return
        self.app.snapshot_state()
        providers[new] = providers.pop(old)
        self.rows[row] = (new,) + tuple(self.rows[row][1:])
        if item.text() != new:
            self._set_key_cell(item, new)
        self.app.mark_dirty()
        self._update_status()

    _FIELD_COL = {"npm": 1, "name": 2}

    def _commit_inline(self, row, field, widget):
        """Write-through for the npm/name cells so a table rebuild (search,
        dialogs, Show deleted, ...) never drops an inline edit."""
        if not 0 <= row < len(self.rows) or self.rows[row][self._FIELD_COL[field]] is not widget:
            return  # stale widget from a previous rebuild
        prov = self._providers().get(self.rows[row][0])
        if not isinstance(prov, dict):
            return
        value = widget.value()
        if not self._differs(prov, field, value):
            return
        self.app.snapshot_state()
        self._apply_field(prov, field, value)
        self.app.mark_dirty()

    @staticmethod
    def _differs(prov: dict, field: str, value: str) -> bool:
        cur = prov.get(field)
        return value != ("" if cur is None else str(cur))

    @staticmethod
    def _apply_field(prov: dict, field: str, value: str):
        """Set the field, or drop it when empty (never writes "npm": "")."""
        if value:
            prov[field] = value
        else:
            prov.pop(field, None)

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

    def _edit_provider(self, name: str):
        """Rename a provider via a dialog."""
        self.app.snapshot_state()
        providers = self._providers()
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

    def _remove_provider(self, name: str):
        """Soft delete: move the provider into the trash file, then drop it from
        the config. It leaves the config file on the next Save."""
        providers = self._providers()
        if name not in providers:
            QMessageBox.warning(self, "Error", f"Provider '{name}' not found")
            self.refresh()
            return
        if not _confirm(self, "Remove Provider",
                        f"Remove provider '{name}'?\n\n"
                        "It can be restored via \"Show deleted\"."):
            return

        entry = copy.deepcopy(providers[name])
        row = self._row_of(name)
        if isinstance(entry, dict) and row is not None:
            # Include inline edits that haven't been committed yet.
            for fld, widget in zip(("npm", "name"), self.rows[row][1:]):
                if self._differs(entry, fld, widget.value()):
                    self._apply_field(entry, fld, widget.value())
        path = self._cfg_path()
        try:
            if path is None:
                raise OSError("no config file is loaded")
            ProviderTrashStore().put(path, name, entry)
        except (OSError, TypeError, ValueError) as e:
            QMessageBox.critical(self, "Remove Provider",
                                 f"Could not save '{name}' to the trash file, "
                                 f"nothing was removed:\n{e}")
            return

        self.app.snapshot_state()
        providers.pop(name, None)
        self.app.mark_dirty()
        self.refresh()

    def _restore_provider(self, name: str):
        """Copy a deleted provider back into the config. The trash entry stays
        until a successful save prunes it, so restore-then-discard loses nothing."""
        path = self._cfg_path()
        entry = ProviderTrashStore().entries(path).get(name) if path is not None else None
        if entry is None:
            QMessageBox.warning(self, "Restore Provider",
                                f"'{name}' is no longer in the trash file")
            self.refresh()
            return
        providers = self.app.cfg.data.setdefault("provider", {})
        if not isinstance(providers, dict):
            QMessageBox.warning(self, "Restore Provider",
                                "The config's 'provider' value is not an object; fix it in Raw JSON")
            return
        if name in providers:
            QMessageBox.warning(self, "Restore Provider",
                                f"Provider '{name}' already exists; rename or remove it first")
            return
        self.app.snapshot_state()
        providers[name] = entry
        self.app.mark_dirty()
        self.refresh()

    def _hard_delete_provider(self, name: str):
        """Permanently drop a deleted provider from the trash file."""
        path = self._cfg_path()
        if path is None:
            return
        if not _confirm(self, "Delete Permanently",
                        f"Permanently delete provider '{name}' from the trash?\n\n"
                        "This cannot be undone."):
            return
        try:
            ProviderTrashStore().discard(path, name)
        except OSError as e:
            QMessageBox.critical(self, "Delete Permanently", str(e))
            return
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

    def _fetch_new_provider(self):
        """Add a NEW provider by fetching its model list from an API, then
        auto-match the fetched models against the catalog.

        Updating an existing provider's models lives in that provider's
        Models... dialog ("Fetch from API"); this toolbar entry is for
        bringing in a provider that isn't in the config yet (the provider
        key is editable in the dialog).
        """
        self.app.snapshot_state()

        # Fill the dialog's reference-provider combo (silently loads bundled catalog).
        try_load_bundled_catalog(self.app.model_catalog)
        providers = self.app.cfg.data.setdefault("provider", {})
        dlg = FetchProviderModelsDialog(self, catalog=self.app.model_catalog,
                                        providers=providers)
        if dlg.exec() != QDialog.Accepted:
            return

        key = dlg.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Fetch", "Provider key cannot be empty.")
            return

        selected = dlg.selected_models
        if not selected:
            QMessageBox.information(self, "Fetch", "No models selected.")
            return

        reference = dlg.reference_provider

        existing_cfg = providers.get(key)
        existing_models = {}
        if isinstance(existing_cfg, dict) and isinstance(existing_cfg.get("models"), dict):
            existing_models = existing_cfg["models"]

        # api_base_url() is format-aware: a list/catalog fetch stored the raw
        # listing URL as options.baseURL, which is not a usable API endpoint.
        base_url = dlg.api_base_url()
        prov, summary = apply_fetched_provider(
            providers, key, selected,
            base_url=base_url,
            api_key=dlg.apikey_edit.text().strip(),
            save_api_key=dlg.save_apikey_check.isChecked(),
            npm=npm_for_fetch(dlg._current_adapter(), dlg.url_edit.text().strip()))

        removed = []
        if dlg.sync_check.isChecked():
            stale = stale_configured_models(existing_models, dlg.fetched_models)
            if stale:
                shown = ", ".join(stale[:8])
                if len(stale) > 8:
                    shown += f", ... (+{len(stale) - 8} more)"
                if _confirm(self, "Sync Models",
                            f"Remove {len(stale)} configured model(s) the API no "
                            f"longer lists?\n{shown}"):
                    for mid in stale:
                        prov["models"].pop(mid, None)
                    removed = stale

        self.app.mark_dirty()
        self._update_table()

        # Auto-match against the catalog in ONE review dialog (no per-model prompts).
        if not self.app.model_catalog.loaded():
            if not self.app._ensure_catalog():
                QMessageBox.information(
                    self, "Fetch Complete",
                    f"'{key}': added {len(summary['added'])} new model(s), "
                    f"kept {len(summary['kept'])} configured. "
                    "Catalog not loaded, skipped auto-match.")
                return

        catalog = self.app.model_catalog
        settings = SettingsManager()
        mappings = settings.get_reference_mappings()
        entries = []       # (model_id, old_spec, new_spec|None, status)
        ambiguous_data = {}
        fallback_data = {}  # {model_id: ModelFormat}

        for mid in sorted(prov["models"]):
            matches = catalog.find_model(mid)
            if not matches:
                fmt = None
                # 1. Previously persisted manual/auto mapping wins.
                saved = mappings.get(f"{key}/{mid}")
                if saved:
                    saved_matches = catalog.find_model(saved)
                    if saved_matches:
                        fmt = _sort_matches(saved_matches, reference or key)[0]
                # 2. Reference provider / normalized-id / prefix fallback.
                if fmt is None:
                    fmt = _find_fallback(mid, reference, catalog)
                if fmt is not None:
                    merged = _merge_model_spec(
                        prov["models"][mid], build_spec_from_format(fmt, mid), overwrite=False)
                    entries.append((mid, dict(prov["models"][mid]), merged,
                                    f"fallback:{fmt.provider}"))
                    fallback_data[mid] = fmt
                else:
                    entries.append((mid, dict(prov["models"][mid]), None, "unknown"))
                continue
            chosen = _resolve_match(matches, key, mid)
            if chosen is None:
                entries.append((mid, dict(prov["models"][mid]), None, "ambiguous"))
                ambiguous_data[mid] = (key, matches)
                continue
            merged = _merge_model_spec(
                prov["models"][mid], build_spec_from_format(chosen, mid), overwrite=False)
            status = "matched" if merged != (prov["models"][mid] or {}) else "unchanged"
            entries.append((mid, dict(prov["models"][mid]), merged, status))

        if not any(e[2] is not None or e[3] == "ambiguous" for e in entries):
            QMessageBox.information(
                self, "Fetch & Match",
                f"'{key}': added {len(summary['added'])} new model(s), "
                f"kept {len(summary['kept'])} configured. "
                "None matched the catalog.")
            return

        preview = MatchFormatPreviewDialog(
            self, entries, ambiguous_data, fallback_data=fallback_data, catalog=catalog)
        if preview.exec() != QDialog.Accepted:
            return

        applied = 0
        for mid, old_spec, new_spec, status in preview.selected_entries:
            if status == "ambiguous":
                new_spec = preview.resolved_specs.get(mid, new_spec)
            elif status == "mapped":
                new_spec = preview.mapped_specs.get(mid, new_spec)
                if mid in preview.mapped_ids:
                    settings.add_reference_mapping(key, mid, preview.mapped_ids[mid])
            elif status.startswith("fallback:"):
                fmt = fallback_data.get(mid)
                if fmt is not None:
                    settings.add_reference_mapping(key, mid, fmt.model_id)
            if new_spec is None:
                continue
            prov["models"][mid] = _merge_model_spec(
                prov["models"][mid], new_spec, overwrite=False)
            applied += 1

        self.app.mark_dirty()
        self._update_table()
        sync_note = f", removed {len(removed)} stale" if removed else ""
        QMessageBox.information(
            self, "Fetch & Match Complete",
            f"'{key}': added {len(summary['added'])} new model(s), "
            f"kept {len(summary['kept'])} configured{sync_note}, "
            f"normalized {applied} from catalog."
        )

    def _export_providers(self):
        """Export providers to JSON file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Providers", "providers.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        providers = section(self.app.cfg.data, "provider")
        if not providers:
            QMessageBox.information(self, "Export", "No providers to export")
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(providers, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _edit_models(self, name: str):
        """Edit models for provider"""
        self.app.snapshot_state()
        providers = section(self.app.cfg.data, "provider")
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
        providers = section(self.app.cfg.data, "provider")
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

    def _health_check_providers(self):
        """Run connectivity and health check for configured providers"""
        providers = section(self.app.cfg.data, "provider") if self.app.cfg else {}
        # Project-scoped {file:...} API keys resolve against the config's dir.
        cfg_path = str(self.app.cfg.path) if self.app.cfg else ""
        dlg = ProviderHealthCheckDialog(self, providers=providers, config_path=cfg_path)
        dlg.exec()

    def collect(self, data: dict):
        """Apply npm/name edits still pending in a focused cell (e.g. Save via
        shortcut). Committed edits and renames already live in cfg.data
        (write-through), so untouched fields keep whatever `data` holds (incl.
        Raw JSON edits) and providers missing from `data` are never recreated."""
        providers = data.get("provider")
        if not isinstance(providers, dict):
            return
        cfg_providers = self._providers()
        for key, npm_edit, name_edit in self.rows:
            prov = providers.get(key)
            if not isinstance(prov, dict):
                continue    # removed (e.g. in Raw JSON) or malformed: never resurrect
            base = cfg_providers.get(key)
            base = base if isinstance(base, dict) else {}
            for fld, widget in (("npm", npm_edit), ("name", name_edit)):
                if self._differs(base, fld, widget.value()):
                    self._apply_field(prov, fld, widget.value())
# MCP servers tab

def _mcp_matches(cfg, text: str) -> bool:
    """Search-text match over a server entry; non-dict entries never match."""
    if not isinstance(cfg, dict):
        return False
    if text in str(cfg.get("type", "")).lower():
        return True
    if text in str(cfg.get("url", "")).lower():
        return True
    if isinstance(cfg.get("command"), list):
        return any(text in str(c).lower() for c in cfg["command"])
    return False

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
        item = QTableWidgetItem(_mask(str(value)) if value else "")
        # The real value lives in UserRole so it can round-trip unedited.
        item.setData(Qt.UserRole, str(value))
        self.table.setItem(r, 1, item)

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
            if not n:
                continue
            if value is None:
                out[n] = ""
                continue
            # An untouched cell still shows the mask; take the stored secret.
            # Once the user types (or clears), the text is what they meant.
            shown = value.text()
            real = str(value.data(Qt.UserRole) or "")
            out[n] = real if shown == _mask(real) else shown
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
            ("🧩 Hub / Templates", self._open_mcp_hub),
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
            self._update_table()
            return

        text = text.lower()
        mcp = self.app.cfg.data.get("mcp", {}) if self.app.cfg else {}
        filtered = {
            name: cfg for name, cfg in mcp.items()
            if text in name.lower() or _mcp_matches(cfg, text)
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

            # Name / Type are not round-trippable from the table (the key is
            # the map key, and type decides the entry's shape), so read-only.
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, name_item)

            type_item = QTableWidgetItem(str(cfg.get("type", "")))
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, type_item)

            # Command/URL. Local commands are argv lists, and shlex.split
            # round-trips exactly what the join displayed.
            if cfg.get("type") == "local":
                cmd = " ".join(cfg.get("command", []))
            else:
                cmd = cfg.get("url", "")
            self.table.setItem(row, 3, QTableWidgetItem(str(cmd or "")))

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
        """Refresh the table, keeping the active search filter applied."""
        self._filter_servers(self.search_edit.text())

    def _visible_names(self) -> dict:
        """{name: cfg} for the rows currently shown in the table."""
        mcp = (self.app.cfg.data.get("mcp", {}) if self.app.cfg else {})
        return {
            name: mcp[name] for name in
            (self.table.item(r, 1).text() for r in range(self.table.rowCount()))
            if name in mcp
        }

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

        # Headers only exist on type=remote entries; a type-less toggle entry
        # ({enabled: false}) matches no schema branch once headers are added.
        if cfg.get("type") != "remote":
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
        """Enable/disable every dict entry (non-dict entries are left alone)"""
        self.app.snapshot_state()
        mcp = self.app.cfg.data.get("mcp", {})
        changed = False
        for name in mcp:
            if isinstance(mcp[name], dict):
                mcp[name]["enabled"] = enabled
                changed = True
        if changed:
            self.app.mark_dirty()
        self.refresh()

    def _toggle_enabled(self, name: str):
        """Toggle enabled state for server"""
        mcp = self.app.cfg.data.get("mcp", {})
        cfg = mcp.get(name)
        if isinstance(cfg, dict) and name in self.cbs:
            self.app.snapshot_state()
            cfg["enabled"] = self.cbs[name].isChecked()
            self.app.mark_dirty()


    def _open_mcp_hub(self):
        """Open MCP Template Hub to install curated MCP servers"""
        dlg = MCPTemplateHubDialog(self, target_mode="opencode")
        if dlg.exec() == QDialog.Accepted:
            key = dlg.result_server_key
            cfg = dlg.result_server_config
            if not key or not cfg:
                return
            mcp = self.app.cfg.data.setdefault("mcp", {})
            if key in mcp:
                if not _confirm(self, "Overwrite Server", f"Server '{key}' already exists. Overwrite?"):
                    return
            self.app.snapshot_state()
            mcp[key] = cfg
            self.app.mark_dirty()
            self.refresh()
            QMessageBox.information(self, "Installed", f"MCP server '{key}' installed successfully.")

    def collect(self, data: dict):
        """Write the Command/URL column back into cfg.data['mcp'].

        Name and Type are read-only in the table, so only column 3 can carry
        an edit. Remote entries take the cell text as their url; local entries
        are re-split with shlex so what was displayed round-trips.
        """
        mcp = self.app.cfg.data.get("mcp", {})
        changed = False
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, 1)
            cell = self.table.item(r, 3)
            if name_item is None or cell is None:
                continue
            name = name_item.text()
            cfg = mcp.get(name)
            if not isinstance(cfg, dict):
                continue
            text = cell.text().strip()
            if cfg.get("type") == "local":
                new = shlex.split(text) if text else []
                if cfg.get("command") != new:
                    cfg["command"] = new
                    changed = True
            elif cfg.get("url", "") != text:
                cfg["url"] = text
                changed = True
        if changed:
            self.app.snapshot_state()
            self.app.mark_dirty()

# Plugins tab
def _name_of_plugin(entry) -> str:
    """Extract plugin name/specifier from string or [name, options] tuple."""
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, (list, tuple)) and entry and isinstance(entry[0], str):
        return entry[0].strip()
    return ""


def _opts_of_plugin(entry) -> Optional[dict]:
    """Extract options dict from [name, options] tuple, if any."""
    if isinstance(entry, (list, tuple)) and len(entry) >= 2 and isinstance(entry[1], dict):
        return entry[1]
    return None


def _format_opts_summary(opts: Optional[dict]) -> str:
    """Format short summary of options for table display."""
    if not opts:
        return ""
    try:
        s = json.dumps(opts, ensure_ascii=False)
        return s if len(s) <= 45 else s[:42] + "..."
    except Exception:
        return "(options)"


class PluginsTab(QWidget):
    """Enhanced plugins tab with search, options configuration, and bulk operations."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.state_store = PluginStateStore()
        self.cbs = {}  # name -> QCheckBox
        self._entries = {}  # name -> full_entry (str or [name, opts])
        # Names removed from the table since the last Save. The store is only
        # rewritten by collect(), so Undo/Reload still restore these entries.
        self._removed = set()
        self._visible_cbs = {}  # name -> checkbox for rows currently in the table
        # name -> bool, the user's in-session choice. Repopulating the table
        # (e.g. clearing a filter) must not lose an unsaved toggle.
        self._checked = {}

        layout = QVBoxLayout(self)

        # Search and buttons
        top_layout = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search plugins or options...")
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
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Enabled", "Plugin", "Options", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table)

        # Status
        self.status_label = QLabel(
            "Disabled plugins are removed from the saved config but remembered in cache "
            "with their options intact so you can re-enable them later."
        )
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

    def _get_raw_plugins(self) -> list:
        """Get plugin list from config data."""
        plugins = self.app.cfg.data.get("plugin", []) if self.app.cfg else []
        return plugins if isinstance(plugins, list) else []

    def _display_entries(self) -> List[Any]:
        """Combine active plugins from config and remembered-disabled ones."""
        active = self._get_raw_plugins()
        seen_names = set()
        entries = []

        # 1) Add active config entries
        for e in active:
            name = _name_of_plugin(e)
            if name and name not in seen_names:
                seen_names.add(name)
                entries.append(e)

        # 2) Add remembered disabled entries from state store
        if self.app.cfg:
            disabled_entries = self.state_store.get_entries(self.app.cfg.path)
            for name, entry in sorted(disabled_entries.items()):
                if name not in seen_names and name not in self._removed:
                    seen_names.add(name)
                    entries.append(entry)

        return entries

    def _active_names(self) -> set:
        """Names currently present in the config's plugin[] list."""
        return {_name_of_plugin(e) for e in self._get_raw_plugins()} - {""}

    def _disabled_names(self) -> set:
        """Remembered-disabled names that are not enabled in the config.

        A plugin listed in `plugin[]` wins over any store entry (which may come
        from a stale legacy file), so migrating old state can never silently
        re-disable a plugin the user has since re-enabled."""
        disabled = self.state_store.get_disabled(self.app.cfg.path) if self.app.cfg else set()
        return set(disabled) - self._active_names() - self._removed

    def _filter_plugins(self, text: str):
        """Filter plugins by search text matching name or options."""
        if not text:
            self.refresh()
            return

        text = text.lower()
        all_entries = self._display_entries()
        disabled_names = self._disabled_names()

        filtered = []
        for e in all_entries:
            name = _name_of_plugin(e)
            opts = _opts_of_plugin(e)
            opts_str = json.dumps(opts, ensure_ascii=False).lower() if opts else ""
            if text in name.lower() or text in opts_str:
                filtered.append((e, name not in disabled_names))

        self._populate_table(filtered)

    def _update_table(self):
        """Update table with full current entries list."""
        all_entries = self._display_entries()
        disabled_names = self._disabled_names()
        pairs = [(e, _name_of_plugin(e) not in disabled_names) for e in all_entries]
        self._populate_table(pairs)

    def _populate_table(self, pairs: List[Tuple[Any, bool]]):
        """Populate table widget rows. `_entries` keeps every known plugin, so a
        filtered-out row is still collected on Save."""
        self.table.blockSignals(True)
        self.table.setRowCount(len(pairs))
        new_cbs = {}

        for row, (entry, enabled) in enumerate(pairs):
            name = _name_of_plugin(entry)
            opts = _opts_of_plugin(entry)
            self._entries[name] = entry
            enabled = self._checked.get(name, enabled)

            # Col 0: Enabled checkbox
            cb = QCheckBox()
            cb.setChecked(enabled)
            cb.stateChanged.connect(
                lambda _state, n=name, box=cb: self._checked.__setitem__(n, box.isChecked()))
            self._checked.setdefault(name, enabled)
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setAlignment(Qt.AlignCenter)
            cell_layout.addWidget(cb)
            self.table.setCellWidget(row, 0, cell)
            new_cbs[name] = cb

            # Col 1: Plugin name
            name_item = QTableWidgetItem(name)
            self.table.setItem(row, 1, name_item)

            # Col 2: Options summary
            opts_item = QTableWidgetItem(_format_opts_summary(opts))
            if opts:
                opts_item.setToolTip(json.dumps(opts, indent=2, ensure_ascii=False))
            self.table.setItem(row, 2, opts_item)

            # Col 3: Configure Options button
            cfg_btn = QPushButton("⚙ Options")
            cfg_btn.clicked.connect(lambda _, n=name: self._configure_plugin(n))
            self.table.setCellWidget(row, 3, cfg_btn)

        # Only the visible rows get fresh checkboxes; hidden rows keep the
        # checkbox object (and its checked state) from before the filter.
        merged = {n: cb for n, cb in self.cbs.items() if n not in new_cbs}
        merged.update(new_cbs)
        self.cbs = merged
        self._visible_cbs = new_cbs


        self.table.blockSignals(False)
        self._update_status()

    def _update_status(self):
        total = self.table.rowCount()
        en = sum(1 for cb in self._visible_cbs.values() if cb.isChecked())
        self.status_label.setText(
            f"{total} plugins ({en} enabled). Disabled plugins are remembered in cache with options intact."
        )

    def refresh(self):
        """Refresh table with current data. Staged removals are dropped, so
        Undo/Reload brings a removed plugin back from the state store."""
        self._removed.clear()
        self._update_table()

    def _on_double_click(self, row: int, col: int):
        """Open options config dialog on row double click."""
        name_item = self.table.item(row, 1)
        if name_item:
            self._configure_plugin(name_item.text())

    def _configure_plugin(self, name: str):
        """Open dialog to edit plugin options."""
        entry = self._entries.get(name, name)
        current_opts = _opts_of_plugin(entry)

        dlg = PluginOptionsDialog(self, name, current_opts)
        if dlg.exec() != QDialog.Accepted:
            return

        self.app.snapshot_state()
        new_opts = dlg.result_options
        if new_opts:
            self._entries[name] = [name, new_opts]
        else:
            self._entries[name] = name

        # Update table row summary
        row = self._find_plugin_row(name)
        if row >= 0:
            opts_item = QTableWidgetItem(_format_opts_summary(new_opts))
            if new_opts:
                opts_item.setToolTip(json.dumps(new_opts, indent=2, ensure_ascii=False))
            self.table.setItem(row, 2, opts_item)

        self.app.mark_dirty()

    def _add_plugin(self):
        """Add new plugin with optional initial options."""
        dlg = AddPluginDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        name = dlg.plugin_name
        if not name:
            return

        if name in self.cbs:
            QMessageBox.warning(self, "Error", f"Plugin '{name}' already exists")
            return

        self.app.snapshot_state()
        opts = dlg.plugin_options
        entry = [name, opts] if opts else name
        self._entries[name] = entry

        # Insert row
        row = self.table.rowCount()
        self.table.insertRow(row)

        cb = QCheckBox()
        cb.setChecked(True)
        cb.stateChanged.connect(self.app.mark_dirty)
        cell = QWidget()
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.setAlignment(Qt.AlignCenter)
        cell_layout.addWidget(cb)
        self.table.setCellWidget(row, 0, cell)
        self.cbs[name] = cb
        self._visible_cbs[name] = cb

        self.table.setItem(row, 1, QTableWidgetItem(name))
        opts_item = QTableWidgetItem(_format_opts_summary(opts))
        if opts:
            opts_item.setToolTip(json.dumps(opts, indent=2, ensure_ascii=False))
        self.table.setItem(row, 2, opts_item)

        cfg_btn = QPushButton("⚙ Options")
        cfg_btn.clicked.connect(lambda _, n=name: self._configure_plugin(n))
        self.table.setCellWidget(row, 3, cfg_btn)

        self.app.mark_dirty()
        self._update_status()

    def _import_plugins(self):
        """Import plugins from JSON."""
        self.app.snapshot_state()
        dlg = JsonImportDialog(
            self, "Import Plugins",
            "Paste or load plugins JSON. Supported formats:\n"
            "- Array of plugins: [\"pkg\", [\"pkg-with-opts\", {\"lang\": \"en\"}]]\n"
            "- Object containing 'plugin': {'plugin': [...]}"
        )
        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.result_data
        if isinstance(data, dict) and "plugin" in data:
            data = data["plugin"]

        if not isinstance(data, list):
            QMessageBox.warning(self, "Import Error", "Expected a JSON array of plugins")
            return

        added = 0
        for item in data:
            name = _name_of_plugin(item)
            if name and name not in self.cbs:
                opts = _opts_of_plugin(item)
                entry = [name, opts] if opts else name
                self._entries[name] = entry

                row = self.table.rowCount()
                self.table.insertRow(row)

                cb = QCheckBox()
                cb.setChecked(True)
                cb.stateChanged.connect(self.app.mark_dirty)
                cell = QWidget()
                cell_layout = QHBoxLayout(cell)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setAlignment(Qt.AlignCenter)
                cell_layout.addWidget(cb)
                self.table.setCellWidget(row, 0, cell)
                self.cbs[name] = cb
                self._visible_cbs[name] = cb

                self.table.setItem(row, 1, QTableWidgetItem(name))
                opts_item = QTableWidgetItem(_format_opts_summary(opts))
                if opts:
                    opts_item.setToolTip(json.dumps(opts, indent=2, ensure_ascii=False))
                self.table.setItem(row, 2, opts_item)

                cfg_btn = QPushButton("⚙ Options")
                cfg_btn.clicked.connect(lambda _, n=name: self._configure_plugin(n))
                self.table.setCellWidget(row, 3, cfg_btn)

                added += 1

        self.app.mark_dirty()
        self._update_status()
        QMessageBox.information(self, "Import Complete", f"Added {added} new plugins")

    def _export_plugins(self):
        """Export plugins to JSON file preserving options."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Plugins", "plugins.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return

        active_entries = []
        for name, cb in self.cbs.items():
            if cb.isChecked():
                active_entries.append(self._entries.get(name, name))

        if not active_entries:
            QMessageBox.information(self, "Export", "No enabled plugins to export")
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(active_entries, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Export Complete", f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _set_all_enabled(self, enabled: bool):
        """Enable/disable all plugins, including any hidden by a filter."""
        self.app.snapshot_state()
        for name, cb in self.cbs.items():
            cb.setChecked(enabled)
            self._checked[name] = enabled
        self.app.mark_dirty()
        self._update_status()

    def _remove_selected(self):
        """Remove selected plugins."""
        self.app.snapshot_state()
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Remove", "Please select plugins to remove")
            return

        names = {
            self.table.item(item.row(), 1).text()
            for item in selected if self.table.item(item.row(), 1) is not None
        }
        if not names:
            return

        if not _confirm(self, "Remove Plugins", f"Remove {len(names)} selected plugin(s)?"):
            return

        for name in names:
            row = self._find_plugin_row(name)
            if row >= 0:
                self.table.removeRow(row)
            self.cbs.pop(name, None)
            self._entries.pop(name, None)
            self._visible_cbs.pop(name, None)
            self._checked.pop(name, None)
            self._removed.add(name)

        self.app.mark_dirty()
        self._update_status()

    def _find_plugin_row(self, plugin_name: str) -> int:
        """Find row index for plugin name."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and item.text() == plugin_name:
                return row
        return -1

    def collect(self, data: dict):
        """Collect data from UI into config dict, preserving options tuples.

        The table only ever holds the rows a search filter left visible, so the
        state comes from `_entries` / `_checked` (all known plugins), never from
        the visible `cbs`.
        """
        disabled_names = self._disabled_names()
        active = []
        disabled_dict = {}

        for name, entry in self._entries.items():
            if name in self._removed:
                continue
            if self._checked.get(name, True) and name not in disabled_names:
                active.append(entry)
            else:
                disabled_dict[name] = entry

        data["plugin"] = active
        if self.app.cfg:
            self.state_store.set_disabled(self.app.cfg.path, disabled_dict)
        self._removed.clear()


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
# Runtime tab and its small editor widgets
class StringListEdit(QWidget):
    """Editable list of strings backed by a nested key path in the config."""

    def __init__(self, app, data_path, placeholder="item", on_change=None):
        super().__init__()
        self.app = app
        self.data_path = data_path  # e.g. ["disabled_providers"]
        self.placeholder = placeholder
        self.on_change = on_change

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

    def _changed(self):
        if self.on_change is not None:
            self.on_change()
        self.app.mark_dirty()

    def _add(self):
        text, ok = QInputDialog.getText(self, "Add", f"New {self.placeholder}:")
        if ok and text.strip():
            self.list.addItem(text.strip())
            self._changed()

    def _remove(self):
        rows = sorted({self.list.row(it) for it in self.list.selectedItems()}, reverse=True)
        for r in rows:
            self.list.takeItem(r)
        if rows:
            self._changed()


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

    def __init__(self, app, data_path, on_change=None):
        super().__init__()
        self.app = app
        self.data_path = data_path
        self.on_change = on_change
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

    def _changed(self, *_):
        if self.on_change is not None:
            self.on_change()
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
            self._changed()

    def _remove(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        if rows:
            self._changed()


class RuntimeTab(BaseTab):
    """Server, session, attachment, advanced and experimental settings."""

    def __init__(self, app):
        super().__init__(app)

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
        self.server_cors = self._list(["server", "cors"], "origin", "server")
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
        self.comp_reserved = self._spin(-1, "compaction")
        sform.addRow("Compaction reserved", self.comp_reserved)
        self.comp_tail = self._spin(-1, "compaction")
        sform.addRow("Compaction tail turns", self.comp_tail)
        self.comp_preserve = self._spin(-1, "compaction")
        sform.addRow("Preserve recent tokens", self.comp_preserve)
        self.tool_lines = self._spin(0, "tool_output")
        sform.addRow("Tool output max lines", self.tool_lines)
        self.tool_bytes = self._spin(0, "tool_output")
        sform.addRow("Tool output max bytes", self.tool_bytes)
        lay.addWidget(session_box)

        # ---- Attachment ----
        att_box = QGroupBox("Image attachments")
        aform = QFormLayout(att_box)
        self.att_resize = QCheckBox("Auto-resize oversized images")
        self.att_resize.stateChanged.connect(self._t("attachment"))
        aform.addRow("Auto resize", self.att_resize)
        self.att_w = self._spin(0, "attachment")
        aform.addRow("Max width", self.att_w)
        self.att_h = self._spin(0, "attachment")
        aform.addRow("Max height", self.att_h)
        self.att_bytes = self._spin(0, "attachment")
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
        self.watcher_ignore = self._list(["watcher", "ignore"], "glob", "watcher")
        aform.addRow("Watcher ignore", self.watcher_ignore)
        self.instructions = self._list(["instructions"], "path/glob", "instructions")
        aform.addRow("Instructions", self.instructions)
        self.skills_paths = self._list(["skills", "paths"], "path", "skills")
        aform.addRow("Skill paths", self.skills_paths)
        self.skills_urls = self._list(["skills", "urls"], "url", "skills")
        aform.addRow("Skill URLs", self.skills_urls)
        self.tools = BoolMapEditor(self.app, ["tools"], on_change=self._t("tools"))
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
        self.exp_mcp_timeout = self._spin(0, "experimental")
        eform.addRow("MCP timeout (ms)", self.exp_mcp_timeout)
        self.exp_primary_tools = self._list(
            ["experimental", "primary_tools"], "tool", "experimental")
        eform.addRow("Primary-only tools", self.exp_primary_tools)
        eform.addRow("Policies", self._build_policies_table())
        lay.addWidget(exp_box)
        lay.addStretch(1)

    # --- helpers ---
    def _spin(self, lo=0, group="server"):
        s = QSpinBox()
        s.setRange(lo, 2**31 - 1)
        s.setSpecialValueText("(unset)")
        s.valueChanged.connect(self._t(group))
        return s

    def _list(self, path, placeholder, group):
        return StringListEdit(self.app, path, placeholder, on_change=self._t(group))

    @staticmethod
    def _opt_int(spin):
        """Value of a '(unset)' spinbox: None at the sentinel, else the number.

        Keeps a schema-valid 0 distinct from "not set" (OC-17).
        """
        return None if spin.value() <= spin.minimum() else spin.value()

    def _set_opt_spin(self, spin, val):
        """Populate a '-1 == (unset)' spinbox, keeping a real 0 visible."""
        spin.blockSignals(True)
        ok = isinstance(val, int) and not isinstance(val, bool) and val >= 0
        spin.setValue(val if ok else -1)
        spin.blockSignals(False)

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
        self._set_opt_spin(self.comp_reserved, comp.get("reserved"))
        self._set_opt_spin(self.comp_tail, comp.get("tail_turns"))
        self._set_opt_spin(self.comp_preserve, comp.get("preserve_recent_tokens"))

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
            # collect from the root: data_path is absolute (["server","cors"])
            self.server_cors.collect(data)
            if not srv:
                data.pop("server", None)

        if "compaction" in self._touched:
            comp = data.setdefault("compaction", {})
            self._put(comp, "auto", self.comp_auto.isChecked(), True)
            self._put(comp, "prune", self.comp_prune.isChecked(), False)
            self._put(comp, "reserved", self._opt_int(self.comp_reserved), None)
            self._put(comp, "tail_turns", self._opt_int(self.comp_tail), None)
            self._put(comp, "preserve_recent_tokens", self._opt_int(self.comp_preserve), None)
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

        if "watcher" in self._touched:
            self.watcher_ignore.collect(data)
            # only prune wrappers this branch just created: an untouched
            # {"watcher": {}} must round-trip unchanged.
            if isinstance(data.get("watcher"), dict) and not data["watcher"]:
                data.pop("watcher")
        if "instructions" in self._touched:
            self.instructions.collect(data)
        if "skills" in self._touched:
            self.skills_paths.collect(data)
            self.skills_urls.collect(data)
            if isinstance(data.get("skills"), dict) and not data["skills"]:
                data.pop("skills")
        if "tools" in self._touched:
            self.tools.collect(data)

        if "experimental" in self._touched:
            exp = data.setdefault("experimental", {})
            self._put(exp, "disable_paste_summary", self.exp_disable_paste.isChecked(), False)
            self._put(exp, "batch_tool", self.exp_batch.isChecked(), False)
            self._put(exp, "openTelemetry", self.exp_otel.isChecked(), False)
            self._put(exp, "continue_loop_on_deny", self.exp_loop.isChecked(), False)
            self._put(exp, "mcp_timeout", self.exp_mcp_timeout.value() or None, None)
            self.exp_primary_tools.collect(data)
            pols = []
            for r in range(self.policies.rowCount()):
                eff = self.policies.item(r, 0).text() if self.policies.item(r, 0) else ""
                act = self.policies.item(r, 1).text() if self.policies.item(r, 1) else ""
                res = self.policies.item(r, 2).text() if self.policies.item(r, 2) else ""
                if not (eff and act and res):
                    continue
                if eff not in ("allow", "deny") or act != "provider.use":
                    # Policy requires a valid effect/action; an incomplete row
                    # would make opencode refuse the whole config.
                    QMessageBox.warning(
                        self, "Policies",
                        f"Skipped row {r + 1}: effect must be allow/deny and "
                        "action must be provider.use.",
                    )
                    continue
                pols.append({"effect": eff, "action": act, "resource": res})
            self._put(exp, "policies", pols, [])
            if not exp:
                data.pop("experimental", None)

        self._touched.clear()


# Agents tab
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
        # -1 == '(inherit)': the schema requires steps > 0, so a dialog that
        # was never touched must omit the key rather than write steps: 0.
        self.steps.setRange(0, 10**6)
        self.steps.setSpecialValueText("(inherit)")
        seed_steps = cfg.get("steps", cfg.get("maxSteps"))
        self.steps.setValue(int(seed_steps) if isinstance(seed_steps, int)
                            and not isinstance(seed_steps, bool) and seed_steps > 0 else 0)
        self._steps_set = isinstance(seed_steps, int) and not isinstance(seed_steps, bool) \
            and seed_steps > 0
        form.addRow("Steps", self.steps)
        self.hidden = QCheckBox("Hidden from @ menu")
        self.hidden.setChecked(bool(cfg.get("hidden", False)))
        form.addRow("Hidden", self.hidden)
        self.disable = QCheckBox("Disabled")
        self.disable.setChecked(bool(cfg.get("disable", False)))
        form.addRow("Disable", self.disable)
        self.color_edit = QLineEdit(cfg.get("color", "") or "")
        self.color_edit.setPlaceholderText("#FF5733 or primary")
        form.addRow("Color", self.color_edit)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._try_accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _try_accept(self):
        """Refuse to close on an invalid color so the input is not lost."""
        err = self.color_error()
        if err:
            QMessageBox.warning(self, "Agent", err)
            return
        self.accept()

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
        # 0 means "inherit": emit None so an existing steps value is removed.
        # The schema (exclusiveMinimum: 0) rejects steps: 0.
        out["steps"] = self.steps.value() or None
        return out

    def color_error(self) -> str:
        """Return an error message for an invalid color, or "" when valid."""
        v = self.color_edit.text().strip()
        if not v:
            return ""
        if re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            return ""
        if v in ("primary", "secondary", "accent", "success", "warning", "error", "info"):
            return ""
        return ("Color must be a hex code like #FF5733, or one of: primary, "
                "secondary, accent, success, warning, error, info")


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
        if not dlg.exec():
            return
        err = dlg.color_error()
        if err:
            QMessageBox.warning(self, "Agent", err)
            return
        v = dlg.values()
        name = v.pop("name")
        if not name:
            return
        if name in self._agents():
            QMessageBox.information(
                self, "Agent", f"An agent named '{name}' already exists.\n"
                "Use Edit to change it.")
            return
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
        if not dlg.exec():
            return
        err = dlg.color_error()
        if err:
            QMessageBox.warning(self, "Agent", err)
            return
        v = dlg.values()
        newname = v.pop("name") or name
        if newname != name and newname in self._agents():
            QMessageBox.information(
                self, "Agent", f"An agent named '{newname}' already exists.")
            return
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


# Commands tab
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
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Description", "Agent", "Model", "Actions"])
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
        if not dlg.exec():
            return
        v = dlg.values()
        name = v.pop("name")
        if not name or not v.get("template"):
            return
        if name in self._commands():
            QMessageBox.information(
                self, "Command", f"A command named '{name}' already exists.\n"
                "Use Edit to change it.")
            return
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
        if not dlg.exec():
            return
        v = dlg.values()
        if not v.get("template"):
            return
        newname = v.pop("name") or name
        if newname != name and newname in self._commands():
            QMessageBox.information(
                self, "Command", f"A command named '{newname}' already exists.")
            return
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
        """Move disabled plugins that exist in the `plugin` list into the editor
        cache, and keep every other `plugin_enabled` entry in the file.

        `plugin_enabled` is schema-valid for names the editor has no `plugin`
        entry for (built-in TUI plugins) and for `true` values, so those must
        survive untouched (OC-09).
        """
        data = self._data
        path = self._cfg_path()
        if path is None or not isinstance(data.get("plugin_enabled"), dict):
            return
        flagged = {n for n, v in data["plugin_enabled"].items() if v is False}
        plugin = data.get("plugin", [])
        migrated = set()
        if flagged:
            kept = []
            for entry in plugin:
                name = self._name_of(entry)
                if name in flagged:
                    self.state_store.set_entry(path, name, entry)
                    migrated.add(name)
                else:
                    kept.append(entry)
            if kept:
                data["plugin"] = kept
            else:
                data.pop("plugin", None)
        # Everything the editor does not own stays in the file: `true` entries,
        # and `false` entries for names absent from the `plugin` list (built-in
        # TUI plugins the editor cannot re-enable from here).
        residual = {k: v for k, v in data["plugin_enabled"].items()
                    if not (v is False and k in migrated)}
        if residual:
            data["plugin_enabled"] = residual
        else:
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
        """Leave `plugin_enabled` alone: entries the editor does not own are
        preserved verbatim (migrated ones were already dropped on refresh)."""
        pass


class TuiTab(BaseTab):
    """Editor for the tui.json schema."""

    def __init__(self, app):
        super().__init__(app)
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

        # max_width is `int > 0 | "auto"`; 0 stays "(unset)" and a checkbox
        # selects the literal "auto" value (OC-15).
        pw_row = QWidget()
        pw_lay = QHBoxLayout(pw_row)
        pw_lay.setContentsMargins(0, 0, 0, 0)
        self.prompt_w = QSpinBox()
        self.prompt_w.setRange(0, 10**6)
        self.prompt_w.setSpecialValueText("(unset)")
        self.prompt_w.valueChanged.connect(self._t("prompt"))
        pw_lay.addWidget(self.prompt_w)
        self.prompt_w_auto = QCheckBox("auto")
        self.prompt_w_auto.toggled.connect(self._t("prompt"))
        pw_lay.addWidget(self.prompt_w_auto)
        self.prompt_w_auto.toggled.connect(self.prompt_w.setDisabled)
        form.addRow("Prompt max width", pw_row)

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
        pw = prompt.get("max_width")
        is_auto = pw == "auto"
        self.prompt_w_auto.blockSignals(True)
        self.prompt_w_auto.setChecked(is_auto)
        self.prompt_w_auto.blockSignals(False)
        self.prompt_w.setDisabled(is_auto)
        self._set_spin(self.prompt_w, None if is_auto else pw)
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
            if self.prompt_w_auto.isChecked():
                prompt["max_width"] = "auto"
            else:
                self._put(prompt, "max_width", self.prompt_w.value() or None, None)
            if not prompt:
                data.pop("prompt", None)
        self.plugins.collect(data)
        self._touched.clear()


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

        # Autoupdate: absent | false | true | "notify"
        self.autoupdate_combo = QComboBox()
        for label, val in [("(default)", "__absent__"), ("Off (false)", False),
                           ("On (true)", True), ('Notify ("notify")', "notify")]:
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

        # Subagent depth: -1 is '(default)'; 0 is a distinct, schema-valid value
        self.subagent_depth = QSpinBox()
        self.subagent_depth.setRange(-1, 100)
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
        for label, val in [("(default)", ""), ("manual", "manual"),
                           ("auto", "auto"), ("disabled", "disabled")]:
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
        if au is False:
            idx = 1
        elif au is True:
            idx = 2
        elif au == "notify":
            idx = 3
        else:
            idx = 0
        self.autoupdate_combo.blockSignals(True)
        self.autoupdate_combo.setCurrentIndex(idx)
        self.autoupdate_combo.blockSignals(False)
        self.model_edit.set_value(data.get("model", ""))
        self.small_model_edit.set_value(data.get("small_model", ""))
        self.default_agent_edit.set_value(data.get("default_agent", ""))
        self._depth_touched = False
        self.subagent_depth.blockSignals(True)
        depth = data.get("subagent_depth")
        self.subagent_depth.setValue(
            int(depth) if isinstance(depth, int) and not isinstance(depth, bool)
            and depth >= 0 else -1)
        self.subagent_depth.blockSignals(False)
        self.username_edit.set_value(data.get("username", ""))
        self.shell_edit.set_value(data.get("shell", ""))
        ll = data.get("logLevel", "")
        ll_idx = self.loglevel_combo.findData(ll)
        self.loglevel_combo.blockSignals(True)
        self.loglevel_combo.setCurrentIndex(ll_idx if ll_idx >= 0 else 0)
        self.loglevel_combo.blockSignals(False)
        sh = data.get("share")
        sh_idx = self.share_combo.findData(sh if isinstance(sh, str) else "")
        self.share_combo.blockSignals(True)
        self.share_combo.setCurrentIndex(sh_idx if sh_idx >= 0 else 0)
        self.share_combo.blockSignals(False)
        self._snapshot_touched = False
        self.snapshot_check.blockSignals(True)
        # snapshot defaults to true, so an absent key must show as enabled
        self.snapshot_check.setChecked(data.get("snapshot") is not False)
        self.snapshot_check.blockSignals(False)
        self.disabled_providers.refresh()
        self.enabled_providers.refresh()

    def collect(self, data: dict):
        """Collect data from UI (struct-tab, so combos always round-trip)."""
        if self.schema_edit.value():
            data["$schema"] = self.schema_edit.value()

        au = self.autoupdate_combo.currentData()
        if au == "__absent__":
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
            # -1 is '(default)'; 0 is a real, schema-valid depth
            if self.subagent_depth.value() >= 0:
                data["subagent_depth"] = self.subagent_depth.value()
            else:
                data.pop("subagent_depth", None)

        ll = self.loglevel_combo.currentData()
        if ll:
            data["logLevel"] = ll
        else:
            data.pop("logLevel", None)

        sh = self.share_combo.currentData()
        if sh:
            data["share"] = sh
        else:
            data.pop("share", None)

        if self._snapshot_touched:
            # snapshot defaults to true, so "off" must be written as false.
            data["snapshot"] = self.snapshot_check.isChecked()

        self.disabled_providers.collect(data)
        self.enabled_providers.collect(data)

# Raw JSON tab and shared confirm helper
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

    def _commit_pending(self):
        """Parse the editor text into the config it belongs to before switching
        away, so a raw edit is not silently thrown away (OC-16)."""
        if not self._modified:
            return True
        kind = self.app._raw_kind
        text = self.editor.toPlainText()
        if not text.strip():
            return True
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            QMessageBox.warning(
                self, "Raw JSON", f"Invalid JSON, keeping the previous values:\n\n{e}")
            return False
        cfg = self.app.cfg_tui if kind == "tui" else self.app.cfg_oc
        if cfg is None or not isinstance(parsed, dict):
            return True
        cfg.data.clear()
        cfg.data.update(parsed)
        return True

    def _switch_file(self):
        prev = self.app._raw_kind
        if prev != self.file_combo.currentData() and not self._commit_pending():
            # the text belongs to the previous file: put the combo back
            self.file_combo.blockSignals(True)
            self.file_combo.setCurrentIndex(max(0, self.file_combo.findData(prev)))
            self.file_combo.blockSignals(False)
            return
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
            json.loads(text)
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

# opencode adapter: registers the built-in opencode/tui config surface with the
# adapter registry. Kept as a distinct module so a second agent (openclaude, …)
# lives in its own sibling adapter module without touching this one or core.

def _opencode_targets(cwd):
    home = Path.home()
    proj_dir = cwd / ".opencode"
    return [
        ("Global opencode.json", home / ".config" / "opencode" / "opencode.json", "opencode"),
        ("Project opencode.json",
         (proj_dir / "opencode.json") if (proj_dir / "opencode.json").exists() else (cwd / "opencode.json"),
         "opencode"),
        ("Global tui.json", home / ".config" / "opencode" / "tui.json", "tui"),
        ("Project tui.json",
         (proj_dir / "tui.json") if (proj_dir / "tui.json").exists() else (cwd / "tui.json"),
         "tui"),
    ]


def _opencode_make_tabs(win):
    """Instantiate the opencode tabs on `win` and return [(tab, title, kind)].

    Named attributes (win.tab_providers, …) are kept because the menu wiring
    references them directly; win._oc_tabs lists the tabs that feed opencode.json.
    """
    win.tab_general = GeneralTab(win)
    win.tab_runtime = RuntimeTab(win)
    win.tab_agents = AgentsTab(win)
    win.tab_commands = CommandsTab(win)
    win.tab_providers = ProvidersTab(win)
    win.tab_mcp = McpTab(win)
    win.tab_plugins = PluginsTab(win)
    win.tab_permission = PermissionTab(win)
    win.tab_tui = TuiTab(win)
    win.tab_raw = RawJsonTab(win)
    win._oc_tabs = [win.tab_general, win.tab_runtime, win.tab_agents,
                    win.tab_commands, win.tab_providers, win.tab_mcp,
                    win.tab_plugins, win.tab_permission]
    return [
        (win.tab_general, "General", "opencode"),
        (win.tab_runtime, "Runtime", "opencode"),
        (win.tab_agents, "Agents", "opencode"),
        (win.tab_commands, "Commands", "opencode"),
        (win.tab_providers, "Providers", "opencode"),
        (win.tab_mcp, "MCP Servers", "opencode"),
        (win.tab_plugins, "Plugins", "opencode"),
        (win.tab_permission, "Permissions", "opencode"),
        (win.tab_tui, "TUI", "tui"),
        (win.tab_raw, "Raw JSON", None),
    ]


OPENCODE_ADAPTER = register_adapter(AdapterSpec(
    name="opencode",
    app_title=APP_NAME,
    version=APP_VERSION,
    kinds=["opencode", "tui"],
    known_keys={"opencode": OPENCODE_KEYS, "generic": OPENCODE_KEYS, "tui": TUI_KEYS},
    raw_files=[("opencode.json", "opencode"), ("tui.json", "tui")],
    targets_fn=_opencode_targets,
    make_tabs_fn=_opencode_make_tabs,
    capabilities={"providers", "mcp", "plugins", "catalog", "tui", "runtime"},
))
# openclaude config constants.
#
# VERIFIED sources (openclaude @gitlawb v0.28.0, 2026-08):
#   1. The shipped binary's SettingsSchema (zod) — superset of the official
#      Claude Code settings schema it embeds:
#      https://json.schemastore.org/claude-code-settings.json
#   2. openclaude docs (openclaude.gitlawb.com/docs/configuration/):
#      theme/verbose/autoUpdates live in the GLOBAL ~/.openclaude.json, not
#      settings.json; effortLevel/smartRouting/agentModels/agentRouting/
#      providerFallbackChain/advisorModel/subscriptionType/modelLimits are
#      real, documented settings keys.
#   3. Layered settings: user -> project -> local (later wins), plus a
#      highest-precedence read-only policy layer managed-settings.json
#      (/etc/claude-code on Linux).
#
# NOTE: keys here form the advisory known-key vocabulary for validation.
# The list is intentionally generous: unknown keys are preserved verbatim on
# save regardless of membership.

APP_NAME_OPENCLAUDE = "openclaude-config-editor"

# Official JSON Schema URL for settings.json (what openclaude itself writes
# into "$schema" for editor validation).
OPENCLAUDE_SETTINGS_SCHEMA_URL = "https://json.schemastore.org/claude-code-settings.json"

# Keys allowed in the layered settings.json files (user/project/local).
OPENCLAUDE_SETTINGS_KEYS = {
    "$schema", "advisorModel", "agent", "agentModels", "agentPushNotifEnabled",
    "agentRouting", "allowAllClaudeAiMcps", "allowManagedHooksOnly", "allowManagedMcpServersOnly", "allowManagedPermissionRulesOnly",
    "allowedChannelPlugins", "allowedHttpHookUrls", "allowedMcpServers", "alwaysThinkingEnabled", "apiKeyHelper",
    "askUserQuestionTimeout", "attribution", "autoCompactEnabled", "autoConnectIde", "autoDreamEnabled",
    "autoFix", "autoInstallIdeExtension", "autoMemoryDirectory", "autoMemoryEnabled", "autoMode",
    "autoScrollEnabled", "autoUpdatesChannel", "availableModels", "awaySummaryEnabled", "awsAuthRefresh",
    "awsCredentialExport", "axScreenReader", "blockedMarketplaces", "browserExternalPageTools", "channelsEnabled",
    "claudeMd", "claudeMdExcludes", "cleanupPeriodDays", "companyAnnouncements", "defaultShell",
    "deniedMcpServers", "diffTool", "disableAgentView", "disableAllHooks", "disableArtifact",
    "disableAutoMode", "disableBrowserExternalNavigation", "disableBundledSkills", "disableClaudeAiConnectors", "disableDeepLinkRegistration",
    "disableMobileSimulatorTools", "disableRemoteControl", "disableSideloadFlags", "disableSkillShellExecution", "disableWorkflows",
    "disabledMcpjsonServers", "editorMode", "effortLevel", "emojiCompletionEnabled", "enableAllProjectMcpServers",
    "enableArtifact", "enabledMcpjsonServers", "enabledPlugins", "enforceAvailableModels", "env",
    "externalEditorContext", "extraKnownMarketplaces", "fallbackModel", "fastMode", "fastModePerSessionOptIn",
    "feedbackSurveyRate", "fileCheckpointingEnabled", "fileSuggestion", "footerLinksRegexes", "forceLoginGatewayUrl",
    "forceLoginMethod", "forceLoginOrgUUID", "forceRemoteSettingsRefresh", "gcpAuthRefresh", "git",
    "hooks", "httpHookAllowedEnvVars", "includeCoAuthoredBy", "includeGitInstructions", "inputNeededNotifEnabled",
    "language", "managedMcpServers", "memory", "minimumVersion", "model",
    "modelLimits", "modelOverrides", "modelPricing", "otelHeadersHelper", "outputStyle",
    "parentSettingsBehavior", "permissionExplainerEnabled", "permissions", "plansDirectory", "pluginConfigs",
    "pluginSuggestionMarketplaces", "pluginTrustMessage", "policyHelper", "prUrlTemplate", "preferredNotifChannel",
    "prefersReducedMotion", "processWrapper", "promptSuggestionEnabled", "providerFallbackChain", "providerProfileModelPickerMode",
    "remote", "remoteControlAtStartup", "requireCoworkFullVmSandbox", "requiredMaximumVersion", "requiredMinimumVersion",
    "respectGitignore", "respondToBashCommands", "sandbox", "showClearContextOnPlanAccept", "showThinkingSummaries",
    "showTurnDuration", "skillListingBudgetFraction", "skillListingMaxDescChars", "skillOverrides", "skipDangerousModePermissionPrompt", "skipFullAccessModePermissionPrompt",
    "skipWebFetchPreflight", "skippedMarketplaces", "skippedPlugins", "smartRouting", "spinnerTipsEnabled",
    "spinnerTipsOverride", "spinnerVerbs", "sponsoredTipsEnabled", "sponsoredTipsFrequency", "sshConfigs",
    "sshHostAllowlist", "statusLine", "strictKnownMarketplaces", "strictPluginOnlyCustomization", "subagentStatusLine",
    "subscriptionType", "syntaxHighlightingDisabled", "teammateDefaultModel", "teammateMode", "terminalProgressBarEnabled",
    "terminalTitleFromRename", "theme", "tui", "useAutoModeDuringPlan", "verbose",
    "viewMode", "vimInsertModeRemaps", "voice", "voiceEnabled", "wheelScrollAccelerationEnabled",
    "workflowKeywordTriggerEnabled", "workflowSizeGuideline", "worktree", "wslInheritsWindowsSettings",
}

# Keys that live in the global ~/.openclaude.json. That file is mostly app
# STATE (numStartups, tipsHistory, projects, skillUsage, ...) which we
# preserve verbatim but never treat as config. These are the user-meaningful
# keys the editor understands:
OPENCLAUDE_GLOBAL_KEYS = {
    "$schema", "theme", "verbose", "autoUpdates",
    "providerProfiles", "activeProviderProfileId", "mcpServers",
}

# Value-bearing fields that hold secrets and must be masked in any UI / raw view.
OPENCLAUDE_SECRET_FIELDS = {"api_key", "apiKey", "token", "authToken"}

# Env dir override precedence (first set wins), default ~/.openclaude.
OPENCLAUDE_CONFIG_ENV = ("OPENCLAUDE_CONFIG_DIR", "CLAUDE_CONFIG_DIR")

# MCP server scopes and where each is stored.
OPENCLAUDE_MCP_SCOPES = ("user", "project", "local")

# openclaude embeds the Claude Code settings schema; schemastore publishes the
# same document. Findings are advisory only (openclaude adds keys of its own,
# and the schema's top level allows extra properties).
OPENCLAUDE_SCHEMA_URL = "https://json.schemastore.org/claude-code-settings.json"
OPENCLAUDE_SCHEMA_CACHE = USER_CONFIG_DIR / "openclaude-settings-schema.json"

# Top-level keys of a project .mcp.json.
OPENCLAUDE_PROJECT_MCP_KEYS = {"$schema", "mcpServers", "allowedTools", "mcpContextUris"}

# Transports openclaude understands for an MCP server entry.
OPENCLAUDE_MCP_TYPES = ("stdio", "http", "sse")
# openclaude layered config model.
#
# openclaude merges three settings layers (user -> project -> local, later
# wins) under a read-only, highest-precedence enterprise policy layer
# (managed-settings.json), plus separate stores:
#   - global ~/.openclaude.json  (providerProfiles, activeProviderProfileId,
#     user-scope mcpServers, app STATE we preserve but never edit)
#   - <cwd>/.mcp.json            (project-scope MCP servers)
#   - global projects[file dict].mcpServers (local-scope MCP servers)
#
# Verified against openclaude @gitlawb v0.28.0:
#   - managed dir: /etc/claude-code (linux), /Library/Application Support/
#     ClaudeCode (macos), C:\Program Files\ClaudeCode (windows); the policy
#     layer = managed-settings.json merged with managed-settings.d/*.json
#     drop-ins (sorted), and managed-mcp.json holds policy MCP servers.
#   - projects[] key = normalize(cwd) with backslashes replaced by "/".

def _needs_jsonc(raw: str) -> bool:
    """True when `raw` only parses as JSONC (comments, BOM or trailing commas),
    i.e. saving it back as plain json.dumps would drop something."""
    if not raw:
        return False
    if raw.lstrip(" \t\r\n").startswith("\ufeff"):
        return True
    try:
        json.loads(raw)
        return False
    except (ValueError, TypeError):
        return True

def default_managed_dir() -> Path:
    if sys.platform == "darwin":
        return Path("/Library/Application Support/ClaudeCode")
    if os.name == "nt":
        return Path("C:/Program Files/ClaudeCode")
    return Path("/etc/claude-code")


class LayeredConfigFile:
    """openclaude settings across user/project/local layers + policy + global."""

    LAYER_ORDER = ("user", "project", "local")

    def __init__(self, cwd, config_dir=None, managed_dir=None):
        self.cwd = Path(cwd)
        self.config_dir = Path(config_dir).expanduser() if config_dir else config_home(
            "~/.openclaude", OPENCLAUDE_CONFIG_ENV)
        dot = self.cwd / ".openclaude"
        self.layer_files = {
            "user": self.config_dir / "settings.json",
            "project": dot / "settings.json",
            "local": dot / "settings.local.json",
        }
        # Global file is a sibling of the config dir: ~/.openclaude -> ~/.openclaude.json
        self.global_file = Path(str(self.config_dir) + ".json")
        # Enterprise policy layer (read-only).
        self.managed_dir = Path(managed_dir) if managed_dir else default_managed_dir()
        self.managed_file = self.managed_dir / "managed-settings.json"
        self.managed_dropin_dir = self.managed_dir / "managed-settings.d"
        self.managed_mcp_file = self.managed_dir / "managed-mcp.json"
        # Project-scope MCP servers live in <cwd>/.mcp.json.
        self.project_mcp_file = self.cwd / ".mcp.json"

        self.layers = {name: {} for name in self.LAYER_ORDER}
        self.global_data = {}
        self.managed_settings = {}
        self.managed_mcp = {}
        self.project_mcp = {}
        self.error = None
        # path-str -> error message for files that exist but are unparsable;
        # guards the form-save path against clobbering them with empty dicts.
        self.parse_errors = {}
        # path-str -> True for files that needed loads_jsonc (comments/BOM);
        # the form-save path asks before rewriting them without comments.
        self.jsonc_files = set()

    def _read(self, path) -> dict:
        try:
            if Path(path).exists():
                raw = Path(path).read_text(encoding="utf-8")
                if _needs_jsonc(raw):
                    self.jsonc_files.add(str(path))
                data = loads_jsonc(raw)
                return data if isinstance(data, dict) else {}
        except OSError as e:
            self.parse_errors[str(path)] = str(e)
        except json.JSONDecodeError as e:
            self.parse_errors[str(path)] = f"invalid JSON: {e}"
        return {}

    def load(self) -> bool:
        self.parse_errors = {}
        self.jsonc_files = set()
        for name, path in self.layer_files.items():
            self.layers[name] = self._read(path)
        self.global_data = self._read(self.global_file)
        self.managed_settings = self._load_managed_settings()
        self.managed_mcp = self._read(self.managed_mcp_file)
        self.project_mcp = self._read(self.project_mcp_file)
        return True

    def _load_managed_settings(self) -> dict:
        """managed-settings.json merged with sorted managed-settings.d drop-ins."""
        sources = [self._read(self.managed_file)]
        try:
            if self.managed_dropin_dir.is_dir():
                for p in sorted(self.managed_dropin_dir.glob("*.json")):
                    sources.append(self._read(p))
        except OSError:
            pass
        return merge_layers(sources)

    def effective(self) -> dict:
        """Deep-merged settings; policy (managed) overrides all user layers."""
        return merge_layers(
            [self.layers[name] for name in self.LAYER_ORDER] + [self.managed_settings])

    def layer(self, name: str) -> dict:
        return self.layers.get(name, {})

    def project_key(self) -> str:
        """Key under global projects[file dict] for this cwd (normalized, '/' separators)."""
        return str(Path(self.cwd).resolve()).replace("\\", "/")

    def local_mcp(self) -> dict:
        """Local-scope MCP servers from global projects[file dict].mcpServers."""
        entry = self.global_data.get("projects", {})
        entry = entry.get(self.project_key(), {}) if isinstance(entry, dict) else {}
        servers = entry.get("mcpServers") if isinstance(entry, dict) else None
        return servers if isinstance(servers, dict) else {}

    def managed_mcp_servers(self) -> dict:
        servers = self.managed_mcp.get("mcpServers")
        return servers if isinstance(servers, dict) else {}

    def save_layer(self, name: str, data: dict) -> Tuple[bool, str]:
        """Atomically write one layer's settings.json."""
        if name not in self.layer_files:
            return False, f"Unknown layer: {name}"
        return self._atomic_write(self.layer_files[name], data, on_ok=lambda: self.layers.__setitem__(name, data))

    def save_global(self, data: dict) -> Tuple[bool, str]:
        """Atomically write the global ~/.openclaude.json (providers/routing/mcp)."""
        ok, msg = self._atomic_write(self.global_file, data, on_ok=lambda: setattr(self, "global_data", data))
        if ok:
            self._prune_provider_trash(data)
        return ok, msg

    def _prune_provider_trash(self, data: dict):
        """Drop trash entries for profiles present in the just-saved global file
        (keys: profile id, or "agentModels:<name>" for legacy rows). Best-effort:
        never changes the save result."""
        present = set()
        profiles = data.get("providerProfiles")
        if isinstance(profiles, list):
            present.update(str(p["id"]) for p in profiles if isinstance(p, dict) and p.get("id"))
        legacy = data.get("agentModels")
        if isinstance(legacy, dict):
            present.update(f"agentModels:{k}" for k in legacy)
        if not present:
            return
        try:
            ProviderTrashStore().prune(self.global_file, present)
        except Exception:
            pass

    def save_project_mcp(self, data: dict) -> Tuple[bool, str]:
        """Atomically write the project-scope .mcp.json."""
        return self._atomic_write(self.project_mcp_file, data, on_ok=lambda: setattr(self, "project_mcp", data))

    def _atomic_write(self, path, data, on_ok=None) -> Tuple[bool, str]:
        if not isinstance(data, dict):
            return False, "Root must be a JSON object."
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            self.parse_errors.pop(str(path), None)
            self.jsonc_files.discard(str(path))
            if on_ok:
                on_ok()
            return True, f"Saved to {path}"
        except OSError as e:
            return False, f"Save error: {e}"


def _openclaude_targets(cwd, config_dir=None):
    """Return [(label, Path, kind)] for the openclaude layers + global file."""
    cf = LayeredConfigFile(cwd, config_dir=config_dir)
    return [
        ("User settings.json", cf.layer_files["user"], "user"),
        ("Project settings.json", cf.layer_files["project"], "project"),
        ("Local settings.local.json", cf.layer_files["local"], "local"),
        ("Global ~/.openclaude.json", cf.global_file, "global"),
        ("Project .mcp.json", cf.project_mcp_file, "project-mcp"),
        ("Managed settings (policy, read-only)", cf.managed_file, "managed"),
    ]


def openclaude_findings(data, layer, validator=None):
    """Check one openclaude layer: returns (errors, warnings).

    Errors are container-shape problems openclaude itself would choke on.
    Warnings are advisory: unknown keys and JSON-Schema findings never block a
    save, because openclaude ships keys the published schema does not list.
    """
    errors, warnings = [], []
    if not isinstance(data, dict):
        return ["Root must be a JSON object."], []

    def want(key, types, label):
        val = data.get(key)
        if key in data and not isinstance(val, types):
            errors.append(f"'{key}' must be {label}.")
            return None
        return val

    if layer in ("global", "project-mcp"):
        servers = want("mcpServers", dict, "an object")
        for name, spec in (servers or {}).items():
            if not isinstance(spec, dict):
                errors.append(f"mcpServers[{name!r}] must be an object.")
                continue
            stype = spec.get("type")
            if stype is not None and stype not in OPENCLAUDE_MCP_TYPES:
                warnings.append(f"mcpServers[{name!r}].type {stype!r} is not one of "
                                + "/".join(OPENCLAUDE_MCP_TYPES))
            if "args" in spec and not isinstance(spec["args"], list):
                errors.append(f"mcpServers[{name!r}].args must be an array.")
        profiles = want("providerProfiles", list, "an array")
        for i, prof in enumerate(profiles or []):
            if isinstance(prof, dict) and not prof.get("id"):
                warnings.append(f"providerProfiles[{i}] has no 'id'; "
                                "activeProviderProfileId cannot point at it")
        if layer == "project-mcp":
            unknown = sorted(k for k in data if k not in OPENCLAUDE_PROJECT_MCP_KEYS)
            if unknown:
                warnings.append("unknown .mcp.json key(s): " + ", ".join(unknown))
        return errors, warnings

    hooks = want("hooks", dict, "an object")
    for event, groups in (hooks or {}).items():
        if not isinstance(groups, list):
            errors.append(f"hooks[{event!r}] must be an array of matcher groups.")
    perms = want("permissions", dict, "an object")
    for key in ("allow", "deny", "ask", "additionalDirectories"):
        if isinstance(perms, dict) and key in perms and not isinstance(perms[key], list):
            errors.append(f"permissions.{key} must be an array of strings.")
    env = want("env", dict, "an object")
    for name, val in (env or {}).items():
        if not isinstance(val, str):
            warnings.append(f"env[{name!r}] should be a string, got {type(val).__name__}")
    limits = want("modelLimits", dict, "an object")
    for model, spec in (limits or {}).items():
        if not isinstance(spec, dict):
            errors.append(f"modelLimits[{model!r}] must be an object.")
    if "statusLine" in data and not isinstance(data["statusLine"], (dict, bool)):
        errors.append("'statusLine' must be an object or a boolean.")

    unknown = sorted(k for k in data if k not in OPENCLAUDE_SETTINGS_KEYS)
    if unknown:
        warnings.append("unknown settings key(s): " + ", ".join(unknown))

    if validator is not None and not errors:
        schema = validator.schema_from(OPENCLAUDE_SCHEMA_URL, OPENCLAUDE_SCHEMA_CACHE,
                                      "openclaude-settings")
        if schema is not None:
            try:
                for e in jsonschema.Draft7Validator(schema).iter_errors(data):
                    warnings.append(f"schema: {e.message} (path: {_path_of(e)})")
            except Exception as ex:
                warnings.append(f"schema error: {ex}")
    return errors, warnings
# openclaude editor tabs. Minimal but functional: a Settings form (scalar keys)
# and a per-layer Raw JSON editor. Both operate on the layer currently selected
# on the window (win.oc_layer) via win.oc_layered (a LayeredConfigFile).

class OpenclaudeTab(BaseTab):
    """Shared base for openclaude layer-aware tabs.

    Centralizes two idioms every openclaude tab repeated inline: the
    mark-dirty/status-message slot, and the (layered, own-layer) lookup.
    """

    def _mark_edited(self):
        """Flag the openclaude doc dirty and show the standard status message."""
        self.app.oc_form_dirty = True
        self.app.status_bar.showMessage("Unsaved changes\u2026")

    def _edited(self, *_):
        """Default edit slot: no-op while the tab is (re)loading, else mark dirty."""
        if getattr(self, "_loading", False):
            return
        self._mark_edited()

    def _layered(self):
        """The window's LayeredConfigFile, or None before one is loaded."""
        return getattr(self.app, "oc_layered", None)

    def _own_layer(self):
        """Return (layered, own) with `own` = the selected layer's own dict."""
        layered = self._layered()
        own = layered.layer(self.app.oc_layer) if layered else {}
        return layered, own


class OpenclaudeSettingsTab(OpenclaudeTab):
    """Form for common scalar settings of the selected layer."""

    EFFORTS = ["", "low", "medium", "high", "xhigh", "max"]
    LAYERS = ["user", "project", "local"]

    def __init__(self, app):
        super().__init__(app)
        form = QFormLayout(self)

        self.layer_combo = QComboBox()
        for lk in self.LAYERS:
            self.layer_combo.addItem(lk, lk)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_change)
        form.addRow("Edit layer:", self.layer_combo)
        self.model_edit = QLineEdit()
        self.effort_combo = QComboBox()
        for e in self.EFFORTS:
            self.effort_combo.addItem(e or "(default)", e)
        self.agent_edit = QLineEdit()
        self.advisor_edit = QLineEdit()
        for w in (self.model_edit, self.agent_edit, self.advisor_edit):
            w.textChanged.connect(self._edited)
        self.effort_combo.currentIndexChanged.connect(self._edited)

        form.addRow("model:", self.model_edit)
        form.addRow("effortLevel:", self.effort_combo)
        form.addRow("agent:", self.agent_edit)
        form.addRow("advisorModel:", self.advisor_edit)

        # statusLine: boolean or {"type": "command", "command": "..."}
        self.statusline_chk = QCheckBox("enabled")
        self.statusline_cmd = QLineEdit()
        self.statusline_chk.stateChanged.connect(self._edited)
        self.statusline_cmd.textChanged.connect(self._edited)
        sl_box = QHBoxLayout()
        sl_box.addWidget(self.statusline_chk)
        sl_box.addWidget(self.statusline_cmd)
        form.addRow("statusLine:", sl_box)

        # skip-permission prompt toggles (settings.json booleans)
        self.skip_dangerous_chk = QCheckBox("skip dangerous-mode prompt")
        self.skip_fullaccess_chk = QCheckBox("skip full-access-mode prompt")
        self.skip_dangerous_chk.stateChanged.connect(self._edited)
        self.skip_fullaccess_chk.stateChanged.connect(self._edited)
        form.addRow("Permission prompts:", self.skip_dangerous_chk)
        form.addRow("", self.skip_fullaccess_chk)

        # MCP gating (settings.json) — controls how .mcp.json project servers
        # are approved. allowed/deniedMcpServers are object lists: edit in Raw.
        self.enable_all_mcp_chk = QCheckBox("enableAllProjectMcpServers")
        self.enable_all_mcp_chk.stateChanged.connect(self._edited)
        self.enabled_mcpjson_edit = QLineEdit()
        self.disabled_mcpjson_edit = QLineEdit()
        self.enabled_mcpjson_edit.textChanged.connect(self._edited)
        self.disabled_mcpjson_edit.textChanged.connect(self._edited)
        form.addRow("Project MCP:", self.enable_all_mcp_chk)
        form.addRow("enabledMcpjsonServers:", self.enabled_mcpjson_edit)
        form.addRow("disabledMcpjsonServers:", self.disabled_mcpjson_edit)

        info = QLabel("Editable text = this layer's own value; greyed placeholder = "
                      "value inherited from the effective merge (user → project → local). "
                      "Saving writes only the fields you set into the selected layer.")
        info.setWordWrap(True)
        info.setStyleSheet("color: gray;")
        form.addRow(info)

    def _on_layer_change(self, *_):
        _layer_change_guarded(self, self.layer_combo)

    def refresh(self):
        layered, own = self._own_layer()
        eff = layered.effective() if layered else {}
        self._set_combo(self.layer_combo, self.app.oc_layer, 0)

        # statusLine (bool or {type,command}) + skip-permission booleans
        sl = own.get("statusLine")
        self._orig_statusline = sl
        self._set_checked(self.statusline_chk, bool(sl))
        self._set_text(self.statusline_cmd,
                       sl.get("command", "") if isinstance(sl, dict) else "")
        self._set_checked(self.skip_dangerous_chk, own.get("skipDangerousModePermissionPrompt"))
        self._set_checked(self.skip_fullaccess_chk, own.get("skipFullAccessModePermissionPrompt"))
        self._had_dangerous = "skipDangerousModePermissionPrompt" in own
        self._had_fullaccess = "skipFullAccessModePermissionPrompt" in own

        # MCP gating fields
        self._set_checked(self.enable_all_mcp_chk, own.get("enableAllProjectMcpServers"))
        for edit, key in ((self.enabled_mcpjson_edit, "enabledMcpjsonServers"),
                          (self.disabled_mcpjson_edit, "disabledMcpjsonServers")):
            val = own.get(key)
            self._set_text(edit, ", ".join(val) if isinstance(val, list) else "")

        def _set(edit, key):
            # Show the selected layer's own value as editable text; show the
            # effective (inherited) value as greyed placeholder so nothing looks
            # empty when the value comes from another layer.
            edit.blockSignals(True)
            edit.setText(str(own.get(key, "")))
            inherited = str(eff.get(key, ""))
            edit.setPlaceholderText(f"inherited: {inherited}" if inherited else "(unset)")
            edit.blockSignals(False)

        _set(self.model_edit, "model")
        _set(self.agent_edit, "agent")
        _set(self.advisor_edit, "advisorModel")
        # effortLevel: select this layer's OWN value only (do not bake in the
        # inherited effective value on save); show effective as a hint via the
        # "(default)" entry when unset.
        eff_val = own.get("effortLevel", "")
        if eff_val and self.effort_combo.findData(eff_val) < 0:
            self.effort_combo.blockSignals(True)
            self.effort_combo.addItem(f"(current) {eff_val}", eff_val)
            self.effort_combo.blockSignals(False)
        self._set_combo(self.effort_combo, eff_val, 0)

    def collect(self, data):
        self._put(data, "model", self.model_edit.text().strip(), "")
        self._put(data, "effortLevel", self.effort_combo.currentData() or "", "")
        self._put(data, "agent", self.agent_edit.text().strip(), "")
        self._put(data, "advisorModel", self.advisor_edit.text().strip(), "")

        # statusLine: write when enabled; explicitly drop when disabled so an
        # existing key is removed rather than left behind.
        if self.statusline_chk.isChecked():
            cmd = self.statusline_cmd.text().strip()
            value = {"type": "command", "command": cmd} if cmd else True
            self._put(data, "statusLine", value, None)
        else:
            data.pop("statusLine", None)
        # MCP gating: write when pre-existing in this layer or explicitly set.
        if "enableAllProjectMcpServers" in data or self.enable_all_mcp_chk.isChecked():
            self._put(data, "enableAllProjectMcpServers",
                      self.enable_all_mcp_chk.isChecked(), None)
        for edit, key in ((self.enabled_mcpjson_edit, "enabledMcpjsonServers"),
                          (self.disabled_mcpjson_edit, "disabledMcpjsonServers")):
            items = [x.strip() for x in edit.text().split(",") if x.strip()]
            if items or key in data:
                self._put(data, key, items, [])

        # skip-permission toggles: write when pre-existing in this layer (so
        # unchecking writes an explicit false) or when explicitly opted in.
        if "skipDangerousModePermissionPrompt" in data or self.skip_dangerous_chk.isChecked():
            self._put(data, "skipDangerousModePermissionPrompt",
                      self.skip_dangerous_chk.isChecked(), None)
        if "skipFullAccessModePermissionPrompt" in data or self.skip_fullaccess_chk.isChecked():
            self._put(data, "skipFullAccessModePermissionPrompt",
                      self.skip_fullaccess_chk.isChecked(), None)


class OpenclaudeRawTab(OpenclaudeTab):
    """Raw JSON editor for the selected layer (full fidelity, incl. secrets)."""

    def __init__(self, app):
        super().__init__(app)
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(" Layer: "))
        self.layer_combo = QComboBox()
        for lk in ("user", "project", "local", "global", "project-mcp"):
            self.layer_combo.addItem(lk, lk)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_change)
        bar.addWidget(self.layer_combo)
        bar.addStretch()
        layout.addLayout(bar)

        self.editor = QPlainTextEdit()
        font = QFont("Monospace")
        font.setStyleHint(QFont.Monospace)
        self.editor.setFont(font)
        self.highlighter = JSONHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._on_text)
        self._modified = False
        layout.addWidget(self.editor)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self._validate_timer = QTimer(self)
        self._validate_timer.setSingleShot(True)
        self._validate_timer.setInterval(400)
        self._validate_timer.timeout.connect(self._validate)

    def _on_layer_change(self, *_):
        new_layer = self.layer_combo.currentData()
        old_layer = self._current_raw_layer()
        if new_layer == old_layer:
            return
        if self._modified:
            act = _confirm_unsaved(self.app,
                                   f"leave Raw layer '{old_layer}' with unsaved edits")
            if act == "cancel":
                self._set_combo(self.layer_combo, old_layer, 0)
                return
            if act == "save":
                self.app._save()          # raw-priority path saves this buffer
        self._raw_layer = new_layer
        self.refresh()

    def _on_text(self, *_):
        self._modified = True
        self.app.status_bar.showMessage("Unsaved changes…")
        self._validate_timer.start()

    def _validate(self):
        text = self.editor.toPlainText().strip()
        if not text:
            self._show_findings([], [])
            return
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText(f"JSON error: {e}")
            return
        errors, warnings = openclaude_findings(
            data, self._current_raw_layer(), getattr(self.app, "validator", None))
        self._show_findings(errors, warnings)

    def _show_findings(self, errors, warnings):
        msgs = [f"error: {m}" for m in errors] + [f"warning: {m}" for m in warnings]
        if not msgs:
            self.status_label.setStyleSheet("color: gray;")
            self.status_label.setText("Valid JSON")
            return
        shown = msgs[:5]
        if len(msgs) > len(shown):
            shown.append(f"... and {len(msgs) - len(shown)} more")
        self.status_label.setStyleSheet(
            "color: #c0392b;" if errors else "color: #b9770e;")
        self.status_label.setText("\n".join(shown))

    def _current_raw_layer(self):
        return getattr(self, "_raw_layer", None) or self.layer_combo.currentData() or "project"

    def refresh(self):
        layered = self._layered()
        layer = self._current_raw_layer()
        if layered is None:
            return
        if layer == "global":
            data = layered.global_data
        elif layer == "project-mcp":
            data = layered.project_mcp
        else:
            data = layered.layer(layer)
        self._set_text(self.editor, json.dumps(data, indent=2, ensure_ascii=False))
        self._modified = False
        self._validate()

    def parsed(self):
        """Return (layer, dict) from the editor, or (layer, None) if invalid."""
        try:
            return self._current_raw_layer(), json.loads(self.editor.toPlainText())
        except json.JSONDecodeError:
            return self._current_raw_layer(), None


class OpenclaudeAgentModelsTab(OpenclaudeTab):
    """Editor for provider connections in the global ~/.openclaude.json.

    OpenClaude stores providers as a `providerProfiles` list of
    {id, name, provider, baseUrl, model, apiKey, ...}. Extra/unknown fields on
    each profile (authHeader, authScheme, id, ...) are preserved on save.
    agentRouting / providerFallbackChain are also edited here when present.
    """

    COLS = ["name", "provider", "baseUrl", "model", "apiKey"]

    def __init__(self, app):
        super().__init__(app)
        self._dirty = False
        self._extra_profiles = []   # non-dict providerProfiles entries, kept verbatim
        self.dupe_names = []        # duplicate profile names skipped by collect
        self._had_profiles = False  # global file already had a providerProfiles key
        self._had_agent_models = False
        self._had_active = False    # global file already had activeProviderProfileId
        layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Providers — providerProfiles in ~/.openclaude.json "
                                    "(apiKey is masked; other fields like id/authScheme are preserved):"))
        top_layout.addStretch()
        self.show_trash_chk = QCheckBox("Show deleted")
        self.show_trash_chk.setToolTip(f"Removed providers are kept in {PROVIDER_TRASH_FILE}")
        self.show_trash_chk.toggled.connect(lambda _: self._reload_trash_rows())
        top_layout.addWidget(self.show_trash_chk)
        layout.addLayout(top_layout)

        self.models_table = QTableWidget(0, len(self.COLS))
        self.models_table.setHorizontalHeaderLabels(self.COLS)
        self.models_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.models_table)
        mbtn = QHBoxLayout()
        add_m = QPushButton("Add provider")
        add_m.clicked.connect(lambda: self._add_model_row())
        del_m = QPushButton("Remove selected")
        del_m.clicked.connect(self._remove_model_row)
        self.restore_btn = QPushButton("Restore selected")
        self.restore_btn.clicked.connect(self._restore_trash_rows)
        self.purge_btn = QPushButton("Delete permanently")
        self.purge_btn.clicked.connect(self._purge_trash_rows)
        for btn in (self.restore_btn, self.purge_btn):
            btn.setEnabled(False)    # act on deleted rows; enabled with "Show deleted"
        mbtn.addWidget(add_m)
        mbtn.addWidget(del_m)
        mbtn.addWidget(self.restore_btn)
        mbtn.addWidget(self.purge_btn)
        mbtn.addStretch()
        layout.addLayout(mbtn)

        # activeProviderProfileId — openclaude uses this global key to select
        # which providerProfile is active. Editable here instead of Raw-only.
        abar = QHBoxLayout()
        abar.addWidget(QLabel("Active provider (activeProviderProfileId):"))
        self.active_combo = QComboBox()
        self.active_combo.currentIndexChanged.connect(self._edited)
        abar.addWidget(self.active_combo, 1)
        layout.addLayout(abar)

        fbar = QHBoxLayout()
        fbar.addWidget(QLabel("providerFallbackChain (comma-separated):"))
        self.fallback_edit = QLineEdit()
        self.fallback_edit.textChanged.connect(self._edited)
        fbar.addWidget(self.fallback_edit)
        layout.addLayout(fbar)

        layout.addWidget(QLabel("Agent routing — agent → profile/model key ('default' = fallback):"))
        self.routing_table = QTableWidget(0, 2)
        self.routing_table.setHorizontalHeaderLabels(["agent", "modelKey"])
        self.routing_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.routing_table)
        # Cell edits (existing rows) must mark the tab dirty, else the global
        # rewrite is skipped on save.
        self.models_table.itemChanged.connect(self._edited)
        self.routing_table.itemChanged.connect(self._edited)
        rbtn = QHBoxLayout()
        add_r = QPushButton("Add route")
        add_r.clicked.connect(lambda: self._add_route_row())
        del_r = QPushButton("Remove selected")
        del_r.clicked.connect(self._remove_route_row)
        rbtn.addWidget(add_r)
        rbtn.addWidget(del_r)
        rbtn.addStretch()
        layout.addLayout(rbtn)

    def _edited(self, *_):
        if getattr(self, "_loading", False):
            return
        self._dirty = True
        self._mark_edited()

    # --- provider rows (providerProfiles) ---
    # Deleted (trash) rows are display-only and sit below the live rows; their
    # name item carries the trash key under this role.
    TRASH_ROLE = Qt.UserRole + 1

    def _flag_of(self, r):
        """Trash key of a display-only deleted row, else None (live row)."""
        item = self.models_table.item(r, 0)
        return item.data(self.TRASH_ROLE) if item else None

    def _first_trash_row(self):
        n = self.models_table.rowCount()
        return next((r for r in range(n) if self._flag_of(r)), n)

    def _add_model_row(self, profile=None):
        profile = profile if isinstance(profile, dict) else {}
        r = self._first_trash_row()          # live rows stay above deleted ones
        self.models_table.insertRow(r)
        name_item = QTableWidgetItem(str(profile.get("name", "")))
        # Preserve the original profile dict (id, authHeader, authScheme, ...).
        self.preserve(name_item, profile)
        self.models_table.setItem(r, 0, name_item)
        self.models_table.setItem(r, 1, QTableWidgetItem(str(profile.get("provider", ""))))
        self.models_table.setItem(r, 2, QTableWidgetItem(str(profile.get("baseUrl", ""))))
        self.models_table.setItem(r, 3, QTableWidgetItem(str(profile.get("model", ""))))
        masked = MaskedLineEdit(str(profile.get("apiKey", "")), field_name="apiKey")
        masked.textChanged.connect(self._edited)
        self.models_table.setCellWidget(r, 4, masked)
        self._edited()

    @staticmethod
    def _legacy_row(key, spec):
        """Row shape (_add_model_row input) for a legacy agentModels entry."""
        spec = spec if isinstance(spec, dict) else {}
        row = dict(spec)   # keep any extra legacy keys
        row.update({"name": key, "provider": spec.get("provider", ""),
                    "baseUrl": spec.get("base_url", ""), "model": spec.get("model", ""),
                    "apiKey": spec.get("api_key", ""), "_legacy_agentModels": True})
        return row

    def _row_entry(self, r):
        """(kind, name, value) for live row r, exactly as collect() writes it:
        ("legacy", name, agentModels spec) or ("profile", name, profile dict).
        None for a row without a name (collect skips those)."""
        name_item = self.models_table.item(r, 0)
        name = name_item.text().strip() if name_item else ""
        if not name:
            return None
        orig = self.preserved(name_item)
        provider = self._cell(r, 1)
        base_url = self._cell(r, 2)
        model = self._cell(r, 3)
        widget = self.models_table.cellWidget(r, 4)
        api_key = widget.value().strip() if widget else ""

        if orig.pop("_legacy_agentModels", False):
            spec = dict(orig)  # preserve extra legacy keys
            for mirror in ("name", "provider", "baseUrl", "model", "apiKey"):
                spec.pop(mirror, None)   # UI mirrors, not schema keys
            self._set_or_pop(spec, "base_url", base_url)
            self._set_or_pop(spec, "model", model)
            self._set_or_pop(spec, "api_key", api_key)
            return "legacy", name, spec

        prof = dict(orig)
        prof["name"] = name
        if not prof.get("id"):
            prof["id"] = f"provider_{os.urandom(6).hex()}"
        self._set_or_pop(prof, "provider", provider)
        self._set_or_pop(prof, "baseUrl", base_url)
        self._set_or_pop(prof, "model", model)
        self._set_or_pop(prof, "apiKey", api_key)
        return "profile", name, prof

    def _trash_entry(self, r):
        """(trash_key, entry) for live row r; the entry is _add_model_row input."""
        got = self._row_entry(r)
        if got is None:
            return None
        kind, name, value = got
        if kind == "legacy":
            return f"agentModels:{name}", self._legacy_row(name, value)
        return str(value["id"]), value

    def _live_keys(self):
        keys = set()
        for r in range(self.models_table.rowCount()):
            item = self.models_table.item(r, 0)
            if item is None or self._flag_of(r):
                continue
            orig = self.preserved(item)
            if orig.get("_legacy_agentModels"):
                keys.add(f"agentModels:{item.text().strip()}")
            elif orig.get("id"):
                keys.add(str(orig["id"]))
        return keys

    def _trashed(self):
        """Trash entries of the global file whose key is not a live row."""
        layered = self._layered()
        if layered is None:
            return {}
        live = self._live_keys()
        return {k: v for k, v in ProviderTrashStore().entries(layered.global_file).items()
                if k not in live}

    def _append_trash_row(self, key, entry):
        entry = entry if isinstance(entry, dict) else {}
        r = self.models_table.rowCount()
        self.models_table.insertRow(r)
        for c, fld in enumerate(("name", "provider", "baseUrl", "model")):
            item = QTableWidgetItem(str(entry.get(fld, "")))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
            item.setForeground(Qt.gray)
            self.models_table.setItem(r, c, item)
        self.models_table.item(r, 0).setData(self.TRASH_ROLE, key)
        masked = MaskedLineEdit(str(entry.get("apiKey", "")), field_name="apiKey")
        masked.setEnabled(False)
        self.models_table.setCellWidget(r, 4, masked)

    def _reload_trash_rows(self):
        """Sync the display-only deleted rows with the trash file. Live rows (and
        their unsaved edits) are untouched and the tab is never marked dirty."""
        show = self.show_trash_chk.isChecked()
        for btn in (self.restore_btn, self.purge_btn):
            btn.setEnabled(show)
        prev = self.models_table.blockSignals(True)
        try:
            for r in reversed(range(self.models_table.rowCount())):
                if self._flag_of(r):
                    self.models_table.removeRow(r)
            if show:
                for key, entry in sorted(self._trashed().items()):
                    self._append_trash_row(key, entry)
        finally:
            self.models_table.blockSignals(prev)

    def _selected_rows(self):
        rows = {i.row() for i in self.models_table.selectedItems()}
        if not rows and self.models_table.currentRow() >= 0:
            rows = {self.models_table.currentRow()}
        return sorted(rows, reverse=True)

    def _remove_model_row(self):
        """Soft delete: move each selected provider (current, edited values) into
        the trash file, then drop its row. It leaves the global file on Save."""
        layered = self._layered()
        rows = [r for r in self._selected_rows() if not self._flag_of(r)]
        if layered is None or not rows:
            return
        store = ProviderTrashStore()
        removed = False
        for r in rows:    # descending, so earlier indices stay valid
            got = self._trash_entry(r)
            if got is not None:
                try:
                    store.put(layered.global_file, *got)
                except (OSError, TypeError, ValueError) as e:
                    QMessageBox.critical(self, "Remove provider",
                                         f"Could not save the provider to the trash file; "
                                         f"it was not removed:\n{e}")
                    break
            self.models_table.removeRow(r)
            removed = True
        if removed:
            self._edited()
            self._reload_trash_rows()

    def _selected_trash_keys(self):
        return [k for k in (self._flag_of(r) for r in self._selected_rows()) if k]

    def _restore_trash_rows(self):
        """Turn selected deleted rows back into live rows. The trash entry stays
        until a successful save prunes it, so restore-then-discard loses nothing."""
        layered = self._layered()
        keys = self._selected_trash_keys()
        if layered is None or not keys:
            return
        trashed = self._trashed()       # excludes keys that are live again
        for key in keys:
            if key in trashed:
                self._add_model_row(trashed[key])     # marks the tab edited
        skipped = sum(key not in trashed for key in keys)
        self._reload_trash_rows()
        if skipped:
            QMessageBox.warning(self, "Restore provider",
                                f"{skipped} selected provider(s) not restored: already "
                                "present, or no longer in the trash file.")

    def _purge_trash_rows(self):
        """Permanently drop selected deleted rows from the trash file."""
        layered = self._layered()
        keys = self._selected_trash_keys()
        if layered is None or not keys:
            return
        if not _confirm(self, "Delete permanently",
                        f"Permanently delete {len(keys)} provider(s) from the trash?\n\n"
                        "This cannot be undone."):
            return
        store = ProviderTrashStore()
        try:
            for key in keys:
                store.discard(layered.global_file, key)
        except OSError as e:
            QMessageBox.critical(self, "Delete permanently", str(e))
        self._reload_trash_rows()

    # --- agentRouting rows ---
    def _add_route_row(self, agent="", key=""):
        r = self.routing_table.rowCount()
        self.routing_table.insertRow(r)
        self.routing_table.setItem(r, 0, QTableWidgetItem(agent))
        self.routing_table.setItem(r, 1, QTableWidgetItem(key))
        self._edited()

    def _remove_route_row(self):
        if self.remove_current(self.routing_table):
            self._edited()

    def refresh(self):
        layered = self._layered()
        # Providers/routing live in the global ~/.openclaude.json file.
        data = layered.global_data if layered else {}

        self._loading = True
        try:
            self.models_table.setRowCount(0)
            profiles = data.get("providerProfiles")
            self._had_profiles = isinstance(profiles, list)
            self._extra_profiles = []
            if isinstance(profiles, list):
                for prof in profiles:
                    if isinstance(prof, dict):
                        self._add_model_row(prof)
                    else:
                        # Preserve malformed/non-dict entries verbatim on save.
                        self._extra_profiles.append(prof)
            # Back-compat: also surface legacy agentModels {key: {...}} as rows.
            agent_models = data.get("agentModels") if isinstance(data.get("agentModels"), dict) else {}
            self._had_agent_models = "agentModels" in data
            for key, spec in agent_models.items():
                self._add_model_row(self._legacy_row(key, spec))

            chain = data.get("providerFallbackChain")
            self._set_text(self.fallback_edit,
                           ", ".join(chain) if isinstance(chain, list) else "")

            # Populate active-provider picker from the saved profiles (stable ids).
            self.active_combo.blockSignals(True)
            self.active_combo.clear()
            self.active_combo.addItem("(none / default)", "")
            if isinstance(profiles, list):
                for prof in profiles:
                    if isinstance(prof, dict) and prof.get("id"):
                        label = prof.get("name") or prof.get("id")
                        self.active_combo.addItem(str(label), str(prof["id"]))
            active_id = data.get("activeProviderProfileId")
            self._had_active = "activeProviderProfileId" in data
            aidx = self.active_combo.findData(str(active_id) if active_id else "")
            self.active_combo.setCurrentIndex(aidx if aidx >= 0 else 0)
            self.active_combo.blockSignals(False)

            self.routing_table.setRowCount(0)
            routing = data.get("agentRouting") if isinstance(data.get("agentRouting"), dict) else {}
            for agent, key in routing.items():
                self._add_route_row(str(agent), str(key))
            self._reload_trash_rows()
        finally:
            self._loading = False
            self._dirty = False

    def collect(self, data):
        profiles = list(self._extra_profiles)  # re-emit preserved non-dict entries
        legacy_models = {}
        seen_names = set()
        dupes = set()
        for r in range(self.models_table.rowCount()):
            if self._flag_of(r):
                continue             # deleted rows are display-only
            name = self._cell(r, 0)
            if not name:
                continue
            if name in seen_names:
                dupes.add(name)      # reported below; first row wins
                continue
            seen_names.add(name)
            kind, _, value = self._row_entry(r)
            if kind == "legacy":
                legacy_models[name] = value
            else:
                profiles.append(value)

        # Only write providerProfiles when the file already had it or we have rows,
        # so an untouched global file isn't polluted with an empty list.
        if "providerProfiles" in data or profiles:
            data["providerProfiles"] = profiles
        if legacy_models or "agentModels" in data:
            self._put(data, "agentModels", legacy_models, {})

        known_ids = {p.get("id") for p in profiles if isinstance(p, dict)}
        active = self.active_combo.currentData() or ""
        if active and active not in known_ids:
            active = ""                     # profile was removed; don't dangle
        if "activeProviderProfileId" in data or active:
            self._put(data, "activeProviderProfileId", active, "")

        chain = [c.strip() for c in self.fallback_edit.text().split(",") if c.strip()]
        self._put(data, "providerFallbackChain", chain, [])

        routing = {}
        for r in range(self.routing_table.rowCount()):
            agent_item = self.routing_table.item(r, 0)
            key_item = self.routing_table.item(r, 1)
            agent = agent_item.text().strip() if agent_item else ""
            key = key_item.text().strip() if key_item else ""
            if agent and key:
                routing[agent] = key
        self._put(data, "agentRouting", routing, {})

        # Reported by the save hook so the success message doesn't overwrite it.
        self.dupe_names = sorted(dupes)

    def _cell(self, r, c):
        return self.cell_text(self.models_table, r, c)

    @staticmethod
    def _set_or_pop(d, k, v):
        if v:
            d[k] = v
        else:
            d.pop(k, None)


class OpenclaudeMcpTab(OpenclaudeTab):
    """MCP servers across user/project/local scopes (+ policy read-only).

    Verified openclaude v0.28.0 storage:
      user    -> global ~/.openclaude.json -> mcpServers
      project -> <cwd>/.mcp.json           -> mcpServers
      local   -> global projects[file dict]     -> mcpServers
      policy  -> <managed>/managed-mcp.json (read-only display)
    Unknown sub-keys on each server (env, args, headers, ...) are preserved.
    """

    SCOPES = OPENCLAUDE_MCP_SCOPES          # from constants (single source)
    SOURCE_TYPES = ("github", "git", "url", "file", "directory", "npm")
    # Transports addressed by a URL rather than a command: openclaude's
    # McpServerConfigSchema requires `url` for both of these.
    URL_TYPES = ("http", "sse")

    def __init__(self, app):
        super().__init__(app)
        self._scopes_cache = {"user": {}, "project": {}, "local": {}}
        self._dirty_scopes = set()
        self._project_mcp_orig = {}
        self._shown_scope = "user"

        layout = QVBoxLayout(self)
        sbar = QHBoxLayout()
        sbar.addWidget(QLabel("Scope:"))
        self.scope_combo = QComboBox()
        for sc in self.SCOPES:
            self.scope_combo.addItem(sc, sc)
        self.scope_combo.currentIndexChanged.connect(self._on_scope_change)
        sbar.addWidget(self.scope_combo)
        sbar.addStretch()
        layout.addLayout(sbar)

        layout.addWidget(QLabel("Servers (args comma-separated; unknown sub-keys "
                                "preserved; edit complex servers in Raw):"))
        self.mcp_table = QTableWidget(0, 6)
        self.mcp_table.setHorizontalHeaderLabels(
            ["name", "transport", "command / url", "args (comma-separated)",
             "env (K=V, ...)", "headers (K=V, ...)"])
        self.mcp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.mcp_table)
        btns = QHBoxLayout()
        add_b = QPushButton("Add server")
        add_b.clicked.connect(lambda: self._add_row())
        hub_b = QPushButton("🧩 Hub / Templates")
        hub_b.clicked.connect(self._open_mcp_hub)
        del_b = QPushButton("Remove selected")
        del_b.clicked.connect(self._remove_row)
        btns.addWidget(add_b)
        btns.addWidget(hub_b)
        btns.addWidget(del_b)
        btns.addStretch()
        layout.addLayout(btns)

        self.managed_label = QLabel("")
        self.managed_label.setWordWrap(True)
        self.managed_label.setStyleSheet("color: gray;")
        layout.addWidget(self.managed_label)

        # Typing into an existing cell must mark the scope dirty too, else
        # global/.mcp.json writes get skipped on save.
        self.mcp_table.itemChanged.connect(self._edited)

    # --- table helpers ---
    def _add_row(self, name="", server=None):
        server = server if isinstance(server, dict) else {}
        r = self.mcp_table.rowCount()
        self.mcp_table.insertRow(r)
        name_item = QTableWidgetItem(name)
        self.preserve(name_item, server)
        self.mcp_table.setItem(r, 0, name_item)
        # Transport as a combo over the supported types so a typo like "SSE"
        # or "htp" cannot produce an entry no schema member accepts. An
        # unknown stored type is added to the list rather than dropped.
        typ = str(server.get("type") or ("http" if server.get("url") else "stdio"))
        choices = list(OPENCLAUDE_MCP_TYPES)
        if typ and typ not in choices:
            choices.append(typ)
        combo = QComboBox()
        combo.addItem("", "")
        for t in choices:
            combo.addItem(t, t)
        idx = combo.findData(typ)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.currentIndexChanged.connect(self._edited)
        self.mcp_table.setCellWidget(r, 1, combo)
        target = server.get("command") if isinstance(server.get("command"), str) else \
            "" if not server.get("url") else str(server.get("url"))
        self.mcp_table.setItem(r, 2, QTableWidgetItem(str(target or "")))
        args = server.get("args") if isinstance(server.get("args"), list) else []
        args_text = ", ".join(str(a) for a in args)
        self.mcp_table.setItem(r, 3, QTableWidgetItem(args_text))
        # env/headers often carry API keys - always masked (reveal via the
        # eye toggle), like provider apiKeys.
        texts = {}
        for key in ("env", "headers"):
            val = server.get(key) if isinstance(server.get(key), dict) else {}
            texts[key] = ", ".join(f"{k}={v}" for k, v in val.items())
        for col, key in ((4, "env"), (5, "headers")):
            w = MaskedLineEdit(texts[key], field_name=key,
                               placeholder="KEY=value, ...", secret=True)
            w.textChanged.connect(self._edited)
            self.mcp_table.setCellWidget(r, col, w)
        # Remember the initially-rendered texts so collect() can tell "user
        # cleared it" apart from "never touched" (byte-fidelity for e.g. env:{}).
        name_item.setData(Qt.UserRole + 1,
                          {"env": texts["env"], "headers": texts["headers"],
                           "args": args_text})
        self._edited()

    def _remove_row(self):
        if self.remove_current(self.mcp_table):
            self._edited()

    def _open_mcp_hub(self):
        dlg = MCPTemplateHubDialog(self, target_mode="openclaude")
        if dlg.exec() == QDialog.Accepted:
            key = dlg.result_server_key
            cfg = dlg.result_server_config
            if not key or not cfg:
                return
            # Appending a row under an existing name would silently replace
            # that server on save (env/args/headers and all), so ask first
            # — same as the opencode MCP tab.
            if key in self._collect_scope_table() and not _confirm(
                self, "Overwrite Server",
                f"Server '{key}' already exists. Overwrite?"
            ):
                return
            self._add_row(key, cfg)
            self._dirty_scopes.add(self._shown_scope)
            self._mark_edited()

    def _transport(self, r):
        """The transport of row `r` (combo cell, '' when unset)."""
        w = self.mcp_table.cellWidget(r, 1)
        if w is not None:
            return w.currentData() or ""
        return self._cell(r, 1)

    def _cell(self, r, c):
        return self.cell_text(self.mcp_table, r, c)

    @staticmethod
    def _pairs(text):
        out = {}
        for part in text.split(","):
            if "=" in part:
                k, _, v = part.partition("=")
                if k.strip():
                    out[k.strip()] = v.strip()
        return out

    # --- scope switching keeps unsaved edits per scope ---
    def _on_scope_change(self, *_):
        prev = getattr(self, "_shown_scope", None)
        new_scope = self.scope_combo.currentData() or "user"
        if prev and prev != new_scope:
            self._scopes_cache[prev] = self._collect_scope_table()
        self._shown_scope = new_scope
        # Loading a scope's rows is population, not an edit — suppress the
        # itemChanged/_add_row dirty marks so merely VIEWING a scope never
        # causes its file to be rewritten.
        self._loading = True
        try:
            self._load_scope_table(new_scope)
        finally:
            self._loading = False

    def _load_scope_table(self, scope):
        self.mcp_table.setRowCount(0)
        for name, srv in self._scopes_cache.get(scope, {}).items():
            if isinstance(srv, dict):
                self._add_row(name, srv)

    def _collect_scope_table(self) -> dict:
        """Rebuild the visible rows into a servers dict, preserving unknown keys."""
        out = {}
        for r in range(self.mcp_table.rowCount()):
            nitem = self.mcp_table.item(r, 0)
            name = nitem.text().strip() if nitem else ""
            if not name:
                continue
            srv = dict(self.preserved(nitem))
            typ = self._transport(r)
            target = self._cell(r, 2)
            args_text = self._cell(r, 3)
            env_w = self.mcp_table.cellWidget(r, 4)
            hdr_w = self.mcp_table.cellWidget(r, 5)
            env_text = env_w.value().strip() if env_w else ""
            hdr_text = hdr_w.value().strip() if hdr_w else ""
            if typ:
                srv["type"] = typ
            else:
                srv.pop("type", None)
            if typ in self.URL_TYPES:
                srv["url"] = target
                srv.pop("command", None)
            elif target:
                srv["command"] = target
                srv.pop("url", None)
            # args/env/headers: only rewrite when the user actually edited the
            # cell; an untouched cell keeps the original verbatim (e.g. env:{}).
            initial = nitem.data(Qt.UserRole + 1) or {}
            for key, cur in (("args", args_text), ("env", env_text), ("headers", hdr_text)):
                if cur != str(initial.get(key, "")).strip():
                    if key == "args" and cur:
                        srv["args"] = [a.strip() for a in cur.split(",") if a.strip()]
                    elif key != "args" and cur:
                        srv[key] = self._pairs(cur)
                    else:
                        srv.pop(key, None)
            out[name] = srv
        return out

    def _edited(self, *_):
        if getattr(self, "_loading", False):
            return
        scope = getattr(self, "_shown_scope", None)
        if scope:
            self._dirty_scopes.add(scope)
            self._mark_edited()

    def refresh(self):
        layered = self._layered()
        self._loading = True
        try:
            if layered:
                guser = layered.global_data.get("mcpServers")
                self._scopes_cache["user"] = guser if isinstance(guser, dict) else {}
                pmc = layered.project_mcp
                self._project_mcp_orig = dict(pmc) if isinstance(pmc, dict) else {}
                psrv = self._project_mcp_orig.get("mcpServers")
                self._scopes_cache["project"] = psrv if isinstance(psrv, dict) else {}
                self._scopes_cache["local"] = layered.local_mcp()
            self._set_combo(self.scope_combo,
                            getattr(self.app, "oc_mcp_scope", None) or "user", 0)
            self._shown_scope = self.scope_combo.currentData() or "user"
            self._load_scope_table(self._shown_scope)
            managed = layered.managed_mcp_servers() if layered else {}
            if managed:
                names = ", ".join(sorted(managed.keys()))
                self.managed_label.setText(
                    f"Policy servers from {layered.managed_mcp_file} (read-only): {names}")
            else:
                self.managed_label.setText("No managed-mcp.json policy layer found.")
        finally:
            self._loading = False
            self._dirty_scopes = set()

    def commit_current(self):
        """Flush the visible table into the cache of the shown scope."""
        self._scopes_cache[self._shown_scope] = self._collect_scope_table()

    def global_dirty(self) -> bool:
        return "user" in self._dirty_scopes or "local" in self._dirty_scopes

    def project_dirty(self) -> bool:
        return "project" in self._dirty_scopes

    def collect_global(self, gdata):
        """Apply dirty user/local scopes into the global data dict."""
        if "user" in self._dirty_scopes:
            servers = self._scopes_cache["user"]
            if servers:
                gdata["mcpServers"] = servers
            else:
                gdata.pop("mcpServers", None)
        if "local" in self._dirty_scopes:
            layered = self._layered()
            if layered is None:
                return
            projects = gdata.get("projects")
            projects = dict(projects) if isinstance(projects, dict) else {}
            key = layered.project_key()
            entry = projects.get(key)
            entry = dict(entry) if isinstance(entry, dict) else {}
            servers = self._scopes_cache["local"]
            if servers:
                entry["mcpServers"] = servers
            else:
                entry.pop("mcpServers", None)
            if entry:
                projects[key] = entry
            else:
                projects.pop(key, None)
            if projects or "projects" in gdata:
                gdata["projects"] = projects

    def project_mcp_data(self) -> dict:
        base = dict(self._project_mcp_orig)
        servers = self._scopes_cache["project"]
        if servers or "mcpServers" in base:
            base["mcpServers"] = servers
        return base


class OpenclaudePluginsTab(OpenclaudeTab):
    """Plugin + marketplace settings keys (settings.json of the selected layer).

    Shapes verified against openclaude v0.28.0 SettingsSchema:
      enabledPlugins: {"plugin-id@marketplace-id": true|false|["version"]}
      extraKnownMarketplaces: {name: {source: {source:"github"|... , ...},
                                      installLocation?, autoUpdate?}}
    blockedMarketplaces / pluginConfigs are object lists/dicts: Raw only.
    """

    MARKET_TYPES = OpenclaudeMcpTab.SOURCE_TYPES   # same vocabulary, one definition

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Edit layer:"))
        self.layer_combo = QComboBox()
        for lk in ("user", "project", "local"):
            self.layer_combo.addItem(lk, lk)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_change)
        top.addWidget(self.layer_combo)
        top.addStretch()
        layout.addLayout(top)

        info = QLabel("Plugins live in the selected settings layer. Complex values "
                      "(version arrays, blockedMarketplaces, pluginConfigs) — edit in Raw.")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(QLabel("enabledPlugins — plugin-id@marketplace-id → true/false:"))
        self.plugins_table = QTableWidget(0, 2)
        self.plugins_table.setHorizontalHeaderLabels(["plugin@marketplace", "value (true/false/[..])"])
        self.plugins_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.plugins_table)
        pbtns = QHBoxLayout()
        add_p = QPushButton("Add plugin")
        add_p.clicked.connect(lambda: self._add_plugin_row())
        del_p = QPushButton("Remove selected")
        del_p.clicked.connect(self._remove_plugin_row)
        pbtns.addWidget(add_p)
        pbtns.addWidget(del_p)
        pbtns.addStretch()
        layout.addLayout(pbtns)

        layout.addWidget(QLabel("extraKnownMarketplaces — additional marketplace sources:"))
        self.market_table = QTableWidget(0, 5)
        self.market_table.setHorizontalHeaderLabels(
            ["name", "source type", "repo / url / path / package", "ref", "autoUpdate"])
        self.market_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.market_table)
        mbtns = QHBoxLayout()
        add_m = QPushButton("Add marketplace")
        add_m.clicked.connect(lambda: self._add_market_row())
        del_m = QPushButton("Remove selected")
        del_m.clicked.connect(self._remove_market_row)
        mbtns.addWidget(add_m)
        mbtns.addWidget(del_m)
        mbtns.addStretch()
        layout.addLayout(mbtns)

        self.cache_label = QLabel("")
        self.cache_label.setWordWrap(True)
        self.cache_label.setStyleSheet("color: gray;")
        layout.addWidget(self.cache_label)

        self.empty_hint = QLabel("")
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet("color: gray;")
        layout.addWidget(self.empty_hint)

    def _on_layer_change(self, *_):
        _layer_change_guarded(self, self.layer_combo)

    # --- plugins rows ---
    def _add_plugin_row(self, pid=""):
        r = self.plugins_table.rowCount()
        self.plugins_table.insertRow(r)
        item = QTableWidgetItem(pid)
        item.setData(Qt.UserRole, None)
        self.plugins_table.setItem(r, 0, item)
        self.plugins_table.setItem(r, 1, QTableWidgetItem("true"))
        self._edited()

    def _remove_plugin_row(self):
        if self.remove_current(self.plugins_table):
            self._edited()

    # --- marketplace rows ---
    def _add_market_row(self, name="", entry=None):
        entry = entry if isinstance(entry, dict) else {}
        src = entry.get("source") if isinstance(entry.get("source"), dict) else {}
        stype = str(src.get("source", "github"))
        value = ""
        for fname in ("repo", "url", "path", "package"):
            if fname in src:
                value = str(src[fname])
                break
        r = self.market_table.rowCount()
        self.market_table.insertRow(r)
        name_item = QTableWidgetItem(name)
        self.preserve(name_item, entry)  # keep installLocation etc.
        ref_text = str(src.get("ref", "") or "")
        item_snapshot = {"name": name, "stype": stype, "value": value,
                         "ref": ref_text, "auto": bool(entry.get("autoUpdate"))}
        name_item.setData(Qt.UserRole + 1, item_snapshot)
        self.market_table.setItem(r, 0, name_item)
        self.market_table.setItem(r, 1, QTableWidgetItem(stype))
        self.market_table.setItem(r, 2, QTableWidgetItem(value))
        self.market_table.setItem(r, 3, QTableWidgetItem(ref_text))
        chk = QCheckBox()
        chk.setChecked(bool(entry.get("autoUpdate")))
        chk.stateChanged.connect(self._edited)
        self.market_table.setCellWidget(r, 4, chk)
        self._edited()

    def _remove_market_row(self):
        if self.remove_current(self.market_table):
            self._edited()

    def _pcell(self, r, c):
        return self.cell_text(self.plugins_table, r, c)

    def _mcell(self, r, c):
        return self.cell_text(self.market_table, r, c)

    def refresh(self):
        layered, own = self._own_layer()
        self._loading = True
        try:
            self._set_combo(self.layer_combo, self.app.oc_layer, 0)
            self.plugins_table.setRowCount(0)
            enabled = own.get("enabledPlugins")
            enabled = enabled if isinstance(enabled, dict) else {}
            for pid, val in enabled.items():
                r = self.plugins_table.rowCount()
                self._add_plugin_row(pid)
                if isinstance(val, list):
                    text = json.dumps(val)
                    self.plugins_table.item(r, 1).setData(Qt.UserRole, json.dumps(val))
                else:
                    text = "true" if val else "false"
                    self.plugins_table.item(r, 1).setData(Qt.UserRole, text)
                self.plugins_table.item(r, 1).setText(text)

            self.market_table.setRowCount(0)
            markets = own.get("extraKnownMarketplaces")
            markets = markets if isinstance(markets, dict) else {}
            for name, entry in markets.items():
                if isinstance(entry, dict):
                    self._add_market_row(name, entry)

            # Read-only listing of cached marketplaces under the config dir.
            cache_txt = ""
            if layered:
                plug_dir = layered.config_dir / "plugins"
                mk_dir = plug_dir / "marketplaces"
                try:
                    if mk_dir.is_dir():
                        found = sorted(p.name for p in mk_dir.iterdir() if p.is_dir())
                        if found:
                            cache_txt = f"Cached marketplaces ({mk_dir}): " + ", ".join(found)
                except OSError:
                    pass
            self.cache_label.setText(cache_txt or "")
            # empty-state hint: point at layers that DO hold plugin settings
            if self.plugins_table.rowCount() or self.market_table.rowCount():
                self.empty_hint.setText("")
            else:
                msg = f"No plugin settings in the '{getattr(self.app, 'oc_layer', '?')}' layer."
                found = []
                if layered:
                    for lk in ("user", "project", "local"):
                        if lk == self.app.oc_layer:
                            continue
                        data = layered.layer(lk)
                        if isinstance(data.get("enabledPlugins"), dict) and data["enabledPlugins"]:
                            found.append(f"{lk} (plugins)")
                        if isinstance(data.get("extraKnownMarketplaces"), dict) and data["extraKnownMarketplaces"]:
                            found.append(f"{lk} (marketplaces)")
                if found:
                    msg += " Found in: " + ", ".join(found) + \
                           " — switch 'Edit layer' above."
                self.empty_hint.setText(msg)
        finally:
            self._loading = False

    def collect(self, data):
        # enabledPlugins
        plugins = {}
        for r in range(self.plugins_table.rowCount()):
            pid = self._pcell(r, 0)
            if not pid:
                continue
            item = self.plugins_table.item(r, 1)
            text = (item.text().strip() if item else "").lower()
            orig = item.data(Qt.UserRole) if item else None
            if text == "true":
                plugins[pid] = True
            elif text == "false":
                plugins[pid] = False
            elif text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        plugins[pid] = [str(v) for v in parsed]
                        continue
                except json.JSONDecodeError:
                    pass
                plugins[pid] = orig  # keep original verbatim when unparsable
        if "enabledPlugins" in data or plugins:
            data["enabledPlugins"] = plugins

        # extraKnownMarketplaces
        markets = {}
        for r in range(self.market_table.rowCount()):
            name = self._mcell(r, 0)
            if not name:
                continue
            nitem = self.market_table.item(r, 0)
            entry = self.preserved(nitem)
            stype = self._mcell(r, 1)
            value = self._mcell(r, 2)
            ref = self._mcell(r, 3)
            chk = self.market_table.cellWidget(r, 4)
            snap = nitem.data(Qt.UserRole + 1) or {}
            auto_now = bool(chk.isChecked()) if chk else False
            untouched = (
                name == str(snap.get("name", ""))
                and stype == str(snap.get("stype", ""))
                and value == str(snap.get("value", ""))
                and ref == str(snap.get("ref", ""))
                and auto_now == bool(snap.get("auto", False)))
            if untouched:
                markets[name] = entry     # byte-fidelity for unedited sources
                continue
            src = {"source": stype or "github"}
            field = {"github": "repo", "git": "url", "url": "url",
                     "file": "path", "directory": "path", "npm": "package"}.get(src["source"], "repo")
            if value:
                src[field] = value
            if ref and src["source"] in ("github", "git"):
                src["ref"] = ref
            entry["source"] = src
            if chk is not None and not chk.isChecked():
                entry.pop("autoUpdate", None)
            elif chk is not None and chk.isChecked():
                entry["autoUpdate"] = True
            markets[name] = entry
        if "extraKnownMarketplaces" in data or markets:
            data["extraKnownMarketplaces"] = markets


class OpenclaudeHooksTab(OpenclaudeTab):
    """Structured editor for settings.json `hooks`.

    Verified shape (binary schema + real configs):
      hooks: {EventName: [ {matcher?: "*",
                            hooks: [{type: "command", command, timeout?, ...},
                                    ...]},
                           ... ] }
    One table row per hook ENTRY. Fidelity model:
    - every row remembers its original (event, group-index, entry-index);
    - untouched rows/events round-trip byte-for-byte (unknown group/entry
      keys survive);
    - editing patches only the touched fields; clearing removes them;
    - deleting a row removes exactly that entry (its group too when emptied);
    - new/moved rows append as fresh groups under their event, grouped by
      matcher text.
    """

    KNOWN_EVENTS = ("SessionStart", "SessionEnd", "UserPromptSubmit", "Stop",
                    "StopFailure", "SubagentStart", "SubagentStop",
                    "TeammateIdle", "PreToolUse", "PostToolUse",
                    "PostToolUseFailure", "PermissionRequest", "Notification",
                    "PreCompact")
    TYPE_FIELDS = {"command": "command", "http": "url", "prompt": "prompt"}

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Edit layer:"))
        self.layer_combo = QComboBox()
        for lk in ("user", "project", "local"):
            self.layer_combo.addItem(lk, lk)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_change)
        top.addWidget(self.layer_combo)
        top.addStretch()
        layout.addLayout(top)

        info = QLabel("hooks — one row per hook entry. Events: "
                      + ", ".join(self.KNOWN_EVENTS)
                      + " (free text allowed). Unknown group/entry keys are "
                        "preserved; edit exotic shapes in Raw.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.hooks_table = QTableWidget(0, 5)
        self.hooks_table.setHorizontalHeaderLabels(
            ["event", "matcher", "type", "command / url / prompt", "timeout"])
        self.hooks_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.hooks_table)
        btns = QHBoxLayout()
        add_b = QPushButton("Add hook")
        add_b.clicked.connect(lambda: self._add_row("SessionStart"))
        del_b = QPushButton("Remove selected")
        del_b.clicked.connect(self._remove_hook_row)
        btns.addWidget(add_b)
        btns.addWidget(del_b)
        btns.addStretch()
        layout.addLayout(btns)

        self.empty_hint = QLabel("")
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet("color: gray;")
        layout.addWidget(self.empty_hint)
        self.hooks_table.itemChanged.connect(self._edited)

    def _on_layer_change(self, *_):
        _layer_change_guarded(self, self.layer_combo)

    @staticmethod
    def _count_hook_entries(hooks):
        """Count hook entries in a parsed hooks dict (0 for odd shapes)."""
        n = 0
        for groups in hooks.values() if isinstance(hooks, dict) else []:
            if isinstance(groups, list):
                for grp in groups:
                    if isinstance(grp, dict) and isinstance(grp.get("hooks"), list):
                        n += sum(1 for e in grp["hooks"] if isinstance(e, dict))
        return n

    def _update_empty_hint(self, layered, own):
        if self.hooks_table.rowCount():
            self.empty_hint.setText("")
            return
        msg = f"No hooks in the '{getattr(self.app, 'oc_layer', '?')}' layer."
        found = []
        if layered:
            for lk in ("user", "project", "local"):
                if lk == self.app.oc_layer:
                    continue
                n = self._count_hook_entries(layered.layer(lk).get("hooks"))
                if n:
                    found.append(f"{lk} ({n} entries)")
        if found:
            msg += " Hooks found in: " + ", ".join(found) + \
                   " — switch 'Edit layer' above."
        self.empty_hint.setText(msg)

    def _add_row(self, event="", matcher="", typ="command", target="",
                 timeout="", orig=None, gi=None, ei=None):
        orig = orig if isinstance(orig, dict) else {"group": {}, "entry": {}}
        r = self.hooks_table.rowCount()
        self.hooks_table.insertRow(r)
        item = QTableWidgetItem(event)
        item.setData(Qt.UserRole, {"group": orig.get("group") or {},
                                   "entry": orig.get("entry") or {}})
        snapshot = {"event": event, "matcher": matcher, "type": typ,
                    "target": target, "timeout": timeout,
                    "gi": gi if gi is not None else -1,
                    "ei": ei if ei is not None else -1}
        item.setData(Qt.UserRole + 1, snapshot)
        self.hooks_table.setItem(r, 0, item)
        self.hooks_table.setItem(r, 1, QTableWidgetItem(matcher))
        self.hooks_table.setItem(r, 2, QTableWidgetItem(typ))
        self.hooks_table.setItem(r, 3, QTableWidgetItem(target))
        self.hooks_table.setItem(r, 4, QTableWidgetItem(timeout))
        self._edited()

    def _remove_hook_row(self):
        if self.remove_current(self.hooks_table):
            self._edited()

    def _cell(self, r, c):
        return self.cell_text(self.hooks_table, r, c)

    @staticmethod
    def _entry_from_cells(typ, target, timeout):
        entry = {"type": typ} if typ else {}
        field = OpenclaudeHooksTab.TYPE_FIELDS.get(typ)
        if target and field:
            entry[field] = target
        if timeout.strip().isdigit():
            entry["timeout"] = int(timeout.strip())
        return entry

    def _rows_snapshot(self):
        """Current cell values + stored metadata for every row, in table order."""
        rows = []
        for r in range(self.hooks_table.rowCount()):
            item = self.hooks_table.item(r, 0)
            if item is None:
                continue
            meta = item.data(Qt.UserRole + 1) or {}
            rows.append({
                "r": r,
                "stored_event": str(meta.get("event", "")),
                "cur_event": self._cell(r, 0),
                "matcher": self._cell(r, 1),
                "typ": self._cell(r, 2),
                "target": self._cell(r, 3),
                "timeout": self._cell(r, 4),
                "meta": meta,
                "orig": self.preserved(item),
            })
        return rows

    @staticmethod
    def _row_touched(row):
        m = row["meta"]
        return (row["cur_event"] != str(m.get("event", ""))
                or row["matcher"] != str(m.get("matcher", ""))
                or row["typ"] != str(m.get("type", ""))
                or row["target"] != str(m.get("target", ""))
                or row["timeout"] != str(m.get("timeout", "")))

    def refresh(self):
        layered, own = self._own_layer()
        self._loading = True
        try:
            self._set_combo(self.layer_combo, self.app.oc_layer, 0)
            self.hooks_table.setRowCount(0)
            hooks = own.get("hooks") if isinstance(own.get("hooks"), dict) else {}
            for ev, groups in hooks.items():
                if not isinstance(groups, list):
                    continue          # odd shapes stay verbatim via Raw/passthrough
                for gi, grp in enumerate(groups):
                    entries = grp.get("hooks") if isinstance(grp, dict) else None
                    if not isinstance(entries, list):
                        continue
                    matcher = str(grp.get("matcher", "") or "")
                    for ei, entry in enumerate(entries):
                        if not isinstance(entry, dict):
                            continue
                        typ = str(entry.get("type", "command"))
                        field = self.TYPE_FIELDS.get(typ, "command")
                        target = str(entry.get(field, "") or "")
                        timeout = (str(entry.get("timeout"))
                                   if entry.get("timeout") is not None else "")
                        self._add_row(str(ev), matcher, typ, target, timeout,
                                      orig={"group": grp, "entry": entry},
                                      gi=gi, ei=ei)
        finally:
            self._loading = False
            self._update_empty_hint(layered, own)

    def collect(self, data):
        rows = self._rows_snapshot()
        if "hooks" not in data and not rows:
            return
        orig_hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
        out = {}

        def place_new(pending):
            """Group brand-new/moved rows by matcher text into fresh groups."""
            buckets = {}
            for row in pending:
                buckets.setdefault(row["matcher"], []).append(row)
            groups = []
            for mtext, rs in buckets.items():
                grp = {}
                if mtext:
                    grp["matcher"] = mtext
                grp["hooks"] = [
                    self._entry_from_cells(x["typ"], x["target"], x["timeout"])
                    for x in rs]
                groups.append(grp)
            return groups

        for ev, groups in orig_hooks.items():
            # Map original entries to their rows. Fresh rows (gi=-1) never map;
            # membership is tracked by id() because dict equality would treat
            # identical-looking rows as the same object.
            slot = {}
            slotted = set()
            for row in rows:
                if (row["stored_event"] == ev and row["cur_event"] == ev
                        and int(row["meta"].get("gi", -1)) >= 0):
                    slot[(row["meta"]["gi"], row["meta"]["ei"])] = row
                    slotted.add(id(row))
            pending = [row for row in rows
                       if row["cur_event"] == ev and id(row) not in slotted]
            if not slot and not pending:
                continue             # event emptied or all rows moved away
            new_groups = []
            for gi, grp in enumerate(groups):
                entries = (grp.get("hooks")
                           if isinstance(grp, dict) and isinstance(grp.get("hooks"), list)
                           else None)
                if entries is None:
                    new_groups.append(grp)   # unknown shape: verbatim
                    continue
                kept = dict(grp)
                live = []
                matcher_new = None
                for ei, entry in enumerate(entries):
                    row = slot.get((gi, ei))
                    if row is None:
                        continue             # entry removed
                    if not self._row_touched(row):
                        live.append(entry)   # byte-verbatim
                        continue
                    e2 = dict(entry) if isinstance(entry, dict) else {}
                    for f in self.TYPE_FIELDS.values():
                        e2.pop(f, None)
                    e2.update(self._entry_from_cells(row["typ"], row["target"],
                                                     row["timeout"]))
                    if not row["typ"]:
                        e2.pop("type", None)
                    if "timeout" not in e2:
                        e2.pop("timeout", None)
                    live.append(e2)
                    if row["matcher"] != str(row["meta"].get("matcher", "")):
                        matcher_new = row["matcher"]
                if not live:
                    continue                 # group emptied by removals
                kept["hooks"] = live
                if matcher_new is not None:
                    if matcher_new:
                        kept["matcher"] = matcher_new
                    else:
                        kept.pop("matcher", None)
                new_groups.append(kept)
            new_groups.extend(place_new(pending))
            if new_groups:
                out[ev] = new_groups

        # Rows added under events the file never had (or moved to new names);
        # rows under existing events were already placed by the loop above.
        pending = [row for row in rows
                   if row["cur_event"] and row["cur_event"] not in orig_hooks]
        pend_by_ev = {}
        for row in pending:
            pend_by_ev.setdefault(row["cur_event"], []).append(row)
        for ev, rs in pend_by_ev.items():
            merged = list(out.get(ev, []))
            merged.extend(place_new(rs))
            out[ev] = merged

        if out or "hooks" in data:
            data["hooks"] = out


class OpenclaudePermissionsTab(OpenclaudeTab):
    """Editor for settings.json `permissions` on the selected layer.

    Verified shape (claude-code-settings schema embedded by openclaude):
      permissions: {allow[], deny[], ask[], additionalDirectories[],
                    defaultMode: enum, disableBypassPermissionsMode?,
                    disableAutoMode?}
    Rules are plain strings (e.g. "Bash(ls)"), one per line here. Unknown
    sub-keys of `permissions` are preserved on save.
    """

    MODES = ("", "default", "manual", "acceptEdits", "plan", "auto",
             "delegate", "dontAsk", "bypassPermissions")
    LISTS = (("allow", "allow — permitted operations"),
             ("deny", "deny — blocked operations"),
             ("ask", "ask — always confirm"),
             ("additionalDirectories", "additionalDirectories — extra paths in scope"))

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        self._orig = {}
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Edit layer:"))
        self.layer_combo = QComboBox()
        for lk in ("user", "project", "local"):
            self.layer_combo.addItem(lk, lk)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_change)
        top.addWidget(self.layer_combo)
        top.addWidget(QLabel("   defaultMode:"))
        self.mode_combo = QComboBox()
        for m in self.MODES:
            self.mode_combo.addItem(m or "(unset)", m)
        self.mode_combo.currentIndexChanged.connect(self._edited)
        top.addWidget(self.mode_combo)
        top.addStretch()
        layout.addLayout(top)

        info = QLabel("One rule per line, e.g. Bash(ls), Edit, WebFetch(domain:example.com). "
                      "Unknown permissions sub-keys are preserved.")
        info.setWordWrap(True)
        info.setStyleSheet("color: gray;")
        layout.addWidget(info)

        self.editors = {}
        for key, label in self.LISTS:
            layout.addWidget(QLabel(label + ":"))
            ed = QPlainTextEdit()
            ed.setTabChangesFocus(True)
            ed.textChanged.connect(self._edited)
            self.editors[key] = ed
            layout.addWidget(ed)

        flags = QHBoxLayout()
        self.no_bypass_chk = QCheckBox("disableBypassPermissionsMode")
        self.no_auto_chk = QCheckBox("disableAutoMode")
        for c in (self.no_bypass_chk, self.no_auto_chk):
            c.stateChanged.connect(self._edited)
            flags.addWidget(c)
        flags.addStretch()
        layout.addLayout(flags)

    def _on_layer_change(self, *_):
        _layer_change_guarded(self, self.layer_combo)

    @staticmethod
    def _lines(text):
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    def refresh(self):
        layered, own = self._own_layer()
        perms = own.get("permissions") if isinstance(own.get("permissions"), dict) else {}
        self._loading = True
        try:
            self._set_combo(self.layer_combo, self.app.oc_layer, 0)
            self._orig = dict(perms)
            for key, _label in self.LISTS:
                val = perms.get(key)
                lines = [str(v) for v in val] if isinstance(val, list) else []
                self._set_text(self.editors[key], "\n".join(lines))
            mode = str(perms.get("defaultMode", "") or "")
            if mode and self.mode_combo.findData(mode) < 0:
                self.mode_combo.addItem(f"(current) {mode}", mode)
            self._set_combo(self.mode_combo, mode, 0)
            self._set_checked(self.no_bypass_chk, perms.get("disableBypassPermissionsMode"))
            self._set_checked(self.no_auto_chk, perms.get("disableAutoMode"))
        finally:
            self._loading = False

    def collect(self, data):
        # Start from the layer's own permissions so unknown sub-keys survive.
        base = data.get("permissions")
        out = dict(base) if isinstance(base, dict) else {}
        for key, _label in self.LISTS:
            items = self._lines(self.editors[key].toPlainText())
            if items:
                out[key] = items
            else:
                out.pop(key, None)
        mode = self.mode_combo.currentData() or ""
        if mode:
            out["defaultMode"] = mode
        else:
            out.pop("defaultMode", None)
        for chk, key in ((self.no_bypass_chk, "disableBypassPermissionsMode"),
                         (self.no_auto_chk, "disableAutoMode")):
            if chk.isChecked():
                out[key] = True
            elif key in out:
                out[key] = False
        if out:
            data["permissions"] = out
        else:
            data.pop("permissions", None)


class OpenclaudeEnvLimitsTab(OpenclaudeTab):
    """Editors for settings.json `env` and `modelLimits` on the selected layer.

      env: {VAR: "string"}  — values are masked (they routinely hold API keys)
      modelLimits: {model: {contextWindow: int, maxOutputTokens: int}}
    Unknown per-model sub-keys are preserved.
    """

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Edit layer:"))
        self.layer_combo = QComboBox()
        for lk in ("user", "project", "local"):
            self.layer_combo.addItem(lk, lk)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_change)
        top.addWidget(self.layer_combo)
        top.addStretch()
        layout.addLayout(top)

        layout.addWidget(QLabel("env — environment variables applied to every session "
                                "(values masked; click the eye to reveal):"))
        self.env_table = QTableWidget(0, 2)
        self.env_table.setHorizontalHeaderLabels(["variable", "value"])
        self.env_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.env_table)
        ebtn = QHBoxLayout()
        add_e = QPushButton("Add variable")
        add_e.clicked.connect(lambda: self._add_env_row())
        del_e = QPushButton("Remove selected")
        del_e.clicked.connect(self._remove_env_row)
        ebtn.addWidget(add_e)
        ebtn.addWidget(del_e)
        ebtn.addStretch()
        layout.addLayout(ebtn)

        layout.addWidget(QLabel("modelLimits — per-model context window / max output tokens "
                                "(for OpenAI-compatible models missing from the catalog):"))
        self.limits_table = QTableWidget(0, 3)
        self.limits_table.setHorizontalHeaderLabels(
            ["model", "contextWindow", "maxOutputTokens"])
        self.limits_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.limits_table)
        lbtn = QHBoxLayout()
        add_l = QPushButton("Add model")
        add_l.clicked.connect(lambda: self._add_limit_row())
        del_l = QPushButton("Remove selected")
        del_l.clicked.connect(self._remove_limit_row)
        lbtn.addWidget(add_l)
        lbtn.addWidget(del_l)
        lbtn.addStretch()
        layout.addLayout(lbtn)

        self.env_table.itemChanged.connect(self._edited)
        self.limits_table.itemChanged.connect(self._edited)

    def _on_layer_change(self, *_):
        _layer_change_guarded(self, self.layer_combo)

    # --- env rows ---
    def _add_env_row(self, name="", value=""):
        r = self.env_table.rowCount()
        self.env_table.insertRow(r)
        self.env_table.setItem(r, 0, QTableWidgetItem(name))
        w = MaskedLineEdit(str(value), field_name="env-value",
                           placeholder="value", secret=True)
        w.textChanged.connect(self._edited)
        self.env_table.setCellWidget(r, 1, w)
        self._edited()

    def _remove_env_row(self):
        if self.remove_current(self.env_table):
            self._edited()

    # --- modelLimits rows ---
    def _add_limit_row(self, model="", spec=None):
        spec = spec if isinstance(spec, dict) else {}
        r = self.limits_table.rowCount()
        self.limits_table.insertRow(r)
        item = QTableWidgetItem(model)
        self.preserve(item, spec)          # keep unknown per-model sub-keys
        self.limits_table.setItem(r, 0, item)
        for col, key in ((1, "contextWindow"), (2, "maxOutputTokens")):
            val = spec.get(key)
            text = str(val) if isinstance(val, int) and not isinstance(val, bool) else ""
            self.limits_table.setItem(r, col, QTableWidgetItem(text))
        self._edited()

    def _remove_limit_row(self):
        if self.remove_current(self.limits_table):
            self._edited()

    def refresh(self):
        layered, own = self._own_layer()
        self._loading = True
        try:
            self._set_combo(self.layer_combo, self.app.oc_layer, 0)
            self._had_env = "env" in own
            self._had_limits = "modelLimits" in own
            self.env_table.setRowCount(0)
            env = own.get("env") if isinstance(own.get("env"), dict) else {}
            for k, v in env.items():
                self._add_env_row(str(k), "" if v is None else str(v))
            self.limits_table.setRowCount(0)
            limits = own.get("modelLimits") if isinstance(own.get("modelLimits"), dict) else {}
            for model, spec in limits.items():
                self._add_limit_row(str(model), spec if isinstance(spec, dict) else {})
        finally:
            self._loading = False

    def collect(self, data):
        env = {}
        for r in range(self.env_table.rowCount()):
            name = self.cell_text(self.env_table, r, 0)
            if not name:
                continue
            w = self.env_table.cellWidget(r, 1)
            env[name] = w.value() if w else ""
        if env or "env" in data:
            data["env"] = env

        limits = {}
        for r in range(self.limits_table.rowCount()):
            item = self.limits_table.item(r, 0)
            model = item.text().strip() if item else ""
            if not model:
                continue
            spec = self.preserved(item)     # unknown sub-keys survive
            for col, key in ((1, "contextWindow"), (2, "maxOutputTokens")):
                text = self.cell_text(self.limits_table, r, col)
                if text.isdigit():
                    spec[key] = int(text)
                else:
                    spec.pop(key, None)
            limits[model] = spec
        if limits or "modelLimits" in data:
            data["modelLimits"] = limits
# openclaude adapter registration + session hooks.
#
# openclaude's config topology (layered settings.json + a global file) differs
# from opencode's fixed pair, so this adapter supplies the initial_load/refresh/
# save session hooks that MainWindow calls instead of its built-in opencode path.

def _openclaude_make_tabs(win):
    win.oc_layer = "project"          # layer currently edited by the form
    win.oc_layered = None             # set by initial_load hook
    settings_tab = OpenclaudeSettingsTab(win)
    models_tab = OpenclaudeAgentModelsTab(win)
    mcp_tab = OpenclaudeMcpTab(win)
    plugins_tab = OpenclaudePluginsTab(win)
    hooks_tab = OpenclaudeHooksTab(win)
    perms_tab = OpenclaudePermissionsTab(win)
    envlim_tab = OpenclaudeEnvLimitsTab(win)
    raw_tab = OpenclaudeRawTab(win)
    win._agent_tabs = [settings_tab, models_tab, mcp_tab, plugins_tab,
                       hooks_tab, perms_tab, envlim_tab, raw_tab]
    win._agent_settings_tab = settings_tab
    win._agent_models_tab = models_tab
    win._agent_mcp_tab = mcp_tab
    win._agent_plugins_tab = plugins_tab
    win._agent_hooks_tab = hooks_tab
    win._agent_perms_tab = perms_tab
    win._agent_envlim_tab = envlim_tab
    win._agent_raw_tab = raw_tab
    return [
        (settings_tab, "Settings", "settings"),
        (models_tab, "Agent Models", "settings"),
        (mcp_tab, "MCP", "settings"),
        (plugins_tab, "Plugins", "settings"),
        (hooks_tab, "Hooks", "settings"),
        (perms_tab, "Permissions", "settings"),
        (envlim_tab, "Env & Limits", "settings"),
        (raw_tab, "Raw (per layer)", None),
    ]


def _openclaude_initial_load(win):
    win.oc_layer = getattr(win, "oc_layer", "project")
    win.oc_form_dirty = False         # any openclaude form tab has unsaved edits
    win.oc_layered = LayeredConfigFile(win.cwd)
    win.oc_layered.load()
    win.refresh_tabs()


def _confirm_unsaved(win, action="switch layer"):
    """Ask what to do about unsaved form edits. Returns 'save'|'discard'|'cancel'.

    Module-level so tests can monkeypatch it (offscreen runs never exec dialogs).
    """
    if not HAS_QT:
        return "cancel"
    box = QMessageBox(win)
    box.setWindowTitle("Unsaved changes")
    box.setText(f"You have unsaved changes.\n{action.capitalize()} anyway?")
    save_btn = box.addButton("Save & continue", QMessageBox.AcceptRole)
    box.addButton("Discard", QMessageBox.DestructiveRole)
    cancel_btn = box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(cancel_btn)
    box.exec()
    if box.clickedButton() is save_btn:
        return "save"
    if box.clickedButton() is cancel_btn:
        return "cancel"
    return "discard"


def _confirm_strip_comments(win, path):
    """Ask before rewriting a comments-carrying settings file without them.

    Returns True to proceed with the save. Module-level so tests can
    monkeypatch it (offscreen runs never exec dialogs).
    """
    if not HAS_QT:
        return False
    box = QMessageBox(win)
    box.setWindowTitle("Comments will be removed")
    box.setText(
        f"{path} contains JSON comments.\n"
        "Saving from the form rewrites it as plain JSON and every comment is lost."
    )
    save_btn = box.addButton("Save anyway", QMessageBox.AcceptRole)
    cancel_btn = box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(cancel_btn)
    box.exec()
    return box.clickedButton() is save_btn


def _layer_change_guarded(tab, combo):
    """Shared layer-combo handler: prompts before discarding unsaved edits."""
    win = tab.app
    new_layer = combo.currentData()
    cur = getattr(win, "oc_layer", None)
    if new_layer == cur:
        return
    if getattr(win, "oc_form_dirty", False):
        act = _confirm_unsaved(win, f"switch to the '{new_layer}' layer")
        if act == "cancel":
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(cur)))
            combo.blockSignals(False)
            return
        if act == "save":
            win._save()
    win.oc_layer = new_layer
    win.refresh_tabs()


def _openclaude_refresh(win):
    for tab in win._agent_tabs:
        tab.refresh()


def _openclaude_save(win):
    layered = win.oc_layered
    raw = win._agent_raw_tab
    # The Raw editor is the source of truth ONLY when it is the active tab AND
    # has unsaved edits — otherwise honoring it would silently discard form
    # edits made on the Settings/Agent Models tabs.
    raw_is_active = win.tabs.currentWidget() is raw
    if raw._modified and raw_is_active:
        layer, parsed = raw.parsed()
        if parsed is None:
            win.status_bar.showMessage("Raw JSON invalid — not saved")
            return
        if layer == "global":
            ok, msg = layered.save_global(parsed)
        elif layer == "project-mcp":
            ok, msg = layered.save_project_mcp(parsed)
        else:
            ok, msg = layered.save_layer(layer, parsed)
        win.status_bar.showMessage(msg if ok else f"Save error: {msg}")
        if ok:
            win.oc_form_dirty = False
            raw._modified = False
        win.refresh_tabs()
        return

    # Form-based save:
    #  - Settings tab writes scalar keys into the selected settings layer
    #  - Plugins/Hooks/Permissions/Env&Limits tabs write into the same layer
    #  - Agent Models tab writes providerProfiles/routing into the global
    #  - MCP tab writes per-scope: user/local -> global, project -> .mcp.json
    layer = win.oc_layer

    # Never let the form path clobber a file whose JSON failed to parse —
    # its in-memory {} would erase the user's real (broken) config on disk.
    if str(layered.layer_files[layer]) in layered.parse_errors:
        win.status_bar.showMessage(
            "Save blocked: settings file has invalid JSON — fix it in the Raw tab")
        return

    # save_layer rewrites the file with json.dumps, dropping every comment a
    # JSONC settings file carried. Ask before destroying them.
    layer_path = layered.layer_files[layer]
    if str(layer_path) in getattr(layered, "jsonc_files", set()):
        if not _confirm_strip_comments(win, layer_path):
            win.status_bar.showMessage(
                f"Save cancelled: comments kept in {layer_path}")
            return

    base = dict(layered.layer(layer))
    win._agent_settings_tab.collect(base)
    win._agent_plugins_tab.collect(base)
    win._agent_hooks_tab.collect(base)
    win._agent_perms_tab.collect(base)
    win._agent_envlim_tab.collect(base)
    ok1, msg1 = layered.save_layer(layer, base)

    # Only rewrite the global file when a tab that owns global data was actually
    # touched, so an untouched global (with app-state keys) is left alone.
    mcp_tab = win._agent_mcp_tab
    mcp_tab.commit_current()
    global_broken = str(layered.global_file) in layered.parse_errors
    mcpjson_broken = str(layered.project_mcp_file) in layered.parse_errors
    if getattr(win._agent_models_tab, "_dirty", False) or mcp_tab.global_dirty():
        if global_broken:
            ok2, msg2 = False, "global file has invalid JSON — fix in Raw"
        else:
            gbase = dict(layered.global_data)
            win._agent_models_tab.collect(gbase)
            mcp_tab.collect_global(gbase)
            ok2, msg2 = layered.save_global(gbase)
        tail = " + global"
    else:
        ok2, msg2, tail = True, "", ""

    ok3 = True
    msg3 = ""
    if mcp_tab.project_dirty():
        if mcpjson_broken:
            ok3, msg3 = False, ".mcp.json has invalid JSON — fix in Raw"
        else:
            ok3, msg3 = layered.save_project_mcp(mcp_tab.project_mcp_data())
        tail += " + .mcp.json"

    if ok1 and ok2 and ok3:
        note = ""
        dupes = getattr(win._agent_models_tab, "dupe_names", [])
        if dupes:
            note += (" — duplicate provider name(s) ignored: "
                     + ", ".join(dupes) + " (rename to keep both)")
        if raw._modified:
            # The raw buffer was edited but wasn't the active tab, so this save
            # ignored it. Say so instead of letting the user assume it landed.
            note = (f" — note: unsaved Raw edits for layer "
                    f"'{raw._current_raw_layer()}' were NOT saved "
                    f"(open the Raw tab and save again)")
        win.status_bar.showMessage(f"Saved layer '{layer}'{tail}{note}")
        win.oc_form_dirty = False
    else:
        first_err = next((m for m in (msg1, msg2, msg3) if m), "")
        win.status_bar.showMessage(f"Save error: {first_err}")
    win.refresh_tabs()


OPENCLAUDE_ADAPTER = register_adapter(AdapterSpec(
    name="openclaude",
    app_title=APP_NAME_OPENCLAUDE,
    version=APP_VERSION,
    kinds=["user", "project", "local", "global", "project-mcp", "managed"],
    known_keys={
        "user": OPENCLAUDE_SETTINGS_KEYS,
        "project": OPENCLAUDE_SETTINGS_KEYS,
        "local": OPENCLAUDE_SETTINGS_KEYS,
        "global": OPENCLAUDE_GLOBAL_KEYS,
        "project-mcp": {"mcpServers"},
        "managed": OPENCLAUDE_SETTINGS_KEYS,
    },
    raw_files=[("settings.json", "project")],
    targets_fn=_openclaude_targets,
    make_tabs_fn=_openclaude_make_tabs,
    capabilities={"layered", "agent_routing"},
    initial_load_fn=_openclaude_initial_load,
    refresh_fn=_openclaude_refresh,
    save_fn=_openclaude_save,
))
class MainWindow(QMainWindow):
    """Enhanced main window with undo/redo, themes, and better UX"""

    def __init__(self, cwd: Path, adapter=None):
        super().__init__()
        self.cwd = Path(cwd)
        self.adapter = adapter or default_adapter()
        # Per-kind config state, keyed by adapter kind. The opencode-named
        # attributes below (cfg_oc, dirty_oc, ...) are backward-compat
        # properties over these dicts, so a future adapter can drive N kinds
        # generically via self._configs while opencode code stays unchanged.
        self._kinds = list(self.adapter.kinds) if self.adapter else ["opencode", "tui"]
        self._configs = {k: None for k in self._kinds}
        self._dirty = {k: False for k in self._kinds}
        self._undo_mgrs = {k: UndoManager() for k in self._kinds}
        self._snap = {k: False for k in self._kinds}
        self.validator = Validator()
        self.model_catalog = ModelCatalog()
        self.settings = SettingsManager()
        self.theme_manager = None
        self.recent_files = []
        self.mode = None
        self.project_path = None
        self._raw_kind = "opencode"

        self._restore_window_state()

        _title = self.adapter.app_title if self.adapter else APP_NAME
        self.setWindowTitle(f"{_title} v{APP_VERSION}")
        self.resize(1200, 800)

        self._setup_theme()

        self._build_tabs()
        self._setup_recent_files()
        self._build_menu()
        self._build_toolbar()
        self._build_status_bar()

        self._do_initial_load()

    def _do_initial_load(self):
        """Initial config load — adapter hook if provided, else opencode global."""
        if self.adapter and self.adapter.initial_load_fn:
            self.adapter.initial_load_fn(self)
        else:
            self._load_global()

    # --- backward-compat properties over per-kind state dicts ---
    # Keep opencode call sites (self.cfg_oc, self.dirty_tui, ...) working while
    # state is stored generically by kind in self._configs / _dirty / _undo / _snap.
    @property
    def cfg_oc(self):
        return self._configs.get("opencode")

    @cfg_oc.setter
    def cfg_oc(self, v):
        self._configs["opencode"] = v

    @property
    def cfg_tui(self):
        return self._configs.get("tui")

    @cfg_tui.setter
    def cfg_tui(self, v):
        self._configs["tui"] = v

    @property
    def dirty_oc(self):
        return self._dirty.get("opencode", False)

    @dirty_oc.setter
    def dirty_oc(self, v):
        self._dirty["opencode"] = v

    @property
    def dirty_tui(self):
        return self._dirty.get("tui", False)

    @dirty_tui.setter
    def dirty_tui(self, v):
        self._dirty["tui"] = v

    @property
    def undo_oc(self):
        return self._undo_mgrs.get("opencode")

    @undo_oc.setter
    def undo_oc(self, v):
        self._undo_mgrs["opencode"] = v

    @property
    def undo_tui(self):
        return self._undo_mgrs.get("tui")

    @undo_tui.setter
    def undo_tui(self, v):
        self._undo_mgrs["tui"] = v

    @property
    def _snap_oc(self):
        return self._snap.get("opencode", False)

    @_snap_oc.setter
    def _snap_oc(self, v):
        self._snap["opencode"] = v

    @property
    def _snap_tui(self):
        return self._snap.get("tui", False)

    @_snap_tui.setter
    def _snap_tui(self, v):
        self._snap["tui"] = v

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

        # Tools menu — catalog + import actions are opencode-specific; only
        # wire them when the active adapter declares the matching capability.
        caps = self.adapter.capabilities if self.adapter else set()
        mtools = mb.addMenu("&Tools")

        if "catalog" in caps:
            self.act_catalog_mgr = QAction("Manage &Custom Models && Rules...", self)
            self.act_catalog_mgr.triggered.connect(self._manage_custom_catalog)
            mtools.addAction(self.act_catalog_mgr)

            self.act_update_catalog = QAction("🔄 Update Model Catalog &Online...", self)
            self.act_update_catalog.triggered.connect(self._update_catalog_online)
            mtools.addAction(self.act_update_catalog)

            self.act_browse_catalog = QAction("&Browse Model Catalog...", self)
            self.act_browse_catalog.triggered.connect(self._browse_model_catalog)
            mtools.addAction(self.act_browse_catalog)

            self.act_catalog = QAction("&Load Model Catalog File...", self)
            self.act_catalog.triggered.connect(self.load_model_catalog)
            mtools.addAction(self.act_catalog)

            self.act_apply_catalog = QAction("&Match & Format Models from Catalog...", self)
            self.act_apply_catalog.triggered.connect(self._apply_model_catalog)
            mtools.addAction(self.act_apply_catalog)

            mtools.addSeparator()

        if "providers" in caps:
            self.act_imp_provider = QAction("Import &Providers...", self)
            self.act_imp_provider.triggered.connect(self.tab_providers._import_providers)
            mtools.addAction(self.act_imp_provider)

        if "mcp" in caps:
            self.act_imp_mcp = QAction("Import &MCP Servers...", self)
            self.act_imp_mcp.triggered.connect(self.tab_mcp._import_servers)
            mtools.addAction(self.act_imp_mcp)

        if "plugins" in caps:
            self.act_imp_plugin = QAction("Import &Plugins...", self)
            self.act_imp_plugin.triggered.connect(self.tab_plugins._import_plugins)
            mtools.addAction(self.act_imp_plugin)

        mtools.addSeparator()

        self.act_health_check = QAction("⚡ &Provider Health Check...", self)
        self.act_health_check.triggered.connect(self._show_health_check)
        mtools.addAction(self.act_health_check)

        self.act_mcp_hub = QAction("🧩 &MCP Server Hub && Templates...", self)
        self.act_mcp_hub.triggered.connect(self._show_mcp_hub)
        mtools.addAction(self.act_mcp_hub)

        self.act_config_converter = QAction("🔄 &Universal Config Converter (OpenCode / OpenClaude / OMP)...", self)
        self.act_config_converter.triggered.connect(self._show_config_converter)
        mtools.addAction(self.act_config_converter)

        mtools.menuAction().setVisible(not mtools.isEmpty())

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
        self._prev_tab = self.tabs.currentWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _sync_raw_into_config(self) -> bool:
        """Apply valid Raw JSON text to the config it belongs to.

        Without this the Raw editor and the form tabs disagree: whichever was
        edited last was silently discarded at save time (OC-08).
        """
        if not self.tab_raw._modified:
            return True
        cfg = self.cfg_tui if self._raw_kind == "tui" else self.cfg_oc
        if cfg is None:
            return True
        try:
            parsed = json.loads(self.tab_raw.editor.toPlainText())
        except json.JSONDecodeError:
            return False
        if not isinstance(parsed, dict):
            return False
        cfg.data.clear()
        cfg.data.update(parsed)
        self.tab_raw._modified = False
        return True

    def _on_tab_changed(self, _index):
        """Keep the Raw editor and the form tabs consistent on every switch."""
        prev, cur = self._prev_tab, self.tabs.currentWidget()
        self._prev_tab = cur
        if prev is None or cur is None or prev is cur:
            return
        if not hasattr(self, "tab_raw") or self.tab_raw is None:
            return
        oc_tabs = list(getattr(self, "_oc_tabs", []))
        if prev is self.tab_raw and self._raw_kind == "opencode":
            # Leaving Raw: its text becomes the base, and the form tabs must
            # not keep the values they were showing before the raw edit.
            if self._sync_raw_into_config() and self.cfg_oc:
                for tab in oc_tabs:
                    tab.refresh()
        elif (prev in oc_tabs and self._raw_kind == "opencode"
              and not self.tab_raw._modified):
            # Leaving a form tab: let the Raw editor show what was just edited
            # here, so a later raw edit is based on it rather than on a stale
            # document.
            self.tab_raw.refresh()

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
        # Global/Local project switching is opencode-specific; adapters with
        # their own initial_load own their loading and ignore this.
        if self.adapter and self.adapter.initial_load_fn:
            return
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
        """Refresh all tabs. Adapter hook if provided, else opencode behavior."""
        if self.adapter and self.adapter.refresh_fn:
            self.adapter.refresh_fn(self)
            return
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
        # A raw edit is folded into cfg.data first, then the form tabs collect
        # on top of it. Neither side overwrites the other (OC-08).
        self._sync_raw_into_config()
        data = dict(self.cfg_oc.data) if isinstance(self.cfg_oc.data, dict) else {}
        for tab in self._oc_tabs:
            try:
                tab.collect(data)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"{type(tab).__name__}: {e}")
        return data

    def _collect_tui(self) -> dict:
        self._sync_raw_into_config()
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
        if self.adapter and self.adapter.save_fn:
            self.adapter.save_fn(self)
            return
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
        # 1. Try ~/.config/opencode-config-editor/catalog.json
        if CATALOG_CACHE.exists():
            try:
                self.model_catalog.load(CATALOG_CACHE)
                self._update_catalog_status()
                self.status_bar.showMessage(f"Loaded catalog: {CATALOG_CACHE}")
                return True
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, "Catalog Error", f"Failed to load user catalog: {e}")

        # 2. Try bundled relative to main script
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

    def _manage_custom_catalog(self):
        """Open the Custom Models & Matching Rules manager dialog."""
        # Only load a catalog when none is loaded: _ensure_catalog() would
        # otherwise throw away the catalog the user just loaded (CAT-06).
        if not self.model_catalog.loaded() and not self._ensure_catalog():
            return
        dlg = CustomCatalogManagerDialog(self, self.model_catalog)
        dlg.exec()
        self._update_catalog_status()

    def _update_catalog_online(self):
        """Update model catalog directly from configured online source."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ok, msg, count = self.model_catalog.fetch_online()
            if ok:
                self._update_catalog_status()
                self.status_bar.showMessage(msg, 5000)
                QMessageBox.information(self, "Catalog Update", msg)
            else:
                QMessageBox.warning(self, "Catalog Update Error", msg)
        finally:
            QApplication.restoreOverrideCursor()

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

    def _show_health_check(self):
        """Show Provider Health Check & Latency Ping dialog"""
        providers = {}
        if hasattr(self, "cfg") and self.cfg and isinstance(self.cfg.data, dict):
            providers = section(self.cfg.data, "provider")
        # Project-scoped {file:...} API keys resolve against the config's dir.
        cfg_path = str(self.cfg_oc.path) if self.cfg_oc else ""
        dlg = ProviderHealthCheckDialog(self, providers=providers, config_path=cfg_path)
        dlg.exec()

    def _show_mcp_hub(self):
        """Show MCP Server Hub & Templates dialog.

        The install itself is delegated to the active adapter's MCP tab, which
        prompts before overwriting an existing server and snapshots the undo
        stack (audit F3/F4).
        """
        if getattr(self, "tab_mcp", None) is not None:
            self.tab_mcp._open_mcp_hub()
            return
        mcp_tab = getattr(self, "_agent_mcp_tab", None)
        if mcp_tab is not None:
            mcp_tab._open_mcp_hub()
            return
        QMessageBox.information(
            self, "MCP Server Hub",
            "The active adapter does not provide an MCP Servers tab.")

    def _show_config_converter(self):
        """Show Universal Config Converter & Importer/Exporter dialog"""
        dlg = CrossConfigConverterDialog(self, app_context=self)
        dlg.exec()

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

# Overridden by build.py when generating a per-adapter single-file artifact
# (e.g. openclaude-config-editor.py sets this to "openclaude").
_BUILD_DEFAULT_ADAPTER = None


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

    # Select the agent adapter: --adapter=<name> or CONFIG_EDITOR_ADAPTER env,
    # then the build-time default, else the first registered (opencode).
    adapter_name = None
    for arg in sys.argv[1:]:
        if arg.startswith("--adapter="):
            adapter_name = arg.split("=", 1)[1]
    adapter_name = adapter_name or os.environ.get("CONFIG_EDITOR_ADAPTER") or _BUILD_DEFAULT_ADAPTER
    adapter = get_adapter(adapter_name) if adapter_name else None

    # Create and show main window
    cwd = Path(os.getcwd())
    win = MainWindow(cwd, adapter=adapter)
    win.show()

    # Run application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
