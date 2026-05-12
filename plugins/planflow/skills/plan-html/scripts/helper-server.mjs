#!/usr/bin/env node
// helper-server.mjs — local HTTP helper for a single plan
// usage: node helper-server.mjs <plan-dir> <tmux-pane-id> [port]
//
// Endpoints:
//   GET  /                  → index.html
//   GET  /assets/*          → static assets
//   GET  /events            → SSE; pushes "reload" on plan.json mtime change
//   POST /answers           → { round, answers } → merge into answers.json + plan.json + tmux notify
//   POST /ask               → { text }           → append questions.log + tmux notify
//   GET  /healthz           → ok
//
// Idle timeout: 30 minutes since last request.

import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { spawn, spawnSync } from 'node:child_process';

const [, , planDirRaw, paneId, portRaw] = process.argv;
if (!planDirRaw || !paneId) {
  console.error('usage: helper-server.mjs <plan-dir> <pane-id> [port]');
  process.exit(2);
}
const planDir = path.resolve(planDirRaw);
const PORT = Number(portRaw || 0);
let activePort = PORT; // updated to assigned port after listen()

const PLAN_PATH = path.join(planDir, 'plan.json');
const INDEX_PATH = path.join(planDir, 'index.html');
const ANSWERS_PATH = path.join(planDir, 'answers.json');
const QLOG_PATH = path.join(planDir, 'questions.log');
const SERVER_INFO_PATH = path.join(planDir, 'server.json');
const ASSETS_DIR = path.join(planDir, 'assets');

const IDLE_MS = 30 * 60 * 1000; // 30 min
const SSE_HEARTBEAT_MS = 25 * 1000;
const POLL_MS = 800;

let lastActivity = Date.now();
const sseClients = new Set();

// ── helpers ──────────────────────────────────────────────────────────────────

const readJsonSafe = (p, fallback) => {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return fallback; }
};

const writeJson = (p, obj) => {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(obj, null, 2) + '\n', 'utf8');
};

const sendJson = (res, code, obj) => {
  const body = JSON.stringify(obj);
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  });
  res.end(body);
};

const send404 = (res) => { res.writeHead(404); res.end('not found'); };

const tmuxSend = (text) => {
  // text is a single line (no embedded newlines).
  // Two-step: -l for literal text (escapes special chars / @ / paths safely),
  //           then a separate Enter to actually submit.
  const safe = text.replace(/[\r\n]+/g, ' ').slice(0, 4000);
  try {
    spawnSync('tmux', ['send-keys', '-t', paneId, '-l', safe]);
    spawnSync('tmux', ['send-keys', '-t', paneId, 'Enter']);
  } catch (e) {
    console.error('[helper] tmux send-keys failed:', e.message);
  }
};

const broadcastReload = () => {
  for (const r of sseClients) {
    try { r.write(`event: reload\ndata: {}\n\n`); } catch {}
  }
};

// ── plan.json watcher ───────────────────────────────────────────────────────

let lastMtime = 0;
const pollPlan = () => {
  try {
    const st = fs.statSync(PLAN_PATH);
    const m = st.mtimeMs;
    if (lastMtime && m > lastMtime) {
      // re-render via render.mjs (sibling script)
      const renderPath = path.resolve(path.dirname(new URL(import.meta.url).pathname), 'render.mjs');
      const tmplPath = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', 'template.html');
      const child = spawn(process.execPath, [renderPath, PLAN_PATH, tmplPath, INDEX_PATH, String(activePort)], { stdio: 'inherit' });
      child.on('exit', (code) => {
        if (code === 0) broadcastReload();
        else console.error('[helper] render failed code=' + code);
      });
    }
    lastMtime = m;
  } catch {}
};
setInterval(pollPlan, POLL_MS);

// ── route handlers ───────────────────────────────────────────────────────────

const handleAnswers = async (req, res) => {
  const body = await readBody(req);
  let payload;
  try { payload = JSON.parse(body); } catch { return sendJson(res, 400, { error: 'bad json' }); }
  const { round = 1, answers = {} } = payload;
  if (typeof answers !== 'object' || answers == null) return sendJson(res, 400, { error: 'answers must be object' });

  // merge into answers.json
  const cur = readJsonSafe(ANSWERS_PATH, {});
  const merged = { ...cur, ...answers };
  writeJson(ANSWERS_PATH, merged);

  // update plan.json's question.answer + answered_at
  const plan = readJsonSafe(PLAN_PATH, null);
  if (plan && Array.isArray(plan.questions)) {
    const ts = new Date().toISOString();
    let touched = false;
    for (const q of plan.questions) {
      if (Object.prototype.hasOwnProperty.call(answers, q.id)) {
        q.answer = answers[q.id];
        q.answered_at = ts;
        touched = true;
      }
    }
    if (touched) writeJson(PLAN_PATH, plan);
  }

  tmuxSend(`플랜파일을 확인해: @${PLAN_PATH}`);

  sendJson(res, 200, { ok: true, count: Object.keys(answers).length });
};

const handleAsk = async (req, res) => {
  const body = await readBody(req);
  let payload;
  try { payload = JSON.parse(body); } catch { return sendJson(res, 400, { error: 'bad json' }); }
  const text = String(payload.text || '').trim();
  if (!text) return sendJson(res, 400, { error: 'empty text' });
  const ts = new Date().toISOString();
  fs.mkdirSync(planDir, { recursive: true });
  fs.appendFileSync(QLOG_PATH, `[${ts}] ${text}\n`, 'utf8');
  tmuxSend(`사용자 질문: ${text}`);
  sendJson(res, 200, { ok: true });
};

const handleReviews = async (req, res) => {
  const body = await readBody(req);
  let payload;
  try { payload = JSON.parse(body); } catch { return sendJson(res, 400, { error: 'bad json' }); }
  const items = Array.isArray(payload.comments) ? payload.comments : [];
  if (!items.length) return sendJson(res, 400, { error: 'no comments' });

  const plan = readJsonSafe(PLAN_PATH, null);
  if (!plan) return sendJson(res, 400, { error: 'plan.json missing' });
  if (!Array.isArray(plan.comments)) plan.comments = [];

  const ts = new Date().toISOString();
  const accepted = [];
  for (const c of items) {
    if (!c || !c.anchor_id || !c.comment) continue;
    accepted.push({
      id: c.id || `c_${Math.random().toString(36).slice(2, 9)}${Date.now().toString(36)}`,
      anchor_id: String(c.anchor_id),
      anchor_text: String(c.anchor_text || ''),
      comment: String(c.comment),
      by: 'user',
      submitted_at: ts,
      replies: [],
      resolved: false,
    });
  }
  if (!accepted.length) return sendJson(res, 400, { error: 'no valid comments' });
  plan.comments.push(...accepted);
  writeJson(PLAN_PATH, plan);

  tmuxSend(`리뷰 등록됨 [${accepted.length}건]: @${PLAN_PATH}`);
  sendJson(res, 200, { ok: true, count: accepted.length });
};

const handleResolve = async (req, res) => {
  const body = await readBody(req);
  let payload;
  try { payload = JSON.parse(body); } catch { return sendJson(res, 400, { error: 'bad json' }); }
  const id = String(payload.id || '');
  const resolved = !!payload.resolved;
  if (!id) return sendJson(res, 400, { error: 'id required' });

  const plan = readJsonSafe(PLAN_PATH, null);
  if (!plan || !Array.isArray(plan.comments)) return sendJson(res, 400, { error: 'no plan/comments' });
  const c = plan.comments.find((x) => x.id === id);
  if (!c) return sendJson(res, 404, { error: 'comment not found' });
  c.resolved = resolved;
  writeJson(PLAN_PATH, plan);
  // no tmux notify — local UX only
  sendJson(res, 200, { ok: true });
};

const handleSSE = (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Access-Control-Allow-Origin': '*',
  });
  res.write(': connected\n\n');
  sseClients.add(res);
  const hb = setInterval(() => { try { res.write(': hb\n\n'); } catch {} }, SSE_HEARTBEAT_MS);
  req.on('close', () => { clearInterval(hb); sseClients.delete(res); });
};

const serveStatic = (filePath, res, mime) => {
  fs.readFile(filePath, (err, data) => {
    if (err) return send404(res);
    res.writeHead(200, {
      'Content-Type': mime,
      'Access-Control-Allow-Origin': '*',
      'Cache-Control': 'no-store',
    });
    res.end(data);
  });
};

const guessMime = (p) => {
  const ext = path.extname(p).toLowerCase();
  return ({
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.mjs': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.gif': 'image/gif', '.svg': 'image/svg+xml', '.webp': 'image/webp',
  })[ext] || 'application/octet-stream';
};

const readBody = (req) => new Promise((resolve, reject) => {
  let data = ''; req.setEncoding('utf8');
  req.on('data', (c) => { data += c; if (data.length > 1e6) { req.destroy(); reject(new Error('too large')); } });
  req.on('end', () => resolve(data));
  req.on('error', reject);
});

// ── server ──────────────────────────────────────────────────────────────────

const server = http.createServer(async (req, res) => {
  lastActivity = Date.now();
  const u = new URL(req.url, 'http://localhost');

  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    });
    return res.end();
  }

  if (u.pathname === '/healthz') return sendJson(res, 200, { ok: true });
  if (u.pathname === '/events' && req.method === 'GET') return handleSSE(req, res);
  if (u.pathname === '/answers' && req.method === 'POST') return handleAnswers(req, res);
  if (u.pathname === '/ask' && req.method === 'POST') return handleAsk(req, res);
  if (u.pathname === '/reviews' && req.method === 'POST') return handleReviews(req, res);
  if (u.pathname === '/resolve' && req.method === 'POST') return handleResolve(req, res);

  if (req.method === 'GET' && (u.pathname === '/' || u.pathname === '/index.html')) {
    return serveStatic(INDEX_PATH, res, 'text/html; charset=utf-8');
  }
  if (req.method === 'GET' && u.pathname.startsWith('/assets/')) {
    const rel = u.pathname.replace(/^\/assets\//, '').replace(/\.\.+/g, '');
    const fp = path.join(ASSETS_DIR, rel);
    if (!fp.startsWith(ASSETS_DIR)) return send404(res);
    return serveStatic(fp, res, guessMime(fp));
  }

  send404(res);
});

server.listen(PORT, '127.0.0.1', () => {
  const addr = server.address();
  activePort = addr.port;
  writeJson(SERVER_INFO_PATH, {
    pid: process.pid,
    port: activePort,
    pane: paneId,
    plan_dir: planDir,
    started_at: new Date().toISOString(),
  });
  // initial mtime
  try { lastMtime = fs.statSync(PLAN_PATH).mtimeMs; } catch {}
  console.log(`[helper] listening http://localhost:${activePort}  pane=${paneId}  plan=${planDir}`);
});

// idle reaper
setInterval(() => {
  if (Date.now() - lastActivity > IDLE_MS) {
    console.log('[helper] idle timeout, exiting');
    process.exit(0);
  }
}, 60 * 1000);

// graceful shutdown
const shutdown = () => {
  try { fs.unlinkSync(SERVER_INFO_PATH); } catch {}
  process.exit(0);
};
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
