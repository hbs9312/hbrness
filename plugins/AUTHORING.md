# 플러그인·스킬 작성 가이드

이 문서는 **새 스킬을 추가할 때** 따라야 할 파일 저장 규약을 정의합니다. 한 플러그인이 claude·codex 등 여러 코딩 에이전트(하네스)에서 동시에 동작해야 하므로, 디스크에 파일을 쓰거나 읽는 모든 스킬은 아래 세 계층 중 하나를 **명시적으로** 선택해야 합니다.

## 4-Tier Storage Convention

### 결정 플로우

```
이 데이터가 프로젝트 repo 안에 살아야 하는가?
(커밋 대상이거나 프로젝트 워킹 디렉토리에 종속)
│
├── 예 ─────────────────────────────────▶ Tier 0 (project-local)
│
└── 아니오 — 사용자 홈에 산다
    │
    ├── 여러 코딩 에이전트에서 공유되어야 하는가? (또는 "상관없음")
    │                                   ──▶ Tier 1 (tool-agnostic)
    │
    ├── 아니오, 하네스 고유 시스템(Claude 자동 메모리, codex AGENTS.md 등)과
    │   동일 디렉토리에 살아야 함        ──▶ Tier 2 (harness-placeholder)
    │
    └── 스킬 자체가 특정 하네스 고유 기능에 종속되어
        다른 하네스에서는 의미 없음       ──▶ Tier 3 (harness-gated)
```

**의심스러우면 Tier 1.** 대부분의 "데이터" 는 Tier 1이 맞고, **프로젝트 산출물·환경 설정**만 Tier 0 입니다.

---

### Tier 0 — Project-local

프로젝트 repo 내부에 살아야 하는 데이터. 커밋 대상인 산출물이거나, 프로젝트 워킹 디렉토리와 수명을 함께하는 스킬 워킹 스토리지.

**경로 규약:**
```
<project-root>/<conventional-dir>/...
```

두 하위 유형이 있습니다:

- **Dot-prefixed (툴 관리 워킹 스토리지)** — 스킬이 쓰고 읽는 임시·상태 파일. 대부분 gitignore 대상.
  - `.e2e/` — dbflow 의 config·state·scenarios·snapshots
  - `.specflow/` (예정) — specflow 의 상태·캐시
  - 규약: 스킬은 `.gitignore` 에 cache/state/snapshots/reports 를 **자동 append** (idempotent)
- **Plain (유저 산출물)** — 팀이 직접 다루는 명세·문서. 보통 커밋 대상.
  - `specs/` — specflow 의 FS/TS/WF/UI/QA 명세
  - `docs/` — 프로젝트 문서
  - 규약: 스킬이 덮어쓸 때 기존 사람 편집이 있으면 **확인 후**

**작성 방법 (소스 `.common.md`):**
```markdown
저장 경로: `<project-root>/.e2e/state.json`
설정 경로: `<project-root>/.e2e/config.yml`
```

별도 placeholder 치환 없이 **프로젝트 상대 경로**로 씀. 스킬은 실행 시점에 `pwd` 또는 `git rev-parse --show-toplevel` 로 root 를 해석.

**주의:**
- 프로젝트 repo 밖에 살아도 되는 데이터(캐시·결과물)는 Tier 1 이 맞습니다. Tier 0 는 "이 프로젝트와 함께 죽고 산다" 는 의미가 있을 때만.
- Tier 0 은 하네스 구분이 없으므로 `{HARNESS_HOME}` placeholder 와 섞이면 안 됩니다.

**현재 Tier 0 스킬/플러그인:**
- `dbflow` — `.e2e/` 전체 (config.yml + scenarios/ + fixtures/ commit, snapshots/state/cache/reports gitignore)
- `specflow` — `specs/` 출력 (플러그인 전체가 Tier 0 산출물 생성)

---

### Tier 1 — Tool-agnostic (기본값)

공유 글로벌 캐시/결과물. 하네스가 뭐든 같은 경로를 쓴다.

**경로 규약:**
```
~/.hbrness/{plugin}/{resource}/...
```

예:
- PR 리뷰 결과: `~/.hbrness/reviews/{owner}/{repo}/pr-NNN-TIMESTAMP.md`
- 스킬별 캐시: `~/.hbrness/{plugin-name}/cache/...`
- 임시 산출물: `~/.hbrness/tmp/{skill}/...`

**레거시 예외**: 이미 독립 디렉토리를 쓰는 기존 스킬은 그대로 둔다.
- `~/.commit-chronicles/` (ghflow:chronicle 계열)

신규 스킬은 **새 최상위 dot-dir 추가 금지**. `~/.hbrness/` 하위에만.

**작성 방법:**
```markdown
저장 경로: `~/.hbrness/reviews/{owner}/{repo}/pr-{N}-{TS}.md`

mkdir -p ~/.hbrness/reviews/{owner}/{repo}
```

별도 placeholder 치환 없이 **리터럴로 씀**.

---

### Tier 2 — Harness-placeholder

해당 하네스의 고유 디렉토리(예: Claude Code가 스캔하는 `~/.claude/` 내부)에 반드시 살아야 할 때. **드물게 필요**합니다.

**Placeholder 문법:**

| Placeholder | claude 빌드 치환 | codex 빌드 치환 |
|---|---|---|
| `{HARNESS_HOME}` | `~/.claude` | `~/.codex` |
| `{HARNESS_NAME}` | `claude` | `codex` |
| `{HBRNESS_HOME}` | `~/.hbrness` | `~/.hbrness` |

**작성 방법 (소스 `.common.md`):**
```markdown
저장 경로: `{HARNESS_HOME}/cache/…`
```

빌드 후 dist/claude → `~/.claude/cache/…`, dist/codex → `~/.codex/cache/…`.

**주의:** "단지 사용자 홈의 dot-dir이 필요해서"가 이유라면 Tier 1이 맞습니다. Tier 2는 **"이 하네스의 구체적인 내부 시스템과 연동되어야 한다"** 는 이유가 있을 때만.

---

### Tier 3 — Harness-gated

스킬 자체가 특정 하네스의 고유 기능에 묶여 다른 하네스에서는 **의미가 없는** 경우. 이 경우 빌드 시점에 해당 하네스 dist에서만 포함시키고 다른 하네스 dist에서는 누락시킨다.

**선언 방법 (소스 `.common.md` frontmatter):**
```yaml
---
name: pick-issue
description: ...
harness: [claude]    # 이 스킬은 claude에만 포함됨
---
```

복수 하네스 지정 가능:
```yaml
harness: [claude, codex]  # 둘 다 포함 (명시. 생략해도 같은 효과)
```

`harness:` 필드를 **생략하면 모든 하네스 포함**(기본값).

**Tier 3 에이전트:** 에이전트 `.common.md`도 같은 방식.

**현재 Tier 3 선언된 스킬:**
- `ghflow:pick-issue` — Claude Code의 자동 메모리(`~/.claude/projects/.../memory/`) 시스템에 종속
- `ghflow:clear-issue` — 위와 동일
- `xreview:review-bridge` (agent) — `~/.claude/plugins/cache/` 에서 codex 바이너리 탐색하는 로직 포함

---

## 금지 사항

다음은 `.common.md` 소스 파일에 **나타나면 안 됨** (`npm run validate` 가 잡아냄):

- `~/.claude` 리터럴
- `~/.codex` 리터럴
- `$HOME/.claude` 리터럴
- `$HOME/.codex` 리터럴
- `${CLAUDE_*}` 환경변수 참조 (이미 lint 있음)
- `${CODEX_*}` 환경변수 참조 (이미 lint 있음)

대신 Tier 0 (프로젝트 상대 경로), Tier 1 (`~/.hbrness/…`), Tier 2 placeholder (`{HARNESS_HOME}/…`) 를 사용하거나, Tier 3로 게이팅하라.

## 체크리스트 — 신규 스킬 작성 시

- [ ] 저장 경로가 있다면 Tier 0/1/2/3 중 **어느 쪽인지 의식적으로 결정**
- [ ] Tier 0이면 프로젝트 상대 경로 + (워킹 스토리지는) `.gitignore` 자동 append 로직
- [ ] Tier 1이면 `~/.hbrness/{plugin}/…` 하위로
- [ ] Tier 2면 `{HARNESS_HOME}` placeholder 사용
- [ ] Tier 3이면 `harness: [...]` frontmatter 선언 + 이 문서의 "현재 Tier 3" 목록에 추가
- [ ] `npm run build && npm run validate` 통과 확인
- [ ] dist/claude 와 dist/codex 양쪽에서 경로 치환이 의도대로 됐는지 spot check

## 마이그레이션 기록

최초 규약은 2026-04-22에 3-tier 로 도입되었습니다. 2026-04-23 에 Tier 0 (project-local) 이 추가되어 4-tier 가 되었습니다.

| 스킬 | 이전 | 이후 |
|---|---|---|
| `ghflow:review-pr` | `~/.claude/reviews/` | `~/.hbrness/reviews/` (Tier 1) |
| `ghflow:clear-issue` | 하드코딩된 `~/.claude/projects/` | `harness: [claude]` (Tier 3) |
| `ghflow:pick-issue` | 하드코딩된 `~/.claude/projects/` | `harness: [claude]` (Tier 3) |
| `xreview:review-bridge` (agent) | 하드코딩된 `~/.claude/plugins/` | `harness: [claude]` (Tier 3) |
| `dbflow` | n/a | `.e2e/` (Tier 0, 본문 적용 — Phase 1.5.0) |
| `specflow` 산출물 | 암묵적 project-local | `specs/` (Tier 0) 로 명시 |
