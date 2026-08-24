from tests.conftest import app

def test_openclaude_findings_root_object():
    err, warn = app.openclaude_findings([], "user")
    assert "Root must be a JSON object" in err[0]

def test_openclaude_findings_mcp_servers_shape():
    data = {"mcpServers": "not-a-dict"}
    err, warn = app.openclaude_findings(data, "global")
    assert "'mcpServers' must be an object" in err[0]

    data = {"mcpServers": {"srv1": "not-a-dict"}}
    err, warn = app.openclaude_findings(data, "global")
    assert "mcpServers['srv1'] must be an object" in err[0]

def test_openclaude_findings_mcp_type_warning():
    data = {"mcpServers": {"srv1": {"type": "unknown-transport"}}}
    err, warn = app.openclaude_findings(data, "global")
    assert not err
    assert "type 'unknown-transport' is not one of" in warn[0]

def test_openclaude_findings_project_mcp_unknown_keys():
    data = {"mcpServers": {}, "unexpected": 123}
    err, warn = app.openclaude_findings(data, "project-mcp")
    assert not err
    assert "unknown .mcp.json key(s): unexpected" in warn[0]

def test_openclaude_findings_hooks_shape():
    data = {"hooks": {"pre-repo": "not-a-list"}}
    err, warn = app.openclaude_findings(data, "user")
    assert "hooks['pre-repo'] must be an array" in err[0]

def test_openclaude_findings_permissions_shape():
    data = {"permissions": {"allow": "not-a-list"}}
    err, warn = app.openclaude_findings(data, "user")
    assert "permissions.allow must be an array" in err[0]

def test_openclaude_findings_env_type_warning():
    data = {"env": {"DEBUG": 123}}
    err, warn = app.openclaude_findings(data, "user")
    assert "env['DEBUG'] should be a string" in warn[0]

def test_openclaude_findings_unknown_settings_keys():
    data = {"model": "gpt-4o", "ghostKey": True}
    err, warn = app.openclaude_findings(data, "user")
    assert "unknown settings key(s): ghostKey" in warn[0]
