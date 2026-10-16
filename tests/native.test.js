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
  for (const plugin of ['agentbus', 'dbflow', 'ghflow', 'sessionflow', 'testflow', 'xreview']) {
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

test('codex hooks merge into ~/.codex/hooks.json only for plugins that opt in, and leave other hooks alone', (t) => {
  const hooks = require('../scripts/install/hooks.js');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hbrness-codex-'));
  const oldHome = process.env.HOME;
  process.env.HOME = root;
  t.after(() => {
    process.env.HOME = oldHome;
    fs.rmSync(root, { recursive: true, force: true });
  });
  const file = path.join(root, '.codex', 'hooks.json');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const other = { hooks: [{ type: 'command', command: 'orca-hook.sh', timeout: 10 }] };
  fs.writeFileSync(file, JSON.stringify({ hooks: { Stop: [other] } }));

  const pluginDir = path.join(root, 'dist dir', 'sessionflow');
  fs.mkdirSync(path.join(pluginDir, 'hooks'), { recursive: true });
  fs.copyFileSync(path.join(__dirname, '..', 'plugins', 'sessionflow', 'hooks', 'codex.hooks.json'),
    path.join(pluginDir, 'hooks', 'hooks.json'));
  const args = { harness: 'codex', plugin: 'sessionflow', pluginDir };

  assert.equal(hooks.applyHooksInstall(args, { dryRun: true }).status, 'planned');
  assert.equal(JSON.parse(fs.readFileSync(file, 'utf8')).hooks.Stop.length, 1);
  const res = hooks.applyHooksInstall(args);
  assert.equal(res.status, 'installed');
  assert.ok(res.backup && fs.existsSync(res.backup));
  hooks.applyHooksInstall(args);  // 다시 깔아도 하나만
  const merged = JSON.parse(fs.readFileSync(file, 'utf8'));
  assert.deepEqual(merged.hooks.Stop[0], other);
  assert.equal(merged.hooks.Stop.length, 2);
  assert.equal(merged.hooks.SessionEnd.length, 1);
  const cmd = merged.hooks.Stop[1].hooks[0].command;
  assert.ok(cmd.includes(`"${pluginDir}/scripts/sfhook.py" stop --tool codex`), cmd);
  assert.ok(cmd.endsWith(' # hbrness:sessionflow'));
  assert.equal(JSON.stringify(merged).includes('_hbrness'), false);  // Codex 가 모르는 key 는 넣지 않는다

  const ghflow = path.join(root, 'ghflow');
  fs.mkdirSync(path.join(ghflow, 'hooks'), { recursive: true });
  fs.writeFileSync(path.join(ghflow, 'hooks', 'hooks.json'), JSON.stringify({ hooks: { SessionStart: [
    { hooks: [{ type: 'command', command: 'python3 "${CODEX_PLUGIN_ROOT}/hooks/fetch-templates.py"' }] }] } }));
  assert.equal(hooks.applyHooksInstall({ harness: 'codex', plugin: 'ghflow', pluginDir: ghflow }).status, 'no-hooks');
  assert.equal(JSON.parse(fs.readFileSync(file, 'utf8')).hooks.SessionStart, undefined);

  // 사용자가 설치된 그룹에 자기 명령을 더했다 — 다시 설치·지워도 그 명령은 남는다
  const edited = JSON.parse(fs.readFileSync(file, 'utf8'));
  const mine = { type: 'command', command: 'my-own-hook.sh' };
  edited.hooks.Stop[1].matcher = 'keep-me';
  edited.hooks.Stop[1].hooks.push(mine);
  fs.writeFileSync(file, JSON.stringify(edited));
  hooks.applyHooksInstall(args);
  const again = JSON.parse(fs.readFileSync(file, 'utf8'));
  assert.deepEqual(again.hooks.Stop[1], { hooks: [mine], matcher: 'keep-me' });
  assert.equal(again.hooks.Stop.length, 3);
  assert.equal(JSON.stringify(again).split('# hbrness:sessionflow').length - 1, 2);  // Stop·SessionEnd 하나씩

  assert.deepEqual(hooks.planHooksUninstall({ plugin: 'sessionflow', harness: 'codex' }).events.map((e) => e.event).sort(),
    ['SessionEnd', 'Stop']);
  assert.equal(hooks.applyHooksUninstall({ plugin: 'sessionflow', harness: 'codex' }).status, 'removed');
  assert.deepEqual(JSON.parse(fs.readFileSync(file, 'utf8')),
    { hooks: { Stop: [other, { hooks: [mine], matcher: 'keep-me' }] } });
});
