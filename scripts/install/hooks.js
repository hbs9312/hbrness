const fs = require('fs');
const path = require('path');
const {
  readSettings,
  backupSettings,
  writeSettings,
} = require('./settings.js');
const { parseJsonc } = require('./jsonc.js');
const { codexRoot } = require('./paths.js');

const SENTINEL = '_hbrness';

const HARNESS_ROOT_VAR = {
  claude: 'CLAUDE_PLUGIN_ROOT',
  codex: 'CODEX_PLUGIN_ROOT',
};

/** Read a plugin's hooks.json. Returns null if missing. Throws on parse error. */
function loadPluginHooks(pluginDir) {
  const hooksPath = path.join(pluginDir, 'hooks', 'hooks.json');
  if (!fs.existsSync(hooksPath)) return null;
  const raw = fs.readFileSync(hooksPath, 'utf8');
  try {
    return JSON.parse(raw);
  } catch (err) {
    throw new Error(`failed to parse ${hooksPath}: ${err.message}`);
  }
}

/** Replace ${VAR} occurrences inside a JSON-serializable object with `replacement`. */
function resolvePaths(obj, varName, replacement) {
  const pattern = new RegExp(`\\$\\{${varName}\\}`, 'g');
  // Round-trip through JSON so we substitute inside every string value at once.
  const replaced = JSON.stringify(obj).replace(pattern, () =>
    replacement.replace(/\\/g, '\\\\').replace(/"/g, '\\"'),
  );
  return JSON.parse(replaced);
}

/**
 * Where a harness keeps user-level hooks. Claude: ~/.claude/settings.json (hooks section).
 * Codex: ~/.codex/hooks.json ({"hooks": {...}}).
 */
function codexHooksPath() {
  return path.join(codexRoot(), 'hooks.json');
}

function readCodexHooks() {
  const file = codexHooksPath();
  if (!fs.existsSync(file)) return {};
  try {
    return parseJsonc(fs.readFileSync(file, 'utf8'));
  } catch (err) {
    throw new Error(`failed to parse ${file}: ${err.message}`);
  }
}

function backupCodexHooks() {
  const file = codexHooksPath();
  if (!fs.existsSync(file)) return null;
  const ts = new Date().toISOString().replace(/[:.]/g, '-').replace(/T/, '-').replace(/Z$/, '');
  const backupPath = `${file}.hbrness-bak.${ts}`;
  fs.copyFileSync(file, backupPath);
  return backupPath;
}

function writeCodexHooks(obj) {
  const file = codexHooksPath();
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp.${process.pid}.${Date.now()}`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + '\n', 'utf8');
  fs.renameSync(tmp, file);
}

function hookStore(harness) {
  if (harness === 'claude') {
    return { label: '~/.claude/settings.json', read: readSettings, backup: backupSettings, write: writeSettings };
  }
  if (harness === 'codex') {
    return { label: '~/.codex/hooks.json', read: readCodexHooks, backup: backupCodexHooks, write: writeCodexHooks };
  }
  return null;
}

/**
 * Codex may reject unknown keys in hooks.json, so ownership is a trailing shell comment on each
 * command instead of a sentinel key: `... # hbrness:<plugin>`.
 */
function codexMarker(plugin) {
  return ` # hbrness:${plugin}`;
}

function markOwnership(group, plugin, harness = 'claude') {
  if (harness === 'codex') {
    return {
      ...group,
      hooks: (group.hooks || []).map((h) =>
        typeof h.command === 'string' ? { ...h, command: h.command + codexMarker(plugin) } : h),
    };
  }
  return {
    ...group,
    [SENTINEL]: { plugin, installedAt: new Date().toISOString() },
  };
}

function isOwnedBy(group, plugin) {
  return Boolean(group && group[SENTINEL] && group[SENTINEL].plugin === plugin);
}

function isOwnedCommand(hook, plugin) {
  return Boolean(hook) && typeof hook.command === 'string' && hook.command.endsWith(codexMarker(plugin));
}

/**
 * Remove this plugin's hooks from one event's groups. Claude: whole groups carrying the sentinel.
 * Codex: only the commands carrying the marker — the user may have added their own command to the
 * same group; the group (matcher etc.) stays unless it ends up empty.
 * Returns { kept, removed } where removed counts groups (claude) or commands (codex).
 */
function stripOwned(groups, plugin, harness) {
  if (harness !== 'codex') {
    const kept = groups.filter((g) => !isOwnedBy(g, plugin));
    return { kept, removed: groups.length - kept.length };
  }
  const kept = [];
  let removed = 0;
  for (const g of groups) {
    if (!g || !Array.isArray(g.hooks)) {
      kept.push(g);
      continue;
    }
    const hooks = g.hooks.filter((h) => !isOwnedCommand(h, plugin));
    removed += g.hooks.length - hooks.length;
    if (hooks.length === g.hooks.length) kept.push(g);
    else if (hooks.length > 0) kept.push({ ...g, hooks });
  }
  return { kept, removed };
}

/**
 * Build a plan for installing a plugin's hooks into user settings.
 * Returns { supported, events: [{ event, groupCount }], resolvedHooks? }.
 * supported === false means the harness has no hook-merge strategy here.
 */
function planHooksInstall({ harness, plugin, pluginDir }) {
  if (!hookStore(harness)) {
    return {
      supported: false,
      reason: `hook merging is only implemented for claude and codex (not ${harness})`,
    };
  }
  const pluginHooks = loadPluginHooks(pluginDir);
  if (!pluginHooks || !pluginHooks.hooks) {
    return { supported: true, events: [], resolvedHooks: {} };
  }
  // Codex: only plugins that declare their own codex.hooks.json with {"_hbrness": {"merge": true}}.
  // Adapter-wide hooks (e.g. ghflow's template fetch) stay out of ~/.codex/hooks.json.
  if (harness === 'codex' && !(pluginHooks[SENTINEL] && pluginHooks[SENTINEL].merge === true)) {
    return { supported: true, events: [], resolvedHooks: {} };
  }
  const varName = HARNESS_ROOT_VAR[harness];
  const resolvedHooks = resolvePaths(pluginHooks.hooks, varName, pluginDir);
  const events = Object.entries(resolvedHooks).map(([event, groups]) => ({
    event,
    groupCount: Array.isArray(groups) ? groups.length : 0,
  }));
  return { supported: true, events, resolvedHooks };
}

/** Apply an install plan to user settings. Idempotent for the same plugin. */
function applyHooksInstall({ harness, plugin, pluginDir }, { dryRun = false } = {}) {
  const plan = planHooksInstall({ harness, plugin, pluginDir });
  if (!plan.supported) {
    return { status: 'unsupported', reason: plan.reason, events: [] };
  }
  if (plan.events.length === 0) {
    return { status: 'no-hooks', events: [] };
  }
  if (dryRun) {
    return { status: 'planned', events: plan.events };
  }

  const store = hookStore(harness);
  const settings = store.read();
  const backup = store.backup();
  settings.hooks = settings.hooks || {};

  for (const [event, groups] of Object.entries(plan.resolvedHooks)) {
    const existing = Array.isArray(settings.hooks[event])
      ? settings.hooks[event]
      : [];
    // Re-install semantics: drop prior hbrness entries for this plugin under this event, then append new.
    const { kept } = stripOwned(existing, plugin, harness);
    for (const g of groups) {
      kept.push(markOwnership(g, plugin, harness));
    }
    settings.hooks[event] = kept;
  }

  store.write(settings);
  return { status: 'installed', events: plan.events, backup, target: store.label };
}

/** Plan removing a plugin's hooks from user settings. */
function planHooksUninstall({ plugin, harness = 'claude' }) {
  const store = hookStore(harness);
  if (!store) return { events: [] };
  const settings = store.read();
  if (!settings.hooks) return { events: [] };
  const events = [];
  for (const [event, groups] of Object.entries(settings.hooks)) {
    if (!Array.isArray(groups)) continue;
    const { removed } = stripOwned(groups, plugin, harness);
    if (removed > 0) events.push({ event, groupCount: removed });
  }
  return { events };
}

/** Apply the removal of a plugin's hooks. */
function applyHooksUninstall({ plugin, harness = 'claude' }, { dryRun = false } = {}) {
  const store = hookStore(harness);
  if (!store) return { status: 'no-hooks', events: [] };
  const settings = store.read();
  if (!settings.hooks) return { status: 'no-hooks', events: [] };

  const events = [];
  const newHooks = {};
  for (const [event, groups] of Object.entries(settings.hooks)) {
    if (!Array.isArray(groups)) {
      newHooks[event] = groups;
      continue;
    }
    const { kept, removed } = stripOwned(groups, plugin, harness);
    if (removed > 0) events.push({ event, groupCount: removed });
    if (kept.length > 0) newHooks[event] = kept;
  }

  if (events.length === 0) return { status: 'no-match', events: [] };
  if (dryRun) return { status: 'planned', events };

  const backup = store.backup();
  settings.hooks = newHooks;
  store.write(settings);
  return { status: 'removed', events, backup, target: store.label };
}

module.exports = {
  SENTINEL,
  hookStore,
  codexHooksPath,
  loadPluginHooks,
  planHooksInstall,
  applyHooksInstall,
  planHooksUninstall,
  applyHooksUninstall,
};
