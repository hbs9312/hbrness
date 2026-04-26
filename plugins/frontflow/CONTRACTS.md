# frontflow — Skill I/O Contracts

> **Scope**: 각 스킬이 어떤 입력(specflow 산출물·레지스트리·선행 스킬 출력·외부 MCP)을 읽고 어떤 출력을 어디에 쓰는지 명시한다.
> **Why this doc exists**: `docs/plugin-gaps-and-plan.md` 의 Phase 0 step 2.
> **Storage tier**: `plugins/AUTHORING.md` 의 4-tier 규약을 따른다.

## 실행 순서 (canonical)

```
scan-codebase
     │
     ▼
map-tasks                 ← decompose 출력을 파일·레이어에 매핑
     │
     ▼
impl-tokens               ← UI §디자인 토큰
     │
     ▼
impl-atoms                ← UI §컴포넌트 명세 (atoms)
     │
     ▼
impl-composites           ← UI §컴포넌트 명세 (composites) + TS §API 응답
     │                      + extract-figma (선택)
     ▼
impl-pages                ← WF (전환·레이아웃) + UI (반응형) + mock data
     │
     ▼
impl-error-handling       ← TS §에러 코드 맵 (+ UI ui_flow 힌트)   ★Phase 1 (1)
     │                      impl-interactions / impl-api-integration 에 앞서 실행 권장
     ▼
sync-api-client           ← openapi.yaml → codegen (types + client + MSW)   ★Phase 1 (3)
     │
     ▼
impl-tracking [Phase A]   ← FS §7 → events/track/adapters/selected-adapter   ★Phase 1 (4)
     │
     ▼
impl-interactions         ← FS BR + UI 인터랙션 + WF 상태 매트릭스 + TS 상태 enum
     │
     ▼
impl-api-integration      ← TS §API 설계 (F5 stub → 실제 호출 교체; handleError 를 impl-error-handling 에서 import)
     │
     ▼
impl-tracking [Phase B]   ← 컴포넌트 hook 삽입 proposal (default) / apply   ★Phase 1 (4)
     │
     ▼
validate-{code,visual,a11y} ← 구현된 코드·스토리·접근성 검증
     │
     ▼
patch-frontend / reimpl-frontend   ← 검증 피드백 반영
```

유틸 스킬(`generate-stories`, `extract-figma`, `screenshot-compare`)는 플로우 어디서든 호출 가능한 보조 도구.

> **⚠️ 순서 주의**: `docs/plugin-gaps-and-plan.md` 초기 서술에는 `interactions → pages` 로 적혀 있으나, 실제 스킬 의존성은 `pages → interactions` (`impl-interactions` 가 `impl-pages` 에 의존). 이 문서가 canonical. 로드맵 문서는 후속 정정 예정.

## 핵심 공통 레지스트리

| 파일 | 쓰는 스킬 | 읽는 스킬 | Tier | 비고 |
|---|---|---|---|---|
| `.frontflow/component-registry.md` | scan-codebase | map-tasks, impl-atoms, impl-composites, validate-* | Tier 0 | 기존 컴포넌트·훅·유틸·디자인시스템 레지스트리 |
| `.frontflow/task-file-map.md` | map-tasks | 모든 impl-*, validate-code | Tier 0 | 태스크 → 파일·레이어, commit plan |
| `frontend.md` (프로젝트 설정) | — | 모든 스킬 | Tier 0 | framework/styling/state_management/api_client 등 |
| `.frontflow/api-contract.lock` | sync-api-client | validate-code (§9 drift 검사) | Tier 0 | version/contract_hash/source_etag/generated_at/generator 박제. commit 대상 |
| `frontend.md.tracking.*` | — (사람 설정) | impl-tracking, validate-code (§10 drift) | Tier 0 | vendor / files / consent_gate / default_properties / pii_redact / codemod_mode |
| Figma data cache | extract-figma | impl-composites, impl-pages | Tier 1 (`~/.hbrness/figma/...`) | Figma MCP 응답 정규화·노이즈 제거 캐시 |

## 스킬별 계약

### scan-codebase

| 항목 | 내용 |
|---|---|
| **Purpose** | 기존 컴포넌트·훅·유틸·디자인시스템 패키지 스캔 → 레지스트리 생성 |
| **Reads (specflow)** | — |
| **Reads (registry/config)** | `frontend.md` (component_dir, design_system_package, hook_dir, util_dir), `npm ls --json` |
| **Writes** | `.frontflow/component-registry.md` (컴포넌트명·Props 인터페이스·의존 그래프) |
| **Storage Tier** | Tier 0 |
| **Depends on** | — |
| **Notes** | 플러그인 도입 시점 1회 실행. design_system_package 는 npm 을 통해 검색. |

### map-tasks

| 항목 | 내용 |
|---|---|
| **Purpose** | 프론트엔드 태스크를 구체 파일·레이어에 매핑 |
| **Reads (specflow)** | `specs/PLAN-*-tasks.md`, `specs/UI/*` (컴포넌트 명세·토큰), `specs/TS/*` (API·state·데이터 흐름) |
| **Reads (registry/config)** | `.frontflow/component-registry.md` (있으면), `frontend.md` (structure, styling, component_pattern) |
| **Writes** | `.frontflow/task-file-map.md` |
| **Storage Tier** | Tier 0 |
| **Depends on** | scan-codebase |
| **Notes** | 레이어 분류: tokens→F1, atoms→F2, composites→F3, pages→F4, interactions→F5, api-integration→F6. co_location 여부 반영. |

### impl-tokens

| 항목 | 내용 |
|---|---|
| **Purpose** | UI 명세 디자인 토큰을 프로젝트 styling 시스템에 설정 |
| **Reads (specflow)** | `specs/UI/*` §디자인 토큰 (colors/typography/spacing/shadow/radius/breakpoints) |
| **Reads (registry/config)** | `frontend.md` (styling.method), 기존 theme 파일(`tailwind.config.ts` / `global.css` / `styled.d.ts`) |
| **Writes** | 토큰 설정 (tailwind extend / CSS variables `:root` / theme object) |
| **Storage Tier** | N/A — project code |
| **Depends on** | — (F1 독립 실행 가능) |
| **Notes** | styling-aware (tailwind/css-modules/vanilla/styled-components). 2-tier mapping(primitive → semantic). 기존 토큰 덮어쓰기 금지, 충돌 감지. |

### impl-atoms

| 항목 | 내용 |
|---|---|
| **Purpose** | UI 명세의 원자 컴포넌트 구현 + Storybook 스토리 생성 |
| **Reads (specflow)** | `specs/UI/*` §컴포넌트 명세(atoms - 상태·variant), `specs/WF/*` (상태 매트릭스) |
| **Reads (registry/config)** | `.frontflow/component-registry.md`, design_system_package 체크, impl-tokens 결과 |
| **Writes** | 컴포넌트 파일 (`{component_dir}/{ComponentName}/{ComponentName}.tsx`), `*.stories.tsx`, `*.test.tsx` (co_location 시) |
| **Storage Tier** | N/A — project code |
| **Depends on** | impl-tokens |
| **Notes** | 재사용 체크 우선. composite 금지(atoms only). 모든 스타일은 토큰 경유(하드코딩 금지). `className + ...rest` 필수. Storybook: Default/AllVariants/Disabled/Loading/Error/Mobile. |

### impl-composites

| 항목 | 내용 |
|---|---|
| **Purpose** | atoms 를 조합해 도메인 복합 컴포넌트 구현 |
| **Reads (specflow)** | `specs/UI/*` §컴포넌트 명세(composites), `specs/TS/*` §API 응답 스키마 (Props 타입 설계) |
| **Reads (registry/config)** | impl-atoms 결과, `.frontflow/component-registry.md`, Figma MCP (있으면 Auto Layout 정밀도) |
| **Writes** | 복합 컴포넌트 파일 (`{component_dir}/composites/{ComponentName}/*.tsx`), mock data Storybook 스토리(현실적 한글 데이터·상태 variant) |
| **Storage Tier** | N/A — project code |
| **Depends on** | impl-atoms |
| **Notes** | Props 는 TS API 스키마에서 유도. Auto Layout(layoutMode/itemSpacing/padding) 은 Figma 값 그대로. API 호출 금지(F6 에서). |

### impl-pages

| 항목 | 내용 |
|---|---|
| **Purpose** | 컴포넌트를 조합해 페이지 구성 (정적 레이아웃·mock data·API 없음) |
| **Reads (specflow)** | `specs/WF/*` (화면 전환·레이아웃), `specs/UI/*` (반응형·breakpoints) |
| **Reads (registry/config)** | impl-atoms/composites 결과, `frontend.md` (page_dir, framework) |
| **Writes** | 페이지 컴포넌트 (`{page_dir}/{route}/*.tsx`), 라우팅 설정 (Next.js `app/` 또는 React Router config), layout 컴포넌트 |
| **Storage Tier** | N/A — project code |
| **Depends on** | impl-composites |
| **Notes** | 정적 구현만. `const MOCK_DATA = ...` 상단 고정. 성공 상태 고정 렌더. 반응형은 UI breakpoints 준수. |

### impl-error-handling

| 항목 | 내용 |
|---|---|
| **Purpose** | TS §에러 코드 맵 → 프론트엔드 상수(`codes.ts`) · 순수 함수 핸들러(`handler.ts`) · UI 프리셋(옵션) · i18n 리소스 |
| **Reads (specflow)** | `specs/TS/*` §4 에러 코드 맵 (필수), `specs/UI/*` (ui_flow 힌트·선택) |
| **Reads (registry/config)** | `.frontflow/task-file-map.md`(있으면), `frontend.md` (error_handling.*, api_client) |
| **Writes** | `src/errors/codes.ts`, `src/errors/handler.ts`, (선택) `src/errors/ui-flow.tsx`, `src/locales/errors.{ko,en}.json` (i18n_library != inline 시) |
| **Storage Tier** | N/A — project code |
| **Depends on** | `map-tasks`, `impl-pages`. `impl-interactions` / `impl-api-integration` 에 앞서 실행 권장 |
| **Notes** | **`code` 문자열 값이 backflow:impl-error-codes 출력과 완전 일치해야 함** (계약의 바이트). handler 는 순수 함수 — 렌더링 책임 없음. i18n 라이브러리(i18next/formatjs/lingui/inline) 에 따라 생성 형태 분기. 3 머지 시나리오 내장. AUTO-GENERATED 주석으로 멱등성. |

### sync-api-client

| 항목 | 내용 |
|---|---|
| **Purpose** | `openapi/openapi.yaml` → TS API 클라이언트 함수 + 타입 정의 + (옵션) MSW 핸들러 codegen. `info.version` + `contractHash` 이중 박제로 stale 검출 |
| **Reads (specflow)** | — (직접 읽지 않음. OpenAPI 가 specflow 의 indirect 출력) |
| **Reads (registry/config)** | `.frontflow/task-file-map.md`(있으면), `frontend.md` (`api_contract.*` 섹션 필수, `api_client.method`, `server_state`), OpenAPI 문서 (path or URL), `.frontflow/api-contract.lock` (이전 sync 의 version/hash) |
| **Writes** | `{client_dir}/{tag}.ts`, `{client_dir}/index.ts` (barrel), `{types_file}` (전체 schema 타입 + ErrorCode union), (`emit_msw=true`) `{msw_handlers_file}`, **`.frontflow/api-contract.lock`** (version/hash/source etag 박제) |
| **Storage Tier** | N/A — project code. `generated/` / `*.gen.ts` 는 commit 대상이지만 사람 편집 금지. `.frontflow/api-contract.lock` 도 commit 대상 |
| **Depends on** | `map-tasks`. **`backflow:export-api-contract` 가 먼저 실행되어 `openapi/openapi.yaml` 이 존재해야 함**. `impl-error-handling` 와 무관 — 에러 코드는 OpenAPI components.schemas.ErrorCode enum 으로 흡수 |
| **Notes** | Phase 1 default generator = **`openapi-typescript-codegen`** 단일 first-class. 다른 generator 는 experimental. AUTO-GENERATED 주석 + 헤더에 `info.version` + `contractHash` 박제. version+hash mismatch 시 validate critical. lock 비교 후 변동 없으면 no-op. |

### impl-tracking

| 항목 | 내용 |
|---|---|
| **Purpose** | FS §7 → 이벤트 상수 + 어댑터 디렉토리 + (옵션) 컴포넌트 hook 삽입 proposal/codemod |
| **Reads (specflow)** | `specs/FS/*` §7 (필수), `specs/UI/*` (where 컬럼 → 실 컴포넌트 경로 매칭), `specs/TS/*` §4 (`error_shown.error_code` 검증) |
| **Reads (registry/config)** | `.frontflow/task-file-map.md`(있으면), `.frontflow/component-registry.md`, `frontend.md` (`tracking.*` 섹션) |
| **Writes (Phase A — generate, 항상)** | `src/tracking/events.ts`, `src/tracking/track.ts`, `src/tracking/index.ts`, `src/tracking/adapters/types.ts`, `src/tracking/adapters/console.ts` (항상), `src/tracking/selected-adapter.ts`, `src/tracking/adapters/{vendor}.ts` (vendor 명시 시), `.env.example` 업데이트 |
| **Writes (Phase B — codemod, 옵션)** | 컴포넌트 파일에 hook 삽입 proposal (default `--proposal-only`) 또는 실제 Edit (`--apply` 또는 사용자 확인) |
| **Storage Tier** | N/A — project code |
| **Depends on (Phase A)** | `map-tasks`, `sync-api-client` |
| **Depends on (Phase B)** | `impl-interactions`, `impl-api-integration` |
| **Notes** | 컴포넌트·공통 tracking API 에 vendor 식별자 0건 (`adapters/{vendor}.ts` 만 예외). selected-adapter.ts 가 build-time static import 로 tree-shake 보장. AUTO-GENERATED 멱등성. |

### impl-interactions

| 항목 | 내용 |
|---|---|
| **Purpose** | 상태 관리·조건부 렌더·애니메이션 구현 (API 없이 simulate) |
| **Reads (specflow)** | `specs/FS/*` BR (조건부 렌더 규칙), `specs/UI/*` (인터랙션·애니메이션 duration/easing), `specs/WF/*` §상태 매트릭스, `specs/TS/*` (상태 enum) |
| **Reads (registry/config)** | `frontend.md` (state_management, form config) |
| **Writes** | store 파일(zustand 등), custom hooks, tanstack-query queryKey 스텁, form validation hook, 애니메이션 CSS / framer-motion |
| **Storage Tier** | N/A — project code |
| **Depends on** | impl-pages |
| **Notes** | **시뮬레이션만** (`setTimeout` mock, 실제 API 금지). FS BR → 조건부 렌더 규칙. UI 애니메이션 스펙은 duration/easing 그대로. WF 전환 → `router.push/back`. form validation 은 FS BR. |

### impl-api-integration

| 항목 | 내용 |
|---|---|
| **Purpose** | impl-interactions 의 stub 을 실제 API 호출로 교체 |
| **Reads (specflow)** | `specs/TS/*` §API 설계 (endpoints, request/response, error codes) |
| **Reads (registry/config)** | impl-interactions 결과의 stub 위치, `frontend.md` (api_client.method, server_state 설정) |
| **Writes** | API 클라이언트 (`api/{feature}.ts`), 타입 정의 (`types/api.ts`, TS 스키마와 1:1), custom hook (`hooks/use{Feature}.ts`), error → UI 플로우(inline/toast/modal/redirect) |
| **Storage Tier** | N/A — project code |
| **Depends on** | impl-interactions, impl-pages |
| **Notes** | `setTimeout` stub 탐지 후 치환. 에러 코드마다 UI 반응 경로. SSE/WebSocket 은 TS 명시 시 구현. api_client.method → fetch/axios/ky. server_state → useQuery/useMutation. |

### generate-stories

| 항목 | 내용 |
|---|---|
| **Purpose** | Storybook 스토리 자동 생성 (유틸 — F2/F3 가 자동 호출하거나 단독 실행) |
| **Reads (specflow)** | `specs/UI/*` (컴포넌트 상태) |
| **Reads (registry/config)** | 컴포넌트 Props 파일 |
| **Writes** | `*.stories.tsx` (co_location 시 컴포넌트 옆, 아니면 `storybook_dir`) |
| **Storage Tier** | N/A — project code |
| **Depends on** | — (독립 호출 가능) |
| **Notes** | 스토리: Default/AllVariants/Loading/Error/Disabled/Empty/Mobile/LongText. Props 타입으로부터 args 파생. |

### validate-code

| 항목 | 내용 |
|---|---|
| **Purpose** | 프론트엔드 코드 컨벤션·재사용성·토큰 준수·타입·a11y 기초·Storybook 커버리지 |
| **Reads (specflow)** | — |
| **Reads (registry/config)** | `.frontflow/task-file-map.md`, `frontend.md`, `.frontflow/component-registry.md` |
| **Writes** | findings YAML, 요약 리포트 (stdout·세션) |
| **Storage Tier** | N/A |
| **Depends on** | F1 ~ F6 (각 phase 별 실행) |
| **Notes** | `disable-model-invocation: false`. 필수: 파일 위치, 네이밍, barrel exports, 하드코딩 금지(토큰만), `any` 금지, 재사용 체크(레지스트리), a11y 기본, Storybook 커버리지. |

### validate-visual

| 항목 | 내용 |
|---|---|
| **Purpose** | Storybook 기반 **사람 QA 체크리스트** 생성 (현재 Phase 1) |
| **Reads (specflow)** | `specs/UI/*` (컴포넌트 시각 명세) |
| **Reads (registry/config)** | `*.stories.tsx` |
| **Writes** | 리뷰 가이드 MD (Storybook URL + Figma 비교 체크리스트), 구조화 피드백 YAML 템플릿 |
| **Storage Tier** | N/A — 리뷰 가이드(파일 쓰기 없음 또는 작업 세션 내) |
| **Depends on** | generate-stories |
| **Notes** | `disable-model-invocation: true`. 모델은 렌더 결과를 볼 수 없음(픽셀 비교 불가). Phase 2 에서 auto screenshot + pixel diff 예정. |

### validate-a11y

| 항목 | 내용 |
|---|---|
| **Purpose** | UI 명세의 a11y 요구사항 + 기본 WCAG 패턴 검증; axe-core 선택적 실행 |
| **Reads (specflow)** | `specs/UI/*` §접근성 요구사항 |
| **Reads (registry/config)** | 컴포넌트 코드, `.frontflow/component-registry.md` |
| **Writes** | a11y findings (명세 vs 구현 차이), axe-core 결과(있으면), 권고 MD |
| **Storage Tier** | N/A |
| **Depends on** | validate-code |
| **Notes** | `disable-model-invocation: true`. 체크: aria-label 상태 전환, aria-hidden, tabIndex, 터치 44×44, img alt, form label, color+icon fallback, modal focus trap, ESC, aria-live. axe-core 는 `npx` 로 감지. |

### screenshot-compare

| 항목 | 내용 |
|---|---|
| **Purpose** | 시각 회귀 테스트 셋업 가이드 (Phase 1 현재는 문서만; Phase 2 에서 자동화) |
| **Reads (specflow)** | — |
| **Reads (registry/config)** | 프로젝트 Storybook·CI 설정 |
| **Writes** | 셋업 가이드 MD (Chromatic / Percy) |
| **Storage Tier** | N/A |
| **Depends on** | — |
| **Notes** | `disable-model-invocation: true`. Phase 2 계획: Playwright headless + Figma API capture + pixel diff. |

### extract-figma

| 항목 | 내용 |
|---|---|
| **Purpose** | Figma 디자인 추출 (layout·colors·typography·effects) 정규화·노이즈 제거 |
| **Reads (specflow)** | — (Figma URL / node ID 인자) |
| **Reads (registry/config)** | Figma MCP (디자인 데이터), `frontend.md` (맥락) |
| **Writes** | 정규화된 Figma YAML(`~/.hbrness/figma/{fileKey}/{nodeId}.yaml`) — layout·style·text·축약 노드 트리 |
| **Storage Tier** | Tier 1 (`~/.hbrness/figma/...`) |
| **Depends on** | — (유틸; F3/F4 에서 호출) |
| **Notes** | `disable-model-invocation: true`. Figma MCP 필요(없으면 Dev Mode 수동). layoutMode→flex / itemSpacing→gap / padding / alignment / fills→color / effects→shadow / corner radius 매핑. 단일 컴포넌트·frame 스코프. |

### patch-frontend

| 항목 | 내용 |
|---|---|
| **Purpose** | validate-* 피드백을 최소 수정으로 반영 |
| **Reads (specflow)** | — |
| **Reads (registry/config)** | validate-* findings YAML |
| **Writes** | 대상 소스 파일(Edit only), change log YAML |
| **Storage Tier** | N/A — project code 수정 |
| **Depends on** | validate-code / validate-visual / validate-a11y |
| **Notes** | spacing·color 토큰 변경 등 미세 수정. Props 변경 시 Storybook args 동기화. 컴포넌트 간 변경 금지. |

### reimpl-frontend

| 항목 | 내용 |
|---|---|
| **Purpose** | 구조적 문제(layout mode·Props interface·wrapper 필요·regression) 재구현 |
| **Reads (specflow)** | — |
| **Reads (registry/config)** | validate-* findings, `.frontflow/component-registry.md`, Figma(있으면) |
| **Writes** | 컴포넌트·페이지 재구현 + 테스트 업데이트 + change log(preserved: types/Storybook, rewritten: JSX/styling) |
| **Storage Tier** | N/A — project code 재작성 |
| **Depends on** | patch-frontend + regression 감지 |
| **Notes** | 선택적 보존(타입·Storybook 구조는 유지, JSX·스타일만 재작성). upstream import Grep 필수. 재구현 후 validate-code 재실행. |

## specflow 섹션 → 스킬 역매핑

| specflow 출력 섹션 | 소비하는 frontflow 스킬 |
|---|---|
| FS §비즈니스 룰(BR) | impl-interactions (조건부 렌더, form validation) |
| UI §디자인 토큰 | impl-tokens |
| UI §컴포넌트 명세(atoms) | impl-atoms |
| UI §컴포넌트 명세(composites) | impl-composites |
| UI §인터랙션·애니메이션 | impl-interactions |
| UI §반응형·breakpoints | impl-pages |
| UI §접근성 요구사항 | validate-a11y |
| UI §컴포넌트 시각 명세 | validate-visual |
| UI §컴포넌트 상태 | generate-stories |
| UI §에러 UI 플로우 힌트 | **impl-error-handling** (ui_flow 컬럼 부재 시 참고) |
| WF §화면 전환·레이아웃 | impl-pages |
| WF §상태 매트릭스 | impl-atoms, impl-interactions |
| TS §API 설계 | **sync-api-client** (codegen), impl-api-integration (wiring) |
| TS §API 응답 스키마 | impl-composites (Props), **sync-api-client** (types codegen), impl-api-integration (wiring) |
| TS §상태 enum | impl-interactions |
| TS §에러 코드 맵 | **impl-error-handling**, impl-api-integration (handleError import), generate-tests |
| TS §4 에러 코드 맵 | **impl-tracking [Phase A]** (error_shown.error_code property 검증) |
| FS §7 이벤트 트래킹 | **impl-tracking** |
| PLAN-*-tasks.md (decompose) | map-tasks |

> **Phase 1 로드맵 영향**: `docs/plugin-gaps-and-plan.md` §3.3 (3) 에서 `impl-api-integration` 이 `backflow:export-api-contract` + `frontflow:sync-api-client` 로 분리 예정. §3.7 의 FS "이벤트 트래킹 테이블" 이 추가되면 신설 `impl-tracking` 행이 이 표에 추가된다. 에러 핸들링 관련 행은 이미 반영(Phase 1 (1) 완료). `impl-api-integration` 은 다음 커밋에서 `impl-error-handling` 의 `handleError` 를 import 하도록 SKILL 문서 정리 필요.

## 신규 frontflow 스킬 추가 체크리스트

- [ ] Purpose 한 문장
- [ ] Reads (specflow): 섹션 이름까지 구체적으로
- [ ] Reads (registry/config): `frontend.md` 어느 키를 보는지 명시
- [ ] Writes: 실제 경로·파일 네이밍 패턴
- [ ] Storage Tier: AUTHORING.md 규약과 일치
- [ ] Depends on: 선행 스킬
- [ ] specflow 섹션 → 스킬 역매핑 표 갱신
