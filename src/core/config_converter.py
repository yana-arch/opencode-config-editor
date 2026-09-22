# Universal Config Converter & Cross-Import/Export Engine
# (OpenCode <-> OpenClaude <-> OMP v1 <-> Claude Desktop / Cursor)
# ---------------------------------------------------------------------------

def detect_config_format(data: dict) -> str:
    """Identify the config format of the given dictionary."""
    if not isinstance(data, dict):
        return "unknown"

    if data.get("format") == "omp/v1" or ("$schema" in data and "omp" in str(data["$schema"])):
        return "omp"

    if "provider" in data or "tui" in data or "plugin" in data:
        return "opencode"

    if "providerProfiles" in data or "activeProviderProfileId" in data:
        return "openclaude_global"

    if "permissions" in data or "modelLimits" in data or "statusLine" in data:
        return "openclaude_settings"

    if "mcpServers" in data:
        if len(data) == 1:
            return "claude_desktop"
        return "openclaude_global"

    if "mcp" in data:
        return "opencode"

    return "generic"


# ---------------------------------------------------------------------------
# OpenCode <-> OpenClaude converters
# ---------------------------------------------------------------------------

def opencode_mcp_to_claude_mcp(opencode_mcp: dict) -> dict:
    """Convert OpenCode `mcp` dictionary to Claude `mcpServers` dictionary."""
    out = {}
    if not isinstance(opencode_mcp, dict):
        return out

    for name, cfg in opencode_mcp.items():
        if not isinstance(cfg, dict):
            continue
        stype = cfg.get("type", "local")
        entry = {}
        if stype == "remote":
            entry["type"] = "sse"
            entry["url"] = cfg.get("url", "")
            if "headers" in cfg and isinstance(cfg["headers"], dict):
                entry["headers"] = dict(cfg["headers"])
        else:
            cmd = cfg.get("command", [])
            if isinstance(cmd, list) and cmd:
                entry["command"] = str(cmd[0])
                if len(cmd) > 1:
                    entry["args"] = [str(x) for x in cmd[1:]]
            elif isinstance(cmd, str) and cmd:
                parts = cmd.split()
                entry["command"] = parts[0]
                if len(parts) > 1:
                    entry["args"] = parts[1:]
        if "env" in cfg and isinstance(cfg["env"], dict):
            entry["env"] = {str(k): str(v) for k, v in cfg["env"].items()}
        out[name] = entry
    return out


def claude_mcp_to_opencode_mcp(claude_mcp: dict) -> dict:
    """Convert Claude `mcpServers` dictionary to OpenCode `mcp` dictionary."""
    out = {}
    if not isinstance(claude_mcp, dict):
        return out

    for name, cfg in claude_mcp.items():
        if not isinstance(cfg, dict):
            continue
        stype = cfg.get("type", "stdio")
        if stype in ("sse", "remote", "http") or "url" in cfg:
            entry = {
                "type": "remote",
                "url": cfg.get("url", ""),
                "enabled": True,
            }
            if "headers" in cfg and isinstance(cfg["headers"], dict):
                entry["headers"] = dict(cfg["headers"])
        else:
            cmd_parts = []
            if "command" in cfg and cfg["command"]:
                cmd_parts.append(str(cfg["command"]))
            if "args" in cfg and isinstance(cfg["args"], list):
                cmd_parts.extend([str(a) for a in cfg["args"]])
            entry = {
                "type": "local",
                "command": cmd_parts,
                "enabled": True,
            }
        if "env" in cfg and isinstance(cfg["env"], dict):
            entry["env"] = {str(k): str(v) for k, v in cfg["env"].items()}
        out[name] = entry
    return out


def opencode_permissions_to_claude(perms: dict) -> dict:
    """Convert OpenCode permissions to OpenClaude permissions format."""
    out = {"allow": [], "deny": [], "ask": []}
    if not isinstance(perms, dict):
        return out

    for cmd, action in perms.items():
        act_str = str(action).lower()
        if act_str in ("allow", "true"):
            out["allow"].append(cmd)
        elif act_str in ("deny", "false", "block"):
            out["deny"].append(cmd)
        elif act_str in ("ask", "prompt"):
            out["ask"].append(cmd)
    return {k: v for k, v in out.items() if v}


def claude_permissions_to_opencode(perms: dict) -> dict:
    """Convert OpenClaude permissions to OpenCode dictionary format."""
    out = {}
    if not isinstance(perms, dict):
        return out
    for cmd in perms.get("allow", []):
        out[str(cmd)] = "allow"
    for cmd in perms.get("deny", []):
        out[str(cmd)] = "deny"
    for cmd in perms.get("ask", []):
        out[str(cmd)] = "ask"
    return out


# ---------------------------------------------------------------------------
# OMP (Open Multi-Platform) Schema v1
# ---------------------------------------------------------------------------

def export_to_omp(
    opencode_cfg: Optional[dict] = None,
    openclaude_global: Optional[dict] = None,
    openclaude_settings: Optional[dict] = None,
    name: str = "My AI Development Profile",
    description: str = "",
) -> dict:
    """Export configs from OpenCode and/or OpenClaude into a unified OMP v1 bundle."""
    bundle: Dict[str, Any] = {
        "$schema": "https://opencode.ai/schemas/omp-v1.json",
        "format": "omp/v1",
        "metadata": {
            "name": name,
            "description": description,
            "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "generator": "opencode-config-editor",
        },
        "providers": {},
        "mcp_servers": {},
        "plugins": [],
        "permissions": {},
        "prompts": {},
        "settings": {},
    }

    # Extract from OpenCode
    if isinstance(opencode_cfg, dict):
        if "provider" in opencode_cfg and isinstance(opencode_cfg["provider"], dict):
            bundle["providers"] = json.loads(json.dumps(opencode_cfg["provider"]))
        if "mcp" in opencode_cfg and isinstance(opencode_cfg["mcp"], dict):
            bundle["mcp_servers"] = json.loads(json.dumps(opencode_cfg["mcp"]))
        if "plugin" in opencode_cfg:
            bundle["plugins"] = json.loads(json.dumps(opencode_cfg["plugin"]))
        if "permission" in opencode_cfg and isinstance(opencode_cfg["permission"], dict):
            bundle["permissions"] = json.loads(json.dumps(opencode_cfg["permission"]))
        if "instructions" in opencode_cfg:
            bundle["prompts"]["instructions"] = opencode_cfg["instructions"]
        if "tui" in opencode_cfg:
            bundle["settings"]["tui"] = json.loads(json.dumps(opencode_cfg["tui"]))

    # Merge/augment from OpenClaude
    if isinstance(openclaude_global, dict):
        if "mcpServers" in openclaude_global and isinstance(openclaude_global["mcpServers"], dict):
            converted = claude_mcp_to_opencode_mcp(openclaude_global["mcpServers"])
            for k, v in converted.items():
                bundle["mcp_servers"].setdefault(k, v)
        if "providerProfiles" in openclaude_global:
            bundle["settings"]["claude_provider_profiles"] = json.loads(
                json.dumps(openclaude_global["providerProfiles"])
            )

    if isinstance(openclaude_settings, dict):
        if "permissions" in openclaude_settings and isinstance(openclaude_settings["permissions"], dict):
            conv_perms = claude_permissions_to_opencode(openclaude_settings["permissions"])
            for k, v in conv_perms.items():
                bundle["permissions"].setdefault(k, v)
        if "env" in openclaude_settings and isinstance(openclaude_settings["env"], dict):
            bundle["settings"]["env"] = json.loads(json.dumps(openclaude_settings["env"]))

    return bundle


def import_from_omp(
    omp_data: dict,
    target: str = "opencode",  # "opencode" | "openclaude_settings" | "openclaude_global"
    selected_components: Optional[List[str]] = None,
) -> dict:
    """Import an OMP v1 bundle into the target config dictionary structure."""
    if not isinstance(omp_data, dict):
        return {}

    comps = set(selected_components or ["providers", "mcp_servers", "plugins", "permissions", "prompts", "settings"])
    result: Dict[str, Any] = {}

    if target == "opencode":
        if "providers" in comps and "providers" in omp_data and isinstance(omp_data["providers"], dict):
            result["provider"] = json.loads(json.dumps(omp_data["providers"]))
        if "mcp_servers" in comps and "mcp_servers" in omp_data and isinstance(omp_data["mcp_servers"], dict):
            result["mcp"] = json.loads(json.dumps(omp_data["mcp_servers"]))
        if "plugins" in comps and "plugins" in omp_data:
            result["plugin"] = json.loads(json.dumps(omp_data["plugins"]))
        if "permissions" in comps and "permissions" in omp_data and isinstance(omp_data["permissions"], dict):
            result["permission"] = json.loads(json.dumps(omp_data["permissions"]))
        if "prompts" in comps and "prompts" in omp_data and isinstance(omp_data["prompts"], dict):
            if "instructions" in omp_data["prompts"]:
                result["instructions"] = omp_data["prompts"]["instructions"]
        if "settings" in comps and "settings" in omp_data and isinstance(omp_data["settings"], dict):
            if "tui" in omp_data["settings"]:
                result["tui"] = json.loads(json.dumps(omp_data["settings"]["tui"]))

    elif target == "openclaude_global":
        if "mcp_servers" in comps and "mcp_servers" in omp_data and isinstance(omp_data["mcp_servers"], dict):
            result["mcpServers"] = opencode_mcp_to_claude_mcp(omp_data["mcp_servers"])
        if "settings" in comps and "settings" in omp_data and isinstance(omp_data["settings"], dict):
            if "claude_provider_profiles" in omp_data["settings"]:
                result["providerProfiles"] = json.loads(json.dumps(omp_data["settings"]["claude_provider_profiles"]))

    elif target == "openclaude_settings":
        if "permissions" in comps and "permissions" in omp_data and isinstance(omp_data["permissions"], dict):
            result["permissions"] = opencode_permissions_to_claude(omp_data["permissions"])
        if "settings" in comps and "settings" in omp_data and isinstance(omp_data["settings"], dict):
            if "env" in omp_data["settings"]:
                result["env"] = json.loads(json.dumps(omp_data["settings"]["env"]))

    return result


def extract_external_mcp_servers(raw_data: dict) -> dict:
    """Extract MCP servers from Claude Desktop (`claude_desktop_config.json`) or Cursor (`mcp.json`)."""
    if not isinstance(raw_data, dict):
        return {}
    if "mcpServers" in raw_data and isinstance(raw_data["mcpServers"], dict):
        return raw_data["mcpServers"]
    if "mcp" in raw_data and isinstance(raw_data["mcp"], dict):
        return opencode_mcp_to_claude_mcp(raw_data["mcp"])
    likely_mcp = {}
    for k, v in raw_data.items():
        if isinstance(v, dict) and ("command" in v or "url" in v or "type" in v):
            likely_mcp[k] = v
    return likely_mcp
