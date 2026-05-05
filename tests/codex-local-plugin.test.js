const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const test = require('node:test');

const REPO_ROOT = path.resolve(__dirname, '..');
const PLUGIN = 'llm-kb';

function freshModules(home) {
  process.env.HOME = home;
  const modules = [
    '../scripts/install/codex-local-plugin.js',
    '../scripts/install/doctor.js',
    '../scripts/install/hooks.js',
    '../scripts/install/paths.js',
  ];
  for (const mod of modules) {
    delete require.cache[require.resolve(mod)];
  }
  return {
    codexLocalPlugin: require('../scripts/install/codex-local-plugin.js'),
    doctor: require('../scripts/install/doctor.js'),
  };
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function writeJson(filePath, value) {
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

function issueTypes(issues) {
  return issues.map((issue) => issue.type).sort();
}

test('Codex hook-capable plugin install, doctor, and repair stay coherent', () => {
  const originalHome = process.env.HOME;
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'hbrness-codex-test-'));

  try {
    const { codexLocalPlugin, doctor } = freshModules(home);
    const pluginDir = path.join(REPO_ROOT, 'dist', 'codex', PLUGIN);
    const manifest = readJson(path.join(pluginDir, '.codex-plugin', 'plugin.json'));
    const cachePath = path.join(
      codexLocalPlugin.CODEX_PLUGIN_CACHE_DIR,
      codexLocalPlugin.MARKETPLACE_NAME,
      PLUGIN,
      manifest.version,
    );

    assert.equal(manifest.hooks, './hooks.json');
    assert.ok(fs.existsSync(path.join(pluginDir, 'hooks.json')));

    const plan = codexLocalPlugin.planInstall({ plugin: PLUGIN, pluginDir });
    const results = codexLocalPlugin.applyInstall(plan, { dryRun: false });
    assert.deepEqual(
      results.map((result) => [result.action, result.status]),
      [
        ['codex-plugin-link', 'linked'],
        ['codex-cache-copy', 'copied'],
        ['codex-marketplace', 'updated'],
        ['codex-enable', 'enabled'],
      ],
    );

    const linkPath = path.join(codexLocalPlugin.USER_PLUGINS_DIR, PLUGIN);
    assert.equal(fs.lstatSync(linkPath).isSymbolicLink(), true);
    assert.equal(fs.readlinkSync(linkPath), pluginDir);

    const marketplace = readJson(codexLocalPlugin.MARKETPLACE_PATH);
    assert.equal(marketplace.name, codexLocalPlugin.MARKETPLACE_NAME);
    assert.ok(marketplace.plugins.some((entry) => entry.name === PLUGIN));

    const config = fs.readFileSync(codexLocalPlugin.CODEX_CONFIG_PATH, 'utf8');
    assert.match(config, /\[plugins\."llm-kb@hbrness"\]/);
    assert.match(config, /codex_hooks = true/);
    assert.match(config, /plugin_hooks = true/);

    assert.equal(fs.lstatSync(cachePath).isDirectory(), true);
    assert.equal(fs.lstatSync(cachePath).isSymbolicLink(), false);
    assert.ok(fs.existsSync(path.join(cachePath, '.hbrness-origin')));

    const cachedHooksPath = path.join(cachePath, 'hooks.json');
    const cachedHooks = readJson(cachedHooksPath);
    const cachedCommand = cachedHooks.hooks.Stop[0].hooks[0].command;
    assert.match(cachedCommand, new RegExp(path.join(cachePath, 'hooks')));
    assert.doesNotMatch(cachedCommand, /\.\/hooks\//);
    assert.deepEqual(doctor.diagnose({ harnesses: ['codex'] }), []);

    cachedHooks.hooks.Stop[0].hooks[0].command =
      'LLM_KB_HARNESS=codex python3 "./hooks/kb-judge.py"';
    writeJson(cachedHooksPath, cachedHooks);
    let issues = doctor.diagnose({ harnesses: ['codex'] });
    assert.ok(issueTypes(issues).includes('codex-hook-relative-path'));

    let repairResult = doctor.repair(issues, { dryRun: false });
    assert.ok(repairResult.results.some((result) => result.status === 'fixed'));
    assert.deepEqual(doctor.diagnose({ harnesses: ['codex'] }), []);

    fs.writeFileSync(
      codexLocalPlugin.CODEX_CONFIG_PATH,
      fs.readFileSync(codexLocalPlugin.CODEX_CONFIG_PATH, 'utf8')
        .replace(/\nplugin_hooks = true\n?/, '\n'),
      'utf8',
    );
    issues = doctor.diagnose({ harnesses: ['codex'] });
    assert.ok(issueTypes(issues).includes('codex-feature-disabled'));
    repairResult = doctor.repair(issues, { dryRun: false });
    assert.ok(repairResult.results.some((result) => result.status === 'fixed'));
    assert.deepEqual(doctor.diagnose({ harnesses: ['codex'] }), []);

    fs.rmSync(cachePath, { recursive: true, force: true });
    fs.symlinkSync(pluginDir, cachePath, 'dir');
    issues = doctor.diagnose({ harnesses: ['codex'] });
    assert.ok(issueTypes(issues).includes('codex-plugin-cache-symlink'));
    doctor.repair(issues, { dryRun: false });
    assert.equal(fs.lstatSync(cachePath).isDirectory(), true);
    assert.equal(fs.lstatSync(cachePath).isSymbolicLink(), false);
    assert.deepEqual(doctor.diagnose({ harnesses: ['codex'] }), []);
  } finally {
    process.env.HOME = originalHome;
    fs.rmSync(home, { recursive: true, force: true });
  }
});
