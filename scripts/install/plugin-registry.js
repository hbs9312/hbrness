const fs = require('fs');
const path = require('path');
const os = require('os');

const PLUGINS_DIR = path.join(os.homedir(), '.claude', 'plugins');
const INSTALLED_PATH = path.join(PLUGINS_DIR, 'installed_plugins.json');
const MARKETPLACES_PATH = path.join(PLUGINS_DIR, 'known_marketplaces.json');
const CACHE_ROOT = path.join(PLUGINS_DIR, 'cache');

const DEFAULT_MARKETPLACE = 'hbrness';

function readJson(p, fallback) {
  if (!fs.existsSync(p)) return fallback;
  const raw = fs.readFileSync(p, 'utf8');
  if (!raw.trim()) return fallback;
  try {
    return JSON.parse(raw);
  } catch (err) {
    throw new Error(`failed to parse ${p}: ${err.message}`);
  }
}

function writeJsonAtomic(p, obj) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  if (fs.existsSync(p)) {
    const ts = new Date()
      .toISOString()
      .replace(/[:.]/g, '-')
      .replace(/T/, '-')
      .replace(/Z$/, '');
    fs.copyFileSync(p, `${p}.hbrness-bak.${ts}`);
  }
  const tmp = `${p}.tmp.${process.pid}.${Date.now()}`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + '\n', 'utf8');
  fs.renameSync(tmp, p);
}

function marketplaceCacheDir(name = DEFAULT_MARKETPLACE) {
  return path.join(CACHE_ROOT, name);
}

function pluginCacheDir(plugin, version, marketplace = DEFAULT_MARKETPLACE) {
  return path.join(CACHE_ROOT, marketplace, plugin, version);
}

/** Ensure the hbrness marketplace entry exists in known_marketplaces.json. */
function ensureMarketplace(name = DEFAULT_MARKETPLACE) {
  const marketplaces = readJson(MARKETPLACES_PATH, {});
  if (marketplaces[name]) return false;
  marketplaces[name] = {
    source: { source: 'local' },
    installLocation: path.join(PLUGINS_DIR, 'marketplaces', name),
    lastUpdated: new Date().toISOString(),
  };
  writeJsonAtomic(MARKETPLACES_PATH, marketplaces);
  // Create a placeholder marketplace directory so Claude Code has a stable
  // install-location path (it's referenced by installLocation above).
  fs.mkdirSync(marketplaces[name].installLocation, { recursive: true });
  return true;
}

function removeMarketplaceIfEmpty(name = DEFAULT_MARKETPLACE) {
  const installed = readJson(INSTALLED_PATH, { plugins: {} });
  const stillUsed = Object.keys(installed.plugins || {}).some((k) => k.endsWith(`@${name}`));
  if (stillUsed) return false;
  const marketplaces = readJson(MARKETPLACES_PATH, {});
  if (!marketplaces[name]) return false;
  delete marketplaces[name];
  writeJsonAtomic(MARKETPLACES_PATH, marketplaces);
  // Clean empty marketplace dir too
  const marketDir = path.join(PLUGINS_DIR, 'marketplaces', name);
  if (fs.existsSync(marketDir)) {
    try {
      fs.rmSync(marketDir, { recursive: true, force: true });
    } catch (_e) {
      // ignore
    }
  }
  return true;
}

function registerPlugin({ plugin, version, installPath, marketplace = DEFAULT_MARKETPLACE }) {
  const key = `${plugin}@${marketplace}`;
  const installed = readJson(INSTALLED_PATH, { version: 2, plugins: {} });
  installed.version = installed.version || 2;
  installed.plugins = installed.plugins || {};
  const now = new Date().toISOString();
  installed.plugins[key] = [
    {
      scope: 'user',
      installPath,
      version,
      installedAt: now,
      lastUpdated: now,
    },
  ];
  writeJsonAtomic(INSTALLED_PATH, installed);
}

function unregisterPlugin({ plugin, marketplace = DEFAULT_MARKETPLACE }) {
  const key = `${plugin}@${marketplace}`;
  const installed = readJson(INSTALLED_PATH, { plugins: {} });
  if (!installed.plugins || !installed.plugins[key]) return false;
  delete installed.plugins[key];
  writeJsonAtomic(INSTALLED_PATH, installed);
  return true;
}

function isPluginRegistered({ plugin, marketplace = DEFAULT_MARKETPLACE }) {
  const key = `${plugin}@${marketplace}`;
  const installed = readJson(INSTALLED_PATH, { plugins: {} });
  return Boolean(installed.plugins && installed.plugins[key]);
}

function listRegisteredPlugins(marketplace = DEFAULT_MARKETPLACE) {
  const installed = readJson(INSTALLED_PATH, { plugins: {} });
  const suffix = `@${marketplace}`;
  const out = [];
  for (const [key, entries] of Object.entries(installed.plugins || {})) {
    if (!key.endsWith(suffix)) continue;
    const plugin = key.slice(0, -suffix.length);
    const e = entries[0] || {};
    out.push({ plugin, marketplace, version: e.version, installPath: e.installPath });
  }
  return out;
}

module.exports = {
  DEFAULT_MARKETPLACE,
  PLUGINS_DIR,
  CACHE_ROOT,
  INSTALLED_PATH,
  MARKETPLACES_PATH,
  marketplaceCacheDir,
  pluginCacheDir,
  ensureMarketplace,
  removeMarketplaceIfEmpty,
  registerPlugin,
  unregisterPlugin,
  isPluginRegistered,
  listRegisteredPlugins,
};
