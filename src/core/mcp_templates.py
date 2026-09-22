# MCP Server Templates and Hub Catalog
# ---------------------------------------------------------------------------
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MCPTemplate:
    id: str
    name: str
    category: str  # "Memory & Context", "System & Files", "Developer Tools", "Data & Web", "Database"
    description: str
    transport_type: str  # "local" | "remote"
    command: List[str] = field(default_factory=list)
    url: str = ""
    env_keys: Dict[str, str] = field(default_factory=dict)  # key -> placeholder/hint
    default_args: List[str] = field(default_factory=list)
    doc_url: str = ""


MCP_REGISTRY: List[MCPTemplate] = [
    MCPTemplate(
        id="memory",
        name="Memory (Knowledge Graph)",
        category="Memory & Context",
        description="Persistent memory and knowledge graph storage across AI sessions using official MCP memory server.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-memory"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/memory",
    ),
    MCPTemplate(
        id="filesystem",
        name="Filesystem Access",
        category="System & Files",
        description="Secure file system access to read, write, and list files within specified directories.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "{allowed_directory}"],
        default_args=["/path/to/allowed/directory"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
    ),
    MCPTemplate(
        id="github",
        name="GitHub Integration",
        category="Developer Tools",
        description="Search repositories, view code, inspect pull requests, and manage issues directly on GitHub.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-github"],
        env_keys={"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxxxxxxxxxx"},
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/github",
    ),
    MCPTemplate(
        id="brave-search",
        name="Brave Search",
        category="Data & Web",
        description="Web search and local business search via Brave Search API for live internet knowledge.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-brave-search"],
        env_keys={"BRAVE_API_KEY": "BSAxxxxxxxxxxxx"},
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search",
    ),
    MCPTemplate(
        id="fetch",
        name="Web Page Fetcher",
        category="Data & Web",
        description="Fetch web pages, extract content, and convert HTML to clean markdown for reading.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-fetch"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/fetch",
    ),
    MCPTemplate(
        id="postgres",
        name="PostgreSQL Inspector",
        category="Database",
        description="Read-only or read/write schema inspection and querying for PostgreSQL databases.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-postgres", "{connection_string}"],
        default_args=["postgresql://user:password@localhost:5432/my_database"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
    ),
    MCPTemplate(
        id="sqlite",
        name="SQLite Explorer",
        category="Database",
        description="Inspect tables, query schemas, and run SQL on local SQLite database files.",
        transport_type="local",
        command=["uvx", "mcp-server-sqlite", "--db-path", "{db_path}"],
        default_args=["/path/to/database.db"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/sqlite",
    ),
    MCPTemplate(
        id="puppeteer",
        name="Puppeteer Browser",
        category="Data & Web",
        description="Headless browser automation to interact with dynamic web pages, take screenshots, and execute JavaScript.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-puppeteer"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/puppeteer",
    ),
    MCPTemplate(
        id="git",
        name="Git Tools",
        category="Developer Tools",
        description="Query repository status, commit history, diffs, and inspect branches.",
        transport_type="local",
        command=["uvx", "mcp-server-git", "--repository", "{repo_path}"],
        default_args=["/path/to/repo"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/git",
    ),
    MCPTemplate(
        id="sequential-thinking",
        name="Sequential Thinking",
        category="Memory & Context",
        description="Dynamic, multi-step structured reasoning tool for complex problem solving and debugging.",
        transport_type="local",
        command=["npx", "-y", "@modelcontextprotocol/server-sequential-thinking"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/sequential-thinking",
    ),
    MCPTemplate(
        id="context7",
        name="Context7 Docs & Libraries",
        category="Developer Tools",
        description="Up-to-date documentation and API reference lookup engine for popular libraries.",
        transport_type="local",
        command=["npx", "-y", "context7-mcp"],
        doc_url="https://context7.com",
    ),
    MCPTemplate(
        id="remote-sse",
        name="Generic Remote MCP (SSE/HTTP)",
        category="Custom & Remote",
        description="Connect to any remote or hosted MCP server via Server-Sent Events (SSE) or HTTP endpoint.",
        transport_type="remote",
        url="https://mcp.example.com/sse",
        doc_url="https://modelcontextprotocol.io",
    ),
]


def get_mcp_template(template_id: str) -> Optional[MCPTemplate]:
    """Retrieve template by its ID."""
    for tmpl in MCP_REGISTRY:
        if tmpl.id == template_id:
            return tmpl
    return None


def instantiate_opencode_mcp(
    template: MCPTemplate,
    server_key: str,
    args_values: Optional[Dict[str, str]] = None,
    env_values: Optional[Dict[str, str]] = None,
    url_value: str = "",
) -> Dict[str, Any]:
    """Create OpenCode format config for an MCP server."""
    args_values = args_values or {}
    env_values = env_values or {}

    if template.transport_type == "remote":
        res: Dict[str, Any] = {
            "type": "remote",
            "url": url_value.strip() or template.url,
            "enabled": True,
        }
        return res

    cmd_list = []
    for part in template.command:
        formatted = part
        for k, v in args_values.items():
            formatted = formatted.replace(f"{{{k}}}", v.strip())
        cmd_list.append(formatted)

    config: Dict[str, Any] = {
        "type": "local",
        "command": cmd_list,
        "enabled": True,
    }
    clean_env = {k: v.strip() for k, v in env_values.items() if v.strip()}
    if clean_env:
        config["env"] = clean_env

    return config


def instantiate_openclaude_mcp(
    template: MCPTemplate,
    server_key: str,
    args_values: Optional[Dict[str, str]] = None,
    env_values: Optional[Dict[str, str]] = None,
    url_value: str = "",
) -> Dict[str, Any]:
    """Create OpenClaude / Claude Code format config for an MCP server (mcpServers entry)."""
    args_values = args_values or {}
    env_values = env_values or {}

    if template.transport_type == "remote":
        return {
            "type": "sse",
            "url": url_value.strip() or template.url,
        }

    cmd_list = []
    for part in template.command:
        formatted = part
        for k, v in args_values.items():
            formatted = formatted.replace(f"{{{k}}}", v.strip())
        cmd_list.append(formatted)

    if not cmd_list:
        return {}

    command = cmd_list[0]
    args = cmd_list[1:]

    config: Dict[str, Any] = {
        "command": command,
        "args": args,
    }
    clean_env = {k: v.strip() for k, v in env_values.items() if v.strip()}
    if clean_env:
        config["env"] = clean_env

    return config
