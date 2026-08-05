# hbrness Skill Reference (Agent-Optimized)

> Compact version of `USAGE_FLOW.md`. Both files must be updated together.
> Human-readable version: `docs/USAGE_FLOW.md`

> **Scope**: 5 plugins — ghflow / xreview / dbflow / sessionflow / agentbus.
> Spec generation (specflow), code generation (frontflow / backflow), and planning intake (meeting-prep) were removed. Planning, specs, and implementation live outside hbrness; hbrness handles issue/PR workflow, cross-model review, E2E DB verification, and session management.

---

## Skill Execution Order

Skills run top-to-bottom per phase. Each phase's output feeds the next.

### P1: Issue & Branch (ghflow)

```
ghflow:list-work          → available work
ghflow:create-issue       → GitHub issue
ghflow:pick-issue         → select + save to memory
ghflow:draft-pr           → branch + empty commit + draft PR + issue link
```

### P2: Implementation

Outside hbrness. Write the code directly or use another tool.

For long runs, wrap with `sessionflow:phase-loop` (see Cross-cutting) — it automates P2→P4 per PR unit.

### P3: E2E DB (dbflow — after backend work lands)

```
# setup (once)
dbflow:init                                → .e2e/ scaffold
# edit .e2e/config.yml manually

dbflow:snapshot                            → source DB → sandbox clone
dbflow:migrate                             → apply migrations to sandbox
dbflow:up                                  → start API server on sandbox

# scenarios
dbflow:gen-scenarios  specs/QA-*.md        → .e2e/scenarios/*.yml   [reads QA spec's E2E DB table]
dbflow:run            <scenario_name>      → execute + verify DB delta
dbflow:validate-scenarios                  → YAML integrity + safety invariants

# debug
dbflow:watch          <tables>             → before snapshot
dbflow:diff                                → show insert/update/delete

# lifecycle
dbflow:status                              → current sandbox state
dbflow:down                                → stop API server
dbflow:reset                               → drop sandbox + reinit
```

`gen-scenarios` input is a hand-authored (or externally generated) QA spec file under `specs/`.

### P4: Review, Commit & PR (xreview + ghflow)

```
xreview:live                               → background code review by the opposite agent (claude↔codex); launcher auto-injects work intent as --context
xreview:status                             → list running review sessions
xreview:stop                               → end a session (review artifacts preserved)

ghflow:commit                              → generate message per team convention + commit
ghflow:commit -y                           → auto-commit (no confirmation)
ghflow:chronicle                           → record commit intent/decisions
ghflow:create-pr                           → GitHub PR (template-based)
ghflow:review-pr                           → check + process review comments (default: unresolved only — token saver)
ghflow:review-pr 101 --all                 → include resolved threads too
ghflow:clear-issue                         → cleanup issue memory
ghflow:chronicle-lookup <query>            → search past commit rationale
```

---

## Cross-cutting — Session Management (sessionflow)

> Not a pipeline phase; applies anywhere. Claude ↔ Codex share the same files (Tier 1).

```
handoff         /handoff [-m|-o] [msg]        → serialize in-flight context → HANDOFF.md (worktree-scoped). Resume in place next session.
handoff-clear   /handoff-clear [-y] [--all]   → delete HANDOFF.md + MEMORY.md line
followup        /followup [-m|-o] [msg]       → append later-TODO to followups/ (project-scoped, persistent)
followup-clear  /followup-clear [-y]          → clear followups/
phase-run       /phase-run <plan>             → split into phases; auto /clear + /phase-run continue at each boundary → fresh session reads HANDOFF.md and continues. No auto-commit. tmux required.
                /phase-run continue|status|pause|resume|stop|reset
phase-loop      /phase-loop <plan>            → phase-run + per-phase xreview → commit → push → PR. Personal repo: direct branch. Team repo: worktree + stacked PRs. Wraps P2→P4.
                /phase-loop continue|status|pause|resume|stop|reset
```

handoff = carry THIS work forward (1-shot/worktree). followup = LATER backlog (persistent/project). phase-run = hands-off multi-phase run that resets context between phases. phase-loop = phase-run plus shipping.

---

## Cross-cutting — Agent Messaging (agentbus)

> Cross-session, tool-agnostic (claude/codex/shell). Fire-and-forget, not RPC.

```
agent-register   /agent-register <alias> [--tool claude|codex|shell]  → bind current tmux pane to an alias
agent-list       /agent-list                                          → registry table (prunes dead panes)
agent-send       /agent-send <alias> <msg>                            → inject into recipient's prompt via send-keys
                 /agent-send <alias> --file <path> | --json           → write to inbox, inject notification only
agent-inbox      /agent-inbox [list|show <id>|mark <id>|clear]        → read own mailbox (file-delivered msgs only)
agent-unregister /agent-unregister [alias]                            → release alias
```

Short messages go straight to the prompt; long or structured payloads land in `~/.hbrness/agentbus/inbox/<recipient>/` and only a notification is injected.

---

## Scenario Quick-Reference

| Scenario | Start at | Skip |
|---|---|---|
| New feature (full) | P1 | — |
| Hotfix | P1 `pick-issue` → `draft-pr` → fix → P4 | P3 |
| Schema change re-verify | write migration → P3 `migrate --fresh` → `up` → `run` | P1, P2, P4 |
| Code archaeology | P4 `chronicle-lookup` | everything else |
| Long unattended run | `phase-loop <plan>` (wraps P2→P4) | — |
| Parallel front/back sessions | `agent-register` per session → `agent-send` to sync | — |

---

## Dependency Graph (compact)

```
ghflow (issue / branch / draft PR)
     │
implementation (outside hbrness)
     │
     ├──────────► dbflow (E2E, after backend)
     │               └── gen-scenarios ← QA spec (specs/)
     ▼
xreview (cross-model review)
     │
     ▼
ghflow (commit · chronicle · create-pr · review-pr)

sessionflow — spans every phase (handoff / followup / phase-run / phase-loop)
agentbus    — cross-session messaging (pipeline-independent)
```

Key cross-plugin data flows:
- **`specs/` is read-only input** — dbflow consumes it; nothing in hbrness generates it
- **QA spec drives dbflow** — `gen-scenarios` reads the QA spec's E2E DB scenario table
- **Review before commit** — `xreview:live` runs on the opposite provider, then `ghflow:commit`

---

## Model Assignment

| Model | Skills | Ratio |
|---|---|---|
| **Sonnet** (auto, via frontmatter) | `ghflow` all (incl. `commit`), `agentbus` all, `xreview` all, `dbflow` (init~diff), `sessionflow` handoff/followup family | 31/36 (86%) |
| **Opus** (session default) | `dbflow:gen-scenarios` / `dbflow:run` / `dbflow:validate-scenarios`, `sessionflow:phase-run` / `phase-loop` | 5/36 (14%) |

---

## Rules

1. **Specs are external** — `specs/` is human-owned; hbrness reads it, never generates it
2. **Review with the opposite model** — same-model self-review misses things; `xreview` crosses claude↔codex
3. **Safety invariants hardcoded** in dbflow (sandbox naming, pg_dump only, confirm)
4. **Commit intent lives outside the diff** — `chronicle` preserves the "why"
5. **Break long work into phases** — `phase-run` / `phase-loop` prevent context-accumulation quality decay
6. **Mechanical work uses Sonnet** — `model: sonnet` frontmatter
