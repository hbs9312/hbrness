const os = require('os');
const path = require('path');
const fs = require('fs');

/** Package root (the hbrness install location — npm global, local clone, or node_modules). */
function pkgRoot() {
  return path.resolve(__dirname, '..', '..');
}

/** Built dist directory for a harness: <pkgRoot>/dist/<harness>. */
function distDir(harness) {
  return path.join(pkgRoot(), 'dist', harness);
}

/** Harness-specific user config roots. */
function claudeRoot() {
  return path.join(os.homedir(), '.claude');
}
function codexRoot() {
  return path.join(os.homedir(), '.codex');
}

/** Where we drop namespaced items into the harness config. */
function harnessTargets(harness) {
  if (harness === 'claude') {
    const root = claudeRoot();
    return {
      skills: path.join(root, 'skills'),
      agents: path.join(root, 'agents'),
      commands: path.join(root, 'commands'),
      hooks: path.join(root, 'hooks'),
    };
  }
  if (harness === 'codex') {
    const root = codexRoot();
    return {
      skills: path.join(root, 'skills'),
      agents: path.join(root, 'skills'), // codex flattens agents next to skills
      commands: null,
      hooks: path.join(root, 'hooks'),
    };
  }
  throw new Error(`unsupported harness: ${harness}`);
}

/** List plugins present in dist for a given harness. */
function listBuiltPlugins(harness) {
  const dir = distDir(harness);
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .sort();
}

/** Validate a plugin exists in dist; throw with a hint if not. */
function requirePluginBuilt(harness, plugin) {
  const pluginDir = path.join(distDir(harness), plugin);
  if (!fs.existsSync(pluginDir)) {
    const available = listBuiltPlugins(harness);
    const hint = available.length
      ? `available: ${available.join(', ')}`
      : `run "npm run build" first (no dist for ${harness})`;
    throw new Error(`plugin not built: ${harness}/${plugin} — ${hint}`);
  }
  return pluginDir;
}

module.exports = {
  pkgRoot,
  distDir,
  claudeRoot,
  codexRoot,
  harnessTargets,
  listBuiltPlugins,
  requirePluginBuilt,
};
