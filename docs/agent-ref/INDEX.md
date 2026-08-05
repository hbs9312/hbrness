# hbrness Skill Index

> Load this file for phase overview. Read `P{n}.md` for detail when entering that phase.
> Monolithic version: `docs/USAGE_FLOW_AGENT.md`
>
> Scope: 5 plugins — ghflow / xreview / dbflow / sessionflow / agentbus.
> Planning, spec generation, and code generation are **not** part of hbrness; `specs/` is human-owned input.

## Phase Pipeline

| Phase | File | Summary | Inputs → Outputs |
|---|---|---|---|
| P1 | [P1.md](P1.md) | Issue & branch (ghflow) | — → issue, branch, draft PR |
| P2 | [P2.md](P2.md) | Implementation (outside hbrness) | issue → code |
| P3 | [P3.md](P3.md) | E2E DB (dbflow) | QA spec → sandbox scenarios + delta verify |
| P4 | [P4.md](P4.md) | Review, commit & PR (xreview + ghflow) | changes → review, commit, chronicle, PR |

## Cross-cutting (any phase)

| Area | File | Summary |
|---|---|---|
| Session management (sessionflow) | [SESSION.md](SESSION.md) | `handoff` / `followup` / `phase-run` / `phase-loop` — preserve & resume context across sessions; `phase-loop` wraps P2→P4 and ships each phase as a PR |
| Agent messaging (agentbus) | [AGENTBUS.md](AGENTBUS.md) | alias-based fire-and-forget messaging between tmux sessions (claude/codex/shell) |

## Scenarios

| Scenario | Flow |
|---|---|
| New feature (full) | P1 → P2 → P3 → P4 |
| Hotfix | P1(pick-issue → draft-pr) → fix → P4 |
| Schema re-verify | write migration → P3(migrate --fresh → up → run) |
| Archaeology | P4(chronicle-lookup) |
| Long unattended run | `phase-loop <plan>` — wraps P2→P4 |
| Parallel sessions | `agent-register` per session → `agent-send` to sync |

## Key Rules

1. `specs/` is read-only input — hbrness consumes it, never generates it
2. Review with the opposite model (`xreview`) before committing
3. dbflow safety invariants are hardcoded (sandbox naming, pg_dump only, confirm)
4. `chronicle` preserves the "why" that the diff cannot
5. Break long work into phases (`phase-run` / `phase-loop`) to avoid context decay
6. Sonnet for mechanical skills (86%), Opus for judgment skills (14%)
