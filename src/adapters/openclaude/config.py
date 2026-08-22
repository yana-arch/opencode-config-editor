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

    @staticmethod
    def _read(path) -> dict:
        try:
            if Path(path).exists():
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}
        return {}

    def load(self) -> bool:
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
            content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, path)
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
