#!/usr/bin/env node
// start.mjs — orchestrator: render plan + start helper + open browser
// usage: node start.mjs <plan-dir> [--no-open]

import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';
import { spawn, spawnSync } from 'node:child_process';

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(__dirname, '..');
const RENDER = path.join(__dirname, 'render.mjs');
const HELPER = path.join(__dirname, 'helper-server.mjs');
const TEMPLATE = path.join(SKILL_DIR, 'template.html');

const args = process.argv.slice(2);
const noOpen = args.includes('--no-open');
const planDirRaw = args.find((a) => !a.startsWith('--'));
if (!planDirRaw) {
  console.error('usage: start.mjs <plan-dir> [--no-open]');
  process.exit(2);
}
const planDir = path.resolve(planDirRaw);
const planPath = path.join(planDir, 'plan.json');
const indexPath = path.join(planDir, 'index.html');
const serverInfo = path.join(planDir, 'server.json');
const logPath = path.join(planDir, 'helper.log');

if (!fs.existsSync(planPath)) {
  console.error(`plan.json not found at ${planPath}`);
  process.exit(1);
}

// ── reuse existing helper if alive ──────────────────────────────────────────
const isAlive = (pid) => {
  try { process.kill(pid, 0); return true; } catch { return false; }
};

let port = null;
if (fs.existsSync(serverInfo)) {
  try {
    const info = JSON.parse(fs.readFileSync(serverInfo, 'utf8'));
    if (info.pid && isAlive(info.pid)) port = info.port;
    else fs.unlinkSync(serverInfo);
  } catch { try { fs.unlinkSync(serverInfo); } catch {} }
}

// ── tmux pane id ────────────────────────────────────────────────────────────
const captureTmuxPane = () => {
  if (!process.env.TMUX) return null;
  const r = spawnSync('tmux', ['display-message', '-p', '#{pane_id}'], { encoding: 'utf8' });
  if (r.status !== 0) return null;
  const id = r.stdout.trim();
  return id || null;
};
const paneId = captureTmuxPane();
if (!paneId && !port) {
  console.error('warning: not running inside tmux — answers/ask will be saved to files but cannot send-keys.');
  console.error('         set planflow:plan-html:no-tmux=1 to silence.');
}

// ── render ──────────────────────────────────────────────────────────────────
const renderOnce = (helperPort) => {
  const r = spawnSync(process.execPath, [RENDER, planPath, TEMPLATE, indexPath, String(helperPort || 0)], {
    stdio: 'inherit',
  });
  if (r.status !== 0) { console.error('render failed'); process.exit(1); }
};

// ── start helper ────────────────────────────────────────────────────────────
if (!port) {
  if (!paneId) {
    // no tmux: still render so user can open file manually
    renderOnce(0);
    console.log(`\n  rendered: file://${indexPath}\n  (tmux not detected — helper not started; you can still open the HTML to view the plan)\n`);
    process.exit(0);
  }

  // initial render with port=0 placeholder; will re-render after helper spins up
  renderOnce(0);

  const out = fs.openSync(logPath, 'a');
  const child = spawn(process.execPath, [HELPER, planDir, paneId, '0'], {
    detached: true,
    stdio: ['ignore', out, out],
  });
  child.unref();

  // wait for server.json to appear (port assigned)
  const start = Date.now();
  while (!port && Date.now() - start < 5000) {
    try {
      const info = JSON.parse(fs.readFileSync(serverInfo, 'utf8'));
      if (info.port && isAlive(info.pid)) port = info.port;
    } catch {}
    if (!port) {
      const waitMs = 80;
      const end = Date.now() + waitMs;
      while (Date.now() < end) {} // tight wait
    }
  }
  if (!port) {
    console.error('helper did not start within 5s; see helper.log:', logPath);
    process.exit(1);
  }
  // re-render with the actual port baked into the page
  renderOnce(port);
}

const urlStr = `http://localhost:${port}`;
console.log(`\n  planflow ready: ${urlStr}`);
console.log(`  plan dir:       ${planDir}`);
console.log(`  helper log:     ${logPath}\n`);

// ── open browser ────────────────────────────────────────────────────────────
if (!noOpen) {
  const opener = process.platform === 'darwin' ? 'open'
    : process.platform === 'win32' ? 'start'
    : 'xdg-open';
  spawn(opener, [urlStr], { detached: true, stdio: 'ignore' }).unref();
}
