const fs = require('fs');
const path = require('path');
const {
  readSettings,
  backupSettings,
  writeSettings,
} = require('./settings.js');

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

function markOwnership(group, plugin) {
  return {
    ...group,
    [SENTINEL]: { plugin, installedAt: new Date().toISOString() },
  };
}

function isOwnedBy(group, plugin) {
  return (
    group &&
    group[SENTINEL] &&
    group[SENTINEL].plugin === plugin
  );
}

/**
 * Build a plan for installing a plugin's hooks into user settings.
 * Returns { supported, events: [{ event, groupCount }], resolvedHooks? }.
 * supported === false means the harness has no hook-merge strategy here.
 */
function planHooksInstall({ harness, plugin, pluginDir }) {
  if (harness !== 'claude') {
    return {
      supported: false,
      reason: `hook merging is only implemented for claude (not ${harness})`,
    };
  }
  const pluginHooks = loadPluginHooks(pluginDir);
  if (!pluginHooks || !pluginHooks.hooks) {
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

  const settings = readSettings();
  const backup = backupSettings();
  settings.hooks = settings.hooks || {};

  for (const [event, groups] of Object.entries(plan.resolvedHooks)) {
    const existing = Array.isArray(settings.hooks[event])
      ? settings.hooks[event]
      : [];
    // Re-install semantics: drop prior hbrness entries for this plugin under this event, then append new.
    const kept = existing.filter((g) => !isOwnedBy(g, plugin));
    for (const g of groups) {
      kept.push(markOwnership(g, plugin));
    }
    settings.hooks[event] = kept;
  }

  writeSettings(settings);
  return { status: 'installed', events: plan.events, backup };
}

/** Plan removing a plugin's hooks from user settings. */
function planHooksUninstall({ plugin }) {
  const settings = readSettings();
  if (!settings.hooks) return { events: [] };
  const events = [];
  for (const [event, groups] of Object.entries(settings.hooks)) {
    if (!Array.isArray(groups)) continue;
    const matched = groups.filter((g) => isOwnedBy(g, plugin)).length;
    if (matched > 0) events.push({ event, groupCount: matched });
  }
  return { events };
}

/** Apply the removal of a plugin's hooks. */
function applyHooksUninstall({ plugin }, { dryRun = false } = {}) {
  const settings = readSettings();
  if (!settings.hooks) return { status: 'no-hooks', events: [] };

  const events = [];
  const newHooks = {};
  for (const [event, groups] of Object.entries(settings.hooks)) {
    if (!Array.isArray(groups)) {
      newHooks[event] = groups;
      continue;
    }
    const kept = [];
    let removed = 0;
    for (const g of groups) {
      if (isOwnedBy(g, plugin)) {
        removed += 1;
      } else {
        kept.push(g);
      }
    }
    if (removed > 0) events.push({ event, groupCount: removed });
    if (kept.length > 0) newHooks[event] = kept;
  }

  if (events.length === 0) return { status: 'no-match', events: [] };
  if (dryRun) return { status: 'planned', events };

  const backup = backupSettings();
  settings.hooks = newHooks;
  writeSettings(settings);
  return { status: 'removed', events, backup };
}

module.exports = {
  SENTINEL,
  loadPluginHooks,
  planHooksInstall,
  applyHooksInstall,
  planHooksUninstall,
  applyHooksUninstall,
};
