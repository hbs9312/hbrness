# Codex Sub-Agent Spawn Reliability Plan

> Created: 2026-05-01 KST
> Purpose: make hbrness plugins trigger and operate Codex sub-agents reliably without changing Claude behavior.

## 1. Goal

Codex 에서 validator, reviewer, orchestrator 계열 sub-agent 가 안정적으로 실행되도록 빌드 산출물, 설치 경로, dispatcher skill 지침, 검증 스크립트를 정비한다.

가장 중요한 원칙:

> Claude 출력과 Claude 플러그인 모드는 기능적으로 변경하지 않는다. Codex 전용 변환·설치·검증만 먼저 고친다.

## 2. Current Findings

### Finding A — Codex agent frontmatter is malformed

Files:

- `scripts/build-plugin.py`
- `adapters/codex.adapter.json`
- `dist/codex/**/agents/*.md`

Problem:

- Codex adapter has `transform_tools_to: null`, so `tools:` should be omitted.
- `scripts/build-plugin.py` currently removes the `tools:` key but leaves YAML list items under it.
- Example generated output:

```yaml
---
name: validator-api
description: ...
  - shell
  - shell
  - shell
  - apply_patch
---
```

Impact:

- Agent files in `dist/codex/**/agents` are invalid or ambiguous.
- `scripts/validate.sh` currently does not catch this.

### Finding B — Codex install does not install most flat-file agents

Files:

- `scripts/install/installer.js`
- `plugins/*/agents/*.common.md`
- `dist/codex/*/agents/*.md`

Problem:

- User-level install scans only `agents/<name>/` directories.
- Most agents are flat files such as `plugins/backflow/agents/validator-api.common.md`.
- `hbrness install codex backflow --dry-run` links skills but not backflow agents.

Impact:

- Codex cannot discover most agents as installed skill-like entries.
- Inline agent definitions partly hide this for validator dispatcher skills, but orchestrator agents and direct agent usage remain fragile.

### Finding C — Codex dispatcher spawn contract is underspecified

Files:

- `plugins/backflow/skills/validate-api/SKILL.common.md`
- `plugins/backflow/skills/validate-security/SKILL.common.md`
- `plugins/specflow/skills/validate*/SKILL.common.md`
- `scripts/build-plugin.py`

Problem:

- Source says "spawn `plugin:agent-name`".
- Codex `spawn_agent` does not accept this plugin-specific `agent_ref`.
- Codex build inlines referenced agent instructions, but the dispatcher does not explicitly say how to pass those instructions to `spawn_agent`.

Impact:

- Codex may try to use a nonexistent custom agent ref, or run the validation locally.
- Clean-room intent is not guaranteed unless the dispatcher explicitly uses `fork_context: false` and passes the inlined agent body as `message`.

### Finding D — Orchestrator agents are not good Codex entry points

Files:

- `plugins/backflow/agents/orchestrator.common.md`
- `plugins/frontflow/agents/orchestrator.common.md`
- `plugins/specflow/agents/orchestrator.common.md`
- `plugins/meeting-prep/agents/meeting-orchestrator/AGENT.common.md`

Problem:

- Claude can use plugin agents more naturally.
- Codex primarily discovers installed skills from `~/.codex/skills`.
- Backflow/frontflow/specflow orchestrators are agents, not user-facing skills.

Impact:

- User phrases like "백엔드 구현 시작" may not reliably trigger the orchestrator path in Codex.

### Finding E — meeting-prep parallel worker instructions are too indirect

Files:

- `plugins/meeting-prep/agents/meeting-orchestrator/AGENT.common.md`
- `plugins/meeting-prep/skills/spec-scanner/SKILL.common.md`
- `plugins/meeting-prep/skills/impl-scanner/SKILL.common.md`

Problem:

- Orchestrator asks sub-agents to follow scanner skill instructions.
- Codex spawned default agents may not automatically load those skill bodies.

Impact:

- Parallel scan quality depends on model inference instead of an explicit worker prompt.

## 3. Non-Goals

- Do not change Claude plugin mode behavior.
- Do not remove Claude `Agent` usage.
- Do not redesign every plugin workflow.
- Do not introduce a new runtime dependency.
- Do not edit `dist/` directly except as generated output after `npm run build`.
- Do not make broad `validate_profile` or validation-skip policy changes here.

## 4. Implementation Phases

### Phase 0 — Baseline and guardrails

Purpose:

- Establish the current failing/passing state before touching code.
- Make sure later changes can prove "Claude unaffected".

Commands:

```bash
npm run build
npm run validate
node bin/hbrness.js install codex backflow --dry-run
node bin/hbrness.js install codex specflow --dry-run
node bin/hbrness.js install codex meeting-prep --dry-run
node bin/hbrness.js install claude backflow --dry-run
```

Manual checks:

- Capture whether Codex agent frontmatter is malformed before the fix.
- Capture which Codex agents are linked before the fix.
- Confirm Claude skill count and plugin manifests are already valid.

Expected output:

- No source changes.
- Baseline notes in PR/commit description, not necessarily committed as a file.

### Phase 1 — Fix Codex agent frontmatter generation

Files:

- `scripts/build-plugin.py`
- `scripts/validate.sh`

Change:

- In `transform_frontmatter`, when `key == "tools"` and `transform_tools_to` is null:
  - skip the `tools:` key
  - skip all following YAML list items that belonged to `tools:`
- Do not alter Claude adapter behavior.
- Add validation that Codex `.md` frontmatter does not contain dangling list items before any key.

Acceptance criteria:

- `dist/codex/**/agents/*.md` no longer contains orphan `- shell`, `- apply_patch`, `- Skill`, or similar frontmatter lines.
- `dist/claude/**/agents/*.md` still contains valid `allowed-tools`.
- `npm run build && npm run validate` passes.

Risk:

- Low if scoped to `transform_tools_to is None`.
- Main risk is accidentally skipping non-tools YAML lists; tests should cover only `tools:` list state.

Recommended commit:

```text
build: fix codex agent frontmatter generation
```

### Phase 2 — Make Codex agent installation deterministic

Preferred approach:

- Standardize agent source layout to directory form.

Example:

```text
plugins/backflow/agents/validator-api.common.md
→ plugins/backflow/agents/validator-api/AGENT.common.md
```

Apply to:

- `plugins/backflow/agents/orchestrator.common.md`
- `plugins/backflow/agents/validator-api.common.md`
- `plugins/backflow/agents/validator-security.common.md`
- `plugins/frontflow/agents/orchestrator.common.md`
- `plugins/specflow/agents/orchestrator.common.md`
- `plugins/specflow/agents/validator-single.common.md`
- `plugins/specflow/agents/validator-cross.common.md`
- `plugins/specflow/agents/validator-boundary.common.md`

Keep existing:

- `plugins/meeting-prep/agents/meeting-orchestrator/AGENT.common.md`

Alternative:

- Teach `scripts/install/installer.js` to also install flat agent files.

Recommendation:

- Use directory form. It matches current installer assumptions and avoids more install branching.

Required build-script support:

- `scripts/build-plugin.py` already walks nested agent files.
- Confirm generated output path becomes `dist/<harness>/<plugin>/agents/<agent-name>/AGENT.md`.

Acceptance criteria:

- `node bin/hbrness.js install codex backflow --dry-run` shows links for `backflow-validator-api`, `backflow-validator-security`, and `backflow-orchestrator`.
- `node bin/hbrness.js install codex specflow --dry-run` shows links for validator/orchestrator agents.
- Claude plugin output still includes the same agents under plugin package.
- No skill behavior changes yet.

Risk:

- Medium due to file moves.
- Mitigation: move only agent files; do not edit bodies in this phase except path-preserving relocation.

Recommended commit:

```text
agents: standardize agent source layout
```

### Phase 3 — Add Codex-safe dispatcher spawn contract

Files:

- `plugins/backflow/skills/validate-api/SKILL.common.md`
- `plugins/backflow/skills/validate-security/SKILL.common.md`
- `plugins/specflow/skills/validate/SKILL.common.md`
- `plugins/specflow/skills/validate-cross/SKILL.common.md`
- `plugins/specflow/skills/validate-boundary/SKILL.common.md`
- `scripts/build-plugin.py`

Change:

- Add a shared dispatcher contract to the relevant source skills.
- Keep it harness-neutral where possible, with a Codex-specific subsection generated by build if needed.

Suggested source text:

```text
실행 계약:
- 이 스킬은 dispatcher 입니다. 직접 검증하지 않습니다.
- 반드시 지정된 검증 에이전트를 격리 컨텍스트로 호출합니다.
- 에이전트에는 "프롬프트 구성" 값과 에이전트 지침 전체를 전달합니다.
- 에이전트가 반환한 summary 를 수정하지 않고 그대로 출력합니다.
```

Suggested Codex build addition:

```text
Codex 실행 규칙:
- spawn_agent 의 custom agent_ref 는 사용하지 않는다.
- spawn_agent 는 default agent 로 호출한다.
- fork_context 는 false 로 둔다.
- message 에 아래 참조 에이전트 정의 전체와 프롬프트 구성을 함께 포함한다.
- 호출 후 wait_agent 로 완료를 기다리고 summary 만 전달한다.
```

Build-script change:

- `inline_agent_into_skill()` should emit Codex-specific instructions like the above.
- Avoid adding this text to Claude output.

Acceptance criteria:

- Codex built dispatcher skills contain clear `spawn_agent` instructions that match actual Codex API shape.
- Claude built dispatcher skills still say `Agent 도구로 ...` and do not contain Codex-only wording.
- `npm run build && npm run validate` passes.

Risk:

- Medium.
- Main risk is mixing Claude/Codex wording. Keep Codex-specific text in adapter/build output, not common source, if possible.

Recommended commit:

```text
codex: clarify dispatcher sub-agent contract
```

### Phase 4 — Add Codex-friendly orchestrator entry skills

Files:

- `plugins/backflow/skills/orchestrate/SKILL.common.md`
- `plugins/frontflow/skills/orchestrate/SKILL.common.md`
- `plugins/specflow/skills/orchestrate/SKILL.common.md`
- optionally `plugins/meeting-prep/skills/orchestrate/SKILL.common.md`

Purpose:

- Give Codex a skill-level entry point for workflow starts.
- Keep existing Claude agents intact.

Design:

- The orchestrate skill is a dispatcher/wrapper around the existing orchestrator instructions.
- For Codex, inline the corresponding orchestrator agent definition into the skill, same as validators.
- For Claude, either:
  - keep the skill as a lightweight wrapper, or
  - mark it Codex-only with `harness: [codex]` if duplicate Claude entry points are undesirable.

Recommendation:

- Start with `harness: [codex]` for these orchestrate skills to avoid changing Claude behavior.

Example frontmatter:

```yaml
---
name: orchestrate
description: Codex에서 backflow 백엔드 구현 전체 워크플로우를 시작합니다. "백엔드 구현 시작", "구현 워크플로우" 요청 시 사용.
harness: [codex]
---
```

Acceptance criteria:

- Codex dist contains `backflow-orchestrate`, `frontflow-orchestrate`, `specflow-orchestrate`.
- Claude dist does not gain duplicate orchestrate skills if `harness: [codex]` is used.
- `npm run validate` skill count accounting still passes.

Risk:

- Low if Codex-only.
- Main risk is user confusion from extra skill names; mitigate through descriptions.

Recommended commit:

```text
codex: add orchestrator entry skills
```

### Phase 5 — Strengthen meeting-prep parallel worker prompts

Files:

- `plugins/meeting-prep/agents/meeting-orchestrator/AGENT.common.md`
- possibly `plugins/meeting-prep/agents/spec-scan-worker/AGENT.common.md`
- possibly `plugins/meeting-prep/agents/impl-scan-worker/AGENT.common.md`

Preferred approach:

- Add dedicated worker agents for scanner subtasks, or inline scanner skill requirements into the spawn prompt.

Recommendation:

- Add two worker agents if meeting-prep remains agent-first:
  - `meeting-prep:spec-scan-worker`
  - `meeting-prep:impl-scan-worker`

Worker rules:

- Read-only except writing the assigned output file.
- Do not modify project docs/source.
- Return output path and summary.
- If one worker fails, orchestrator still produces partial meeting doc.

Acceptance criteria:

- Meeting orchestrator spawn prompts no longer depend on "follow scanner skill instructions" alone.
- Codex and Claude both have explicit worker instructions.
- Existing `spec-scanner` and `impl-scanner` skills remain independently usable.

Risk:

- Medium because meeting-prep uses real parallelism.
- Mitigation: keep worker outputs identical to current intermediate format.

Recommended commit:

```text
meeting-prep: make parallel scan workers explicit
```

### Phase 6 — Expand validation coverage

Files:

- `scripts/validate.sh`
- optionally `scripts/install/doctor.js`

Add checks:

1. Codex frontmatter validity:
   - no dangling YAML list items in frontmatter after stripped keys
2. Codex dispatcher integrity:
   - if a Codex skill mentions `spawn_agent로 \`plugin:agent\``, it must include `참조 에이전트 정의`
3. No raw `agent_ref:` in Codex output:
   - unless explicitly documented as inert example text
4. Agent installability:
   - for each source agent not harness-gated out, Codex dry-run install should have a corresponding linkable directory
5. Claude unaffected guard:
   - Claude skill count and agent count match expected source counts after harness gating

Acceptance criteria:

- The previous malformed Codex agent frontmatter would fail validation.
- Current fixed build passes.
- Validation remains shell-only; no new dependency.

Risk:

- Low to medium.
- Shell parsing frontmatter can be brittle. Keep checks simple and conservative.

Recommended commit:

```text
validate: cover codex agent spawn outputs
```

## 5. Suggested Execution Order

Run as separate PRs or commits:

1. Phase 1 only — build bug fix and validator guard.
2. Phase 2 only — agent file layout migration.
3. Phase 3 only — dispatcher spawn contract.
4. Phase 4 only — Codex orchestrator entry skills.
5. Phase 5 only — meeting-prep parallel worker clarity.
6. Phase 6 can be partly done with Phase 1 and finished after Phase 5.

Recommended first implementation chunk:

- Phase 1 + the frontmatter portion of Phase 6.

Reason:

- It has the highest certainty.
- It prevents invalid Codex dist output before touching workflow semantics.
- It should not affect Claude behavior.

## 6. Claude No-Impact Strategy

Rules:

- Prefer Codex-only changes through `harness: [codex]` or `adapter.get("harness") == "codex"` build branches.
- Do not change `adapters/claude.adapter.json` unless a validation check proves it is necessary.
- Do not remove or rename Claude `Agent` wording in common files unless build replacement keeps the Claude output identical.
- For every phase, inspect both outputs:

```bash
git diff -- dist/claude dist/codex
rg -n "Agent 도구|allowed-tools|spawn_agent|agent_ref|참조 에이전트 정의" dist/claude dist/codex
```

Expected:

- Claude output may change only when source file moves are mirrored by generated path changes, not behavior.
- Codex output should get the new spawn contract and valid frontmatter.

## 7. Verification Matrix

After each phase:

```bash
npm run build
npm run validate
node bin/hbrness.js install codex backflow --dry-run
node bin/hbrness.js install codex specflow --dry-run
node bin/hbrness.js install codex meeting-prep --dry-run
node bin/hbrness.js install claude backflow --dry-run
```

Additional targeted checks:

```bash
rg -n "^- (shell|apply_patch|Skill|spawn_agent)$|^  - (shell|apply_patch|Skill|spawn_agent)$" dist/codex -g "*.md"
rg -n "agent_ref:" dist/codex
rg -n "참조 에이전트 정의|spawn_agent 호출 시" dist/codex/*/skills
rg -n "allowed-tools|Agent 도구" dist/claude/*/skills dist/claude/*/agents
```

Manual smoke tests:

- Invoke Codex `backflow-validate-api` on a small fixture repo/spec and confirm a spawned validator returns only summary.
- Invoke Codex `specflow-validate` on a small fixture doc and confirm report file is written under `specs/reviews/`.
- Invoke Codex `meeting-prep-meeting-orchestrator` and confirm two workers produce separate intermediate files.

## 8. Acceptance Criteria

- Codex built agent files have valid frontmatter.
- Codex install dry-run lists expected agents or Codex-only orchestrator skills.
- Dispatcher skills for validator agents explicitly instruct Codex to use `spawn_agent` with `fork_context: false` and inlined agent instructions.
- Claude build still passes and preserves `Agent`/`allowed-tools` semantics.
- `npm run build && npm run validate` catches the previously observed malformed Codex output.
- No direct edits to `dist/` are committed as source changes.

## 9. Rollback Plan

If a phase causes unexpected Claude drift:

1. Revert that phase commit only.
2. Rebuild both harnesses.
3. Compare `dist/claude` against the pre-phase output.
4. Reapply as Codex-only adapter/build logic.

If Codex spawn behavior remains unreliable after Phase 3:

1. Keep dispatcher skills from performing local validation.
2. Fail closed with a clear message: "Codex sub-agent spawn failed; validation not performed."
3. Do not silently fall back to same-context validation for clean-room validators.

## 10. Context-Clear Resume Prompt

```text
Read docs/designs/codex-subagent-spawn-plan.md.
Implement the plan phase by phase.
Start with Phase 1: fix Codex agent frontmatter generation and add validation that catches dangling tools list items.
Keep Claude behavior unchanged. Do not edit dist directly; regenerate with npm run build.
After each phase run npm run build, npm run validate, and Codex/Claude install dry-runs listed in the plan.
```
