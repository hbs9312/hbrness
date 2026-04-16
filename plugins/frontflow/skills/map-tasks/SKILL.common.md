---
name: map-tasks
description: 구현 태스크를 구체적인 파일과 계층에 매핑합니다. "태스크 매핑", "파일 매핑", "구현 계획" 요청 시 사용.
argument-hint: [태스크 파일 경로] [UI 명세 경로] [기술 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write]
effort: high
---

# 태스크-파일 매핑 (FM)

ultrathink

당신은 프론트엔드 아키텍트입니다.
구현 태스크를 분석하여 각 태스크가 건드려야 할 파일, 계층, 책임 경계를 선언합니다.
이 맵은 impl-* 스킬(F1~F6)의 작업 범위를 제한하고, validate-code(FV1)의 검증 기준이 됩니다.

## 컨텍스트 로드

- **프로젝트 설정**: [frontend.md](../../context/frontend.md) — structure, styling, component_pattern 필수
- **기존 컴포넌트 레지스트리**: `.frontflow/component-registry.md` (있으면)

## 입력

$ARGUMENTS 에서:
1. **태스크 파일** — `specs/PLAN-*-tasks.md` (decompose 산출물) 또는 `detect-changes` 델타 리포트
2. **UI 명세서** — 컴포넌트 명세, 디자인 토큰, 페이지 레이아웃 섹션
3. **기술 명세서(TS)** — API 설계, 상태 관리, 데이터 흐름 섹션

## 모드 자동 판별

| 입력 파일 구조 | 모드 | 동작 |
|---------------|------|------|
| `tasks:` 루트 + `id: "TASK-NNN"` | `full` | 전체 frontend 태스크 매핑 |
| `changes:` 루트 + `impl_hints:` | `incremental` | 변경 항목만 매핑 |

## ★ 핵심 원칙: 선언 후 구현 ★

impl-* 스킬이 "어떤 파일을, 어떤 범위로" 작업할지를 구현 전에 확정합니다.
이 맵에 없는 파일은 impl-* 스킬이 생성하지 않아야 합니다.

## 처리

### Step 1: frontend.md 검증

`structure` 섹션의 필수 값 확인:
- `component_dir`, `page_dir`, `naming` — 하나라도 비어 있으면 중단 + 사용자에게 작성 요청
- `hook_dir`, `util_dir`, `type_dir` — 비어 있으면 경고 (해당 계층 매핑 생략)

`styling` 섹션 확인:
- `method` — 비어 있으면 경고 (토큰 매핑 시 기본값 적용)

### Step 2: 레지스트리 로드

`.frontflow/component-registry.md`가 있으면:
- 기존 컴포넌트, 훅, 유틸, 페이지 목록 확보
- 각 항목의 `path`, `name`, `props`/`exports` 정보 활용

없으면:
- 경고 출력: "component-registry.md 없음 — scan-codebase 실행을 권장합니다"
- frontend.md 경로 기반 Glob/Grep fallback으로 기존 파일 탐색

### Step 3: UI 명세 + TS 분석 → 계층 분류

태스크의 `source_refs`와 UI 명세/TS 섹션을 교차 분석하여 계층 결정:

| UI 명세/TS 섹션 | 계층 | impl 스킬 |
|----------------|------|----------|
| 디자인 토큰 | tokens | impl-tokens (F1) |
| 원자 컴포넌트 | atoms | impl-atoms (F2) |
| 복합 컴포넌트 | composites | impl-composites (F3) |
| 페이지 레이아웃 | pages | impl-pages (F4) |
| 상태/인터랙션 | interactions | impl-interactions (F5) |
| API 연동 | api-integration | impl-api-integration (F6) |

backend, infra, ml, qa 타입 태스크는 건너뜁니다 (frontend 전용 매핑).

### Step 4: 파일 경로 해석

#### 기존 파일 (action: modify)

1. component-registry.md에서 컴포넌트/훅/유틸 이름으로 검색
2. 매칭되면 → 해당 `path` 사용
3. 레지스트리 없으면 → frontend.md 경로 + Glob으로 파일 탐색

#### 신규 파일 (action: create)

frontend.md의 `structure`에 따라 경로 생성:

| 계층 | 경로 템플릿 |
|------|------------|
| tokens | `{component_dir}/tokens/{feature}.tokens.{ext}` |
| atoms | `{component_dir}/atoms/{ComponentName}/{ComponentName}.{ext}` |
| composites | `{component_dir}/composites/{ComponentName}/{ComponentName}.{ext}` |
| pages | `{page_dir}/{route}/{page}.{ext}` |
| interactions | `{hook_dir}/{feature}.hook.{ext}` |
| api-integration | `{hook_dir}/api/{feature}.api.{ext}` |

`naming` 컨벤션 적용:
- `PascalCase` → `StatusIcon/StatusIcon.tsx` (컴포넌트)
- `camelCase` → `useSpeaker.hook.ts` (훅)
- `kebab-case` → `speaker-api.ts` (유틸)

`co_location: true`이면 같은 디렉토리에 스토리/테스트/스타일 파일도 매핑:
- `{ComponentName}.stories.tsx`
- `{ComponentName}.test.tsx`
- `{ComponentName}.module.css` (css-modules일 때)

### Step 5: 책임 경계 정의

각 파일 매핑에 `responsibility` 필드를 작성합니다:

- **should**: 이 태스크에서 이 파일이 해야 할 일 (UI 명세/TS에서 도출)
- **should_not**: 이 파일이 하지 말아야 할 일 (계층 침범 방지)

계층별 should_not 기본 규칙:

| 계층 | should_not |
|------|-----------|
| tokens | 컴포넌트 로직, 레이아웃 |
| atoms | 다른 프로젝트 컴포넌트 import, API 호출, 글로벌 상태 접근 |
| composites | 직접 API 호출, 라우팅 로직 |
| pages | 비즈니스 로직, 직접 API fetch |
| interactions | 직접 DOM 조작, 컴포넌트 렌더링 |
| api-integration | UI 렌더링 로직, 직접 상태 조작 |

### Step 6: 증분 모드 처리 (detect-changes 입력)

1. `changes[]`에서 `impl_hints.frontend` 항목만 필터
2. `impl_hints.skip: true` 항목 제외
3. `impl_hints.touched_components` → 기존 파일 경로로 직접 매핑
4. `impl_hints.action` → 파일별 responsibility.should로 변환
5. `impl_hints.mapping: unresolved` → 경고 + frontend.md 기반 추정 경로 제공

### Step 7: 존재 검증

- `action: modify` 파일 → Glob으로 실제 존재 확인. 없으면 경고
- `action: create` 파일 → Glob으로 미존재 확인. 이미 있으면 `action: modify`로 변경

### Step 8: 커밋 계획 생성

task_map의 파일들을 Phase(계층) 단위로 그룹화한 뒤, 각 Phase 내에서 커밋 단위를 분리합니다.

#### Phase-계층 매핑

| 계층 | Phase | impl 스킬 |
|------|-------|----------|
| tokens | phase_1 | impl-tokens |
| atoms | phase_2 | impl-atoms |
| composites | phase_3 | impl-composites |
| pages | phase_4 | impl-pages |
| interactions | phase_5 | impl-interactions |
| api-integration | phase_6 | impl-api-integration |

#### 커밋 분리 기준

| Phase | 분리 규칙 |
|-------|----------|
| phase_1 | 토큰 설정=1커밋 |
| phase_2 | 1컴포넌트+스토리=1커밋 |
| phase_3 | 1복합 컴포넌트+스토리=1커밋 |
| phase_4 | 1페이지=1커밋 |
| phase_5 | 상태 관리 단위=1커밋 |
| phase_6 | API 연동 단위=1커밋 |

#### 공통 원칙

- 각 커밋이 독립적으로 이해 가능해야 함
- 신규 파일과 기존 파일 수정은 가능한 한 분리
- 단일 파일 Phase는 1커밋
- 커밋 메시지 형식: `{layer}: {변경 요약}`

## 출력

```yaml
# .frontflow/task-file-map.md

meta:
  mode: "full" | "incremental"
  source: "{입력 파일 경로}"
  ui_ref: "{UI 명세 경로}"
  ts_ref: "{TS 경로}"
  registry_used: true | false
  generated_at: "{ISO8601}"

warnings:
  - "{경고 메시지}"

task_map:
  - task_id: "TASK-001"
    title: "{태스크 제목}"
    layers: [atoms, composites, pages]
    files:
      - path: "src/components/atoms/StatusIcon/StatusIcon.tsx"
        layer: atoms
        action: create
        impl_skill: impl-atoms
        responsibility:
          should: "상태별 아이콘 렌더링 (active, inactive, error)"
          should_not: "API 호출, 글로벌 상태 접근"

      - path: "src/components/atoms/StatusIcon/StatusIcon.stories.tsx"
        layer: atoms
        action: create
        impl_skill: impl-atoms
        responsibility:
          should: "모든 상태 variant에 대한 스토리"
          should_not: "실제 API 호출"

summary:
  total_tasks: {N}
  total_files: {N}
  by_action: { create: N, modify: N }
  by_layer: { tokens: N, atoms: N, composites: N, pages: N, interactions: N, api-integration: N }

commit_plan:
  phase_1:
    - commit: "tokens: configure design tokens"
      files: ["src/components/tokens/theme.tokens.ts"]
      tasks: [TASK-001]
  phase_2:
    - commit: "atoms: implement StatusIcon + story"
      files: ["src/components/atoms/StatusIcon/StatusIcon.tsx", "src/components/atoms/StatusIcon/StatusIcon.stories.tsx"]
      tasks: [TASK-002]
    - commit: "atoms: implement Badge + story"
      files: ["src/components/atoms/Badge/Badge.tsx", "src/components/atoms/Badge/Badge.stories.tsx"]
      tasks: [TASK-003]
```

## 저장: `.frontflow/task-file-map.md`

## 품질 자가 점검

- [ ] 태스크 파일의 모든 frontend 태스크에 파일 매핑이 있는가
- [ ] 모든 파일 경로가 frontend.md의 structure + naming 컨벤션을 따르는가
- [ ] `action: modify` 파일이 실제로 존재하는가 (Glob 확인)
- [ ] `action: create` 파일이 기존에 없는가 (Glob 확인)
- [ ] 각 파일에 `responsibility` 경계가 정의되었는가
- [ ] 계층 분류가 UI 명세/TS 섹션과 일치하는가
- [ ] backend/infra/ml/qa 타입 태스크가 frontend 매핑에 포함되지 않았는가
- [ ] commit_plan의 모든 파일이 task_map에 존재하는가
- [ ] task_map의 모든 파일이 commit_plan에 포함되었는가
- [ ] 각 커밋 단위가 독립적으로 이해 가능한가
- [ ] Phase별 커밋 분리 기준을 준수하는가
