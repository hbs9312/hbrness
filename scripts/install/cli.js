const {
  planInstall,
  applyPlan,
  planUninstall,
  applyUninstall,
  listInstalled,
  listBuiltPlugins,
} = require('./installer.js');
const { diagnose, repair } = require('./doctor.js');
const { update, detectMode } = require('./update.js');

const SUPPORTED_HARNESSES = ['claude', 'codex'];

function help() {
  return `hbrness — multi-harness plugin installer

Usage:
  hbrness install <harness> [plugin]       Set up hbrness plugins
                                           Claude default: build marketplace dir, then invoke "claude plugin
                                             marketplace add" and "claude plugin install" automatically
                                           Codex default: symlink into ~/.codex/skills
                                           --print-only (claude): skip running claude CLI; print commands to paste manually
                                           --mode user-level (claude): symlink fallback instead of plugin mode
  hbrness uninstall <harness> [plugin]     Remove installed hbrness plugin + user-level symlinks
  hbrness list <harness>                   List currently installed items
  hbrness plugins <harness>                List built plugins in dist/
  hbrness doctor [harness]                 Scan for dangling links and stale hooks
  hbrness repair [harness]                 Apply fixes for issues doctor finds
  hbrness update                           Pull latest (git clone) or show upgrade hint (npm)
  hbrness --help                           Show this help
  hbrness --version                        Print package version

Harnesses: ${SUPPORTED_HARNESSES.join(', ')}

Options:
  --dry-run                                Show the plan; do not modify the filesystem
  --json                                   Machine-readable output
  --mode <plugin|user-level>               Override the default install mode for this command
  --print-only                             (plugin mode) Don't invoke the claude CLI; just print the commands
  --no-hooks                               (user-level mode) Skip merging plugin hooks into settings.json
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
  const flags = {
    dryRun: false,
    json: false,
    yes: false,
    skipHooks: false,
    mode: null,
    printOnly: false,
  };
  const positional = [];
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--dry-run') flags.dryRun = true;
    else if (a === '--json') flags.json = true;
    else if (a === '--yes' || a === '-y') flags.yes = true;
    else if (a === '--no-hooks') flags.skipHooks = true;
    else if (a === '--print-only') flags.printOnly = true;
    else if (a === '--mode') {
      flags.mode = argv[++i];
      if (!['plugin', 'user-level'].includes(flags.mode)) {
        throw new Error(`--mode must be "plugin" or "user-level" (got "${flags.mode}")`);
      }
    } else if (a.startsWith('--mode=')) {
      flags.mode = a.slice('--mode='.length);
      if (!['plugin', 'user-level'].includes(flags.mode)) {
        throw new Error(`--mode must be "plugin" or "user-level" (got "${flags.mode}")`);
      }
    } else if (a === '--help' || a === '-h') flags.help = true;
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
    const plan = planInstall({
      harness,
      plugin: p,
      mode: flags.mode,
      printOnly: flags.printOnly,
    });
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
  printDeferredHints(runs);
}

function printDeferredHints(runs) {
  const deferred = [];
  for (const run of runs) {
    for (const r of run.results) {
      if (r.status === 'deferred' && r.hint) deferred.push(r.hint);
    }
  }
  if (deferred.length === 0) return;
  console.log('');
  console.log('The `claude` CLI was unavailable or --print-only was set.');
  console.log('Run the following commands to finish wiring the plugins into Claude Code:');
  console.log('');
  const seen = new Set();
  for (const cmd of deferred) {
    if (seen.has(cmd)) continue;
    seen.add(cmd);
    console.log(`  ${cmd}`);
  }
}

async function cmdUninstall(positional, flags) {
  const [harness, plugin] = positional;
  requireHarness(harness);
  const plugins = pluginsToOperate(harness, plugin);

  const runs = plugins.map((p) => {
    const plan = planUninstall({ harness, plugin: p, printOnly: flags.printOnly });
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
  printDeferredHints(runs);
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

async function cmdDoctor(positional, flags) {
  const [harness] = positional;
  const harnesses = harness ? [harness] : SUPPORTED_HARNESSES;
  for (const h of harnesses) requireHarness(h);
  const issues = diagnose({ harnesses });

  if (flags.json) {
    process.stdout.write(JSON.stringify({ action: 'doctor', harnesses, issues }, null, 2) + '\n');
    if (issues.some((i) => i.severity === 'error')) process.exitCode = 1;
    return;
  }

  if (issues.length === 0) {
    console.log('No issues found.');
    return;
  }

  printIssues(issues);
  const errorCount = issues.filter((i) => i.severity === 'error').length;
  if (errorCount > 0) process.exitCode = 1;
}

async function cmdRepair(positional, flags) {
  const [harness] = positional;
  const harnesses = harness ? [harness] : SUPPORTED_HARNESSES;
  for (const h of harnesses) requireHarness(h);
  const issues = diagnose({ harnesses });
  const fixable = issues.filter((i) => i.fix);

  if (flags.json) {
    const { results, backup } = repair(fixable, { dryRun: flags.dryRun });
    process.stdout.write(
      JSON.stringify({ action: 'repair', issues, results, backup }, null, 2) + '\n',
    );
    return;
  }

  if (issues.length === 0) {
    console.log('No issues found.');
    return;
  }
  if (fixable.length === 0) {
    console.log('Issues found but none are auto-fixable:');
    printIssues(issues);
    return;
  }

  const { results, backup } = repair(fixable, { dryRun: flags.dryRun });
  const dry = flags.dryRun ? ' (dry-run)' : '';
  console.log(`Repair${dry}:`);
  for (const r of results) {
    const marker = { fixed: '✓', planned: '…', 'already-clean': '·', 'no-fix': '·', error: '✗' }[r.status] || '?';
    const err = r.error ? ` — ${r.error}` : '';
    console.log(`  ${marker} ${r.status.padEnd(14)} ${r.issue.detail}${err}`);
  }
  if (backup) console.log(`\nSettings backup: ${relPath(backup)}`);
  const nonFixable = issues.filter((i) => !i.fix);
  if (nonFixable.length > 0) {
    console.log('\nUnfixable issues (informational):');
    printIssues(nonFixable);
  }
  const errors = results.filter((r) => r.status === 'error').length;
  if (errors > 0) process.exitCode = 1;
}

async function cmdUpdate(positional, flags) {
  if (flags.json) {
    const mode = detectMode();
    const result = update({ dryRun: flags.dryRun });
    process.stdout.write(
      JSON.stringify({ action: 'update', mode, result }, null, 2) + '\n',
    );
    return;
  }
  update({ dryRun: flags.dryRun });
}

function printIssues(issues) {
  const bySeverity = { error: [], warn: [], info: [] };
  for (const i of issues) (bySeverity[i.severity] || bySeverity.info).push(i);
  for (const [sev, list] of Object.entries(bySeverity)) {
    if (list.length === 0) continue;
    const label = { error: '🔴', warn: '🟡', info: 'ℹ' }[sev];
    console.log(`${label} ${sev} (${list.length})`);
    for (const i of list) console.log(`    [${i.type}] ${i.detail}`);
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
        refreshed: '✓',
        added: '✓',
        installed: '✓',
        created: '✓',
        exists: '·',
        ok: '·',
        skipped: '·',
        'already-clean': '·',
        deferred: '➜',
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
  if (r.action === 'setup-marketplace')
    return `${relPath(r.target)}  [${r.count} plugins]`;
  if (r.action === 'claude-marketplace-add')
    return `claude plugin marketplace add ${relPath(r.target)}`;
  if (r.action === 'claude-plugin-install')
    return `claude plugin install ${r.target}`;
  if (r.action === 'claude-plugin-uninstall')
    return `claude plugin uninstall ${r.target}`;
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
    case 'doctor':
      return cmdDoctor(rest, flags);
    case 'repair':
      return cmdRepair(rest, flags);
    case 'update':
      return cmdUpdate(rest, flags);
    default:
      throw new Error(`unknown command "${cmd}" (try "hbrness --help")`);
  }
}

module.exports = { main, parseArgs, help };
