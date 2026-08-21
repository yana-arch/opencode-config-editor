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
| `provider` (base_url/api_key/models) | `agentModels` {key:{base_url,api_key,model}} | closest analog |
| `agent` | `agent` + `agentRouting` | routing is separate |
| `permission` | `permissions` | similar allow/deny |
| `model` / `small_model` | `model` + `smartRouting.simpleModel/strongModel` | |
| `mcp` | (UNVERIFIED) | no confirmed settings.json key for MCP |
| `plugin` | (none confirmed) | |
| — | `hooks`, `env`, `modelLimits`, `providerFallbackChain`, `effortLevel` | openclaude-only |

## Security

`agentModels[*].api_key` is stored in **plaintext** in settings.json. The editor MUST mask
these fields and must never commit them. Same for any token-bearing values.
