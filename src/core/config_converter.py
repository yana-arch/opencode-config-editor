# Universal Config Converter & Cross-Import/Export Engine
# (OpenCode <-> OpenClaude <-> OMP v1 <-> Claude Desktop / Cursor)
# ---------------------------------------------------------------------------

def detect_config_format(data: dict) -> str:
    """Identify the config format of the given dictionary."""
    if not isinstance(data, dict):
        return "unknown"

    if data.get("format") == "omp/v1" or ("$schema" in data and "omp" in str(data["$schema"])):
        return "omp"

    # opencode.json (and tui.json) markers win over the OpenClaude settings keys,
    # which overlap (env, model, ...) with other formats.
    if "provider" in data or "tui" in data or "plugin" in data or "mcp" in data:
        return "opencode"

    if "providerProfiles" in data or "activeProviderProfileId" in data:
        return "openclaude_global"

    _SETTINGS_KEYS = (
        "permissions", "modelLimits", "statusLine", "env", "hooks", "model",
        "includeCoAuthoredBy", "forceLoginMethod", "cleanupPeriodDays",
    )
    if any(k in data for k in _SETTINGS_KEYS):
        return "openclaude_settings"

    if "mcpServers" in data:
        if len(data) == 1:
            return "claude_desktop"
        return "openclaude_global"

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
        if cfg.get("enabled") is False:
            continue
        entry = {}
        if stype == "remote":
            # opencode carries no transport hint; streamable HTTP is the modern default
            entry["type"] = "http"
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
            if isinstance(cfg.get("cwd"), str) and cfg["cwd"]:
                entry["cwd"] = cfg["cwd"]
        env = cfg.get("environment")
        if not isinstance(env, dict):
            env = cfg.get("env")
        if isinstance(env, dict):
            entry["env"] = {str(k): str(v) for k, v in env.items()}
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
                "enabled": bool(cfg.get("enabled", True)),
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
                "enabled": bool(cfg.get("enabled", True)),
            }
            if isinstance(cfg.get("cwd"), str) and cfg["cwd"]:
                entry["cwd"] = cfg["cwd"]
        env = cfg.get("env")
        if isinstance(env, dict):
            entry["environment"] = {str(k): str(v) for k, v in env.items()}
        out[name] = entry
    return out


_OC_TOOL_TO_CLAUDE_RULE = {
    "read": "Read",
    "edit": "Edit",
    "write": "Write",
    "glob": "Glob",
    "grep": "Grep",
    "list": "LS",
    "bash": "Bash",
    "task": "Task",
    "todowrite": "TodoWrite",
    "webfetch": "WebFetch",
    "websearch": "WebSearch",
    "lsp": "LSP",
    "external_directory": "Read",
}
_CLAUDE_RULE_TO_OC_TOOL = {
    "read": "read",
    "edit": "edit",
    "write": "edit",
    "glob": "glob",
    "grep": "grep",
    "ls": "list",
    "bash": "bash",
    "task": "task",
    "todowrite": "todowrite",
    "webfetch": "webfetch",
    "websearch": "websearch",
}
_PERM_ACTIONS = {
    "allow": "allow",
    "true": "allow",
    "deny": "deny",
    "false": "deny",
    "block": "deny",
    "ask": "ask",
    "prompt": "ask",
}


def _opencode_rule_to_claude(tool: str, pattern, action: str) -> str:
    base = _OC_TOOL_TO_CLAUDE_RULE.get(str(tool).lower(), str(tool))
    if pattern is None:
        return base
    return f"{base}({pattern})"


def opencode_permissions_to_claude(perms: dict) -> dict:
    """Convert OpenCode permissions to OpenClaude permissions format.

    Handles both flat actions ("bash": "allow") and per-pattern rule objects
    ("bash": {"npm run *": "allow"}).
    """
    out = {"allow": [], "deny": [], "ask": []}
    if not isinstance(perms, dict):
        return out

    def _add(rule: str, action: str):
        bucket = _PERM_ACTIONS.get(str(action).lower())
        if bucket:
            out[bucket].append(rule)

    for tool, value in perms.items():
        if isinstance(value, dict):
            for pattern, action in value.items():
                _add(_opencode_rule_to_claude(tool, pattern, action), action)
        else:
            _add(_opencode_rule_to_claude(tool, None, value), value)
    for rules in out.values():
        rules.sort()
    return {k: v for k, v in out.items() if v}


def _claude_rule_to_opencode(rule: str):
    """Split a Claude rule into (tool, pattern or None)."""
    rule = str(rule).strip()
    if "(" in rule and rule.endswith(")"):
        base, pattern = rule.split("(", 1)
        return base.strip(), pattern[:-1]
    return rule, None


def claude_permissions_to_opencode(perms: dict) -> dict:
    """Convert OpenClaude permissions to OpenCode dictionary format.

    deny takes precedence over ask, which takes precedence over allow
    (Claude Code evaluates rules in that order).
    """
    out: Dict[str, Any] = {}
    if not isinstance(perms, dict):
        return out
    # Claude evaluates deny, then ask, then allow: write in that order and keep
    # the strongest action per rule so deny is never downgraded to ask/allow.
    for bucket in ("deny", "ask", "allow"):
        rules = perms.get(bucket, [])
        if isinstance(rules, str) or not isinstance(rules, (list, tuple)):
            continue
        for rule in rules:
            base, pattern = _claude_rule_to_opencode(rule)
            tool = _CLAUDE_RULE_TO_OC_TOOL.get(base.lower())
            if tool is None:
                tool = base
            if pattern is None:
                if not isinstance(out.get(tool), dict):
                    out[tool] = bucket
            else:
                nested = out.get(tool)
                if not isinstance(nested, dict):
                    if nested in ("allow", "ask", "deny"):
                        # keep the tool-wide rule and add the narrower pattern
                        nested = {"*": nested}
                    else:
                        nested = {}
                    out[tool] = nested
                nested.setdefault(pattern, bucket)
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

    if selected_components is None:
        comps = {"providers", "mcp_servers", "plugins", "permissions", "prompts", "settings"}
    else:
        comps = set(selected_components)
    result: Dict[str, Any] = {}

    def _has(key: str) -> bool:
        """A selected component is transferred only when the bundle carries data for it."""
        if key not in comps:
            return False
        val = omp_data.get(key)
        if isinstance(val, (dict, list, str)):
            return bool(val)
        return val is not None
    if target == "opencode":
        if _has("providers") and isinstance(omp_data["providers"], dict):
            result["provider"] = json.loads(json.dumps(omp_data["providers"]))
        if _has("mcp_servers") and isinstance(omp_data["mcp_servers"], dict):
            result["mcp"] = json.loads(json.dumps(omp_data["mcp_servers"]))
        if _has("plugins"):
            result["plugin"] = json.loads(json.dumps(omp_data["plugins"]))
        if _has("permissions") and isinstance(omp_data["permissions"], dict):
            result["permission"] = json.loads(json.dumps(omp_data["permissions"]))
        if _has("prompts") and isinstance(omp_data["prompts"], dict):
            if "instructions" in omp_data["prompts"]:
                result["instructions"] = omp_data["prompts"]["instructions"]
        if _has("settings") and isinstance(omp_data["settings"], dict):
            if "tui" in omp_data["settings"]:
                result["tui"] = json.loads(json.dumps(omp_data["settings"]["tui"]))

    elif target == "openclaude_global":
        if _has("mcp_servers") and isinstance(omp_data["mcp_servers"], dict):
            servers = opencode_mcp_to_claude_mcp(omp_data["mcp_servers"])
            if servers:
                result["mcpServers"] = servers
        if _has("settings") and isinstance(omp_data["settings"], dict):
            if "claude_provider_profiles" in omp_data["settings"]:
                result["providerProfiles"] = json.loads(json.dumps(omp_data["settings"]["claude_provider_profiles"]))

    elif target == "openclaude_settings":
        if _has("permissions") and isinstance(omp_data["permissions"], dict):
            perms = opencode_permissions_to_claude(omp_data["permissions"])
            if perms:
                result["permissions"] = perms
        if _has("settings") and isinstance(omp_data["settings"], dict):
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
