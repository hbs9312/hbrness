# Grok Build / Devin CLI integration — 2026-09-22

Implementation branch: `feat/grok-devin` in
`/Users/seok/orca/workspaces/hbrness/grok-devin`.
The original `/Users/seok/development/hbrness` checkout was left unchanged.
Its five pre-existing uncommitted phaseflow/xreview script changes were copied
into this worktree before implementation; they are not newly authored changes
from this task. No commits or releases were created during that initial installation.

On 2026-09-23 the user requested local main integration. The pre-existing
phaseflow/xreview diff was excluded from the feature commit and preserved in
the original main working tree. Use `/Users/seok/development/hbrness` for
subsequent builds and installs after integration; the earlier paths below
describe the initial verification.

## Installed on this machine

- Grok Build 1.0.34: `~/.grok/plugins/{agentbus,dbflow,ghflow,sessionflow,xreview}`.
- Devin CLI 3000.11.1: `~/.config/devin/hbrness-plugins/<plugin>`, registered with
  `devin plugins install --local --yes`. No personal cloud registration.
- Each CLI discovers 5 hbrness plugins and 35 skills. Grok resolves each plugin
  once from its native directory instead of the imported Claude copy.
- `pick-issue` and `clear-issue` keep their existing Claude-only gate.
- The system-wide npm `hbrness` command was not replaced. Until this branch is
  integrated/released, run the new installer explicitly:

```bash
node /Users/seok/orca/workspaces/hbrness/grok-devin/bin/hbrness.js install grok
node /Users/seok/orca/workspaces/hbrness/grok-devin/bin/hbrness.js install devin
```

## Verification

- `npm run build`: all four harnesses built.
- `npm run validate`: source rules, manifests, and skill counts passed.
- `npm test`: 5 Node tests and 5 Python tests passed, covering local registration,
  rollback, ownership protection, path quoting, hook omission, caller identity,
  failed-commit suppression, recipient-specific Enter, and namespaced resume.
- `hbrness doctor grok` and `hbrness doctor devin`: no issues.
- `grok inspect --json`: all 35 native skills, no duplicate hbrness plugins.
- `devin skills list`: all 35 qualified plugin skills.
- `devin plugins info ghflow`: native `PostToolUse` hook with matcher `^exec$`.
- Devin live smoke test: read installed xreview status instructions and execute
  the status script against a temporary empty review registry. Exit 0 and
  `no review sessions` output; recorded a real `PostToolUse` event for `exec`.
  Only that command was allowed in a temporary config. No review agent was
  launched. An initial natural-language skill lookup chose the ambiguous short
  name `status` (dbflow); the agent corrected it by reading the xreview skill.
  Prefer qualified slash commands such as `/xreview:status`.
- Real Devin payloads use `tool_response.success` for tool success and embed
  `Exit code: 0` in `tool_response.output`. The commit hook checks that trailing
  status, suppressing failed or still-running shell commands.
- Grok live smoke test did not start: its `read-only` sandbox rejected the
  existing `/var/run/docker.sock` symlink while resolving socket deny paths.
  The sandbox was not disabled. Discovery and local script tests passed.
- No live tmux pane was reset, no reviewer agent was launched, and no repository
  commit/PR or database workflow was executed as part of validation.

## Runtime limits

- Grok ignores passive hook stdout. Commit chronicles are invoked explicitly
  with `/ghflow:chronicle`; no ineffective PostToolUse reminder is installed.
- Devin installs the commit reminder. Template-fetch hooks stay disabled.
- xreview supports Grok/Devin callers with Codex as the default reviewer;
  built-in reviewer launch commands remain Claude and Codex.
- phase-run/phase-loop remain tmux workflows. Relay requires the CLI's subagent
  capability. Session control was tested with fixtures, not live reset loops.
- Handoff/followup data remains shared under `~/.hbrness`. Existing Claude/Codex
  memory indexes are maintained; native automatic-memory loading for the new
  CLIs is not implemented.

## Personal shared hooks

The companion `.claude` worktree is
`/Users/seok/orca/workspaces/.claude/add-devin` (`hbs9312/add-devin`).
`stop.sh`, `save_diff.sh`, and `gcloud_guard.sh` were updated there and copied to
the active `~/.claude/hooks/` directory. Devin's user config gained an explicit
`^exec$` guard registration. Existing Orca hooks were preserved.

Original scripts and Devin config are backed up at
`~/.hbrness/backups/grok-devin-20260922-121705/`.
Synthetic Claude/Grok/Devin guard inputs verified blocking and allowed results;
the Stop script produced no output, including when a test secret was present
in its process environment. No actual gcloud operation was executed.

## References

- [Grok plugin discovery](https://docs.x.ai/build/features/skills-plugins-marketplaces)
- [Grok hook contract](https://docs.x.ai/build/features/hooks)
- [Devin native plugins](https://docs.devin.ai/cli/extensibility/plugins/overview)
- [Devin hook contract](https://docs.devin.ai/cli/extensibility/hooks/overview)
