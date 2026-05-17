const { spawnSync } = require('child_process');

/** Test whether the `claude` command is on PATH and executable. */
function claudeAvailable() {
  const res = spawnSync('claude', ['--version'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: 10_000,
  });
  return !res.error && res.status === 0;
}

function runClaude(args) {
  const res = spawnSync('claude', args, {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: 120_000,
  });
  const stdout = (res.stdout || '').trim();
  const stderr = (res.stderr || '').trim();
  if (res.error) {
    return { ok: false, error: res.error.message, stdout, stderr };
  }
  return {
    ok: res.status === 0,
    status: res.status,
    stdout,
    stderr,
  };
}

function marketplaceAdd(sourcePath) {
  return runClaude(['plugin', 'marketplace', 'add', sourcePath]);
}

function pluginInstall(spec) {
  return runClaude(['plugin', 'install', spec]);
}

function pluginUninstall(spec) {
  return runClaude(['plugin', 'uninstall', spec]);
}

function marketplaceRemove(name) {
  return runClaude(['plugin', 'marketplace', 'remove', name]);
}

/** Treat "already added/installed" messages as idempotent success. */
function isIdempotentFailure(result) {
  if (result.ok) return false;
  const blob = `${result.stdout}\n${result.stderr}`.toLowerCase();
  return /already\s+(added|installed|exists|present)/.test(blob);
}

// Claude Code's `plugin install` returns exit 0 even when it skips an
// already-installed spec (logging "Plugin X is already installed"). The
// success exit hides the no-op from our caller, leaving the cache dir
// stale. Check the install output regardless of exit code so we can force
// a refresh via uninstall+reinstall.
function looksAlreadyInstalled(result) {
  const blob = `${result.stdout || ''}\n${result.stderr || ''}`.toLowerCase();
  return /already\s+(installed|added|exists|present)/.test(blob);
}

module.exports = {
  claudeAvailable,
  runClaude,
  marketplaceAdd,
  pluginInstall,
  pluginUninstall,
  marketplaceRemove,
  isIdempotentFailure,
  looksAlreadyInstalled,
};
