# hbrness

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

## Quick Start

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

## Install

```bash
# Build + install all plugins to Codex CLI
./scripts/install.sh codex

# Build + install a single plugin
./scripts/install.sh codex specflow

# List installed plugins
./scripts/install.sh list codex

# Uninstall
./scripts/install.sh uninstall codex specflow
./scripts/install.sh uninstall codex          # all
```

For Claude Code, use `--plugin-dir` per session:

```bash
claude --plugin-dir dist/claude/specflow
```

## Architecture

```
plugins/           # Harness-neutral source (.common.md)
adapters/          # Transformation rules per harness
scripts/           # Build & validation tooling
dist/              # Build output (gitignored)
  claude/          # Claude Code plugin packages
  codex/           # Codex CLI plugin packages
```

**Source files** use abstract tool names (`file:read`, `sub-agent`, `${SKILL_DIR}`) and the build script transforms them to harness-specific equivalents.

### Adding a New Harness

1. Create `adapters/<harness>.adapter.json` with tool mappings and body replacements
2. Add hook config to `adapters/hooks/` if needed
3. Run `./scripts/build.sh <harness>`

## Development

Edit files in `plugins/` (`.common.md` format only). Never edit `dist/` directly.

```bash
# After editing a common source:
./scripts/build.sh all
./scripts/validate.sh
```
