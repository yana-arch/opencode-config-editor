# openclaude config notes (research capture)

Source: github.com/Gitlawb/openclaude README + openclaude.gitlawb.com/docs/configuration/
(fetched during this project). Anything not directly confirmed is marked UNVERIFIED.

## File locations & precedence

Settings merge order: **user -> project -> local** (later overrides earlier).

| File | Scope | Notes |
|---|---|---|
| `~/.openclaude/settings.json` | user | global default for all projects; moved under `OPENCLAUDE_CONFIG_DIR` when set |
| `.openclaude/settings.json` | project | committed to repo |
| `.openclaude/settings.local.json` | local | per-machine overrides, usually gitignored |
| `~/.openclaude.json` | global | `theme`, `verbose`, `autoUpdates` live here — NOT in settings.json |
| `~/.openclaude/keybindings.json` | user | keyboard overrides |
| `CLAUDE.md` / `.claude/CLAUDE.md` | project | instructions loaded at session start |

Env dir overrides (first set wins): `OPENCLAUDE_CONFIG_DIR`, then legacy `CLAUDE_CONFIG_DIR`; default `~/.openclaude`.

UNVERIFIED: exact relationship between `~/.openclaude/` (dir) and `~/.openclaude.json` (file)
when `OPENCLAUDE_CONFIG_DIR` is set — docs are ambiguous on whether the global file also moves.

## Format

`settings.json` appears to be strict JSON (Claude Code lineage). UNVERIFIED whether JSONC
(comments) is accepted. Do NOT assume JSON5 — that is OpenClaw (a different product).

## settings.json top-level keys

| key | type/shape | description |
|---|---|---|
| `model` | str | default model (alias or full id) |
| `effortLevel` | str | low/medium/high/xhigh/max |
| `agent` | str | default agent for new sessions |
| `permissions` | obj | allow/deny rules + default permission mode |
| `env` | obj{str:str} | env vars applied to every session |
| `hooks` | obj | shell hooks on tool events (PreToolUse, PostToolUse, …) |
| `smartRouting` | obj{enabled,simpleModel,strongModel} | opt-in auto-routing |
| `modelLimits` | obj{model:{contextWindow,maxOutputTokens}} | per-model overrides |
| `providerFallbackChain` | list[str] | ordered provider profile ids for rate-limit fallback |
| `agentModels` | obj{key:{base_url,api_key,model}} | cross-provider agent routing connections |
| `agentRouting` | obj{agentId:modelKey} | map agent -> agentModels key; `default` = fallback |
| `advisorModel` | str | advisor model for server-side advisor tool |
| `subscriptionType` | str | free/pro/max/team/enterprise (user settings only) |

Global `~/.openclaude.json`: `theme`, `verbose`, `autoUpdates`.

## Official schema

No published JSON Schema file confirmed. `openclaude config schema` MAY print one (UNVERIFIED).
Plan: derive known-keys set from the list above until a schema is confirmed.

## opencode -> openclaude concept mapping

| opencode | openclaude | notes |
|---|---|---|
| `provider` (base_url/api_key/models) | `agentModels` {key:{base_url,api_key,model}} | VERIFIED: lives in the **global `~/.openclaude.json`** (docs/agent-routing.md, docs/smart-routing.md) |
| `agent` | `agent` + `agentRouting` | agentRouting also in `~/.openclaude.json` |
| `permission` | `permissions` | similar allow/deny |
| `model` / `small_model` | `model` + `smartRouting.simpleModel/strongModel` | scalar `model` in settings.json |
| `mcp` | (UNVERIFIED) | no confirmed settings.json key for MCP |
| `plugin` | (none confirmed) | |
| — | `hooks`, `env`, `modelLimits`, `providerFallbackChain`, `effortLevel` | openclaude-only |

### VERIFIED via MCP (context7 /gitlawb/openclaude + docs)

- Providers = `agentModels`, and `agentModels`/`agentRouting`/`smartRouting`
  are configured in the **global `~/.openclaude.json`** file
  (docs/agent-routing.md, docs/smart-routing.md). `agentModels` may ALSO appear
  in `~/.openclaude/settings.json` (issue #1119) — the editor writes providers
  to the global file, which is the documented primary location.
- OpenClaude keeps its own config dir `~/.openclaude` and does NOT read legacy
  Claude paths (README "config cutover").
- Session metadata/logs under the resolved config dir, e.g. `~/.openclaude/bg-sessions/`.

## Security

`agentModels[*].api_key` is stored in **plaintext** in settings.json. The editor MUST mask
these fields and must never commit them. Same for any token-bearing values.

## VERIFIED against a live install (openclaude @gitlawb v0.28.0)

Inspected the shipped binary (`dist/cli.mjs`) and a real config on disk.
This supersedes the doc-derived guesses above where they conflict.

### Settings layers (confirmed)
- `~/.openclaude/settings.json` (user), `.openclaude/settings.json` (project),
  `.openclaude/settings.local.json` (local) — later wins. CONFIRMED.
- **NEW: `managed-settings.json`** is a 4th, HIGHEST-precedence policy layer
  (enterprise/MDM, read via `getManagedFilePath()`; ~130 `policySettings` refs,
  `strictPluginOnlyCustomization`, etc.). Read-only; the editor does not write
  it but the effective-merge view is technically incomplete without it.

### Real `settings.json` keys (from a live file)
`model`, `env`, `hooks`, `statusLine`, `modelLimits`,
`skipDangerousModePermissionPrompt`, `skipFullAccessModePermissionPrompt`;
`permissions` typically in `settings.local.json`. Common CC-compatible keys
also honored: `outputStyle`, `cleanupPeriodDays`, `includeCoAuthoredBy`,
`autoCompactEnabled`, `apiKeyHelper`, `enableAllProjectMcpServers`.

### Global `~/.openclaude.json` (CORRECTION)
It is NOT `{theme, verbose, autoUpdates}`. It is mostly **app state**
(`numStartups`, `tipsHistory`, `projects`, `skillUsage`, `firstStartTime`, …).
User-meaningful keys: **`providerProfiles`** (list of
`{id,name,provider,baseUrl,model[,apiKey]}`), **`activeProviderProfileId`**
(selects the active profile; default = ANTHROPIC_DEFAULT_PROFILE), and
**`mcpServers`**. => The editor must NOT rewrite this file unless a provider
field actually changed (implemented: per-tab `_dirty` guard).

### CORRECTION (schema extraction, later session)
The earlier literal-grep conclusion "could not be confirmed" for effortLevel,
advisorModel, smartRouting, providerFallbackChain, agentModels, agentRouting,
subscriptionType was WRONG (minification defeated the grep). Extracting
SettingsSchema from dist/cli.mjs shows ALL of them are real settings keys.
Likewise docs confirm theme/verbose/autoUpdates DO belong in the global
~/.openclaude.json. The full key vocabulary now comes from:
  - SettingsSchema in dist/cli.mjs (zod), which extends
  - https://json.schemastore.org/claude-code-settings.json ($schema URL that
    openclaude itself writes; 142 top-level props) + openclaude extensions.
constants.py OPENCLAUDE_SETTINGS_KEYS is generated from that union (159 keys).

### Editor gaps still open
- No `managed-settings.json` in the effective/inherited view.
- `mcpServers` (global) not editable via form (Raw only).
- Form still lacks `statusLine`/`modelLimits`/permission-mode/env/hooks editors.

## MCP scopes + Plugins surface (verified v0.28.0, drives the editor tabs)

### MCP — 4 storage locations
| scope | file | key |
|---|---|---|
| user | `~/.openclaude.json` | `mcpServers` |
| project | `<cwd>/.mcp.json` | `mcpServers` (atomic tmp+rename, preserves file mode) |
| local | `~/.openclaude.json` | `projects[file dict].mcpServers` (project key = normalized cwd, backslashes→"/") |
| policy | `<managed>/managed-mcp.json` | read-only |

Server shape: `{type: "stdio"|"http", command|url, env?, headers?, args?, ...}`
(unknown sub-keys must be preserved). CLI: `openclaude mcp add --transport
stdio|http [-e K=V] [--header K:V] name ...`.
Gating settings keys: `enableAllProjectMcpServers` (bool),
`enabled/disabledMcpjsonServers` (string arrays; approval of .mcp.json),
`allowed/deniedMcpServers` (object lists — enterprise, Raw only).

### Policy layer
managed dir per platform: `/etc/claude-code`,
`/Library/Application Support/ClaudeCode`, `C:\Program Files\ClaudeCode`.
Policy = managed-settings.json merged with sorted `managed-settings.d/*.json`
drop-ins; highest precedence in effective view. Editor reads it read-only.

### Plugins / marketplaces (settings.json keys)
- `enabledPlugins`: {"plugin-id@marketplace-id": true|false|["version"]}.
- `extraKnownMarketplaces`: {name: {source: {source:"github"|"git"|"url"|"npm"|
  "file"|"directory"|..., repo/url/path/package, ref?, headers?},
  installLocation?, autoUpdate?}}. Field mapping per source type matters.
- `blockedMarketplaces`: array of source OBJECTS (Raw only).
- Official marketplace: claude-plugins-official (github anthropics/
  claude-plugins-official); plugin cache at <configdir>/plugins.
- CLI: `openclaude plugin install/uninstall/enable/disable/update`, group
  `marketplace`.

### Other config files (targets)
`<configdir>/keybindings.json` (KeybindingsSchema), output styles under the
config dir (`output-styles/`), CLAUDE.md project instructions.
