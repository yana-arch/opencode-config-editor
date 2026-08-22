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
    raw_tab = OpenclaudeRawTab(win)
    win._agent_tabs = [settings_tab, models_tab, mcp_tab, plugins_tab,
                       hooks_tab, raw_tab]
    win._agent_settings_tab = settings_tab
    win._agent_models_tab = models_tab
    win._agent_mcp_tab = mcp_tab
    win._agent_plugins_tab = plugins_tab
    win._agent_hooks_tab = hooks_tab
    win._agent_raw_tab = raw_tab
    return [
        (settings_tab, "Settings", "settings"),
        (models_tab, "Agent Models", "settings"),
        (mcp_tab, "MCP", "settings"),
        (plugins_tab, "Plugins", "settings"),
        (hooks_tab, "Hooks", "settings"),
        (raw_tab, "Raw (per layer)", None),
    ]


def _openclaude_initial_load(win):
    win.oc_layer = getattr(win, "oc_layer", "project")
    win.oc_layered = LayeredConfigFile(win.cwd)
    win.oc_layered.load()
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
        win.refresh_tabs()
        return

    # Form-based save:
    #  - Settings tab writes scalar keys into the selected settings layer
    #  - Plugins/Hooks tabs write their settings keys into the same layer
    #  - Agent Models tab writes providerProfiles/routing into the global
    #  - MCP tab writes per-scope: user/local -> global, project -> .mcp.json
    layer = win.oc_layer
    base = dict(layered.layer(layer))
    win._agent_settings_tab.collect(base)
    win._agent_plugins_tab.collect(base)
    win._agent_hooks_tab.collect(base)
    ok1, msg1 = layered.save_layer(layer, base)

    # Only rewrite the global file when a tab that owns global data was actually
    # touched, so an untouched global (with app-state keys) is left alone.
    mcp_tab = win._agent_mcp_tab
    mcp_tab.commit_current()
    if getattr(win._agent_models_tab, "_dirty", False) or mcp_tab.global_dirty():
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
        ok3, msg3 = layered.save_project_mcp(mcp_tab.project_mcp_data())
        tail += " + .mcp.json"

    if ok1 and ok2 and ok3:
        win.status_bar.showMessage(f"Saved layer '{layer}'{tail}")
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
