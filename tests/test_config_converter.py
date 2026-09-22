import pytest
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
            "env": {"DEBUG": "1"},
        },
        "remote_srv": {
            "type": "remote",
            "url": "https://example.com/sse",
        }
    }
    claude_mcp = app.opencode_mcp_to_claude_mcp(opencode_mcp)
    assert claude_mcp["memory"]["command"] == "npx"
    assert claude_mcp["memory"]["args"] == ["-y", "@modelcontextprotocol/server-memory"]
    assert claude_mcp["memory"]["env"] == {"DEBUG": "1"}
    assert claude_mcp["remote_srv"]["type"] == "sse"
    assert claude_mcp["remote_srv"]["url"] == "https://example.com/sse"

    # Convert back
    back = app.claude_mcp_to_opencode_mcp(claude_mcp)
    assert back["memory"]["type"] == "local"
    assert back["memory"]["command"] == ["npx", "-y", "@modelcontextprotocol/server-memory"]
    assert back["remote_srv"]["type"] == "remote"
    assert back["remote_srv"]["url"] == "https://example.com/sse"


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
