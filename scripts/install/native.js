// Local plugin installation for Grok Build and Devin CLI. Never registers in
// Devin Cloud and never changes another harness's settings or marketplace.
const fs = require('fs');
const path = require('path');
const cp = require('child_process');
const { harnessTargets } = require('./paths.js');

const MARKER = '.hbrness-origin';
const supports = (harness) => ['grok', 'devin'].includes(harness);

function targetFor(harness, plugin) {
  if (!supports(harness) || !/^[a-z0-9][a-z0-9-]*$/.test(plugin)) {
    throw new Error(`invalid native plugin: ${harness}/${plugin}`);
  }
  return path.join(harnessTargets(harness).plugins, plugin);
}

function receipt(target) {
  try {
    if (fs.lstatSync(target).isSymbolicLink()) return null;
    const value = JSON.parse(fs.readFileSync(path.join(target, MARKER), 'utf8'));
    return value.installer === 'hbrness' ? value : null;
  } catch (_) { return null; }
}

function assertOwned(target, harness, plugin) {
  if (!fs.existsSync(target) && !fs.lstatSync(target, { throwIfNoEntry: false })) return;
  const owner = receipt(target);
  if (!owner || owner.harness !== harness || owner.plugin !== plugin) {
    throw new Error(`refusing to replace non-hbrness plugin at ${target}`);
  }
}

function planInstall({ harness, plugin, pluginDir }) {
  const target = targetFor(harness, plugin);
  assertOwned(target, harness, plugin);
  return {
    harness, plugin, pluginDir, target, mode: 'plugin',
    ops: [
      { action: 'install-native-plugin', source: pluginDir, target },
      ...(harness === 'devin' ? [{ action: 'devin-local-register', target }] : []),
    ],
  };
}

// Tokens occur inside double-quoted shell arguments in skill code blocks and
// hook commands. Escape shell metacharacters instead of interpolating raw paths.
function shellPath(value) { return value.replace(/[\\"$`]/g, '\\$&'); }

function renderTree(stage, target, skipHooks) {
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) { walk(file); continue; }
      const rel = path.relative(stage, file);
      if (skipHooks && (rel === 'hooks.json' || rel === path.join('hooks', 'hooks.json'))) {
        fs.unlinkSync(file);
        continue;
      }
      if (!/\.(md|json)$/.test(file)) continue;
      const skillDir = path.join(target, path.dirname(rel));
      const replace = (s) => s
        .replaceAll('{HBRNESS_PLUGIN_PATH}', shellPath(target))
        .replaceAll('{HBRNESS_SKILL_PATH}', shellPath(skillDir));
      let text = fs.readFileSync(file, 'utf8');
      if (file.endsWith('.json')) {
        const visit = (v) => typeof v === 'string' ? replace(v)
          : Array.isArray(v) ? v.map(visit)
          : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, visit(x)])) : v;
        text = JSON.stringify(visit(JSON.parse(text)), null, 2) + '\n';
      } else { text = replace(text); }
      fs.writeFileSync(file, text);
    }
  }
  walk(stage);
}

function devin(args) {
  const result = cp.spawnSync('devin', ['plugins', ...args], {
    encoding: 'utf8', timeout: 30000, maxBuffer: 1024 * 1024,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (result.error || result.status !== 0) {
    throw new Error(`devin plugins ${args[0]} failed: ${result.error?.message || result.stderr || result.stdout || result.status}`);
  }
}

function install(plan, { dryRun = false, skipHooks = false } = {}) {
  if (dryRun) return plan.ops.map((op) => ({ ...op, status: 'planned' }));
  const { harness, plugin, pluginDir, target } = plan;
  let stage, backup;
  let promoted = false;
  try {
    assertOwned(target, harness, plugin);
    const parent = path.dirname(path.dirname(target));
    const staging = path.join(parent, '.hbrness-staging');
    fs.mkdirSync(staging, { recursive: true });
    stage = fs.mkdtempSync(path.join(staging, `${plugin}-`));
    fs.cpSync(pluginDir, stage, { recursive: true, dereference: true });
    renderTree(stage, target, skipHooks);
    const manifestDir = harness === 'devin' ? '.devin-plugin' : '.claude-plugin';
    const manifest = JSON.parse(fs.readFileSync(path.join(stage, manifestDir, 'plugin.json'), 'utf8'));
    if (manifest.name !== plugin) throw new Error('plugin manifest name does not match installation target');
    fs.writeFileSync(path.join(stage, MARKER), JSON.stringify({
      installer: 'hbrness', harness, plugin, version: manifest.version,
      source: pluginDir, skipHooks, installedAt: new Date().toISOString(),
    }, null, 2) + '\n');
    fs.mkdirSync(path.dirname(target), { recursive: true });
    if (fs.existsSync(target)) {
      const backupRoot = path.join(parent, 'hbrness-backups');
      fs.mkdirSync(backupRoot, { recursive: true });
      backup = path.join(backupRoot, `${plugin}-${Date.now()}-${process.pid}`);
      fs.renameSync(target, backup);
    }
    fs.renameSync(stage, target);
    stage = null;
    promoted = true;
    if (harness === 'devin') devin(['install', '--local', '--yes', target]);
    return [{ action: 'install-native-plugin', target, status: 'installed', backup }];
  } catch (error) {
    if (promoted) fs.rmSync(target, { recursive: true, force: true });
    if (backup && fs.existsSync(backup)) fs.renameSync(backup, target);
    return [{ action: 'install-native-plugin', target, status: 'error', error: error.message }];
  } finally {
    if (stage) fs.rmSync(stage, { recursive: true, force: true });
  }
}

function planUninstall({ harness, plugin }) {
  const target = targetFor(harness, plugin);
  assertOwned(target, harness, plugin);
  return { harness, plugin, target, mode: 'plugin', ops: [{ action: 'remove-native-plugin', target }] };
}

function uninstall(plan, { dryRun = false } = {}) {
  if (dryRun) return plan.ops.map((op) => ({ ...op, status: 'planned' }));
  try {
    assertOwned(plan.target, plan.harness, plan.plugin);
    if (!fs.existsSync(plan.target)) return [{ action: 'remove-native-plugin', target: plan.target, status: 'already-clean' }];
    if (plan.harness === 'devin') devin(['remove', '--local', '--yes', plan.plugin]);
    fs.rmSync(plan.target, { recursive: true });
    return [{ action: 'remove-native-plugin', target: plan.target, status: 'removed' }];
  } catch (error) {
    return [{ action: 'remove-native-plugin', target: plan.target, status: 'error', error: error.message }];
  }
}

function listInstalled(harness) {
  const root = harnessTargets(harness).plugins;
  if (!fs.existsSync(root)) return [];
  return fs.readdirSync(root).flatMap((plugin) => {
    const target = path.join(root, plugin);
    const r = receipt(target);
    return r && r.harness === harness && r.plugin === plugin ? [{
      harness, plugin, name: `@${r.version}`, kind: 'plugin', linkPath: target,
      source: r.source, mode: 'plugin',
    }] : [];
  });
}

function diagnose(harness) {
  const issues = [];
  for (const item of listInstalled(harness)) {
    const check = (dir) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const file = path.join(dir, entry.name);
        if (entry.isDirectory()) check(file);
        else if (/\.(md|json)$/.test(file) && /\{HBRNESS_(PLUGIN|SKILL)_PATH\}/.test(fs.readFileSync(file, 'utf8'))) {
          issues.push({ type: 'unresolved-runtime-path', severity: 'error', harness, plugin: item.plugin, detail: file });
        }
      }
    };
    check(item.linkPath);
  }
  return issues;
}

module.exports = { supports, planInstall, install, planUninstall, uninstall, listInstalled, diagnose };
