const fs = require('fs');
const path = require('path');
const os = require('os');
const { parseJsonc } = require('./jsonc.js');

const SETTINGS_PATH = path.join(os.homedir(), '.claude', 'settings.json');

function settingsPath() {
  return SETTINGS_PATH;
}

function readSettings() {
  if (!fs.existsSync(SETTINGS_PATH)) {
    return {};
  }
  const raw = fs.readFileSync(SETTINGS_PATH, 'utf8');
  try {
    return parseJsonc(raw);
  } catch (err) {
    throw new Error(`failed to parse ${SETTINGS_PATH}: ${err.message}`);
  }
}

/** Copy settings.json to a timestamped backup. Returns backup path or null. */
function backupSettings() {
  if (!fs.existsSync(SETTINGS_PATH)) return null;
  const ts = new Date()
    .toISOString()
    .replace(/[:.]/g, '-')
    .replace(/T/, '-')
    .replace(/Z$/, '');
  const backupPath = `${SETTINGS_PATH}.hbrness-bak.${ts}`;
  fs.copyFileSync(SETTINGS_PATH, backupPath);
  return backupPath;
}

/** Atomic write: tmp file + rename. */
function writeSettings(obj) {
  const dir = path.dirname(SETTINGS_PATH);
  fs.mkdirSync(dir, { recursive: true });
  const tmp = `${SETTINGS_PATH}.tmp.${process.pid}.${Date.now()}`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + '\n', 'utf8');
  fs.renameSync(tmp, SETTINGS_PATH);
}

module.exports = {
  SETTINGS_PATH,
  settingsPath,
  readSettings,
  backupSettings,
  writeSettings,
};
