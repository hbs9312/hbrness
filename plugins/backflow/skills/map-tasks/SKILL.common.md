---
name: map-tasks
description: 구현 태스크를 구체적인 파일과 계층에 매핑합니다. "태스크 매핑", "파일 매핑", "구현 계획" 요청 시 사용.
argument-hint: [태스크 파일 경로] [기술 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write]
effort: high
---

# 태스크-파일 매핑 (BM)

ultrathink

당신은 백엔드 아키텍트입니다.
구현 태스크를 분석하여 각 태스크가 건드려야 할 파일, 계층, 책임 경계를 선언합니다.
이 맵은 impl-* 스킬(B1~B6)의 작업 범위를 제한하고, validate-code(BV1)의 검증 기준이 됩니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md) — structure, database, naming 필수
- **기존 코드 레지스트리**: `.backflow/service-registry.md` (있으면)

## 입력

$ARGUMENTS 에서:
1. **태스크 파일** — `specs/PLAN-*-tasks.md` (decompose 산출물) 또는 `detect-changes` 델타 리포트
2. **기술 명세서(TS)** — API 설계, 데이터 모델, 처리 흐름 섹션

## 모드 자동 판별

| 입력 파일 구조 | 모드 | 동작 |
|---------------|------|------|
| `tasks:` 루트 + `id: "TASK-NNN"` | `full` | 전체 backend 태스크 매핑 |
| `changes:` 루트 + `impl_hints:` | `incremental` | 변경 항목만 매핑 |

## ★ 핵심 원칙: 선언 후 구현 ★

impl-* 스킬이 "어떤 파일을, 어떤 범위로" 작업할지를 구현 전에 확정합니다.
이 맵에 없는 파일은 impl-* 스킬이 생성하지 않아야 합니다.

## 처리

### Step 1: backend.md 검증

`structure` 섹션의 필수 값 확인:
- `src_root`, `module_pattern`, `naming` — 하나라도 비어 있으면 중단 + 사용자에게 작성 요청
- `controller_dir`, `service_dir`, `repository_dir` — 비어 있으면 경고 (해당 계층 매핑 생략)

### Step 2: 레지스트리 로드

`.backflow/service-registry.md`가 있으면:
- 기존 엔티티, 리포지토리, 서비스, 컨트롤러, 미들웨어, 유틸 목록 확보
- 각 항목의 `path`, `name`, `methods`/`endpoints` 정보 활용

없으면:
- 경고 출력: "service-registry.md 없음 — scan-codebase 실행을 권장합니다"
- backend.md 경로 기반 Glob/Grep fallback으로 기존 파일 탐색

### Step 3: TS 분석 + 계층 분류

태스크의 `source_refs`와 TS 섹션을 교차 분석하여 계층 결정:

| TS 섹션 | 계층 | impl 스킬 |
|---------|------|----------|
| 데이터 모델 | schema | impl-schema (B1) |
| 데이터 모델 + 처리 흐름 | repository | impl-repositories (B2) |
| 처리 흐름 + 비즈니스 룰(BR) | service | impl-services (B3) |
| API 설계 | controller + dto | impl-controllers (B4) |
| 보안/인증/비기능 | middleware | impl-middleware (B5) |
| 인프라/비동기/외부 호출 | integration | impl-integrations (B6) |

frontend, infra, ml, qa 타입 태스크는 건너뜁니다 (backend 전용 매핑).

### Step 4: 파일 경로 해석

#### 기존 파일 (action: modify)

1. service-registry.md에서 엔티티/서비스/컨트롤러 이름으로 검색
2. 매칭되면 → 해당 `path` 사용
3. 레지스트리 없으면 → backend.md 경로 + Glob으로 파일 탐색

#### 신규 파일 (action: create)

backend.md의 `module_pattern`에 따라 경로 생성:

| module_pattern | 경로 템플릿 |
|----------------|------------|
| flat | `{layer_dir}/{feature}.{layer}.{ext}` |
| feature-module | `{src_root}/modules/{feature}/{layer_dir_name}/{feature}.{layer}.{ext}` |
| domain-driven | `{src_root}/domain/{aggregate}/{infra_or_app}/{feature}.{layer}.{ext}` |

`naming` 컨벤션 적용:
- `kebab-case` → `speaker-enrollment.service.ts`
- `camelCase` → `speakerEnrollment.service.ts`
- `PascalCase` → `SpeakerEnrollment.service.ts`

### Step 5: 책임 경계 정의

각 파일 매핑에 `responsibility` 필드를 작성합니다:

- **should**: 이 태스크에서 이 파일이 해야 할 일 (TS/FS에서 도출)
- **should_not**: 이 파일이 하지 말아야 할 일 (계층 침범 방지)

계층별 should_not 기본 규칙:

| 계층 | should_not |
|------|-----------|
| schema | 비즈니스 로직, 쿼리 메서드 |
| repository | 비즈니스 로직, 트랜잭션 관리, 다른 리포지토리 호출 |
| service | HTTP 상태 코드, 요청 파싱, Request/Response 객체, 직접 DB 접근 |
| controller | 비즈니스 로직, 직접 리포지토리 호출 |
| dto | 비즈니스 로직 |
| middleware | 특정 비즈니스 도메인 로직 |
| integration | HTTP 관심사, 직접 비즈니스 로직 |

### Step 6: 증분 모드 처리 (detect-changes 입력)

1. `changes[]`에서 `impl_hints.backend` 항목만 필터
2. `impl_hints.skip: true` 항목 제외
3. `impl_hints.touched_modules` → 기존 파일 경로로 직접 매핑
4. `impl_hints.action` → 파일별 responsibility.should로 변환
5. `impl_hints.mapping: unresolved` → 경고 + backend.md 기반 추정 경로 제공

### Step 7: 존재 검증

- `action: modify` 파일 → Glob으로 실제 존재 확인. 없으면 경고
- `action: create` 파일 → Glob으로 미존재 확인. 이미 있으면 `action: modify`로 변경

### Step 8: 커밋 계획 생성

task_map의 파일들을 Phase(계층) 단위로 그룹화한 뒤, 각 Phase 내에서 커밋 단위를 분리합니다.

#### Phase-계층 매핑

| 계층 | Phase | impl 스킬 |
|------|-------|----------|
| schema | phase_1 | impl-schema |
| repository | phase_2 | impl-repositories |
| service | phase_3 | impl-services |
| controller + dto | phase_4 | impl-controllers |
| middleware | phase_5 | impl-middleware |
| integration | phase_6 | impl-integrations |

#### 커밋 분리 기준

| Phase | 분리 규칙 |
|-------|----------|
| phase_1 | 모델+마이그레이션=1커밋, DTO 별도 |
| phase_2 | 신규 리포지토리 1개=1커밋, 기존 수정은 묶음 |
| phase_3 | 서비스 1개=1커밋 (관련 예외/유틸 포함) |
| phase_4 | 엔드포인트 추가 단위=1커밋 |
| phase_5 | 각각 1커밋 (auth guard, error handler, rate limiter 등 항목별) |
| phase_6 | 각각 1커밋 (메시지 큐, 캐시, 스토리지 등 항목별) |

#### 공통 원칙

- 각 커밋이 독립적으로 이해 가능해야 함
- 신규 파일과 기존 파일 수정은 가능한 한 분리
- 단일 파일 Phase는 1커밋
- 커밋 메시지 형식: `{layer}: {변경 요약}`

## 출력

```yaml
# .backflow/task-file-map.md

meta:
  mode: "full" | "incremental"
  source: "{입력 파일 경로}"
  ts_ref: "{TS 경로}"
  registry_used: true | false
  generated_at: "{ISO8601}"

warnings:
  - "{경고 메시지}"

task_map:
  - task_id: "TASK-001"
    title: "{태스크 제목}"
    layers: [schema, repository, service, controller]
    files:
      - path: "src/services/payment.service.ts"
        layer: service
        action: create | modify
        impl_skill: impl-services
        responsibility:
          should: "BR-001 쿼터 검증, BR-003 중복 검사"
          should_not: "HTTP 상태 코드, 직접 DB 접근"

      - path: "src/controllers/payment.controller.ts"
        layer: controller
        action: create
        impl_skill: impl-controllers
        responsibility:
          should: "POST /payments — 요청 파싱 + 서비스 호출 + 응답 변환"
          should_not: "비즈니스 로직, 직접 리포지토리 호출"

summary:
  total_tasks: {N}
  total_files: {N}
  by_action: { create: N, modify: N }
  by_layer: { schema: N, repository: N, service: N, controller: N, dto: N, middleware: N, integration: N }

commit_plan:
  phase_1:
    - commit: "schema: add speakers table and migration"
      files: ["src/entities/speaker.entity.ts", "src/migrations/..."]
      tasks: [TASK-001]
  phase_3:
    - commit: "service: implement SpeakerEnrollmentService"
      files: ["src/services/speaker-enrollment.service.ts"]
      tasks: [TASK-003]
    - commit: "service: implement SpeakerQueryService"
      files: ["src/services/speaker-query.service.ts"]
      tasks: [TASK-004]
```

## 저장: `.backflow/task-file-map.md`

## 품질 자가 점검

- [ ] 태스크 파일의 모든 backend 태스크에 파일 매핑이 있는가
- [ ] 모든 파일 경로가 backend.md의 structure + naming 컨벤션을 따르는가
- [ ] `action: modify` 파일이 실제로 존재하는가 (Glob 확인)
- [ ] `action: create` 파일이 기존에 없는가 (Glob 확인)
- [ ] 각 파일에 `responsibility` 경계가 정의되었는가
- [ ] 계층 분류가 TS 섹션과 일치하는가
- [ ] frontend/infra/ml/qa 타입 태스크가 backend 매핑에 포함되지 않았는가
- [ ] commit_plan의 모든 파일이 task_map에 존재하는가
- [ ] task_map의 모든 파일이 commit_plan에 포함되었는가
- [ ] 각 커밋 단위가 독립적으로 이해 가능한가
- [ ] Phase별 커밋 분리 기준을 준수하는가
