const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { pkgRoot } = require('./paths.js');
const { listInstalled, planInstall, applyPlan } = require('./installer.js');

/**
 * Determine how this copy of hbrness was installed.
 * - "git"     → we live in a git clone; `git pull && build && re-link` updates in place.
 * - "npm"     → we live under node_modules; the user must upgrade via npm.
 * - "unknown" → fall back to showing version info only.
 */
function detectMode() {
  const root = pkgRoot();
  if (root.split(path.sep).includes('node_modules')) return 'npm';
  if (fs.existsSync(path.join(root, '.git'))) return 'git';
  return 'unknown';
}

function currentVersion() {
  return require('../../package.json').version;
}

function queryRegistryVersion() {
  try {
    return execSync('npm view hbrness version', {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch (_err) {
    return null;
  }
}

function runStreamed(cmd, cwd) {
  execSync(cmd, { cwd, stdio: 'inherit', encoding: 'utf8' });
}

function currentlyInstalled() {
  const byKey = new Map();
  for (const h of ['claude', 'codex']) {
    for (const it of listInstalled(h)) {
      const key = `${h}:${it.plugin}`;
      if (!byKey.has(key)) byKey.set(key, { harness: h, plugin: it.plugin });
    }
  }
  return Array.from(byKey.values());
}

/** Git-clone update: pull + rebuild + refresh currently-installed plugins. */
function updateFromGit({ dryRun = false } = {}) {
  const root = pkgRoot();
  const installed = currentlyInstalled();

  if (dryRun) {
    console.log('Dry-run plan:');
    console.log(`  cd ${root}`);
    console.log('  git pull --ff-only');
    console.log('  bash scripts/build.sh all');
    console.log('  bash scripts/validate.sh');
    if (installed.length === 0) {
      console.log('  (no plugins currently installed — skipping refresh)');
    } else {
      for (const { harness, plugin } of installed) {
        console.log(`  hbrness install ${harness} ${plugin}   # refresh symlinks + hooks`);
      }
    }
    return { mode: 'git', dryRun: true };
  }

  console.log('→ git pull --ff-only');
  runStreamed('git pull --ff-only', root);
  console.log('→ build');
  runStreamed('bash scripts/build.sh all', root);
  console.log('→ validate');
  runStreamed('bash scripts/validate.sh', root);

  if (installed.length === 0) {
    console.log('No plugins currently installed — nothing to refresh.');
    return { mode: 'git', refreshed: [] };
  }

  const refreshed = [];
  for (const { harness, plugin } of installed) {
    console.log(`→ refresh ${harness}/${plugin}`);
    const plan = planInstall({ harness, plugin });
    applyPlan(plan);
    refreshed.push({ harness, plugin });
  }
  return { mode: 'git', refreshed };
}

/** npm-install update: compare versions and tell the user how to upgrade. */
function updateFromNpm({ dryRun = false } = {}) {
  const local = currentVersion();
  const latest = queryRegistryVersion();
  if (!latest) {
    console.log('Could not reach registry. Try again when online, or run: npm view hbrness version');
    return { mode: 'npm', reachable: false };
  }
  if (local === latest) {
    console.log(`hbrness is up to date (${local}).`);
    return { mode: 'npm', current: local, latest, uptoDate: true };
  }
  console.log(`Installed: ${local}`);
  console.log(`Latest:    ${latest}`);
  console.log('');
  console.log('hbrness cannot upgrade itself from inside node_modules. Run:');
  console.log('  npm install -g hbrness@latest   # (or --save if installed locally)');
  console.log('Then refresh installed plugins:');
  console.log('  hbrness install claude');
  console.log('  hbrness install codex');
  if (dryRun) console.log('\n(dry-run — no changes applied.)');
  return { mode: 'npm', current: local, latest, uptoDate: false };
}

function update({ dryRun = false } = {}) {
  const mode = detectMode();
  if (mode === 'git') return updateFromGit({ dryRun });
  if (mode === 'npm') return updateFromNpm({ dryRun });
  console.log(`hbrness is installed in an unrecognized layout (${pkgRoot()}).`);
  console.log(`Current version: ${currentVersion()}`);
  console.log('Reinstall via npm or a fresh git clone to enable update.');
  return { mode: 'unknown', current: currentVersion() };
}

module.exports = { update, detectMode };
