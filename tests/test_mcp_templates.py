import pytest
from conftest import app


def test_mcp_registry_loaded():
    assert len(app.MCP_REGISTRY) >= 8
    tmpl = app.get_mcp_template("memory")
    assert tmpl is not None
    assert tmpl.name == "Memory (Knowledge Graph)"
    assert tmpl.transport_type == "local"


def test_instantiate_opencode_mcp_filesystem():
    tmpl = app.get_mcp_template("filesystem")
    assert tmpl is not None
    cfg = app.instantiate_opencode_mcp(
        tmpl, "my-fs", args_values={"allowed_directory": "/tmp/sandbox"}
    )
    assert cfg["type"] == "local"
    assert "/tmp/sandbox" in cfg["command"]
    assert cfg["enabled"] is True


def test_instantiate_openclaude_mcp_github():
    tmpl = app.get_mcp_template("github")
    assert tmpl is not None
    cfg = app.instantiate_openclaude_mcp(
        tmpl, "github", env_values={"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_secret123"}
    )
    assert cfg["command"] == "npx"
    assert cfg["args"] == ["-y", "@modelcontextprotocol/server-github"]
    assert cfg["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"] == "ghp_secret123"
