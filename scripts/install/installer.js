const fs = require('fs');
const path = require('path');
const {
  distDir,
  harnessTargets,
  listBuiltPlugins,
  requirePluginBuilt,
} = require('./paths.js');

/**
 * Install plan item shape:
 *   { action: 'link' | 'unlink' | 'mkdir' | 'skip',
 *     target: string, source?: string, reason?: string }
 */

const MARKER_FILE = '.hbrness-origin';

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
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

/**
 * Build an install plan for a single plugin. Plan is a list of operations;
 * no filesystem mutation happens here.
 */
function planInstall({ harness, plugin }) {
  const pluginDir = requirePluginBuilt(harness, plugin);
  const targets = harnessTargets(harness);
  const ops = [];

  const items = scanSkillsAndAgents(pluginDir);
  if (items.length === 0) {
    return {
      harness,
      plugin,
      pluginDir,
      ops: [
        {
          action: 'skip',
          target: pluginDir,
          reason: 'no skills or agents found',
        },
      ],
    };
  }

  for (const item of items) {
    const targetRoot =
      item.kind === 'skill' ? targets.skills : targets.agents;
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

  return { harness, plugin, pluginDir, ops };
}

/**
 * Apply a plan to the filesystem. Idempotent: re-linking is safe.
 */
function applyPlan(plan, { dryRun = false } = {}) {
  const results = [];
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
  return results;
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
      // Only remove if it looks like one of ours (has marker) or is empty
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

/**
 * Build an uninstall plan: remove our symlinks for a given plugin.
 */
function planUninstall({ harness, plugin }) {
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
        // Only remove if it points inside our dist for this plugin
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

  if (ops.length === 0) {
    ops.push({
      action: 'skip',
      target: pluginDir,
      reason: 'no hbrness symlinks found',
    });
  }

  return { harness, plugin, ops };
}

function applyUninstall(plan, { dryRun = false } = {}) {
  const results = [];
  for (const op of plan.ops) {
    if (dryRun) {
      results.push({ ...op, status: 'planned' });
      continue;
    }
    try {
      if (op.action === 'unlink') {
        fs.unlinkSync(op.target);
        results.push({ ...op, status: 'removed' });
      } else if (op.action === 'skip') {
        results.push({ ...op, status: 'skipped' });
      }
    } catch (err) {
      results.push({ ...op, status: 'error', error: err.message });
    }
  }
  return results;
}

/**
 * List installed hbrness items for a harness by scanning symlink targets.
 * Plugin/name is inferred from the symlink's resolved target path
 * (dist/<harness>/<plugin>/skills|agents/<name>), not from the link's own name.
 */
function listInstalled(harness) {
  const targets = harnessTargets(harness);
  const dist = distDir(harness);
  const found = [];
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
      // Expect: <plugin>/skills|agents/<name>
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
};
