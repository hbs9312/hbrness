# hbrness

[![npm version](https://img.shields.io/npm/v/hbrness.svg)](https://www.npmjs.com/package/hbrness)
[![npm downloads](https://img.shields.io/npm/dm/hbrness.svg)](https://www.npmjs.com/package/hbrness)
[![license](https://img.shields.io/npm/l/hbrness.svg)](./LICENSE)
[![node](https://img.shields.io/node/v/hbrness.svg)](https://www.npmjs.com/package/hbrness)

Multi-harness AI coding plugin repository. Common sources build into Claude Code, Codex CLI, Grok Build, and Devin CLI packages.

## Plugins

| Plugin | Version | Skills | Description |
|--------|---------|--------|-------------|
| dbflow | 0.1.2 | 12 | Sandbox E2E DB scenario testing |
| ghflow | 0.5.3 | 10 | GitHub issue/PR/review workflow |
| sessionflow | 0.12.0 | 6 | Session handoff, followup backlog & phase loop |
| agentbus | 0.2.0 | 5 | Cross-agent messaging over tmux |
| xreview | 1.2.0 | 3 | Background peer code review (claude↔codex) |

## Install

```bash
npm install -g hbrness
hbrness install claude             # writes ~/.claude/plugins/marketplaces/hbrness/
```

Then inside Claude Code, paste the commands the installer prints — something like:

```
/plugin marketplace add ~/.claude/plugins/marketplaces/hbrness
/plugin install ghflow@hbrness
/plugin install dbflow@hbrness
```

Claude Code owns the final registration — it writes its own `known_marketplaces.json` and `installed_plugins.json` entries, which means hbrness never drifts out of sync with Claude's plugin-config schema.

Invocation afterwards: `/ghflow:review-pr`, `/sessionflow:handoff`, etc.

### Modes

| Harness | Default | What hbrness does | What you do |
|---|---|---|---|
| Claude | marketplace-only | builds `~/.claude/plugins/marketplaces/hbrness/` | `/plugin marketplace add <path>` + `/plugin install <name>@hbrness` |
| Codex  | user-level | symlinks into `~/.codex/skills/<plugin>-<name>` | nothing — already live after restart |
| Grok Build | plugin | copies native packages into `$GROK_HOME/plugins/<plugin>` (default `~/.grok`) | restart the session |
| Devin CLI | plugin | copies packages into `$XDG_CONFIG_HOME/devin/hbrness-plugins/<plugin>` and registers with `devin plugins install --local --yes` | restart the session |

### Grok Build and Devin CLI

```bash
npm run build
node bin/hbrness.js install grok --dry-run
node bin/hbrness.js install grok
node bin/hbrness.js install devin
node bin/hbrness.js doctor grok
node bin/hbrness.js doctor devin
```

Both use `/<plugin>:<skill>`, for example `/ghflow:create-pr`,
`/sessionflow:handoff`, and `/xreview:status`. Each gets 35 skills across the five
plugins. `ghflow:pick-issue` and `ghflow:clear-issue` remain Claude-only because
they manage Claude session memory. Skill-level Claude model pins and tool
auto-approval lists are omitted; the current session's model and permissions apply.

Grok's native packages take precedence over Claude-imported plugins with the
same name, preventing duplicate hbrness skills. Other Claude imports remain
enabled. Devin installations are **local only**, not added to the personal cloud
manifest. Devin must be signed in for its plugin registration command.

Installations contain concrete script paths; they do not depend on
`CLAUDE_PLUGIN_ROOT` or undocumented environment variables. The installer owns
only directories marked `.hbrness-origin`, refuses to overwrite other plugins,
backs up an existing package outside the discovery directory, and restores it
if registration fails. `--no-hooks` omits hook registration files. Install again
after rebuilding to refresh the installed copy. `uninstall grok|devin` removes
the owned local package; Grok may then discover the original Claude plugin again.

Runtime differences:

- `xreview` accepts Grok/Devin as the **caller**, defaults to a Codex reviewer,
  and returns its notification to that caller. Built-in reviewer launchers remain
  Claude/Codex; other reviewers require `--launch-cmd`.
- `agentbus` identifies Grok/Devin recipients and submits with Enter, even when
  the sender inherited Codex environment variables.
- `phase-run`/`phase-loop` use `/new` and namespaced resume commands for the new
  CLIs. These workflows still need tmux. `relay` uses the current agent's subagent
  capability; enable that capability before starting a relay.
- Devin's `PostToolUse` hook reminds the agent to run `ghflow:chronicle` after a
  successful `exec` commit. Grok ignores passive hook stdout, so invoke
  `/ghflow:chronicle` explicitly there. Template-fetch hooks remain disabled.
- Shared handoff/followup files stay in `~/.hbrness`; the existing skills also
  maintain the Claude/Codex memory indexes. This does not create a native
  Grok/Devin automatic-memory integration.

Verify discovery with `grok inspect --json`, `devin skills list`, and
`devin plugins info ghflow`. `npm test` checks local-only registration, rollback,
quoting, hook outcomes, and session-control command selection without sending
messages or resetting a live session.

### Flags

- `--auto-register` (Claude, plugin mode): also writes Claude's registry files directly. Removes the manual `/plugin` step but relies on hbrness shipping an up-to-date schema. Not recommended — Claude Code's schema may change between versions.
- `--mode user-level` (Claude): skip the plugin system, symlink each skill into `~/.claude/skills/<plugin>-<name>/` and merge hooks into `settings.json`. Invocation becomes `/ghflow-review-pr` (hyphen).
- `--dry-run`: show the plan without touching the filesystem.
- `--json`: machine-readable output.

### Via npm (recommended)

```bash
# One-off — no global install
npx hbrness install claude               # all plugins
npx hbrness install claude ghflow        # single plugin
npx hbrness install codex sessionflow

# Or install globally
npm install -g hbrness
hbrness install claude
```

### From a local clone (development)

```bash
git clone https://github.com/hbs9312/hbrness.git
cd hbrness
npm run build
./scripts/install.sh claude            # legacy shorthand
# or: node bin/hbrness.js install claude
```

### CLI commands

```bash
hbrness install   <harness> [plugin]    # register plugin (claude) or symlink (codex)
hbrness uninstall <harness> [plugin]    # clean both plugin and user-level installs
hbrness list      <harness>             # show what's installed
hbrness plugins   <harness>             # show what's built in dist/
hbrness doctor    [harness]             # scan for dangling links, stale hooks
hbrness repair    [harness]             # apply auto-fixes for issues doctor finds
hbrness update                          # git pull + rebuild + refresh (clone), or upgrade hint (npm)
hbrness --help
```

Options:
- `--dry-run` — print the plan without touching the filesystem
- `--json` — machine-readable output
- `--mode <plugin|user-level>` — override the default install mode
- `--no-hooks` — (user-level mode) skip merging plugin hooks into `~/.claude/settings.json`

### Hooks

When a Claude plugin ships a `hooks/hooks.json`, `hbrness install claude <plugin>` also merges its entries into `~/.claude/settings.json` under the matching event (e.g. `SessionStart`). Each injected entry is tagged with an `_hbrness` sentinel so uninstall removes only hbrness-owned entries and leaves the rest of your hook configuration untouched. A timestamped backup (`settings.json.hbrness-bak.<ts>`) is written before every modification. Use `--no-hooks` to opt out.

Codex hook merging is not supported yet. Devin uses a native plugin hook file;
Grok does not install the passive commit-reminder hook (see above).

Restart the harness (Claude Code / Codex) after install or uninstall so it picks up new skills.

## Build

```bash
# Build for a specific harness
./scripts/build.sh claude
./scripts/build.sh codex
./scripts/build.sh all

# Build a single plugin
./scripts/build.sh claude ghflow

# Validate build outputs
./scripts/validate.sh
```

## Architecture

```
plugins/           # Harness-neutral source (.common.md)
adapters/          # Transformation rules per harness
scripts/           # Build, validation, install tooling
  build.sh            # Shell entry to build
  install.sh          # Legacy shorthand → delegates to bin/hbrness.js
  install/            # Node installer modules
  build-plugin.py     # Python build logic
bin/
  hbrness.js       # npm bin — CLI entry
dist/              # Build output (gitignored)
  claude/          # Claude Code plugin packages
  codex/           # Codex CLI plugin packages
  grok/            # Grok native packages (Claude-compatible manifest)
  devin/           # Devin native packages
```

**Source files** use abstract tool names (`file:read`, `sub-agent`, `${SKILL_DIR}`) and the build script transforms them to harness-specific equivalents.

### Adding a New Harness

1. Create `adapters/<harness>.adapter.json` with tool mappings and body replacements
2. Add hook config to `adapters/hooks/` if needed
3. Extend `scripts/install/paths.js#harnessTargets` with the new harness's skill/agent roots
4. Run `./scripts/build.sh <harness>`

## Development

Edit files in `plugins/` (`.common.md` format only). Never edit `dist/` directly.

```bash
# After editing a common source:
npm run build
npm run validate
```

Iterate on the installer itself with `node bin/hbrness.js ...`. Use `--dry-run` to preview changes.
