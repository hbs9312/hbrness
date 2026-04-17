const fs = require('fs');
const path = require('path');
const {
  distDir,
  harnessTargets,
  listBuiltPlugins,
  requirePluginBuilt,
} = require('./paths.js');
const hooksModule = require('./hooks.js');
const registry = require('./plugin-registry.js');

/**
 * Install modes:
 *  - "plugin"      : Claude only. Populates ~/.claude/plugins/cache/hbrness/<plugin>/<version>/
 *                    and registers in installed_plugins.json so /plugin list picks it up.
 *                    Namespaced invocation (`/ghflow:skill-name`).
 *  - "user-level"  : Symlink each skill/agent into ~/.<harness>/skills/<plugin>-<name>.
 *                    Hooks merged into settings.json for claude.
 *                    Hyphen-prefixed invocation (`/ghflow-skill-name`).
 *
 * Default: "plugin" for claude, "user-level" for codex.
 */

const MARKER_FILE = '.hbrness-origin';

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

function defaultMode(harness) {
  return harness === 'claude' ? 'plugin' : 'user-level';
}

function readPluginManifest(pluginDir) {
  const manifestPath = path.join(pluginDir, '.claude-plugin', 'plugin.json');
  if (!fs.existsSync(manifestPath)) {
    throw new Error(`plugin manifest missing: ${manifestPath}`);
  }
  const raw = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  if (!raw.name || !raw.version) {
    throw new Error(`plugin manifest ${manifestPath} missing name/version`);
  }
  return raw;
}

function scanSkillsAndAgents(pluginDir) {
  const items = [];
  const skillsDir = path.join(pluginDir, 'skills');
  if (fs.existsSync(skillsDir)) {
    for (const name of fs.readdirSync(skillsDir)) {
      const full = path.join(skillsDir, name);
      if (fs.statSync(full).isDirectory()) {
        items.push({ kind: 'skill', name, source: full });
      }
    }
  }
  const agentsDir = path.join(pluginDir, 'agents');
  if (fs.existsSync(agentsDir)) {
    for (const name of fs.readdirSync(agentsDir)) {
      const full = path.join(agentsDir, name);
      const stat = fs.statSync(full);
      if (stat.isDirectory()) {
        items.push({ kind: 'agent', name, source: full });
      }
    }
  }
  return items;
}

// ---------------------------------------------------------------------------
// Plugin mode (Claude only)
// ---------------------------------------------------------------------------

function collectAllBuiltPluginManifests(harness) {
  const out = [];
  for (const name of listBuiltPlugins(harness)) {
    const dir = path.join(distDir(harness), name);
    try {
      const manifest = readPluginManifest(dir);
      out.push({
        name,
        description: manifest.description || `${name} plugin`,
        sourceDir: dir,
      });
    } catch (_e) {
      // skip plugins missing a manifest
    }
  }
  return out;
}

function planInstallClaudePlugin({ plugin, pluginDir, autoRegister = false }) {
  const manifest = readPluginManifest(pluginDir);
  const version = manifest.version;
  const cacheTarget = registry.pluginCacheDir(plugin, version);
  const allPlugins = collectAllBuiltPluginManifests('claude');

  const ops = [
    {
      action: 'setup-marketplace',
      target: registry.marketplaceDir(),
      count: allPlugins.length,
      plugins: allPlugins,
    },
  ];

  if (autoRegister) {
    ops.push(
      { action: 'register-marketplace', target: registry.MARKETPLACES_PATH },
      { action: 'copy-plugin', target: cacheTarget, source: pluginDir, version },
      {
        action: 'register-plugin',
        target: registry.INSTALLED_PATH,
        plugin,
        version,
        installPath: cacheTarget,
      },
    );
  }

  return {
    ops,
    mode: 'plugin',
    targetDir: cacheTarget,
    version,
    autoRegister,
    marketplaceDir: registry.marketplaceDir(),
  };
}

function applyInstallClaudePlugin({ plan, results, dryRun }) {
  for (const op of plan.ops) {
    if (dryRun) {
      results.push({ ...op, status: 'planned' });
      continue;
    }
    try {
      if (op.action === 'setup-marketplace') {
        registry.setupMarketplaceContents(op.plugins);
        results.push({ ...op, status: 'refreshed' });
      } else if (op.action === 'register-marketplace') {
        const changed = registry.ensureMarketplaceEntry();
        results.push({ ...op, status: changed ? 'created' : 'exists' });
      } else if (op.action === 'copy-plugin') {
        copyPluginContents(op.source, op.target);
        results.push({ ...op, status: 'copied' });
      } else if (op.action === 'register-plugin') {
        registry.registerPlugin({
          plugin: op.plugin,
          version: op.version,
          installPath: op.installPath,
        });
        results.push({ ...op, status: 'registered' });
      }
    } catch (err) {
      results.push({ ...op, status: 'error', error: err.message });
    }
  }
}

function copyPluginContents(source, target) {
  if (fs.existsSync(target)) {
    fs.rmSync(target, { recursive: true, force: true });
  }
  fs.mkdirSync(target, { recursive: true });
  fs.cpSync(source, target, { recursive: true, dereference: true });
}

function planUninstallClaudePlugin({ plugin }) {
  const ops = [];
  if (registry.isPluginRegistered({ plugin })) {
    ops.push({
      action: 'unregister-plugin',
      target: registry.INSTALLED_PATH,
      plugin,
    });
  }
  // Remove the plugin's cache contents (all versions) from our marketplace.
  const pluginCacheRoot = path.join(registry.CACHE_ROOT, registry.DEFAULT_MARKETPLACE, plugin);
  if (fs.existsSync(pluginCacheRoot)) {
    ops.push({ action: 'remove-cache', target: pluginCacheRoot });
  }
  return { ops };
}

function applyUninstallClaudePlugin({ plan, results, dryRun }) {
  for (const op of plan.ops) {
    if (dryRun) {
      results.push({ ...op, status: 'planned' });
      continue;
    }
    try {
      if (op.action === 'unregister-plugin') {
        const ok = registry.unregisterPlugin({ plugin: op.plugin });
        results.push({ ...op, status: ok ? 'unregistered' : 'already-clean' });
      } else if (op.action === 'remove-cache') {
        fs.rmSync(op.target, { recursive: true, force: true });
        results.push({ ...op, status: 'removed' });
      }
    } catch (err) {
      results.push({ ...op, status: 'error', error: err.message });
    }
  }
  if (!dryRun) registry.removeMarketplaceIfEmpty();
}

// ---------------------------------------------------------------------------
// User-level mode (symlinks + hook merge)
// ---------------------------------------------------------------------------

function planInstallUserLevel({ harness, plugin, pluginDir }) {
  const targets = harnessTargets(harness);
  const ops = [];

  const items = scanSkillsAndAgents(pluginDir);
  if (items.length === 0) {
    ops.push({
      action: 'skip',
      target: pluginDir,
      reason: 'no skills or agents found',
    });
  }

  for (const item of items) {
    const targetRoot = item.kind === 'skill' ? targets.skills : targets.agents;
    if (!targetRoot) {
      ops.push({
        action: 'skip',
        target: item.source,
        reason: `${harness} does not support ${item.kind}`,
      });
      continue;
    }
    const linkName = `${plugin}-${item.name}`;
    const linkPath = path.join(targetRoot, linkName);
    ops.push({ action: 'mkdir', target: targetRoot });
    ops.push({
      action: 'link',
      target: linkPath,
      source: item.source,
      kind: item.kind,
      linkName,
    });
  }

  const hooksPlan = hooksModule.planHooksInstall({ harness, plugin, pluginDir });
  return { ops, mode: 'user-level', hooksPlan };
}

function applyInstallUserLevel({ plan, results, dryRun, skipHooks, harness, plugin, pluginDir }) {
  for (const op of plan.ops) {
    if (dryRun) {
      results.push({ ...op, status: 'planned' });
      continue;
    }
    try {
      if (op.action === 'mkdir') {
        ensureDir(op.target);
        results.push({ ...op, status: 'ok' });
      } else if (op.action === 'skip') {
        results.push({ ...op, status: 'skipped' });
      } else if (op.action === 'link') {
        replaceWithSymlink(op.target, op.source);
        results.push({ ...op, status: 'linked' });
      }
    } catch (err) {
      results.push({ ...op, status: 'error', error: err.message });
    }
  }

  if (!skipHooks && plan.hooksPlan && plan.hooksPlan.supported) {
    if (plan.hooksPlan.events.length > 0) {
      try {
        const hookRes = hooksModule.applyHooksInstall(
          { harness, plugin, pluginDir },
          { dryRun },
        );
        results.push({
          action: 'hooks',
          target: '~/.claude/settings.json',
          plugin,
          events: hookRes.events,
          backup: hookRes.backup,
          status: mapHookStatus(hookRes.status, dryRun),
        });
      } catch (err) {
        results.push({
          action: 'hooks',
          target: '~/.claude/settings.json',
          status: 'error',
          error: err.message,
        });
      }
    }
  }
}

function planUninstallUserLevel({ harness, plugin }) {
  const targets = harnessTargets(harness);
  const pluginDir = path.join(distDir(harness), plugin);
  const ops = [];

  const roots = new Set();
  if (targets.skills) roots.add(targets.skills);
  if (targets.agents) roots.add(targets.agents);

  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    for (const name of fs.readdirSync(root)) {
      if (!name.startsWith(`${plugin}-`)) continue;
      const linkPath = path.join(root, name);
      try {
        const stat = fs.lstatSync(linkPath);
        if (!stat.isSymbolicLink()) continue;
        const resolved = fs.readlinkSync(linkPath);
        const absResolved = path.isAbsolute(resolved)
          ? resolved
          : path.resolve(path.dirname(linkPath), resolved);
        if (absResolved.startsWith(pluginDir)) {
          ops.push({ action: 'unlink', target: linkPath });
        }
      } catch (_e) {
        // broken or inaccessible link — skip
      }
    }
  }

  const hooksPlan =
    harness === 'claude' ? hooksModule.planHooksUninstall({ plugin }) : { events: [] };

  return { ops, mode: 'user-level', hooksPlan };
}

function applyUninstallUserLevel({ plan, results, dryRun, skipHooks, harness, plugin }) {
  for (const op of plan.ops) {
    if (dryRun) {
      results.push({ ...op, status: 'planned' });
      continue;
    }
    try {
      if (op.action === 'unlink') {
        fs.unlinkSync(op.target);
        results.push({ ...op, status: 'removed' });
      }
    } catch (err) {
      results.push({ ...op, status: 'error', error: err.message });
    }
  }
  if (!skipHooks && harness === 'claude' && plan.hooksPlan && plan.hooksPlan.events.length > 0) {
    try {
      const hookRes = hooksModule.applyHooksUninstall({ plugin }, { dryRun });
      results.push({
        action: 'hooks',
        target: '~/.claude/settings.json',
        plugin,
        events: hookRes.events,
        backup: hookRes.backup,
        status: mapHookStatus(hookRes.status, dryRun),
      });
    } catch (err) {
      results.push({
        action: 'hooks',
        target: '~/.claude/settings.json',
        status: 'error',
        error: err.message,
      });
    }
  }
}

function mapHookStatus(status, _dryRun) {
  if (status === 'planned') return 'planned';
  if (status === 'installed') return 'merged';
  if (status === 'removed') return 'removed';
  if (status === 'no-hooks' || status === 'no-match') return 'skipped';
  if (status === 'unsupported') return 'skipped';
  return status;
}

function replaceWithSymlink(target, source) {
  let prior = null;
  try {
    prior = fs.lstatSync(target);
  } catch (_e) {
    // target doesn't exist — proceed
  }
  if (prior) {
    if (prior.isSymbolicLink()) {
      fs.unlinkSync(target);
    } else if (prior.isDirectory()) {
      const marker = path.join(target, MARKER_FILE);
      if (fs.existsSync(marker)) {
        fs.rmSync(target, { recursive: true, force: true });
      } else {
        throw new Error(
          `refusing to overwrite non-hbrness directory at ${target} (no ${MARKER_FILE} marker)`,
        );
      }
    } else {
      fs.unlinkSync(target);
    }
  }
  fs.symlinkSync(source, target, 'dir');
}

// ---------------------------------------------------------------------------
// Public API (dispatching on mode)
// ---------------------------------------------------------------------------

function planInstall({ harness, plugin, mode, autoRegister = false }) {
  const pluginDir = requirePluginBuilt(harness, plugin);
  const resolvedMode = mode || defaultMode(harness);
  // Codex does not have a plugin system we target; force user-level.
  const effectiveMode = harness === 'codex' ? 'user-level' : resolvedMode;

  if (effectiveMode === 'plugin') {
    const inner = planInstallClaudePlugin({ plugin, pluginDir, autoRegister });
    return {
      harness,
      plugin,
      pluginDir,
      mode: 'plugin',
      ops: inner.ops,
      targetDir: inner.targetDir,
      version: inner.version,
      autoRegister: inner.autoRegister,
      marketplaceDir: inner.marketplaceDir,
    };
  }

  const inner = planInstallUserLevel({ harness, plugin, pluginDir });
  return {
    harness,
    plugin,
    pluginDir,
    mode: 'user-level',
    ops: inner.ops,
    hooksPlan: inner.hooksPlan,
  };
}

function applyPlan(plan, { dryRun = false, skipHooks = false } = {}) {
  const results = [];

  // Migration: if the opposite mode has leftovers for this plugin, clean them
  // before applying the new install. Keeps /plugin list and ~/.claude/skills/
  // from drifting into an inconsistent duplicate state.
  if (plan.harness === 'claude') {
    if (plan.mode === 'plugin') {
      const ulPlan = planUninstallUserLevel({ harness: 'claude', plugin: plan.plugin });
      const hasUlWork =
        ulPlan.ops.length > 0 || (ulPlan.hooksPlan?.events?.length || 0) > 0;
      if (hasUlWork) {
        applyUninstallUserLevel({
          plan: ulPlan,
          results,
          dryRun,
          skipHooks: false,
          harness: 'claude',
          plugin: plan.plugin,
        });
      }
    } else if (plan.mode === 'user-level') {
      const pPlan = planUninstallClaudePlugin({ plugin: plan.plugin });
      if (pPlan.ops.length > 0) {
        applyUninstallClaudePlugin({ plan: pPlan, results, dryRun });
      }
    }
  }

  if (plan.mode === 'plugin') {
    applyInstallClaudePlugin({ plan, results, dryRun });
  } else {
    applyInstallUserLevel({
      plan,
      results,
      dryRun,
      skipHooks,
      harness: plan.harness,
      plugin: plan.plugin,
      pluginDir: plan.pluginDir,
    });
  }
  return results;
}

/**
 * Uninstall always cleans both modes so migration and legacy removal Just Work.
 */
function planUninstall({ harness, plugin }) {
  const userLevel = planUninstallUserLevel({ harness, plugin });
  const plugin_ =
    harness === 'claude' ? planUninstallClaudePlugin({ plugin }) : { ops: [] };

  const hasWork = userLevel.ops.length + plugin_.ops.length + (userLevel.hooksPlan?.events?.length || 0) > 0;
  if (!hasWork) {
    return {
      harness,
      plugin,
      mode: 'cleanup',
      ops: [
        {
          action: 'skip',
          target: plugin,
          reason: 'no hbrness installation found',
        },
      ],
      hooksPlan: userLevel.hooksPlan,
      pluginRegistryOps: plugin_.ops,
    };
  }

  return {
    harness,
    plugin,
    mode: 'cleanup',
    ops: userLevel.ops,
    hooksPlan: userLevel.hooksPlan,
    pluginRegistryOps: plugin_.ops,
  };
}

function applyUninstall(plan, { dryRun = false, skipHooks = false } = {}) {
  const results = [];
  applyUninstallUserLevel({
    plan,
    results,
    dryRun,
    skipHooks,
    harness: plan.harness,
    plugin: plan.plugin,
  });

  if (plan.harness === 'claude' && plan.pluginRegistryOps && plan.pluginRegistryOps.length > 0) {
    applyUninstallClaudePlugin({
      plan: { ops: plan.pluginRegistryOps },
      results,
      dryRun,
    });
  }
  return results;
}

function listInstalled(harness) {
  const found = [];

  // Plugin-mode (Claude only): read from installed_plugins.json
  if (harness === 'claude') {
    const cacheRoot = path.join(registry.CACHE_ROOT, registry.DEFAULT_MARKETPLACE);
    for (const entry of registry.listRegisteredPlugins()) {
      if (!entry.installPath) continue;
      const rel = entry.installPath.startsWith(cacheRoot)
        ? entry.installPath.slice(cacheRoot.length + 1)
        : entry.installPath;
      found.push({
        harness,
        plugin: entry.plugin,
        name: `@${entry.version}`,
        kind: 'plugin',
        linkPath: entry.installPath,
        source: rel,
        mode: 'plugin',
      });
    }
  }

  // User-level mode: scan symlinks
  const targets = harnessTargets(harness);
  const dist = distDir(harness);
  const roots = new Set();
  if (targets.skills) roots.add(targets.skills);
  if (targets.agents) roots.add(targets.agents);
  const distWithSep = dist.endsWith(path.sep) ? dist : dist + path.sep;

  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    for (const name of fs.readdirSync(root)) {
      const full = path.join(root, name);
      let stat;
      try {
        stat = fs.lstatSync(full);
      } catch (_e) {
        continue;
      }
      if (!stat.isSymbolicLink()) continue;
      let resolved;
      try {
        resolved = fs.readlinkSync(full);
      } catch (_e) {
        continue;
      }
      const absResolved = path.isAbsolute(resolved)
        ? resolved
        : path.resolve(path.dirname(full), resolved);
      if (!absResolved.startsWith(distWithSep)) continue;

      const tail = absResolved.slice(distWithSep.length);
      const parts = tail.split(path.sep).filter(Boolean);
      if (parts.length < 3) continue;
      const plugin = parts[0];
      const kindSegment = parts[1];
      const sourceName = parts.slice(2).join(path.sep);
      const kind =
        kindSegment === 'agents'
          ? 'agent'
          : kindSegment === 'skills'
          ? 'skill'
          : kindSegment;

      found.push({
        harness,
        plugin,
        name: sourceName,
        kind,
        linkPath: full,
        source: absResolved,
        mode: 'user-level',
      });
    }
  }
  return found;
}

module.exports = {
  planInstall,
  applyPlan,
  planUninstall,
  applyUninstall,
  listInstalled,
  listBuiltPlugins,
  defaultMode,
};
