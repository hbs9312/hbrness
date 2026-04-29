# hbrness Skill Reference (Agent-Optimized)

> Compact version of `USAGE_FLOW.md`. Both files must be updated together.
> Human-readable version: `docs/USAGE_FLOW.md`

---

## Skill Execution Order

Skills run top-to-bottom per phase. Each phase's output feeds the next.

### P1: Planning

```
meeting-prep:spec-scanner  specs/          → gap report
meeting-prep:impl-scanner  src/            → impl status
meeting-prep:meeting-doc-gen               → meeting doc (consumes both above)
```

### P2: Specification (specflow — sequential, order matters)

```
generate-fs    PRD.md                      → specs/FS-*.md
generate-wf    specs/FS-*.md               → specs/WF-*.md
  OR extract-wf-from-figma <figma-url>     → specs/WF-*.md
state-matrix   specs/WF-*.md               → (appended to WF)
extract-ui     specs/WF-*.md               → specs/UI-*.md
generate-ts    specs/FS-*.md specs/WF-*.md → specs/TS-*.md
generate-erd   specs/TS-*.md               → (optional) ERD image
generate-qa    specs/FS-*.md specs/TS-*.md → specs/QA-*.md
extract-refs   specs/                      → ref index
decompose      specs/TS-*.md              → specs/PLAN-*-tasks.md
```

**TS contains**: §3.2 OpenAPI fragment, §4 error code map, §7.1 observability, §9 file handling, §10 webhook.

### P3: Spec Validation (gate — must pass before P5/P6)

```
xreview:review            specs/TS-*.md
backend-spec-review       specs/TS-*.md
backend-team-review       specs/TS-*.md    (optional)
```

On failure → revise + re-validate:
```
specflow:revise           specs/TS-*.md
specflow:change-impact    specs/TS-*.md
spec-refine-loop          specs/TS-*.md    (iterative)
```

### P4: Issue & Branch (ghflow)

```
ghflow:create-issue       → GitHub issue
ghflow:pick-issue         → select + save to memory
ghflow:draft-pr           → branch + empty commit + draft PR + issue link
```

### P5: Backend (backflow — sequential, can parallel with P6)

Run `scan-codebase` once per project.

```
scan-codebase                              → registry
map-tasks      specs/PLAN-*-tasks.md       → file/layer mapping

impl-schema         specs/TS-*.md          → DB schema + migration
impl-repositories   specs/TS-*.md          → data access layer
impl-error-codes    specs/TS-*.md          → error constants + HTTP map + i18n   [TS §4]
impl-observability  specs/TS-*.md          → logger + tracing + OTel            [TS §7.1]
impl-services       specs/TS-*.md          → business logic (BR 1:1)
impl-controllers    specs/TS-*.md          → API endpoints (thin)
impl-middleware     specs/TS-*.md          → auth, authz, error filter, CORS
impl-integrations   specs/TS-*.md          → MQ, cache, storage

# conditional:
impl-file-upload    specs/TS-*.md          → presigned URL + storage adapter     [TS §9, if needed]
impl-webhook        specs/TS-*.md          → signature verify + idempotency      [TS §10, if needed]

export-api-contract specs/TS-*.md          → openapi/openapi.yaml               [TS §3.2 + §4]
generate-tests      specs/TS-*.md          → unit + integration tests
```

### P6: Frontend (frontflow — sequential, can parallel with P5)

Run `scan-codebase` once per project.

```
scan-codebase                              → registry
map-tasks      specs/PLAN-*-tasks.md       → file/layer mapping

# optional: figma-extract <url>

impl-tokens         specs/UI-*.md          → design tokens (tailwind/CSS vars)
impl-atoms          specs/UI-*.md          → atomic components + Storybook
impl-composites     specs/UI-*.md          → composite components
impl-pages          specs/WF-*.md          → pages (static, mock data)
impl-error-handling specs/TS-*.md          → error handler + UI flow             [TS §4]

sync-api-client                            → openapi.yaml → types + functions + MSW  [needs P5 export-api-contract]

impl-tracking       specs/FS-*.md          → event constants + adapter           [FS §7]
impl-tracking       specs/FS-*.md --phase=codemod  → component hook insertion

impl-interactions   specs/FS-*.md          → state mgmt + conditional render + animation
impl-api-integration specs/TS-*.md         → replace stubs with real API calls

generate-stories                           → Storybook stories
```

### P7: Validation

```
# backend
backflow:validate-code   src/              → convention, layer, error, type, security + drift (§7-§11)
backflow:validate-api    specs/TS-*.md     → API vs TS contract (clean-room)
backflow:validate-tests                    → coverage check

# frontend
frontflow:validate-code  src/              → convention, reuse, token, type, a11y + drift (§7,§9,§10)
frontflow:validate-visual                  → Storybook visual QA checklist
frontflow:validate-a11y                    → WCAG check
```

### P8: E2E DB (dbflow — after P5 complete)

```
# setup (once)
dbflow:init                                → .e2e/ scaffold
# edit .e2e/config.yml manually

dbflow:snapshot                            → source DB → sandbox clone
dbflow:migrate                             → apply migrations to sandbox
dbflow:up                                  → start API server on sandbox

# scenarios
dbflow:gen-scenarios  specs/QA-*.md        → .e2e/scenarios/*.yml                [QA §5]
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

### P9: Commit & PR (ghflow)

```
ghflow:commit                              → generate message per team convention + commit
ghflow:commit -y                           → auto-commit (no confirmation)
ghflow:chronicle                           → record commit intent/decisions
ghflow:create-pr                           → GitHub PR (template-based)
xreview:review        src/                 → external code review
ghflow:review-pr                           → check + process review comments (default: unresolved only — token saver)
ghflow:review-pr 101 --all                 → include resolved threads too
ghflow:clear-issue                         → cleanup issue memory
ghflow:chronicle-lookup <query>            → search past commit rationale
```

---

## Scenario Quick-Reference

| Scenario | Start at | Skip |
|---|---|---|
| New feature (full) | P1 | — |
| Add to existing code | P5 `scan-codebase` → P2 `generate-ts --base` → P4~P9 | P1 |
| Spec-only improvement | P3 `revise` → `xreview` → `change-impact` → `spec-refine-loop` | P4~P9 |
| Figma-first | `figma-extract` → P2 `extract-wf-from-figma` → `extract-ui` → P2 `generate-ts` onward | P1 |
| Hotfix (no spec) | P4 `pick-issue` → `draft-pr` → fix → P7 `validate-code` → P9 | P1~P3, P5~P6 |
| Schema change re-verify | P5 `impl-schema` → P8 `migrate --fresh` → `up` → `run` | — |
| Code archaeology | P9 `chronicle-lookup` | everything else |

---

## Dependency Graph (compact)

```
meeting-prep → specflow → ghflow(issue/PR)
                 │              │
                 │         frontflow ←→ backflow  (parallel OK)
                 │              │            │
                 │         sync-api-client ← export-api-contract ← TS §3.2+§4
                 │              │
                 │         validate-* (both sides)
                 ▼              │
              xreview ←── (spec review + code review)
                                │
                            dbflow (E2E, after backend)
```

Key cross-plugin data flows:
- **TS is source of truth** — all `impl-*` skills consume TS (+ FS/WF/UI/QA)
- **OpenAPI is front↔back contract** — `export-api-contract` → `sync-api-client`
- **QA §5 drives dbflow** — `gen-scenarios` reads QA spec

---

## Model Assignment

| Model | Skills | Ratio |
|---|---|---|
| **Sonnet** (auto, via frontmatter) | `impl-*`, `scan-*`, `map-*`, `generate-tests/stories`, `export-api-contract`, `sync-api-client`, `dbflow` (init~diff), `ghflow` all (incl. `commit`), `meeting-prep` all | 70% |
| **Opus** (session default) | `generate-fs/ts/qa/wf`, `extract-ui`, `decompose`, `validate-*`, `reimpl-*`, `xreview`, `dbflow:run/gen-scenarios/validate-scenarios` | 30% |

---

## Rules

1. **No implementation before spec gate** — xreview must pass before P5/P6
2. **scan-codebase once per plugin adoption** — prevents duplicate code
3. **TS = source of truth** for all impl skills
4. **OpenAPI = front↔back contract** (export → sync pipeline)
5. **Safety invariants hardcoded** in dbflow (sandbox naming, pg_dump only, confirm)
6. **Vendor-neutral** — all external integrations use adapter pattern
7. **Mechanical work uses Sonnet** — `model: sonnet` frontmatter
