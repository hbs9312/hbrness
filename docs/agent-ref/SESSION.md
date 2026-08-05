# Cross-cutting: Session Management (sessionflow)

> Not a pipeline phase — applies at any point to preserve & resume context across sessions. Claude ↔ Codex share the same files (Tier 1).

```
handoff         /handoff [-m|-o] [msg]        → serialize in-flight context (editing files, last cmd, error, next single step) to HANDOFF.md. Worktree-scoped. Next session resumes in place.
handoff-clear   /handoff-clear [-y] [--all]   → delete HANDOFF.md + MEMORY.md line (--all = all worktrees in project)
followup        /followup [-m|-o] [msg]       → append a follow-up item (TODO / deferred issue / idea) to followups/. Project-scoped, persistent, accumulates.
followup-clear  /followup-clear [-y]          → clear the whole followups/ dir + MEMORY.md section
phase-run       /phase-run <plan>             → split a long task into phases; at each boundary auto-inject /clear + /phase-run continue so a fresh session reads HANDOFF.md and continues. Resets context accumulation per phase. No auto-commit. tmux required.
                /phase-run continue|status|pause|resume|stop|reset
phase-loop      /phase-loop <plan>            → phase-run + per-phase xreview review → commit → push → PR. Personal repo: direct branch. Team repo: worktree + stacked PRs. Repeats until every PR unit is done.
                /phase-loop continue|status|pause|resume|stop|reset
```

**handoff vs followup vs phase-run vs phase-loop**

- `handoff` — carry THIS in-flight work to the next session (1-shot, per-worktree).
- `followup` — record work to do LATER (persistent backlog, per-project).
- `phase-run` — drive a long multi-phase task hands-off, clearing context between phases. It can wrap *any* work — including the whole P1→P4 pipeline — so each phase starts with a fresh context window. (`phase-run` writes a per-phase `HANDOFF.md` at the boundary, so it builds on the same handoff plumbing.)
- `phase-loop` — `phase-run` plus shipping: each phase boundary also runs review, commit, push, and PR. Wraps P2→P4.

**Storage** (Tier 1, tool-agnostic): `~/.hbrness/sessionflow/<project-key>/` → `HANDOFF.md`, `followups/`, `phases/`. Both harnesses' `MEMORY.md` auto-synced to point here.
