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

