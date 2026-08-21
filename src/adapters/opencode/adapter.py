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
