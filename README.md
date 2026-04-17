# hbrness

[![npm version](https://img.shields.io/npm/v/hbrness.svg)](https://www.npmjs.com/package/hbrness)
[![npm downloads](https://img.shields.io/npm/dm/hbrness.svg)](https://www.npmjs.com/package/hbrness)
[![license](https://img.shields.io/npm/l/hbrness.svg)](./LICENSE)
[![node](https://img.shields.io/node/v/hbrness.svg)](https://www.npmjs.com/package/hbrness)

Multi-harness AI coding plugin repository. Harness-neutral common sources build into Claude Code and Codex CLI plugin packages.

## Plugins

| Plugin | Version | Skills | Description |
|--------|---------|--------|-------------|
| specflow | 1.5.0 | 21 | Spec generation & validation workflow |
| frontflow | 1.3.0 | 16 | Frontend implementation (tokens → pages) |
| backflow | 0.4.0 | 14 | Backend implementation (schema → API) |
| ghflow | 0.3.0 | 7 | GitHub issue/PR/review workflow |
| meeting-prep | 0.1.0 | 3 | Meeting preparation automation |
| xreview | 0.1.1 | 1 | External LLM code review |

## Install

| Harness | Default mode | Install location | Invocation |
|---|---|---|---|
| Claude | `plugin` | `~/.claude/plugins/cache/hbrness/<plugin>/<version>/` | `/ghflow:review-pr` (plugin namespace) |
| Codex  | `user-level` | `~/.codex/skills/<plugin>-<name>` (symlink) | `/ghflow-review-pr` (hyphen prefix) |

Claude installs register the plugin in `installed_plugins.json` and appear in `/plugin list`. Pass `--mode user-level` to fall back to per-skill symlinks in `~/.claude/skills/` (hyphen-prefixed invocation, hooks merged into `settings.json`). Installing in one mode auto-migrates any leftovers from the other mode.

### Via npm (recommended)

```bash
# One-off — no global install
npx hbrness install claude               # all plugins
npx hbrness install claude ghflow        # single plugin
npx hbrness install codex specflow

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

Codex hook merging is not supported yet.

Restart the harness (Claude Code / Codex) after install or uninstall so it picks up new skills.

## Build

```bash
# Build for a specific harness
./scripts/build.sh claude
./scripts/build.sh codex
./scripts/build.sh all

# Build a single plugin
./scripts/build.sh claude specflow

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
