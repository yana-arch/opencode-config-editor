# openclaude layered config model.
#
# Unlike opencode (a single file per kind), openclaude merges three settings
# layers (user -> project -> local, later wins) plus a separate global file.
# LayeredConfigFile reads each layer independently, exposes the deep-merged
# effective view for display, and writes edits back to ONE chosen layer.

class LayeredConfigFile:
    """openclaude settings across user/project/local layers + global file."""

    LAYER_ORDER = ("user", "project", "local")

    def __init__(self, cwd, config_dir=None):
        self.cwd = Path(cwd)
        self.config_dir = Path(config_dir).expanduser() if config_dir else config_home(
            "~/.openclaude", OPENCLAUDE_CONFIG_ENV)
        dot = self.cwd / ".openclaude"
        self.layer_files = {
            "user": self.config_dir / "settings.json",
            "project": dot / "settings.json",
            "local": dot / "settings.local.json",
        }
        self.global_file = self.config_dir / ".." / ".openclaude.json"
        # Prefer the canonical ~/.openclaude.json when config_dir is the default.
        home_global = Path("~/.openclaude.json").expanduser()
        if not self.global_file.exists() and home_global.exists():
            self.global_file = home_global
        self.layers = {name: {} for name in self.LAYER_ORDER}
        self.global_data = {}
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
        return True

    def effective(self) -> dict:
        """Deep-merged settings across layers (later layer wins)."""
        return merge_layers(self.layers[name] for name in self.LAYER_ORDER)

    def layer(self, name: str) -> dict:
        return self.layers.get(name, {})

    def save_layer(self, name: str, data: dict) -> Tuple[bool, str]:
        """Atomically write one layer's settings.json."""
        if name not in self.layer_files:
            return False, f"Unknown layer: {name}"
        if not isinstance(data, dict):
            return False, "Root must be a JSON object."
        path = self.layer_files[name]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, path)
            self.layers[name] = data
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
    ]
