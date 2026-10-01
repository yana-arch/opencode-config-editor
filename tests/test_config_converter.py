from conftest import app


def test_detect_config_format():
    assert app.detect_config_format({"format": "omp/v1"}) == "omp"
    assert app.detect_config_format({"provider": {"openai": {}}}) == "opencode"
    assert app.detect_config_format({"mcpServers": {"memory": {}}}) == "claude_desktop"
    assert app.detect_config_format({"permissions": {"allow": ["git"]}}) == "openclaude_settings"


def test_mcp_conversion_roundtrip():
    opencode_mcp = {
        "memory": {
            "type": "local",
            "command": ["npx", "-y", "@modelcontextprotocol/server-memory"],
            "environment": {"DEBUG": "1"},
        },
        "remote_srv": {
            "type": "remote",
            "url": "https://example.com/mcp",
        }
    }
    claude_mcp = app.opencode_mcp_to_claude_mcp(opencode_mcp)
    assert claude_mcp["memory"]["command"] == "npx"
    assert claude_mcp["memory"]["args"] == ["-y", "@modelcontextprotocol/server-memory"]
    assert claude_mcp["memory"]["env"] == {"DEBUG": "1"}
    assert claude_mcp["remote_srv"]["type"] == "http"
    assert claude_mcp["remote_srv"]["url"] == "https://example.com/mcp"

    # Convert back: opencode spells env vars "environment", never "env"
    back = app.claude_mcp_to_opencode_mcp(claude_mcp)
    assert back["memory"]["type"] == "local"
    assert back["memory"]["command"] == ["npx", "-y", "@modelcontextprotocol/server-memory"]
    assert back["memory"]["environment"] == {"DEBUG": "1"}
    assert "env" not in back["memory"]
    assert back["remote_srv"]["type"] == "remote"
    assert back["remote_srv"]["url"] == "https://example.com/mcp"


def test_mcp_conversion_keeps_enabled_and_cwd():
    """CC-07: a disabled server is not exported; enabled:false and cwd survive the trip back."""
    out = app.opencode_mcp_to_claude_mcp(
        {"off": {"type": "local", "command": ["npx"], "enabled": False},
         "on": {"type": "local", "command": ["npx"], "cwd": "/srv"}}
    )
    assert "off" not in out
    assert out["on"]["cwd"] == "/srv"

    back = app.claude_mcp_to_opencode_mcp(
        {"off": {"command": "npx", "enabled": False}, "on": {"command": "npx", "cwd": "/srv"}}
    )
    assert back["off"]["enabled"] is False
    assert back["on"]["cwd"] == "/srv"


def test_import_from_omp_skips_empty_components():
    """CC-02: an MCP-only source must not hand the target an empty plugin list."""
    bundle = app.export_to_omp(openclaude_global={"mcpServers": {"fs": {"command": "npx"}}})
    assert bundle["plugins"] == [] and bundle["providers"] == {}

    imported = app.import_from_omp(bundle, "opencode")
    assert "plugin" not in imported
    assert "provider" not in imported
    assert "fs" in imported["mcp"]


def test_import_from_omp_empty_selection_transfers_nothing():
    """CC-11: unchecking every component transfers nothing."""
    bundle = app.export_to_omp(opencode_cfg={"mcp": {"fs": {"type": "local", "command": ["npx"]}}})
    assert app.import_from_omp(bundle, "opencode", []) == {}
    assert "mcp" not in app.import_from_omp(bundle, "opencode", ["providers", "plugins"])



def test_permission_rules_are_translated():
    """CC-09: per-pattern permission objects become Claude rules, not dropped strings."""
    out = app.opencode_permissions_to_claude(
        {"bash": {"npm run *": "allow", "rm -rf:*": "deny"}, "webfetch": "ask"}
    )
    assert out["allow"] == ["Bash(npm run *)"]
    assert out["deny"] == ["Bash(rm -rf:*)"]
    assert out["ask"] == ["WebFetch"]


def test_deny_wins_over_ask_when_converting_permissions():
    """CC-10: a rule in both deny and ask stays deny (Claude evaluates deny first)."""
    out = app.claude_permissions_to_opencode(
        {"allow": ["Bash(npm run *)"], "deny": ["Bash(rm -rf:*)"], "ask": ["Bash(rm -rf:*)"]}
    )
    assert out["bash"] == {"npm run *": "allow", "rm -rf:*": "deny"}


def test_detect_settings_json_without_permissions():
    """CC-12: a settings.json carrying only model/env is still OpenClaude settings."""
    assert app.detect_config_format({"model": "claude-sonnet-4", "env": {"A": "b"}}) == "openclaude_settings"
    env = app.import_from_omp(
        app.export_to_omp(openclaude_settings={"env": {"A": "b"}}), "openclaude_settings"
    )
    assert env["env"] == {"A": "b"}


def test_permissions_conversion():
    oc_perms = {"git commit": "allow", "rm -rf": "deny", "curl": "ask"}
    cl_perms = app.opencode_permissions_to_claude(oc_perms)
    assert "git commit" in cl_perms["allow"]
    assert "rm -rf" in cl_perms["deny"]
    assert "curl" in cl_perms["ask"]

    back_perms = app.claude_permissions_to_opencode(cl_perms)
    assert back_perms["git commit"] == "allow"
    assert back_perms["rm -rf"] == "deny"
    assert back_perms["curl"] == "ask"


def test_omp_export_and_import():
    opencode_cfg = {
        "provider": {"ollama": {"npm": "@ai-sdk/openai-compatible", "models": {"qwen2.5-coder": {}}}},
        "mcp": {"memory": {"type": "local", "command": ["npx", "-y", "@modelcontextprotocol/server-memory"]}},
        "permission": {"git": "allow"},
        "plugin": ["plugin-a", ["plugin-b", {"opt": True}]]
    }

    omp_bundle = app.export_to_omp(opencode_cfg=opencode_cfg, name="Test Profile")
    assert omp_bundle["format"] == "omp/v1"
    assert "ollama" in omp_bundle["providers"]
    assert "memory" in omp_bundle["mcp_servers"]
    assert "git" in omp_bundle["permissions"]

    # Import into OpenCode
    imported_oc = app.import_from_omp(omp_bundle, target="opencode")
    assert "ollama" in imported_oc["provider"]
    assert "memory" in imported_oc["mcp"]
    assert "git" in imported_oc["permission"]
    assert imported_oc["plugin"] == ["plugin-a", ["plugin-b", {"opt": True}]]

    # Import into OpenClaude Global
    imported_cl_global = app.import_from_omp(omp_bundle, target="openclaude_global")
    assert "memory" in imported_cl_global["mcpServers"]
    assert imported_cl_global["mcpServers"]["memory"]["command"] == "npx"

    # Import into OpenClaude Settings
    imported_cl_settings = app.import_from_omp(omp_bundle, target="openclaude_settings")
    assert "git" in imported_cl_settings["permissions"]["allow"]
