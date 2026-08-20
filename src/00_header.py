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
import urllib.parse
import ipaddress
import socket
import html
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
        QScrollArea
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

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

# Constants
APP_NAME = "opencode-config-editor"
APP_VERSION = "4.3.1"
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

