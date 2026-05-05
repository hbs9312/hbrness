const fs = require('fs');
const os = require('os');
const path = require('path');
const { loadPluginHooks } = require('./hooks.js');
const { pkgRoot } = require('./paths.js');

const MARKETPLACE_NAME = 'hbrness';
const MARKETPLACE_PATH = path.join(os.homedir(), '.agents', 'plugins', 'marketplace.json');
const USER_PLUGINS_DIR = path.join(os.homedir(), 'plugins');
const CODEX_PLUGIN_CACHE_DIR = path.join(os.homedir(), '.codex', 'plugins', 'cache');
const CODEX_CONFIG_PATH = path.join(os.homedir(), '.codex', 'config.toml');
const CACHE_MARKER_FILE = '.hbrness-origin';

function hasHooks(pluginDir) {
  const hooks = loadPluginHooks(pluginDir);
  return !!(hooks && hooks.hooks && Object.keys(hooks.hooks).length > 0);
}

function readJson(filePath, fallback) {
  if (!fs.existsSync(filePath)) return fallback;
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function writeJsonAtomic(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tmp = `${filePath}.tmp.${process.pid}.${Date.now()}`;
  fs.writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  fs.renameSync(tmp, filePath);
}

function defaultMarketplace() {
  return {
    name: MARKETPLACE_NAME,
    interface: { displayName: 'hbrness' },
    plugins: [],
  };
}

function readMarketplace() {
  const marketplace = readJson(MARKETPLACE_PATH, defaultMarketplace());
  if (!marketplace.name) marketplace.name = MARKETPLACE_NAME;
  if (!marketplace.interface) marketplace.interface = { displayName: marketplace.name };
  if (!Array.isArray(marketplace.plugins)) marketplace.plugins = [];
  return marketplace;
}

function marketplaceEntry(plugin) {
  return {
    name: plugin,
    source: {
      source: 'local',
      path: `./plugins/${plugin}`,
    },
    policy: {
      installation: 'AVAILABLE',
      authentication: 'ON_INSTALL',
    },
    category: 'Coding',
  };
}

function readPluginVersion(pluginDir) {
  const manifestPath = path.join(pluginDir, '.codex-plugin', 'plugin.json');
  const manifest = readJson(manifestPath, {});
  return String(manifest.version || '0.0.0');
}

function upsertMarketplacePlugin(plugin) {
  const marketplace = readMarketplace();
  const entry = marketplaceEntry(plugin);
  marketplace.plugins = marketplace.plugins.filter((p) => p && p.name !== plugin);
  marketplace.plugins.push(entry);
  marketplace.plugins.sort((a, b) => a.name.localeCompare(b.name));
  writeJsonAtomic(MARKETPLACE_PATH, marketplace);
  return marketplace.name;
}

function removeMarketplacePlugin(plugin) {
  if (!fs.existsSync(MARKETPLACE_PATH)) return null;
  const marketplace = readMarketplace();
  const before = marketplace.plugins.length;
  marketplace.plugins = marketplace.plugins.filter((p) => p && p.name !== plugin);
  if (marketplace.plugins.length === before) return marketplace.name;
  writeJsonAtomic(MARKETPLACE_PATH, marketplace);
  return marketplace.name;
}

function tomlString(s) {
  return String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function pluginKey(plugin, marketplace) {
  return `${plugin}@${marketplace}`;
}

function findTomlSection(lines, header) {
  const start = lines.findIndex((line) => line.trim() === header);
  if (start === -1) return null;
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i += 1) {
    if (/^\s*\[/.test(lines[i])) {
      end = i;
      break;
    }
  }
  return { start, end };
}

function setCodexPluginEnabled(plugin, marketplace) {
  const key = pluginKey(plugin, marketplace);
  const header = `[plugins."${tomlString(key)}"]`;
  const raw = fs.existsSync(CODEX_CONFIG_PATH)
    ? fs.readFileSync(CODEX_CONFIG_PATH, 'utf8')
    : '';
  const lines = raw.split('\n');
  if (lines.length === 1 && lines[0] === '') lines.pop();

  const section = findTomlSection(lines, header);
  if (!section) {
    if (lines.length > 0 && lines[lines.length - 1].trim() !== '') lines.push('');
    lines.push(header, 'enabled = true');
  } else {
    const enabledIndex = lines
      .slice(section.start + 1, section.end)
      .findIndex((line) => /^\s*enabled\s*=/.test(line));
    if (enabledIndex === -1) {
      lines.splice(section.start + 1, 0, 'enabled = true');
    } else {
      lines[section.start + 1 + enabledIndex] = 'enabled = true';
    }
  }

  setTomlBoolean(lines, '[features]', 'codex_hooks', true);
  setTomlBoolean(lines, '[features]', 'plugin_hooks', true);

  fs.mkdirSync(path.dirname(CODEX_CONFIG_PATH), { recursive: true });
  fs.writeFileSync(CODEX_CONFIG_PATH, `${lines.join('\n').replace(/\n*$/, '')}\n`, 'utf8');
}

function setTomlBoolean(lines, header, key, value) {
  const rendered = `${key} = ${value ? 'true' : 'false'}`;
  const section = findTomlSection(lines, header);
  if (!section) {
    if (lines.length > 0 && lines[lines.length - 1].trim() !== '') lines.push('');
    lines.push(header, rendered);
    return;
  }

  const keyIndex = lines
    .slice(section.start + 1, section.end)
    .findIndex((line) => new RegExp(`^\\s*${key}\\s*=`).test(line));
  if (keyIndex === -1) {
    lines.splice(section.start + 1, 0, rendered);
  } else {
    lines[section.start + 1 + keyIndex] = rendered;
  }
}

function removeCodexPluginSections(plugin) {
  if (!fs.existsSync(CODEX_CONFIG_PATH)) return 0;
  const raw = fs.readFileSync(CODEX_CONFIG_PATH, 'utf8');
  const lines = raw.split('\n');
  let removed = 0;
  for (let i = 0; i < lines.length; ) {
    const match = lines[i].trim().match(/^\[plugins\."([^"]+)"\]$/);
    if (!match || !match[1].startsWith(`${plugin}@`)) {
      i += 1;
      continue;
    }
    const section = findTomlSection(lines, lines[i].trim());
    if (!section) break;
    lines.splice(section.start, section.end - section.start);
    removed += 1;
    if (section.start < lines.length && lines[section.start] === '') {
      lines.splice(section.start, 1);
    }
    i = section.start;
  }
  if (removed > 0) {
    fs.writeFileSync(CODEX_CONFIG_PATH, `${lines.join('\n').replace(/\n*$/, '')}\n`, 'utf8');
  }
  return removed;
}

function replacePluginSymlink(target, source) {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  let prior = null;
  try {
    prior = fs.lstatSync(target);
  } catch (_e) {
    // target does not exist
  }
  if (prior) {
    if (!prior.isSymbolicLink()) {
      throw new Error(`refusing to overwrite non-symlink local Codex plugin at ${target}`);
    }
    fs.unlinkSync(target);
  }
  fs.symlinkSync(source, target, 'dir');
}

function cachePluginRoot(marketplace, plugin) {
  return path.join(CODEX_PLUGIN_CACHE_DIR, marketplace, plugin);
}

function cachePluginPath(marketplace, plugin, version) {
  return path.join(cachePluginRoot(marketplace, plugin), version);
}

function isHbrnessPluginLink(target, plugin) {
  if (!fs.existsSync(target)) return false;
  const stat = fs.lstatSync(target);
  if (!stat.isSymbolicLink()) return false;
  const link = fs.readlinkSync(target);
  const resolved = path.isAbsolute(link) ? link : path.resolve(path.dirname(target), link);
  const expected = path.join(pkgRoot(), 'dist', 'codex', plugin);
  return resolved === expected || resolved.startsWith(`${expected}${path.sep}`);
}

function ensureCachePluginRoot(root, plugin) {
  let prior = null;
  try {
    prior = fs.lstatSync(root);
  } catch (_e) {
    // root does not exist
  }
  if (prior) {
    if (prior.isSymbolicLink()) {
      if (!isHbrnessPluginLink(root, plugin)) {
        throw new Error(`refusing to overwrite non-hbrness Codex plugin cache link at ${root}`);
      }
      fs.unlinkSync(root);
    } else if (!prior.isDirectory()) {
      throw new Error(`refusing to overwrite non-directory Codex plugin cache at ${root}`);
    }
  }
  fs.mkdirSync(root, { recursive: true });
}

function isHbrnessCacheCopy(target) {
  return fs.existsSync(path.join(target, CACHE_MARKER_FILE));
}

function replaceCacheCopy(target, source, plugin) {
  ensureCachePluginRoot(path.dirname(target), plugin);
  let prior = null;
  try {
    prior = fs.lstatSync(target);
  } catch (_e) {
    // target does not exist
  }
  if (prior) {
    if (prior.isSymbolicLink()) {
      if (!isHbrnessPluginLink(target, plugin)) {
        throw new Error(`refusing to overwrite non-hbrness Codex plugin cache link at ${target}`);
      }
      fs.unlinkSync(target);
    } else if (prior.isDirectory()) {
      if (!isHbrnessCacheCopy(target)) {
        throw new Error(`refusing to overwrite non-hbrness Codex plugin cache directory at ${target}`);
      }
      fs.rmSync(target, { recursive: true, force: true });
    } else {
      throw new Error(`refusing to overwrite non-directory Codex plugin cache at ${target}`);
    }
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.cpSync(source, target, { recursive: true, dereference: true });
  rewriteCachedHookCommands(target);
  fs.writeFileSync(path.join(target, CACHE_MARKER_FILE), `${source}\n`, 'utf8');
}

function rewriteCachedHookCommands(pluginRoot) {
  const hooksPath = path.join(pluginRoot, 'hooks.json');
  if (!fs.existsSync(hooksPath)) return;
  const hooks = readJson(hooksPath, null);
  if (!hooks) return;
  rewriteCommandStrings(hooks, pluginRoot);
  writeJsonAtomic(hooksPath, hooks);
}

function rewriteCommandStrings(value, pluginRoot) {
  if (Array.isArray(value)) {
    for (const item of value) rewriteCommandStrings(item, pluginRoot);
    return;
  }
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    if (key === 'command' && typeof child === 'string') {
      value[key] = rewritePluginRelativePaths(child, pluginRoot);
    } else {
      rewriteCommandStrings(child, pluginRoot);
    }
  }
}

function rewritePluginRelativePaths(command, pluginRoot) {
  return command.replace(/(^|[\s"'])\.\/(hooks|scripts|assets|bin)\//g, (_match, prefix, dir) => {
    return `${prefix}${path.join(pluginRoot, dir)}/`;
  });
}

function removeEmptyDirsUpTo(dir, stop) {
  let current = dir;
  const boundary = path.resolve(stop);
  while (path.resolve(current).startsWith(boundary) && path.resolve(current) !== boundary) {
    try {
      fs.rmdirSync(current);
    } catch (_e) {
      return;
    }
    current = path.dirname(current);
  }
}

function isHbrnessCacheEntry(candidate, plugin) {
  if (!fs.existsSync(candidate)) return false;
  const stat = fs.lstatSync(candidate);
  if (stat.isSymbolicLink()) return isHbrnessPluginLink(candidate, plugin);
  if (stat.isDirectory()) return isHbrnessCacheCopy(candidate);
  return false;
}

function findHbrnessCacheEntries(marketplace, plugin) {
  const root = cachePluginRoot(marketplace, plugin);
  const entries = [];
  if (!fs.existsSync(root)) return entries;
  if (isHbrnessCacheEntry(root, plugin)) {
    entries.push(root);
    return entries;
  }
  let children = [];
  try {
    children = fs.readdirSync(root);
  } catch (_e) {
    return entries;
  }
  for (const child of children) {
    const candidate = path.join(root, child);
    if (isHbrnessCacheEntry(candidate, plugin)) entries.push(candidate);
  }
  return entries;
}

function planInstall({ plugin, pluginDir }) {
  if (!hasHooks(pluginDir)) return { ops: [], marketplace: null };
  const marketplace = readMarketplace();
  const linkPath = path.join(USER_PLUGINS_DIR, plugin);
  const version = readPluginVersion(pluginDir);
  const cachePath = cachePluginPath(marketplace.name, plugin, version);
  return {
    marketplace: marketplace.name,
    ops: [
      { action: 'codex-plugin-link', target: linkPath, source: pluginDir, plugin },
      { action: 'codex-cache-copy', target: cachePath, source: pluginDir, plugin, marketplace: marketplace.name },
      { action: 'codex-marketplace', target: MARKETPLACE_PATH, plugin, marketplace: marketplace.name },
      { action: 'codex-enable', target: CODEX_CONFIG_PATH, plugin, marketplace: marketplace.name },
    ],
  };
}

function applyInstall(plan, { dryRun = false } = {}) {
  const results = [];
  for (const op of plan.ops) {
    if (dryRun) {
      results.push({ ...op, status: 'planned' });
      continue;
    }
    try {
      if (op.action === 'codex-plugin-link') {
        replacePluginSymlink(op.target, op.source);
        results.push({ ...op, status: 'linked' });
      } else if (op.action === 'codex-cache-copy') {
        replaceCacheCopy(op.target, op.source, op.plugin);
        results.push({ ...op, status: 'copied' });
      } else if (op.action === 'codex-marketplace') {
        const marketplace = upsertMarketplacePlugin(op.plugin);
        results.push({ ...op, marketplace, status: 'updated' });
      } else if (op.action === 'codex-enable') {
        setCodexPluginEnabled(op.plugin, op.marketplace);
        results.push({ ...op, status: 'enabled' });
      }
    } catch (err) {
      results.push({ ...op, status: 'error', error: err.message });
    }
  }
  return results;
}

function planUninstall({ plugin }) {
  const ops = [];
  const linkPath = path.join(USER_PLUGINS_DIR, plugin);
  if (isHbrnessPluginLink(linkPath, plugin)) {
    ops.push({ action: 'codex-plugin-unlink', target: linkPath, plugin });
  }
  if (fs.existsSync(MARKETPLACE_PATH)) {
    const marketplace = readMarketplace();
    for (const cachePath of findHbrnessCacheEntries(marketplace.name, plugin)) {
      ops.push({ action: 'codex-cache-remove', target: cachePath, plugin, marketplace: marketplace.name });
    }
    if (marketplace.plugins.some((p) => p && p.name === plugin)) {
      ops.push({ action: 'codex-marketplace-remove', target: MARKETPLACE_PATH, plugin, marketplace: marketplace.name });
    }
  }
  if (fs.existsSync(CODEX_CONFIG_PATH)) {
    const raw = fs.readFileSync(CODEX_CONFIG_PATH, 'utf8');
    if (new RegExp(`^\\[plugins\\."${plugin.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}@`, 'm').test(raw)) {
      ops.push({ action: 'codex-disable', target: CODEX_CONFIG_PATH, plugin });
    }
  }
  return { ops };
}

function applyUninstall(plan, { dryRun = false } = {}) {
  const results = [];
  for (const op of plan.ops) {
    if (dryRun) {
      results.push({ ...op, status: 'planned' });
      continue;
    }
    try {
      if (op.action === 'codex-plugin-unlink') {
        fs.unlinkSync(op.target);
        results.push({ ...op, status: 'removed' });
      } else if (op.action === 'codex-cache-remove') {
        fs.rmSync(op.target, { recursive: true, force: true });
        removeEmptyDirsUpTo(path.dirname(op.target), CODEX_PLUGIN_CACHE_DIR);
        results.push({ ...op, status: 'removed' });
      } else if (op.action === 'codex-marketplace-remove') {
        const marketplace = removeMarketplacePlugin(op.plugin);
        results.push({ ...op, marketplace, status: 'updated' });
      } else if (op.action === 'codex-disable') {
        const count = removeCodexPluginSections(op.plugin);
        results.push({ ...op, count, status: count > 0 ? 'removed' : 'already-clean' });
      }
    } catch (err) {
      results.push({ ...op, status: 'error', error: err.message });
    }
  }
  return results;
}

module.exports = {
  MARKETPLACE_NAME,
  MARKETPLACE_PATH,
  USER_PLUGINS_DIR,
  CODEX_PLUGIN_CACHE_DIR,
  CODEX_CONFIG_PATH,
  planInstall,
  applyInstall,
  planUninstall,
  applyUninstall,
};
