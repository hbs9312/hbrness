const fs = require('fs');
const path = require('path');
const os = require('os');
const { parseJsonc } = require('./jsonc.js');

const PLUGINS_DIR = path.join(os.homedir(), '.claude', 'plugins');
const INSTALLED_PATH = path.join(PLUGINS_DIR, 'installed_plugins.json');
const MARKETPLACES_PATH = path.join(PLUGINS_DIR, 'known_marketplaces.json');
const CACHE_ROOT = path.join(PLUGINS_DIR, 'cache');
const MARKETPLACE_ROOT = path.join(PLUGINS_DIR, 'marketplaces');

const DEFAULT_MARKETPLACE = 'hbrness';
const MARKETPLACE_SCHEMA = 'https://anthropic.com/claude-code/marketplace.schema.json';

function readJson(p, fallback) {
  if (!fs.existsSync(p)) return fallback;
  const raw = fs.readFileSync(p, 'utf8');
  if (!raw.trim()) return fallback;
  try {
    return parseJsonc(raw);
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

function marketplaceDir(name = DEFAULT_MARKETPLACE) {
  return path.join(MARKETPLACE_ROOT, name);
}

function marketplaceManifestPath(name = DEFAULT_MARKETPLACE) {
  return path.join(marketplaceDir(name), '.claude-plugin', 'marketplace.json');
}

function marketplacePluginDir(plugin, name = DEFAULT_MARKETPLACE) {
  return path.join(marketplaceDir(name), 'plugins', plugin);
}

function pluginCacheDir(plugin, version, name = DEFAULT_MARKETPLACE) {
  return path.join(CACHE_ROOT, name, plugin, version);
}

/**
 * Build and write the marketplace manifest. Also copies each plugin from
 * its source directory into marketplaces/<name>/plugins/<plugin>/ so the
 * marketplace entry can resolve plugin sources via the "./plugins/<name>"
 * relative path convention.
 *
 * allPlugins: [{ name, description, sourceDir }]
 */
function setupMarketplaceContents(allPlugins, name = DEFAULT_MARKETPLACE) {
  const dir = marketplaceDir(name);
  const pluginsDir = path.join(dir, 'plugins');
  fs.mkdirSync(pluginsDir, { recursive: true });
  fs.mkdirSync(path.join(dir, '.claude-plugin'), { recursive: true });

  for (const p of allPlugins) {
    const target = marketplacePluginDir(p.name, name);
    if (fs.existsSync(target)) {
      fs.rmSync(target, { recursive: true, force: true });
    }
    fs.cpSync(p.sourceDir, target, { recursive: true, dereference: true });
  }

  const manifest = {
    $schema: MARKETPLACE_SCHEMA,
    name,
    description: 'hbrness plugins (distributed via npm).',
    owner: { name: 'hbs9312' },
    plugins: allPlugins.map((p) => ({
      name: p.name,
      description: p.description || `${p.name} plugin`,
      source: `./plugins/${p.name}`,
    })),
  };
  fs.writeFileSync(
    marketplaceManifestPath(name),
    JSON.stringify(manifest, null, 2) + '\n',
    'utf8',
  );
}

function ensureMarketplaceEntry(name = DEFAULT_MARKETPLACE) {
  const marketplaces = readJson(MARKETPLACES_PATH, {});
  const dir = marketplaceDir(name);
  const now = new Date().toISOString();
  const existing = marketplaces[name];
  const desired = {
    source: { source: 'local', path: dir },
    installLocation: dir,
    lastUpdated: now,
  };
  if (
    existing &&
    existing.source &&
    existing.source.source === 'local' &&
    existing.source.path === dir &&
    existing.installLocation === dir
  ) {
    return false;
  }
  marketplaces[name] = desired;
  writeJsonAtomic(MARKETPLACES_PATH, marketplaces);
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

  const dir = marketplaceDir(name);
  if (fs.existsSync(dir)) {
    try {
      fs.rmSync(dir, { recursive: true, force: true });
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
  MARKETPLACE_ROOT,
  INSTALLED_PATH,
  MARKETPLACES_PATH,
  marketplaceDir,
  marketplaceManifestPath,
  marketplacePluginDir,
  pluginCacheDir,
  setupMarketplaceContents,
  ensureMarketplaceEntry,
  removeMarketplaceIfEmpty,
  registerPlugin,
  unregisterPlugin,
  isPluginRegistered,
  listRegisteredPlugins,
};
