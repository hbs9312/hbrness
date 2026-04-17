const {
  planInstall,
  applyPlan,
  planUninstall,
  applyUninstall,
  listInstalled,
  listBuiltPlugins,
} = require('./installer.js');

const SUPPORTED_HARNESSES = ['claude', 'codex'];

function help() {
  return `hbrness — multi-harness plugin installer

Usage:
  hbrness install <harness> [plugin]       Install (default: all plugins)
  hbrness uninstall <harness> [plugin]     Remove installed hbrness symlinks
  hbrness list <harness>                   List currently installed items
  hbrness plugins <harness>                List built plugins in dist/
  hbrness --help                           Show this help
  hbrness --version                        Print package version

Harnesses: ${SUPPORTED_HARNESSES.join(', ')}

Options:
  --dry-run                                Show the plan; do not modify the filesystem
  --json                                   Machine-readable output
  --no-hooks                               Skip merging plugin hooks into ~/.claude/settings.json
  --yes, -y                                Skip confirmation prompts (reserved, future use)

Examples:
  hbrness install claude                   # install all plugins into ~/.claude/
  hbrness install claude ghflow            # install one plugin
  hbrness install codex specflow --dry-run
  hbrness uninstall claude ghflow
  hbrness list claude
`;
}

function parseArgs(argv) {
  const flags = { dryRun: false, json: false, yes: false, skipHooks: false };
  const positional = [];
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--dry-run') flags.dryRun = true;
    else if (a === '--json') flags.json = true;
    else if (a === '--yes' || a === '-y') flags.yes = true;
    else if (a === '--no-hooks') flags.skipHooks = true;
    else if (a === '--help' || a === '-h') flags.help = true;
    else if (a === '--version' || a === '-v') flags.version = true;
    else if (a.startsWith('--')) throw new Error(`unknown flag: ${a}`);
    else positional.push(a);
  }
  return { flags, positional };
}

function requireHarness(harness) {
  if (!SUPPORTED_HARNESSES.includes(harness)) {
    throw new Error(
      `unsupported harness "${harness}" (use one of: ${SUPPORTED_HARNESSES.join(', ')})`,
    );
  }
}

function pluginsToOperate(harness, plugin) {
  if (plugin) return [plugin];
  const all = listBuiltPlugins(harness);
  if (all.length === 0) {
    throw new Error(
      `no built plugins found for ${harness}. Run "npm run build" first.`,
    );
  }
  return all;
}

async function cmdInstall(positional, flags) {
  const [harness, plugin] = positional;
  requireHarness(harness);
  const plugins = pluginsToOperate(harness, plugin);

  const runs = plugins.map((p) => {
    const plan = planInstall({ harness, plugin: p });
    const results = applyPlan(plan, {
      dryRun: flags.dryRun,
      skipHooks: flags.skipHooks,
    });
    return { plan, results };
  });

  if (flags.json) {
    process.stdout.write(JSON.stringify({ action: 'install', runs }, null, 2) + '\n');
    return;
  }
  printRuns('Install', runs, flags);
}

async function cmdUninstall(positional, flags) {
  const [harness, plugin] = positional;
  requireHarness(harness);
  const plugins = pluginsToOperate(harness, plugin);

  const runs = plugins.map((p) => {
    const plan = planUninstall({ harness, plugin: p });
    const results = applyUninstall(plan, {
      dryRun: flags.dryRun,
      skipHooks: flags.skipHooks,
    });
    return { plan, results };
  });

  if (flags.json) {
    process.stdout.write(JSON.stringify({ action: 'uninstall', runs }, null, 2) + '\n');
    return;
  }
  printRuns('Uninstall', runs, flags);
}

async function cmdList(positional, flags) {
  const [harness] = positional;
  requireHarness(harness);
  const items = listInstalled(harness);
  if (flags.json) {
    process.stdout.write(JSON.stringify({ action: 'list', harness, items }, null, 2) + '\n');
    return;
  }
  if (items.length === 0) {
    console.log(`No hbrness items installed for ${harness}.`);
    return;
  }
  const byPlugin = {};
  for (const it of items) {
    (byPlugin[it.plugin] ||= []).push(it);
  }
  console.log(`Installed for ${harness}:`);
  for (const [plugin, list] of Object.entries(byPlugin)) {
    console.log(`  ${plugin} (${list.length})`);
    for (const it of list) {
      console.log(`    - ${it.kind}: ${it.name}  →  ${it.linkPath}`);
    }
  }
}

async function cmdPlugins(positional, flags) {
  const [harness] = positional;
  requireHarness(harness);
  const list = listBuiltPlugins(harness);
  if (flags.json) {
    process.stdout.write(JSON.stringify({ harness, plugins: list }, null, 2) + '\n');
    return;
  }
  if (list.length === 0) {
    console.log(`No built plugins in dist/${harness}/ (run "npm run build").`);
    return;
  }
  console.log(`Built plugins for ${harness}:`);
  for (const p of list) console.log(`  - ${p}`);
}

function printRuns(title, runs, flags) {
  const dry = flags.dryRun ? ' (dry-run)' : '';
  console.log(`${title}${dry}:`);
  let total = 0;
  let errors = 0;
  for (const { plan, results } of runs) {
    console.log(`\n  ${plan.harness}/${plan.plugin}`);
    for (const r of results) {
      total += 1;
      if (r.status === 'error') errors += 1;
      const marker = {
        linked: '✓',
        removed: '✓',
        merged: '✓',
        ok: '·',
        skipped: '·',
        planned: '…',
        error: '✗',
      }[r.status] || '?';
      const detail = formatOpDetail(r);
      const err = r.error ? ` — ${r.error}` : '';
      console.log(`    ${marker} ${r.action.padEnd(6)} ${detail}${err}`);
    }
  }
  console.log(`\n${total} operation(s)${errors ? `, ${errors} error(s)` : ''}.`);
  if (errors) process.exitCode = 1;
}

function formatOpDetail(r) {
  if (r.action === 'link') return `${r.linkName}  →  ${relPath(r.source)}`;
  if (r.action === 'unlink') return relPath(r.target);
  if (r.action === 'skip') return `(skipped: ${r.reason || ''})`;
  if (r.action === 'hooks') {
    const events = (r.events || []).map((e) => `${e.event}(${e.groupCount})`).join(', ');
    const backup = r.backup ? ` · backup: ${relPath(r.backup)}` : '';
    return `${relPath(r.target)}  [${events || 'no events'}]${backup}`;
  }
  return relPath(r.target);
}

function relPath(p) {
  if (!p) return '';
  const home = require('os').homedir();
  if (p.startsWith(home)) return '~' + p.slice(home.length);
  return p;
}

async function main(argv) {
  const { flags, positional } = parseArgs(argv);

  if (flags.version) {
    const pkg = require('../../package.json');
    console.log(pkg.version);
    return;
  }
  if (flags.help || positional.length === 0) {
    process.stdout.write(help());
    return;
  }

  const [cmd, ...rest] = positional;
  switch (cmd) {
    case 'install':
      return cmdInstall(rest, flags);
    case 'uninstall':
    case 'remove':
      return cmdUninstall(rest, flags);
    case 'list':
    case 'ls':
      return cmdList(rest, flags);
    case 'plugins':
      return cmdPlugins(rest, flags);
    default:
      throw new Error(`unknown command "${cmd}" (try "hbrness --help")`);
  }
}

module.exports = { main, parseArgs, help };
