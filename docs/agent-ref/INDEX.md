# hbrness Skill Index

> Load this file for phase overview. Read `P{n}.md` for detail when entering that phase.
> Monolithic version: `docs/USAGE_FLOW_AGENT.md`

## Phase Pipeline

| Phase | File | Summary | Inputs → Outputs |
|---|---|---|---|
| P1 | [P1.md](P1.md) | Planning (meeting-prep) | specs/, src/ → gap report, meeting doc |
| P2 | [P2.md](P2.md) | Specification (specflow, sequential) | PRD → FS → WF → UI → TS → QA → PLAN |
| P3 | [P3.md](P3.md) | Spec validation gate | TS → xreview/spec-review pass |
| P4 | [P4.md](P4.md) | Issue & branch (ghflow) | — → issue, branch, draft PR |
| P5 | [P5.md](P5.md) | Backend impl (backflow) | TS → schema, repo, service, controller, tests |
| P6 | [P6.md](P6.md) | Frontend impl (frontflow) | UI/WF/TS → tokens, components, pages, API integration |
| P7 | [P7.md](P7.md) | Validation (both sides) | src/ → convention/drift/coverage/a11y checks |
| P8 | [P8.md](P8.md) | E2E DB (dbflow) | QA §5 → sandbox scenarios + delta verify |
| P9 | [P9.md](P9.md) | Commit & PR (ghflow) | changes → commit, chronicle, PR, review |

## Cross-cutting (any phase)

| Area | File | Summary |
|---|---|---|
| Session management (sessionflow) | [SESSION.md](SESSION.md) | `handoff` / `followup` / `phase-run` — preserve & resume context across sessions; `phase-run` auto-resets context between phases and can wrap the whole pipeline |

## Scenarios

| Scenario | Flow |
|---|---|
| New feature (full) | P1 → P2 → P3 → P4 → P5∥P6 → P7 → P8 → P9 |
| Add to existing | scan-codebase → P2(generate-ts --base) → P4~P9 |
| Spec-only | P3: revise → xreview → change-impact → spec-refine-loop |
| Figma-first | figma-extract → P2(extract-wf-from-figma → extract-ui → generate-ts) → P4~P9 |
| Hotfix | P4(pick-issue → draft-pr) → fix → P7(validate-code) → P9 |
| Schema re-verify | P5(impl-schema) → P8(migrate --fresh → up → run) |
| Archaeology | P9(chronicle-lookup) |

## Key Rules

1. No impl before spec gate (P3 must pass before P5/P6)
2. scan-codebase once per plugin adoption
3. TS = source of truth for all impl skills
4. OpenAPI = front↔back contract (export-api-contract → sync-api-client)
5. Sonnet for mechanical skills (70%), Opus for judgment skills (30%)
