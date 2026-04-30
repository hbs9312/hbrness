# Validate Call Optimization Plan

> Created: 2026-04-30 KST
> Purpose: reduce token waste from repeated validate calls while preserving code/spec quality gates.

## 1. Goal

Reduce unnecessary validator invocations in the orchestrator workflows without weakening the checks that catch code quality, contract drift, security, accessibility, and cross-document consistency issues.

The guiding rule:

> Prefer removing duplicated whole-scope validation over skipping local quality gates.

## 2. Current Finding

The highest-value redundancy is in `backflow` Phase 4:

- `plugins/backflow/agents/orchestrator.common.md`
  - Phase 4 loop currently runs `/backflow:validate-api [TS 경로]` for every controller commit unit.
  - Final Gate already runs `/backflow:validate-api [TS 경로]` once.
- `plugins/backflow/skills/validate-api/SKILL.common.md`
  - `validate-api` validates the TS-level API contract through a clean-room sub-agent.
  - It is not scoped to `commit_unit.files`, so repeating it per controller commit is mostly duplicated work.

In contrast, `validate-code` should remain conservative:

- `backflow:validate-code` checks conventions, layer boundaries, error handling, type safety, security, and multiple drift rules.
- `frontflow:validate-code` checks conventions, reuse, tokens, type safety, accessibility basics, and drift rules.
- These are the primary per-commit quality gates and should not be broadly skipped.

## 3. Non-Goals

- Do not remove `validate-code` from normal code-changing commit units.
- Do not remove specflow `validate-cross` / `validate-boundary` from initial generation workflows.
- Do not rely on weak heuristics to skip security or accessibility checks.
- Do not introduce a large `validate_profile` system as the first change.

## 4. Implementation Plan

### Step 1 — Backflow duplicate `validate-api` removal

File:

- `plugins/backflow/agents/orchestrator.common.md`

Change:

- In Phase 4, remove `/backflow:validate-api [TS 경로]` from inside the `for commit_unit in commit_plan.phase_4` loop.
- Keep `/backflow:validate-code [commit_unit.files]`.
- Keep `/backflow:generate-tests [commit_unit.files] --type integration`.
- Keep Final Gate `/backflow:validate-api [TS 경로]`.

Expected resulting Phase 4:

```text
for commit_unit in commit_plan.phase_4:
  /backflow:impl-controllers [TS 경로] → commit_unit.files 범위만 구현
  /backflow:validate-code [commit_unit.files]
  /backflow:generate-tests [commit_unit.files] --type integration
  → 커밋 리뷰: "{commit_unit.commit} 커밋 준비 완료.
     확인해주세요. 특히: 요청/응답 스키마, 상태 코드, 에러 응답"
  → 승인 → /commit

Phase 4 완료 → Phase 5
```

Quality impact:

- Low.
- API contract feedback moves from every controller commit to Final Gate.
- Per-commit code quality and integration test generation remain intact.

Token impact:

- High when Phase 4 has multiple controller commit units.
- Reduces `validate-api` from `N + 1` calls to `1` call for a full backflow run.

### Step 2 — Conservative Final Gate wording

File:

- `plugins/backflow/agents/orchestrator.common.md`

Change:

- Add a note under Final Gate that validators may be skipped only when the relevant surface is provably untouched.
- Default rule: if uncertain, run the validator.

Suggested text:

```text
Final Gate 최적화 원칙:
- 기본값은 실행한다. 영향 여부가 불명확하면 skip 하지 않는다.
- validate-api: controller, DTO, route, response schema, error response, OpenAPI/export contract, API security scheme 변경이 없을 때만 생략 가능.
- validate-security: auth, middleware, public route, upload, webhook, external integration, secret/config handling 변경이 없을 때만 생략 가능.
- validate-tests: 테스트 파일 또는 테스트 대상 코드 변경이 없을 때만 생략 가능.
```

Quality impact:

- Low if phrased as a conservative rule.
- Avoids treating optional skip as a default optimization.

Token impact:

- Medium.
- Saves tokens on clearly non-API/non-security/non-test changes.

### Step 3 — Docs/config-only `validate-code` skip rule

Files:

- `plugins/backflow/agents/orchestrator.common.md`
- `plugins/frontflow/agents/orchestrator.common.md`

Change:

- Add a small rule to commit-unit execution rules:
  - If `commit_unit.files` contains only docs/reports/metadata files, `validate-code` may be skipped.
  - If any source code, migration, DTO, route, service, repository, hook, component, generated API client, config that affects runtime behavior, or test target changes, run `validate-code`.

Suggested text:

```text
validate-code skip 예외:
- commit_unit.files 가 문서/리포트/비런타임 메타 파일만 포함할 때만 생략 가능.
- `src/**`, migration, DTO, route/controller, service, repository, middleware, integration, hook, component, generated API client, runtime config, test target 이 하나라도 포함되면 validate-code 를 실행한다.
- 애매하면 실행한다.
```

Quality impact:

- Low.
- Avoids spending tokens reviewing files that cannot affect runtime/code quality.

Token impact:

- Low to medium.
- Useful for mixed documentation/metadata workflows, but not a primary savings lever.

### Step 4 — Frontflow a11y surface rule

File:

- `plugins/frontflow/agents/orchestrator.common.md`

Change:

- Keep Phase 4 `validate-a11y` as default.
- Allow skipping only when the commit unit does not touch accessibility surface.

Suggested text near Phase 4:

```text
validate-a11y 실행 원칙:
- JSX/TSX, CSS, layout, aria, form, button, modal, navigation, focus, keyboard interaction 변경이 있으면 실행한다.
- 순수 타입, API hook, 내부 상태 계산만 변경하고 DOM/accessibility surface 를 건드리지 않을 때만 생략 가능.
- 애매하면 실행한다.
```

Quality impact:

- Low to medium.
- Safe only with conservative interpretation.

Token impact:

- Medium when page phase contains non-DOM logic commits.

### Step 5 — Specflow optimization later, after schema enrichment

Files:

- `plugins/specflow/skills/change-impact/SKILL.common.md`
- `plugins/specflow/agents/orchestrator.common.md`

Do not change this in the first pass unless explicitly requested.

Reason:

- Current `change-impact` output only has `impact` and `no_impact`.
- It lacks enough structured signal to safely skip `validate-cross` or `validate-boundary`.

Future prerequisite:

```yaml
impact:
  - document: "{문서}"
    scope: trivial | moderate | major
    axes: [content | cross-ref | boundary]
    items:
      - location: "{위치}"
        action_needed: "{필요한 변경}"
```

Future conservative rule:

- Initial generation: keep full validation.
- Revise/extend only:
  - Always keep single `validate` unless explicitly docs-only/trivial.
  - Skip `validate-cross` only when `axes` excludes `cross-ref`.
  - Skip `validate-boundary` only when `axes` excludes `boundary`.
  - If `scope` is `moderate` or `major`, run the relevant validators.
  - If uncertain, run validators.

## 5. Recommended Execution Order

1. Apply Step 1 only.
2. Review diff.
3. Apply Step 2.
4. Optionally apply Step 3 and Step 4 in a second commit.
5. Leave Step 5 as a future design unless token pressure remains high.

## 6. Acceptance Criteria

- `backflow` Phase 4 no longer calls `validate-api` inside the commit loop.
- `backflow` Final Gate still includes `validate-api`.
- `validate-code` remains in all normal code-changing commit loops.
- Any skip language says "if uncertain, run the validator."
- No broad `validate_profile` implementation is introduced in this pass.
- No specflow cross/boundary validation is removed from initial generation flows.

## 7. Verification

Run after edits:

```bash
rg -n "validate-api|validate-code|validate-a11y|Final Gate|skip|생략|애매하면" plugins/backflow/agents/orchestrator.common.md plugins/frontflow/agents/orchestrator.common.md plugins/specflow/agents/orchestrator.common.md
git diff -- docs/designs/validate-call-optimization.md plugins/backflow/agents/orchestrator.common.md plugins/frontflow/agents/orchestrator.common.md
```

Manual checks:

- Confirm Phase 4 `validate-api` appears only in Final Gate for backflow.
- Confirm `validate-code` is not broadly removed.
- Confirm all optional skip rules are conservative and default to running validators.

## 8. Context-Clear Resume Prompt

Use this prompt after clearing context:

```text
Read docs/designs/validate-call-optimization.md.
Implement the plan in order, starting with Step 1.
Keep code quality impact minimal: remove duplicated whole-scope validation first, keep validate-code for normal code changes, and use "if uncertain, run validator" for any conditional skip rule.
Do not implement broad validate_profile or specflow cross/boundary skipping unless explicitly asked.
```
