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
