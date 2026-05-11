#!/usr/bin/env node
// stop.mjs — terminate helper server for a plan-dir
// usage: node stop.mjs <plan-dir>

import fs from 'node:fs';
import path from 'node:path';

const planDir = path.resolve(process.argv[2] || '.');
const info = path.join(planDir, 'server.json');

if (!fs.existsSync(info)) {
  console.log('no server.json — nothing to stop');
  process.exit(0);
}
const data = JSON.parse(fs.readFileSync(info, 'utf8'));
try {
  process.kill(data.pid, 'SIGTERM');
  console.log(`stopped pid=${data.pid} port=${data.port}`);
} catch (e) {
  console.log(`pid ${data.pid} not running`);
}
try { fs.unlinkSync(info); } catch {}
