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
        self._formats_cache = None
        self._model_index = {}  # model_id -> [provider_id, ...]

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
            # Provide a synthetic provider so the normalized formats still work.
            by_provider["provider"] = data

        else:
            raise ValueError("Unrecognized model catalog format.")

        self.raw, self.by_provider, self.flat = data, by_provider, flat
        self._formats_cache = None
        self._model_index = {}
        for pid, models in by_provider.items():
            for mid in models:
                self._model_index.setdefault(mid, []).append(pid)

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

    def formats(self) -> Dict[str, Dict[str, ModelFormat]]:
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

    def all_formats(self) -> List[ModelFormat]:
        """Flatten all formats across providers."""
        return [fmt for pmap in self.formats().values() for fmt in pmap.values()]

    def find_model(self, model_id: str) -> List[ModelFormat]:
        """Match a model id across the whole catalog (may match many providers)."""
        providers = self._model_index.get(model_id)
        if not providers:
            return []
        fmts = self.formats()
        return [fmts[p][model_id] for p in providers if model_id in fmts.get(p, {})]

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
            name=str(spec.get("name") or model_id),
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


def build_spec_from_format(fmt: ModelFormat) -> dict:
    """Convert a normalized ModelFormat back into a config-shaped spec."""
    spec = {}
    if fmt.name and fmt.name != fmt.model_id:
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

            merged = _merge_model_spec(spec, build_spec_from_format(chosen), overwrite)
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

