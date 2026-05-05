const fs = require('fs');
const path = require('path');
const { distDir, harnessTargets } = require('./paths.js');
const { readSettings, SETTINGS_PATH } = require('./settings.js');
const { SENTINEL } = require('./hooks.js');
const codexLocalPlugin = require('./codex-local-plugin.js');

const CODEX_CACHE_MARKER_FILE = '.hbrness-origin';

/**
 * Issue shape:
 *   {
 *     type: string,              // dangling-symlink | stale-hook-path | stale-backup
 *     severity: 'error'|'warn'|'info',
 *     harness?: string,
 *     plugin?: string,
 *     detail: string,            // single-line human summary
 *     fix?: { action, ... }      // describes repair op; absent for info-only
 *   }
 */

function diagnose({ harnesses = ['claude', 'codex'] } = {}) {
  const issues = [];
  for (const harness of harnesses) {
    issues.push(...scanSymlinks(harness));
  }
  if (harnesses.includes('claude')) {
    issues.push(...scanHooks());
    issues.push(...scanBackups());
  }
  if (harnesses.includes('codex')) {
    issues.push(...scanCodexLocalPlugins());
  }
  return issues;
}

function scanSymlinks(harness) {
  const issues = [];
  const targets = harnessTargets(harness);
  const dist = distDir(harness);
  const distWithSep = dist.endsWith(path.sep) ? dist : dist + path.sep;

  const roots = new Set();
  if (targets.skills) roots.add(targets.skills);
  if (targets.agents) roots.add(targets.agents);

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

      const isOurs = absResolved.startsWith(distWithSep);
      if (!isOurs) continue; // someone else's symlink — leave alone

      const targetExists = fs.existsSync(absResolved);
      if (!targetExists) {
        const tail = absResolved.slice(distWithSep.length).split(path.sep);
        const plugin = tail[0] || '?';
        issues.push({
          type: 'dangling-symlink',
          severity: 'error',
          harness,
          plugin,
          detail: `${full} → ${absResolved} (target missing)`,
          fix: { action: 'unlink', target: full },
        });
      }
    }
  }
  return issues;
}

function scanHooks() {
  const issues = [];
  let settings;
  try {
    settings = readSettings();
  } catch (err) {
    issues.push({
      type: 'settings-parse-error',
      severity: 'error',
      detail: `cannot parse ${SETTINGS_PATH}: ${err.message}`,
    });
    return issues;
  }
  if (!settings.hooks) return issues;

  for (const [event, groups] of Object.entries(settings.hooks)) {
    if (!Array.isArray(groups)) continue;
    groups.forEach((g, i) => {
      if (!g || !g[SENTINEL]) return;
      const plugin = g[SENTINEL].plugin;
      const hookCmds = Array.isArray(g.hooks) ? g.hooks : [];
      for (const hc of hookCmds) {
        if (hc.type !== 'command' || typeof hc.command !== 'string') continue;
        const filePath = extractScriptPath(hc.command);
        if (filePath && !fs.existsSync(filePath)) {
          issues.push({
            type: 'stale-hook-path',
            severity: 'error',
            plugin,
            detail: `hook ${event}[${i}] (${plugin}) references missing file: ${filePath}`,
            fix: {
              action: 'remove-hook-group',
              plugin,
              event,
              sentinelKey: SENTINEL,
            },
          });
          return; // one error per group is enough
        }
      }
    });
  }
  return issues;
}

/** Best-effort parse of the file path out of a hook command string. */
function extractScriptPath(cmd) {
  // "python3 \"/abs/path/script.py\""  → /abs/path/script.py
  const quoted = cmd.match(/"([^"]+)"/);
  if (quoted) return quoted[1];
  // bare: /abs/path/script.sh arg1 arg2
  const parts = cmd.trim().split(/\s+/);
  for (const p of parts) {
    if (p.startsWith('/') || p.startsWith('~')) return p.replace(/^~/, require('os').homedir());
  }
  return null;
}

function scanBackups() {
  const issues = [];
  const dir = path.dirname(SETTINGS_PATH);
  if (!fs.existsSync(dir)) return issues;
  const names = fs.readdirSync(dir).filter((n) => n.startsWith('settings.json.hbrness-bak.'));
  if (names.length > 10) {
    issues.push({
      type: 'stale-backup',
      severity: 'info',
      detail: `${names.length} settings backups present in ${dir} (consider pruning older ones)`,
      fix: { action: 'prune-backups', dir, keep: 5, names },
    });
  }
  return issues;
}

function scanCodexLocalPlugins() {
  const issues = [];
  const config = readCodexConfig();
  const hookPlugins = enabledHbrnessCodexHookPlugins(config);
  if (hookPlugins.length === 0) return issues;

  for (const feature of ['codex_hooks', 'plugin_hooks']) {
    if (config.features[feature] !== true) {
      issues.push({
        type: 'codex-feature-disabled',
        severity: 'error',
        harness: 'codex',
        detail: `~/.codex/config.toml must set [features] ${feature} = true for plugin hooks`,
        fix: {
          action: 'reinstall-codex-plugin',
          plugin: hookPlugins[0].plugin,
          pluginDir: hookPlugins[0].pluginDir,
        },
      });
    }
  }

  for (const entry of hookPlugins) {
    issues.push(...scanCodexPluginInstall(entry));
  }
  return issues;
}

function enabledHbrnessCodexHookPlugins(config) {
  const out = [];
  const codexDist = distDir('codex');
  for (const section of config.plugins) {
    if (!section.enabled) continue;
    if (section.marketplace !== codexLocalPlugin.MARKETPLACE_NAME) continue;
    const pluginDir = path.join(codexDist, section.plugin);
    if (!fs.existsSync(path.join(pluginDir, 'hooks.json'))) continue;
    out.push({
      plugin: section.plugin,
      marketplace: section.marketplace,
      pluginDir,
    });
  }
  return out;
}

function scanCodexPluginInstall(entry) {
  const issues = [];
  const { plugin, marketplace, pluginDir } = entry;
  const manifest = readJsonSafe(path.join(pluginDir, '.codex-plugin', 'plugin.json'), {});
  const version = String(manifest.version || '0.0.0');
  const fix = { action: 'reinstall-codex-plugin', plugin, pluginDir };

  const localLink = path.join(codexLocalPlugin.USER_PLUGINS_DIR, plugin);
  if (!isSymlinkTo(localLink, pluginDir)) {
    issues.push({
      type: 'codex-local-plugin-link',
      severity: 'warn',
      harness: 'codex',
      plugin,
      detail: `${localLink} should symlink to ${pluginDir}`,
      fix,
    });
  }

  const marketplaceIssue = scanCodexMarketplaceEntry(plugin, marketplace, fix);
  if (marketplaceIssue) issues.push(marketplaceIssue);

  const cacheRoot = path.join(codexLocalPlugin.CODEX_PLUGIN_CACHE_DIR, marketplace, plugin);
  const cachePath = path.join(cacheRoot, version);
  const cacheStat = lstatOrNull(cachePath);
  if (!cacheStat) {
    issues.push({
      type: 'codex-plugin-cache-missing',
      severity: 'error',
      harness: 'codex',
      plugin,
      detail: `Codex plugin cache missing: ${cachePath}`,
      fix,
    });
    return issues;
  }
  if (cacheStat.isSymbolicLink()) {
    issues.push({
      type: 'codex-plugin-cache-symlink',
      severity: 'error',
      harness: 'codex',
      plugin,
      detail: `Codex plugin cache must be a real directory, not a symlink: ${cachePath}`,
      fix,
    });
    return issues;
  }
  if (!cacheStat.isDirectory()) {
    issues.push({
      type: 'codex-plugin-cache-invalid',
      severity: 'error',
      harness: 'codex',
      plugin,
      detail: `Codex plugin cache is not a directory: ${cachePath}`,
      fix,
    });
    return issues;
  }
  if (!fs.existsSync(path.join(cachePath, CODEX_CACHE_MARKER_FILE))) {
    issues.push({
      type: 'codex-plugin-cache-unmarked',
      severity: 'warn',
      harness: 'codex',
      plugin,
      detail: `Codex plugin cache is not marked as hbrness-managed: ${cachePath}`,
      fix,
    });
  }

  const cachedManifest = readJsonSafe(path.join(cachePath, '.codex-plugin', 'plugin.json'), null);
  if (!cachedManifest || cachedManifest.hooks !== './hooks.json') {
    issues.push({
      type: 'codex-plugin-manifest-hooks',
      severity: 'error',
      harness: 'codex',
      plugin,
      detail: `Codex cached manifest must contain "hooks": "./hooks.json": ${cachePath}`,
      fix,
    });
  }

  const hooksPath = path.join(cachePath, 'hooks.json');
  const hooks = readJsonSafe(hooksPath, null);
  if (!hooks) {
    issues.push({
      type: 'codex-plugin-cache-hooks-missing',
      severity: 'error',
      harness: 'codex',
      plugin,
      detail: `Codex cached hooks.json is missing or invalid: ${hooksPath}`,
      fix,
    });
    return issues;
  }

  for (const command of collectHookCommands(hooks)) {
    if (hasPluginRelativePath(command)) {
      issues.push({
        type: 'codex-hook-relative-path',
        severity: 'error',
        harness: 'codex',
        plugin,
        detail: `Codex hook command must use absolute plugin paths because hooks run from workspace cwd: ${command}`,
        fix,
      });
      continue;
    }
    const scriptPath = extractScriptPath(command);
    if (scriptPath && !fs.existsSync(scriptPath)) {
      issues.push({
        type: 'codex-hook-missing-script',
        severity: 'error',
        harness: 'codex',
        plugin,
        detail: `Codex hook command references missing file: ${scriptPath}`,
        fix,
      });
    }
  }

  return issues;
}

function scanCodexMarketplaceEntry(plugin, marketplace, fix) {
  const payload = readJsonSafe(codexLocalPlugin.MARKETPLACE_PATH, null);
  const found = payload
    && payload.name === marketplace
    && Array.isArray(payload.plugins)
    && payload.plugins.some((p) => p && p.name === plugin && p.source && p.source.path === `./plugins/${plugin}`);
  if (found) return null;
  return {
    type: 'codex-marketplace-entry',
    severity: 'warn',
    harness: 'codex',
    plugin,
    detail: `${codexLocalPlugin.MARKETPLACE_PATH} should contain ${plugin}@${marketplace}`,
    fix,
  };
}

function readCodexConfig() {
  const filePath = codexLocalPlugin.CODEX_CONFIG_PATH;
  const raw = fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : '';
  const plugins = [];
  const features = {};
  let current = null;

  for (const line of raw.split('\n')) {
    const trimmed = line.trim();
    const pluginMatch = trimmed.match(/^\[plugins\."([^"]+)"\]$/);
    if (pluginMatch) {
      const key = pluginMatch[1];
      const at = key.lastIndexOf('@');
      current = {
        type: 'plugin',
        key,
        plugin: at === -1 ? key : key.slice(0, at),
        marketplace: at === -1 ? 'unknown' : key.slice(at + 1),
        enabled: false,
      };
      plugins.push(current);
      continue;
    }
    if (trimmed === '[features]') {
      current = { type: 'features' };
      continue;
    }
    if (/^\[/.test(trimmed)) {
      current = null;
      continue;
    }
    const kv = trimmed.match(/^([A-Za-z0-9_.-]+)\s*=\s*(true|false)\s*$/);
    if (!kv || !current) continue;
    if (current.type === 'plugin' && kv[1] === 'enabled') {
      current.enabled = kv[2] === 'true';
    } else if (current.type === 'features') {
      features[kv[1]] = kv[2] === 'true';
    }
  }
  return { plugins, features };
}

function readJsonSafe(filePath, fallback) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (_e) {
    return fallback;
  }
}

function lstatOrNull(filePath) {
  try {
    return fs.lstatSync(filePath);
  } catch (_e) {
    return null;
  }
}

function isSymlinkTo(linkPath, targetPath) {
  const stat = lstatOrNull(linkPath);
  if (!stat || !stat.isSymbolicLink()) return false;
  const link = fs.readlinkSync(linkPath);
  const resolved = path.isAbsolute(link) ? link : path.resolve(path.dirname(linkPath), link);
  return resolved === targetPath;
}

function collectHookCommands(value, out = []) {
  if (Array.isArray(value)) {
    for (const item of value) collectHookCommands(item, out);
    return out;
  }
  if (!value || typeof value !== 'object') return out;
  for (const [key, child] of Object.entries(value)) {
    if (key === 'command' && typeof child === 'string') out.push(child);
    else collectHookCommands(child, out);
  }
  return out;
}

function hasPluginRelativePath(command) {
  return /(^|[\s"'])\.\/(hooks|scripts|assets|bin)\//.test(command);
}

/**
 * Apply repair fixes for a list of issues.
 * Returns { results: [{ issue, status, error? }] }
 */
function repair(issues, { dryRun = false } = {}) {
  const results = [];
  const repairedCodexPlugins = new Set();
  // Re-read settings once; we'll flush at most once at the end.
  let settingsMutated = false;
  let settings = null;
  const loadSettings = () => {
    if (!settings) settings = readSettings();
    return settings;
  };

  for (const issue of issues) {
    if (!issue.fix) {
      results.push({ issue, status: 'no-fix' });
      continue;
    }
    try {
      if (dryRun) {
        results.push({ issue, status: 'planned' });
        continue;
      }
      if (issue.fix.action === 'unlink') {
        fs.unlinkSync(issue.fix.target);
        results.push({ issue, status: 'fixed' });
      } else if (issue.fix.action === 'remove-hook-group') {
        const s = loadSettings();
        if (!s.hooks || !Array.isArray(s.hooks[issue.fix.event])) {
          results.push({ issue, status: 'already-clean' });
          continue;
        }
        const before = s.hooks[issue.fix.event].length;
        s.hooks[issue.fix.event] = s.hooks[issue.fix.event].filter(
          (g) =>
            !(g && g[issue.fix.sentinelKey] && g[issue.fix.sentinelKey].plugin === issue.fix.plugin),
        );
        const after = s.hooks[issue.fix.event].length;
        if (s.hooks[issue.fix.event].length === 0) {
          delete s.hooks[issue.fix.event];
        }
        if (before !== after) settingsMutated = true;
        results.push({ issue, status: before !== after ? 'fixed' : 'already-clean' });
      } else if (issue.fix.action === 'prune-backups') {
        const sorted = issue.fix.names
          .slice()
          .sort()
          .reverse(); // newest first (ISO stamp sorts lexicographically)
        const toKeep = new Set(sorted.slice(0, issue.fix.keep));
        let pruned = 0;
        for (const name of issue.fix.names) {
          if (toKeep.has(name)) continue;
          fs.unlinkSync(path.join(issue.fix.dir, name));
          pruned += 1;
        }
        results.push({ issue, status: pruned > 0 ? 'fixed' : 'already-clean', pruned });
      } else if (issue.fix.action === 'reinstall-codex-plugin') {
        if (repairedCodexPlugins.has(issue.fix.plugin)) {
          results.push({ issue, status: 'already-clean' });
          continue;
        }
        const plan = codexLocalPlugin.planInstall({
          plugin: issue.fix.plugin,
          pluginDir: issue.fix.pluginDir,
        });
        const ops = codexLocalPlugin.applyInstall(plan, { dryRun: false });
        const failed = ops.find((op) => op.status === 'error');
        if (failed) throw new Error(failed.error || `failed to reinstall ${issue.fix.plugin}`);
        repairedCodexPlugins.add(issue.fix.plugin);
        results.push({ issue, status: 'fixed', operations: ops.length });
      } else {
        results.push({ issue, status: 'unknown-fix' });
      }
    } catch (err) {
      results.push({ issue, status: 'error', error: err.message });
    }
  }

  if (settingsMutated && !dryRun) {
    const { backupSettings, writeSettings } = require('./settings.js');
    const backup = backupSettings();
    writeSettings(settings);
    return { results, backup };
  }
  return { results };
}

module.exports = { diagnose, repair };
