const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const cp = require('child_process');
const native = require('../scripts/install/native.js');
const installer = require('../scripts/install/installer.js');

function fixture(t, harness = 'grok') {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hbrness-test-'));
  const old = { GROK_HOME: process.env.GROK_HOME, XDG_CONFIG_HOME: process.env.XDG_CONFIG_HOME };
  process.env.GROK_HOME = path.join(root, 'grok $dollar `literal` "quote"');
  process.env.XDG_CONFIG_HOME = path.join(root, 'config');
  t.after(() => {
    for (const [key, value] of Object.entries(old)) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
    fs.rmSync(root, { recursive: true, force: true });
  });
  const pluginDir = path.join(root, 'source');
  const manifest = harness === 'devin' ? '.devin-plugin' : '.claude-plugin';
  fs.mkdirSync(path.join(pluginDir, manifest), { recursive: true });
  fs.mkdirSync(path.join(pluginDir, 'skills', 'probe'), { recursive: true });
  fs.writeFileSync(path.join(pluginDir, manifest, 'plugin.json'), JSON.stringify({ name: 'probe', version: '1.0.0' }));
  fs.writeFileSync(path.join(pluginDir, 'skills', 'probe', 'SKILL.md'), 'printf "%s" "{HBRNESS_PLUGIN_PATH}"\n');
  fs.writeFileSync(path.join(pluginDir, 'hooks.json'), JSON.stringify({ PostToolUse: [{ hooks: [{ type: 'command', command: 'python3 "{HBRNESS_PLUGIN_PATH}/hook.py"' }] }] }));
  return { root, pluginDir, plan: native.planInstall({ harness, plugin: 'probe', pluginDir }) };
}

test('dry run does not write; native install renders safe paths and preserves unrelated plugins', (t) => {
  const { plan } = fixture(t);
  assert.equal(native.install(plan, { dryRun: true })[0].status, 'planned');
  assert.equal(fs.existsSync(plan.target), false);
  assert.equal(native.install(plan)[0].status, 'installed');
  const command = fs.readFileSync(path.join(plan.target, 'skills/probe/SKILL.md'), 'utf8');
  assert.equal(cp.execFileSync('bash', ['-c', command], { encoding: 'utf8' }), plan.target);
  const hook = JSON.parse(fs.readFileSync(path.join(plan.target, 'hooks.json'), 'utf8'));
  assert.ok(hook.PostToolUse[0].hooks[0].command.includes('\\$dollar'));
  assert.equal(native.listInstalled('grok').length, 1);
  const other = path.join(path.dirname(plan.target), 'other');
  fs.mkdirSync(other);
  assert.equal(native.install(plan)[0].status, 'installed');
  assert.equal(native.listInstalled('grok').length, 1);
  assert.equal(native.uninstall(native.planUninstall(plan))[0].status, 'removed');
  assert.equal(fs.existsSync(other), true);
  assert.equal(native.listInstalled('grok').length, 0);
});

test('unowned directories and symlinks are never overwritten', (t) => {
  const { plan, root } = fixture(t);
  fs.mkdirSync(plan.target, { recursive: true });
  assert.equal(native.install(plan)[0].status, 'error');
  assert.throws(() => native.planUninstall(plan), /non-hbrness/);
  fs.rmdirSync(plan.target);
  fs.symlinkSync(path.join(root, 'missing'), plan.target);
  assert.equal(native.install(plan)[0].status, 'error');
  assert.equal(fs.lstatSync(plan.target).isSymbolicLink(), true);
});

test('Devin install/remove are local-only; failed refresh restores previous contents', (t) => {
  const { plan, pluginDir } = fixture(t, 'devin');
  const real = cp.spawnSync;
  const calls = [];
  cp.spawnSync = (bin, args) => { calls.push([bin, ...args]); return { status: 0 }; };
  t.after(() => { cp.spawnSync = real; });
  assert.equal(native.install(plan)[0].status, 'installed');
  assert.deepEqual(calls[0], ['devin', 'plugins', 'install', '--local', '--yes', plan.target]);
  const before = fs.readFileSync(path.join(plan.target, 'skills/probe/SKILL.md'), 'utf8');
  fs.writeFileSync(path.join(pluginDir, 'skills/probe/SKILL.md'), 'new version');
  cp.spawnSync = () => ({ status: 1, stderr: 'registration failed' });
  assert.equal(native.install(plan)[0].status, 'error');
  assert.equal(fs.readFileSync(path.join(plan.target, 'skills/probe/SKILL.md'), 'utf8'), before);
  cp.spawnSync = (bin, args) => { calls.push([bin, ...args]); return { status: 0 }; };
  assert.equal(native.uninstall(native.planUninstall(plan))[0].status, 'removed');
  assert.deepEqual(calls.at(-1), ['devin', 'plugins', 'remove', '--local', '--yes', 'probe']);
});

test('--no-hooks removes both hook layouts, including on reinstall', (t) => {
  const { plan, pluginDir } = fixture(t);
  fs.mkdirSync(path.join(pluginDir, 'hooks'));
  fs.writeFileSync(path.join(pluginDir, 'hooks/hooks.json'), '{}');
  native.install(plan);
  native.install(plan, { skipHooks: true });
  assert.equal(fs.existsSync(path.join(plan.target, 'hooks.json')), false);
  assert.equal(fs.existsSync(path.join(plan.target, 'hooks/hooks.json')), false);
});

test('built native workflows contain the correct caller and install without unresolved paths', (t) => {
  fixture(t);
  for (const plugin of ['agentbus', 'dbflow', 'ghflow', 'sessionflow', 'xreview']) {
    const plan = installer.planInstall({ harness: 'grok', plugin });
    assert.equal(installer.applyPlan(plan)[0].status, 'installed');
  }
  assert.deepEqual(native.diagnose('grok'), []);
  const root = path.join(process.env.GROK_HOME, 'plugins');
  const review = fs.readFileSync(path.join(root, 'xreview/skills/live/SKILL.md'), 'utf8');
  assert.ok(review.includes('--current-tool grok'));
  assert.ok(!review.includes('--current-tool claude'));
  const phase = fs.readFileSync(path.join(root, 'sessionflow/skills/phase-loop/SKILL.md'), 'utf8');
  assert.ok(phase.includes('--tool grok'));
  assert.ok(phase.includes('/sessionflow:phase-loop continue'));
  assert.throws(() => installer.planInstall({ harness: 'grok', plugin: 'ghflow', mode: 'user-level' }), /requires --mode plugin/);
  assert.throws(() => installer.planInstall({ harness: 'grok', plugin: 'ghflow', printOnly: true }), /--dry-run/);
  assert.throws(() => installer.planUninstall({ harness: 'grok', plugin: 'ghflow', printOnly: true }), /--dry-run/);
});
