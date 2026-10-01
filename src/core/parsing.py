# JSON parsing / import helpers for providers, MCP servers and models
def _load_json_file(path: Path) -> dict:
    """Load JSON with error handling"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _slugify(s: str) -> str:
    """Convert string to slug"""
    s = re.sub(r"[^a-zA-Z0-9_.\-]+", "-", str(s)).strip("-")
    return s or "item"

def _looks_like_provider_cfg(v) -> bool:
    """Check if object looks like a provider config"""
    return isinstance(v, dict) and any(k in v for k in ("npm", "models", "options", "name", "id"))

def parse_provider_import(obj: dict) -> dict:
    """Parse provider import from various JSON formats"""
    if isinstance(obj, dict) and isinstance(obj.get("provider"), dict) and obj["provider"]:
        obj = obj["provider"]

    if isinstance(obj, dict) and obj and all(_looks_like_provider_cfg(v) for v in obj.values()):
        return obj

    if _looks_like_provider_cfg(obj):
        key = _slugify(obj.get("id") or obj.get("name") or "provider")
        cfg = {k: v for k, v in obj.items() if k != "id"}
        return {key: cfg}

    raise ValueError(
        "Unrecognized provider JSON. Expected a provider object, a "
        "{name: provider} map, or a full config containing 'provider'."
    )

def _looks_like_mcp_cfg(v) -> bool:
    """Check if object looks like an MCP config"""
    return isinstance(v, dict) and any(k in v for k in ("type", "command", "url", "enabled"))


def _is_opencode_mcp_cfg(v) -> bool:
    """True for an entry already in opencode's own mcp shape.

    opencode uses type:local with an argv list, or type:remote with a url.
    Claude Desktop / Cursor instead use a bare 'command' string plus 'args'
    (and 'env'), or a bare 'url' with no type, which opencode does not accept.
    """
    if not _looks_like_mcp_cfg(v):
        return False
    if v.get("type") in ("local", "remote"):
        return True
    if "command" in v or "url" in v or "args" in v:
        return False
    return True   # toggle-only entry, e.g. {"enabled": false}


def parse_mcp_import(obj: dict) -> dict:
    """Parse MCP import from various JSON formats.

    Accepts opencode entries as-is, and converts Claude Desktop / Cursor
    entries (bare 'command' + 'args' + 'env', or a bare 'url') through
    claude_mcp_to_opencode_mcp so the result always matches opencode's schema.
    """
    if isinstance(obj, dict) and isinstance(obj.get("mcpServers"), dict) and obj["mcpServers"]:
        obj = obj["mcpServers"]
    elif isinstance(obj, dict) and isinstance(obj.get("mcp"), dict) and obj["mcp"]:
        obj = obj["mcp"]

    if isinstance(obj, dict) and obj and all(isinstance(v, dict) for v in obj.values()):
        converted = {}
        for name, entry in obj.items():
            if _is_opencode_mcp_cfg(entry):
                converted[name] = entry
            else:
                item = claude_mcp_to_opencode_mcp({name: entry})
                if name not in item:
                    raise ValueError(f"Unrecognized MCP server entry: {name}")
                converted[name] = item[name]
        return converted

    if _looks_like_mcp_cfg(obj):
        if _is_opencode_mcp_cfg(obj):
            key = _slugify(obj.get("name") or obj.get("id") or "server")
            cfg = {k: v for k, v in obj.items() if k not in ("name", "id")}
            return {key: cfg}
        converted = claude_mcp_to_opencode_mcp({"server": obj})
        if converted:
            key = _slugify(obj.get("name") or obj.get("id") or "server")
            return {key: converted["server"]}

    raise ValueError(
        "Unrecognized MCP JSON. Expected a server object, a {name: server} "
        "map, a 'mcpServers' wrapper, or a full config with 'mcp'."
    )


def merge_dict(base: dict, incoming: dict) -> dict:
    """Merge two configs with special handling for models/options"""
    out = dict(base)
    for k, v in incoming.items():
        if k in ("models", "options") and isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out

def _extract_models_map(data) -> dict:
    """Extract models map from various formats"""
    if isinstance(data, dict):
        if isinstance(data.get("models"), dict):
            return data["models"]
        if data and all(isinstance(v, dict) for v in data.values()):
            return data

    if isinstance(data, list):
        out = {}
        for item in data:
            if isinstance(item, dict) and "id" in item:
                out[item["id"]] = {k: v for k, v in item.items() if k != "id"}
        if not out:
            raise ValueError("Array items must be objects with an 'id' field.")
        return out

    raise ValueError("Unrecognized models JSON shape.")

