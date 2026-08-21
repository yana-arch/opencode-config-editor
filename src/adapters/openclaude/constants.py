# openclaude config constants: top-level keys for settings.json and the global
# ~/.openclaude.json.
#
# Verified against openclaude v0.28.0 (@gitlawb/openclaude) and a live install:
#   - settings.json (user/project) real keys: model, env, hooks, statusLine,
#     modelLimits, permissions, skipDangerousModePermissionPrompt,
#     skipFullAccessModePermissionPrompt, plus common Claude-Code-compatible
#     keys (outputStyle, cleanupPeriodDays, includeCoAuthoredBy,
#     autoCompactEnabled, apiKeyHelper, enableAllProjectMcpServers).
#   - settings.local.json commonly holds `permissions`.
#   - A 4th, highest-precedence policy layer `managed-settings.json` exists
#     (enterprise/MDM) — read-only, not edited here.
#   - Global ~/.openclaude.json is mostly app STATE; the user-meaningful keys
#     are providerProfiles, activeProviderProfileId, mcpServers.
#   - `agentModels`/`agentRouting` appear once in the README but are absent from
#     the shipped binary and live config; kept only for lenient back-compat.
#   - `effortLevel`, `advisorModel`, `smartRouting`, `providerFallbackChain`,
#     `subscriptionType` could NOT be confirmed in v0.28.0 (absent from binary,
#     README, and live config) — treat as unverified/legacy.

APP_NAME_OPENCLAUDE = "openclaude-config-editor"

# Keys allowed in the layered settings.json files (user/project/local).
OPENCLAUDE_SETTINGS_KEYS = {
    "$schema", "model", "agent", "permissions", "env", "hooks",
    "statusLine", "modelLimits",
    "skipDangerousModePermissionPrompt", "skipFullAccessModePermissionPrompt",
    "outputStyle", "cleanupPeriodDays", "includeCoAuthoredBy",
    "autoCompactEnabled", "apiKeyHelper", "enableAllProjectMcpServers",
    # Unverified against v0.28.0 but tolerated for back-compat:
    "effortLevel", "advisorModel", "smartRouting", "providerFallbackChain",
    "agentModels", "agentRouting", "subscriptionType",
}

# Keys that live in the global ~/.openclaude.json (user-meaningful subset;
# the file also stores app state like numStartups/tipsHistory which we preserve
# verbatim but do not treat as config).
OPENCLAUDE_GLOBAL_KEYS = {
    "$schema", "providerProfiles", "activeProviderProfileId", "mcpServers",
}

# Value-bearing fields that hold secrets and must be masked in any UI / raw view.
OPENCLAUDE_SECRET_FIELDS = {"api_key", "apiKey", "token", "authToken"}

# Env dir override precedence (first set wins), default ~/.openclaude.
OPENCLAUDE_CONFIG_ENV = ("OPENCLAUDE_CONFIG_DIR", "CLAUDE_CONFIG_DIR")
