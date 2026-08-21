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
    raw_tab = OpenclaudeRawTab(win)
    win._agent_tabs = [settings_tab, models_tab, raw_tab]
    win._agent_settings_tab = settings_tab
    win._agent_models_tab = models_tab
    win._agent_raw_tab = raw_tab
    return [
        (settings_tab, "Settings", "settings"),
        (models_tab, "Agent Models", "settings"),
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
    # If the raw editor was edited, it is the source of truth for its layer.
    if raw._modified:
        layer, parsed = raw.parsed()
        if parsed is None:
            win.status_bar.showMessage("Raw JSON invalid — not saved")
            return
        if layer == "global":
            ok, msg = layered.save_global(parsed)
        else:
            ok, msg = layered.save_layer(layer, parsed)
        win.status_bar.showMessage(msg if ok else f"Save error: {msg}")
        win.refresh_tabs()
        return

    # Form-based save:
    #  - Settings tab writes scalar keys into the selected settings layer
    #  - Agent Models tab writes agentModels/agentRouting/fallback into the
    #    global ~/.openclaude.json (where providers live per openclaude docs)
    layer = win.oc_layer
    base = dict(layered.layer(layer))
    win._agent_settings_tab.collect(base)
    ok1, msg1 = layered.save_layer(layer, base)

    gbase = dict(layered.global_data)
    win._agent_models_tab.collect(gbase)
    ok2, msg2 = layered.save_global(gbase)

    if ok1 and ok2:
        win.status_bar.showMessage(f"Saved layer '{layer}' + global providers")
    else:
        win.status_bar.showMessage(f"Save error: {msg1 if not ok1 else msg2}")
    win.refresh_tabs()


OPENCLAUDE_ADAPTER = register_adapter(AdapterSpec(
    name="openclaude",
    app_title=APP_NAME_OPENCLAUDE,
    version=APP_VERSION,
    kinds=["user", "project", "local", "global"],
    known_keys={
        "user": OPENCLAUDE_SETTINGS_KEYS,
        "project": OPENCLAUDE_SETTINGS_KEYS,
        "local": OPENCLAUDE_SETTINGS_KEYS,
        "global": OPENCLAUDE_GLOBAL_KEYS,
    },
    raw_files=[("settings.json", "project")],
    targets_fn=_openclaude_targets,
    make_tabs_fn=_openclaude_make_tabs,
    capabilities={"layered", "agent_routing"},
    initial_load_fn=_openclaude_initial_load,
    refresh_fn=_openclaude_refresh,
    save_fn=_openclaude_save,
))
