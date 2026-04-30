# Codex Sub-Agent Spawn Implementation Prompts

> Created: 2026-05-01 KST
> Companion plan: `docs/designs/codex-subagent-spawn-plan.md`

이 문서는 context clear 또는 새 Codex 세션으로 phase 단위 구현을 이어가기 위한 프롬프트 모음이다.

사용 원칙:

- 한 세션에서는 가능하면 한 phase 만 구현한다.
- phase 완료 후 검증 결과와 변경 파일을 보고받고, 필요하면 commit 한 뒤 다음 phase 로 넘어간다.
- 새 세션에서는 아래 phase별 프롬프트를 그대로 붙여넣되, 이미 완료한 phase 번호만 맞춘다.
- 항상 `git status --short` 와 최근 diff 를 먼저 확인한다.
- `dist/` 는 직접 수정하지 않는다. source 를 수정한 뒤 `npm run build` 로 재생성한다.

## Phase 1 Prompt

```text
Read docs/designs/codex-subagent-spawn-plan.md first.

Implement the plan phase by phase. Do not skip phases.
Important constraints:
1. Keep Claude behavior unchanged. Prefer Codex-only adapter/build logic or `harness: [codex]`.
2. Do not edit `dist/` directly. Edit source files under `plugins/`, `scripts/`, `adapters/`, then regenerate with `npm run build`.
3. Preserve existing user changes. Check `git status --short` before editing.
4. After each phase, run:
   - npm run build
   - npm run validate
   - node bin/hbrness.js install codex backflow --dry-run
   - node bin/hbrness.js install codex specflow --dry-run
   - node bin/hbrness.js install codex meeting-prep --dry-run
   - node bin/hbrness.js install claude backflow --dry-run
5. Stop after the current phase, summarize changed files, verification results, and the next phase prompt.

Start with Phase 1 only:
- Fix Codex agent frontmatter generation in scripts/build-plugin.py.
- Add validation in scripts/validate.sh so malformed Codex agent frontmatter with dangling YAML list items fails.
- Do not implement Phase 2 or later yet.
```

## Phase 2 Prompt

```text
Continue from docs/designs/codex-subagent-spawn-plan.md.

Previous phase completed: Phase 1.
First inspect:
- git status --short
- git diff -- scripts/build-plugin.py scripts/validate.sh

Now implement Phase 2 only:
- Standardize flat agent files into directory form:
  plugins/backflow/agents/*.common.md
  plugins/frontflow/agents/*.common.md
  plugins/specflow/agents/*.common.md
  should become agents/<agent-name>/AGENT.common.md.
- Keep plugins/meeting-prep/agents/meeting-orchestrator/AGENT.common.md as-is.
- Do not change agent bodies except path-preserving relocation.
- Regenerate with npm run build.
- Verify Codex install dry-run shows backflow/specflow agents.
- Verify Claude build still passes.
Stop after Phase 2 and report changed files + verification.
```

## Phase 3 Prompt

```text
Continue from docs/designs/codex-subagent-spawn-plan.md.

Previous phases completed: Phase 1 and Phase 2.
Inspect git status and relevant diffs first.

Implement Phase 3 only:
- Add/ensure a clear dispatcher execution contract for:
  plugins/backflow/skills/validate-api/SKILL.common.md
  plugins/backflow/skills/validate-security/SKILL.common.md
  plugins/specflow/skills/validate/SKILL.common.md
  plugins/specflow/skills/validate-cross/SKILL.common.md
  plugins/specflow/skills/validate-boundary/SKILL.common.md
- Update scripts/build-plugin.py so Codex inlined agent definitions include Codex-specific instructions:
  - do not use custom agent_ref
  - call spawn_agent with default agent
  - use fork_context: false
  - include the referenced agent definition and prompt configuration in message
  - wait for completion and return summary unchanged
- Do not add Codex-only wording to Claude output.
- Run full verification listed in the plan.
Stop after Phase 3 and report.
```

## Phase 4 Prompt

```text
Continue from docs/designs/codex-subagent-spawn-plan.md.

Previous phases completed: Phase 1, Phase 2, and Phase 3.
Inspect git status and relevant diffs first.

Implement Phase 4 only:
- Add Codex-only orchestrator entry skills:
  plugins/backflow/skills/orchestrate/SKILL.common.md
  plugins/frontflow/skills/orchestrate/SKILL.common.md
  plugins/specflow/skills/orchestrate/SKILL.common.md
- Use `harness: [codex]` to avoid Claude behavior changes.
- Each skill should route to the existing orchestrator instructions using the same Codex-safe spawn/inlined-agent pattern.
- Ensure Codex dist contains backflow-orchestrate, frontflow-orchestrate, specflow-orchestrate.
- Ensure Claude dist does not gain duplicate orchestrate skills.
Run full verification and stop.
```

## Phase 5 Prompt

```text
Continue from docs/designs/codex-subagent-spawn-plan.md.

Previous phases completed: Phase 1 through Phase 4.
Inspect git status and relevant diffs first.

Implement Phase 5 only:
- Strengthen meeting-prep parallel worker prompts.
- Prefer adding explicit worker agents:
  plugins/meeting-prep/agents/spec-scan-worker/AGENT.common.md
  plugins/meeting-prep/agents/impl-scan-worker/AGENT.common.md
- Update meeting-orchestrator so spawned workers have complete, explicit instructions.
- Workers may write only their assigned output file.
- Existing spec-scanner and impl-scanner skills must remain independently usable.
Run full verification and stop.
```

## Phase 6 Prompt

```text
Continue from docs/designs/codex-subagent-spawn-plan.md.

Previous phases completed: Phase 1 through Phase 5.
Inspect git status and relevant diffs first.

Implement Phase 6 only:
- Expand scripts/validate.sh coverage:
  1. Codex frontmatter has no dangling YAML list items.
  2. Codex dispatcher skills that mention spawn_agent to plugin agents include referenced agent definitions.
  3. Codex output does not leave raw active agent_ref usage.
  4. Source agents expected for Codex are installable or intentionally gated out.
  5. Claude agent/skill counts still match expected source counts after harness gating.
- Keep checks conservative and shell-only.
Run npm run build && npm run validate and all dry-runs from the plan.
Stop with final summary and remaining risks.
```

## Generic Resume Prompt

```text
Read docs/designs/codex-subagent-spawn-plan.md and docs/designs/codex-subagent-spawn-prompts.md.
Continue from the last completed phase.
Before editing, inspect git status --short and recent diff.
Keep Claude behavior unchanged.
Do not edit dist directly; regenerate with npm run build.
Implement only the next phase, verify, then stop and report.
```

## Final Verification Prompt

```text
Read docs/designs/codex-subagent-spawn-plan.md.
Do not implement new features.
Perform final verification only:
- npm run build
- npm run validate
- node bin/hbrness.js install codex backflow --dry-run
- node bin/hbrness.js install codex specflow --dry-run
- node bin/hbrness.js install codex meeting-prep --dry-run
- node bin/hbrness.js install claude backflow --dry-run
- rg -n "^- (shell|apply_patch|Skill|spawn_agent)$|^  - (shell|apply_patch|Skill|spawn_agent)$" dist/codex -g "*.md"
- rg -n "agent_ref:" dist/codex
- rg -n "참조 에이전트 정의|spawn_agent 호출 시" dist/codex/*/skills
- rg -n "allowed-tools|Agent 도구" dist/claude/*/skills dist/claude/*/agents

Report pass/fail, remaining risks, and exact files that changed.
```
