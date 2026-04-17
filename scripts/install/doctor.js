const fs = require('fs');
const path = require('path');
const { distDir, harnessTargets } = require('./paths.js');
const { readSettings, SETTINGS_PATH } = require('./settings.js');
const { SENTINEL } = require('./hooks.js');

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

/**
 * Apply repair fixes for a list of issues.
 * Returns { results: [{ issue, status, error? }] }
 */
function repair(issues, { dryRun = false } = {}) {
  const results = [];
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
