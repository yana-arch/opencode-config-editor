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

    def _read(self, path) -> dict:
        try:
            if Path(path).exists():
                data = loads_jsonc(Path(path).read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except OSError as e:
            self.parse_errors[str(path)] = str(e)
        except json.JSONDecodeError as e:
            self.parse_errors[str(path)] = f"invalid JSON: {e}"
        return {}

    def load(self) -> bool:
        self.parse_errors = {}
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
        return self._atomic_write(self.global_file, data, on_ok=lambda: setattr(self, "global_data", data))

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
