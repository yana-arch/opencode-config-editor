# openclaude config constants: top-level keys for settings.json and the global
# ~/.openclaude.json. Derived from openclaude docs (see
# .planning/openclaude-config-notes.md); no official JSON Schema confirmed yet.

APP_NAME_OPENCLAUDE = "openclaude-config-editor"

# Keys allowed in the layered settings.json files (user/project/local).
OPENCLAUDE_SETTINGS_KEYS = {
    "$schema", "model", "effortLevel", "agent", "permissions", "env", "hooks",
    "smartRouting", "modelLimits", "providerFallbackChain", "agentModels",
    "agentRouting", "advisorModel", "subscriptionType",
}

# Keys that live in the global ~/.openclaude.json (not settings.json).
OPENCLAUDE_GLOBAL_KEYS = {
    "$schema", "theme", "verbose", "autoUpdates",
}

# Value-bearing fields that hold secrets and must be masked in any UI / raw view.
OPENCLAUDE_SECRET_FIELDS = {"api_key", "apiKey", "token", "authToken"}

# Env dir override precedence (first set wins), default ~/.openclaude.
OPENCLAUDE_CONFIG_ENV = ("OPENCLAUDE_CONFIG_DIR", "CLAUDE_CONFIG_DIR")
