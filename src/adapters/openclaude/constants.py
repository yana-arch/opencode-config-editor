# openclaude config constants.
#
# VERIFIED sources (openclaude @gitlawb v0.28.0, 2026-08):
#   1. The shipped binary's SettingsSchema (zod) — superset of the official
#      Claude Code settings schema it embeds:
#      https://json.schemastore.org/claude-code-settings.json
#   2. openclaude docs (openclaude.gitlawb.com/docs/configuration/):
#      theme/verbose/autoUpdates live in the GLOBAL ~/.openclaude.json, not
#      settings.json; effortLevel/smartRouting/agentModels/agentRouting/
#      providerFallbackChain/advisorModel/subscriptionType/modelLimits are
#      real, documented settings keys.
#   3. Layered settings: user -> project -> local (later wins), plus a
#      highest-precedence read-only policy layer managed-settings.json
#      (/etc/claude-code on Linux).
#
# NOTE: keys here form the advisory known-key vocabulary for validation.
# The list is intentionally generous: unknown keys are preserved verbatim on
# save regardless of membership.

APP_NAME_OPENCLAUDE = "openclaude-config-editor"

# Official JSON Schema URL for settings.json (what openclaude itself writes
# into "$schema" for editor validation).
OPENCLAUDE_SETTINGS_SCHEMA_URL = "https://json.schemastore.org/claude-code-settings.json"

# Keys allowed in the layered settings.json files (user/project/local).
OPENCLAUDE_SETTINGS_KEYS = {
    "$schema", "advisorModel", "agent", "agentModels", "agentPushNotifEnabled",
    "agentRouting", "allowAllClaudeAiMcps", "allowManagedHooksOnly", "allowManagedMcpServersOnly", "allowManagedPermissionRulesOnly",
    "allowedChannelPlugins", "allowedHttpHookUrls", "allowedMcpServers", "alwaysThinkingEnabled", "apiKeyHelper",
    "askUserQuestionTimeout", "attribution", "autoCompactEnabled", "autoConnectIde", "autoDreamEnabled",
    "autoFix", "autoInstallIdeExtension", "autoMemoryDirectory", "autoMemoryEnabled", "autoMode",
    "autoScrollEnabled", "autoUpdatesChannel", "availableModels", "awaySummaryEnabled", "awsAuthRefresh",
    "awsCredentialExport", "axScreenReader", "blockedMarketplaces", "browserExternalPageTools", "channelsEnabled",
    "claudeMd", "claudeMdExcludes", "cleanupPeriodDays", "companyAnnouncements", "defaultShell",
    "deniedMcpServers", "diffTool", "disableAgentView", "disableAllHooks", "disableArtifact",
    "disableAutoMode", "disableBrowserExternalNavigation", "disableBundledSkills", "disableClaudeAiConnectors", "disableDeepLinkRegistration",
    "disableMobileSimulatorTools", "disableRemoteControl", "disableSideloadFlags", "disableSkillShellExecution", "disableWorkflows",
    "disabledMcpjsonServers", "editorMode", "effortLevel", "emojiCompletionEnabled", "enableAllProjectMcpServers",
    "enableArtifact", "enabledMcpjsonServers", "enabledPlugins", "enforceAvailableModels", "env",
    "externalEditorContext", "extraKnownMarketplaces", "fallbackModel", "fastMode", "fastModePerSessionOptIn",
    "feedbackSurveyRate", "fileCheckpointingEnabled", "fileSuggestion", "footerLinksRegexes", "forceLoginGatewayUrl",
    "forceLoginMethod", "forceLoginOrgUUID", "forceRemoteSettingsRefresh", "gcpAuthRefresh", "git",
    "hooks", "httpHookAllowedEnvVars", "includeCoAuthoredBy", "includeGitInstructions", "inputNeededNotifEnabled",
    "language", "managedMcpServers", "memory", "minimumVersion", "model",
    "modelLimits", "modelOverrides", "modelPricing", "otelHeadersHelper", "outputStyle",
    "parentSettingsBehavior", "permissionExplainerEnabled", "permissions", "plansDirectory", "pluginConfigs",
    "pluginSuggestionMarketplaces", "pluginTrustMessage", "policyHelper", "prUrlTemplate", "preferredNotifChannel",
    "prefersReducedMotion", "processWrapper", "promptSuggestionEnabled", "providerFallbackChain", "providerProfileModelPickerMode",
    "remote", "remoteControlAtStartup", "requireCoworkFullVmSandbox", "requiredMaximumVersion", "requiredMinimumVersion",
    "respectGitignore", "respondToBashCommands", "sandbox", "showClearContextOnPlanAccept", "showThinkingSummaries",
    "showTurnDuration", "skillListingBudgetFraction", "skillListingMaxDescChars", "skillOverrides", "skipDangerousModePermissionPrompt",
    "skipWebFetchPreflight", "skippedMarketplaces", "skippedPlugins", "smartRouting", "spinnerTipsEnabled",
    "spinnerTipsOverride", "spinnerVerbs", "sponsoredTipsEnabled", "sponsoredTipsFrequency", "sshConfigs",
    "sshHostAllowlist", "statusLine", "strictKnownMarketplaces", "strictPluginOnlyCustomization", "subagentStatusLine",
    "subscriptionType", "syntaxHighlightingDisabled", "teammateDefaultModel", "teammateMode", "terminalProgressBarEnabled",
    "terminalTitleFromRename", "theme", "tui", "useAutoModeDuringPlan", "verbose",
    "viewMode", "vimInsertModeRemaps", "voice", "voiceEnabled", "wheelScrollAccelerationEnabled",
    "workflowKeywordTriggerEnabled", "workflowSizeGuideline", "worktree", "wslInheritsWindowsSettings",
}

# Keys that live in the global ~/.openclaude.json. That file is mostly app
# STATE (numStartups, tipsHistory, projects, skillUsage, ...) which we
# preserve verbatim but never treat as config. These are the user-meaningful
# keys the editor understands:
OPENCLAUDE_GLOBAL_KEYS = {
    "$schema", "theme", "verbose", "autoUpdates",
    "providerProfiles", "activeProviderProfileId", "mcpServers",
}

# Value-bearing fields that hold secrets and must be masked in any UI / raw view.
OPENCLAUDE_SECRET_FIELDS = {"api_key", "apiKey", "token", "authToken"}

# Env dir override precedence (first set wins), default ~/.openclaude.
OPENCLAUDE_CONFIG_ENV = ("OPENCLAUDE_CONFIG_DIR", "CLAUDE_CONFIG_DIR")

# MCP server scopes and where each is stored.
OPENCLAUDE_MCP_SCOPES = ("user", "project", "local")
