# Phase 1 (4) — 이벤트 트래킹 Skill 설계

> **Generated**: 2026-04-27
> **Scope**: Phase 1 네 번째 항목 — `frontflow:impl-tracking` 신설 + `specflow:generate-fs` 에 `§7 이벤트 트래킹` 부속섹션 의무화 + `frontflow:validate-code` §10 drift 룰
> **Parent roadmap**: `docs/plugin-gaps-and-plan.md` §3.3 (4), §3.7
> **Companion designs**: `phase-1-error-contract.md` (1), `phase-1-observability.md` (2), `phase-1-api-sync.md` (3)
>
> **Revision (2026-04-27, Task 0 codex review — 10 findings, 3 critical · 6 warning · 1 info)**:
> - **XR-001 (critical)**: `error_shown` hook 은 `handler.ts` **외부에서만** 호출. handler.ts 의 순수 함수 원칙(Phase 1 (1)) 유지. hook 위치는 `presentError` wrapper / `impl-interactions` / `impl-api-integration` 의 에러 presentation 지점.
> - **XR-002 (critical)**: `src/tracking/adapters/types.ts` + `src/tracking/adapters/console.ts` 는 **항상 생성**. vendor 별 어댑터(`ga4.ts` 등) 만 vendor 명시 시 조건부 생성. `vendor: ""` 모드에서도 import 깨지지 않음.
> - **XR-003 (critical)**: "벤더 식별자 0건" 원칙을 좁힘 — **컴포넌트 + 공통 tracking API (`track.ts`, `events.ts`, hook 호출 라인)** 에 0건. `adapters/{vendor}.ts` 파일 내부는 예외. validate-code §10 drift 룰도 adapter 디렉토리는 vendor 식별자 검사에서 제외.
> - **XR-004 (warning)**: hook 삽입 모드 명시 — **default = `--proposal-only` (dry-run 텍스트 출력)**. 실제 파일 수정은 `--apply` 옵션 또는 사용자 확인 후만.
> - **XR-005 (warning)**: 단일 skill 안 두 phase 로 분리 — Phase A (generate: events/track/adapters/selected-adapter, sync-api-client 후 실행) + Phase B (codemod: hook 삽입 proposal, impl-interactions/api-integration 후 실행). Depends on 모순 해소.
> - **XR-006 (warning)**: properties 컬럼 파싱 규칙 명시 — comma split → trim → `?` suffix 제거 → `:` 뒤 타입 제거 → 정규화 → nested key (`contact.email`) 의 마지막 segment 까지 PII 검사.
> - **XR-007 (warning)**: tree-shake 메커니즘 구체화 — `selected-adapter.ts` 가 vendor 1종만 static `export { ga4Adapter as vendorAdapter } from './adapters/ga4'` 형태로 빌드 타임에 fix.
> - **XR-008 (warning)**: codemod 실패 시나리오 명시 — confidence threshold, ambiguous handler 다중 후보, 컴포넌트 미발견, alias 충돌, barrel 부재 시 edit 금지 + proposal 만.
> - **XR-009 (warning)**: validate-code §10 룰을 4개로 분리 (FS↔events 양방향 / callsite literal / vendor↔adapter 일치 / adapter 디렉토리 예외).
> - **XR-010 (info)**: `default_properties` resolver 형식 명시 — `{ app_version: 'env:NEXT_PUBLIC_APP_VERSION', locale: 'navigator.language' }`.

## 목표

Frontend 사용자 이벤트를 **벤더-중립 추상**으로 정의·구현·검증한다. 기획자가 FS 에 적은 "버튼 클릭 추적" 같은 자연어를 **이벤트 상수 + 컴포넌트 hook proposal** 로 변환하고, 변경 시 코드와 명세 사이의 drift 를 잡는다. 벤더(GA4 / Amplitude / Mixpanel / PostHog) 는 어댑터 디렉토리로 격리해 컴포넌트·공통 tracking API 출력에 벤더명 0건 (어댑터 디렉토리 내부는 예외).

### Non-goals

- Backend 측 트래킹·로깅 — Phase 1 (2) Observability 범위
- 비즈니스 KPI metrics 집계 — backend `impl-services` 또는 별도 metrics 파이프
- 동의 관리(GDPR consent banner) — Phase 2 (`frontflow:impl-consent`)
- A/B 테스트 분기 — Phase 2 (`impl-feature-flags` 와 통합)
- Server-side event ingestion — Phase 2
- 익명 ID·세션 ID 관리 — vendor SDK 내장
- 이벤트 properties 의 런타임 schema 검증 — Phase 2 (zod/valibot)

## 1. FS 포맷 변경 — `§7 이벤트 트래킹` 부속섹션 의무화

### 섹션 포맷

```markdown
# 7. 이벤트 트래킹

| event_name | when (trigger) | where (UI 요소) | properties | related |
|---|---|---|---|---|
| signup_submitted | 회원가입 폼 submit 직후 (검증 통과) | SignupForm.tsx onSubmit | method: string, plan: string, referral_source?: string | US-001, AC-003 |
| speaker_enrolled | 화자 등록 성공 응답 수신 | SpeakerEnrollPage useEnroll onSuccess | speaker_id: string, name_length: number, audio_duration_sec: number | US-005, AC-009 |
| nav_click | 네비게이션 메뉴 클릭 | Header.tsx, SideNav.tsx 의 NavItem onClick | from_path: string, to_path: string, item_id: string | (전역) |
| error_shown | 에러 메시지 사용자 노출 (handleError 호출자가 결과 받은 직후) | presentError wrapper / impl-interactions / impl-api-integration 의 onError | error_code: string, ui_flow: string | TS §4 모든 code |
```

### 섹션 규약

| 필드 | 필수 | 규칙 |
|---|---|---|
| `event_name` | required | `snake_case`, 동사_과거형 또는 `noun_verbed`. 전역 유일. 예약어: `page_view`, `error_shown`, `nav_click` 은 어댑터 default 제공 |
| `when (trigger)` | required | "X 직후", "Y 수신 시", "Z 노출" — 시점이 코드 위치로 변환 가능해야 함 |
| `where (UI 요소)` | required | **컴포넌트 파일명(.tsx) + 함수/handler 명**. impl-tracking codemod 의 매칭 대상 |
| `properties` | optional | `key: type` 또는 `key?: type` 콤마 구분 (예: `id: string, count?: number`). **타입 미작성 가능** (`id, count?` — Phase 1 hint) |
| `related` | optional | US/AC/BR 또는 TS 섹션 참조. "(전역)" 은 글로벌 이벤트 |

### error_shown 의 hook 위치 (XR-001 명시)

`error_shown` 이벤트의 `where` 컬럼은 **`handler.ts` 가 아닌 호출자** 를 가리켜야 한다. handler.ts (Phase 1 (1)) 는 순수 함수로 유지 — `track()` 호출 금지.

권장 위치 우선순위:
1. **`presentError` wrapper** (있으면): `handleError(raw)` → ErrorDecision 받은 직후, presentError 로 넘기기 직전
2. **`impl-interactions`** 의 mutation `onError` 콜백
3. **`impl-api-integration`** 의 client.ts response interceptor

handler.ts 자체에 hook 을 넣으면 validate-code §10 룰이 critical 로 차단.

### properties 파싱 규칙 (XR-006 명시)

fs-rules / impl-tracking 에서 properties 컬럼 파싱:
1. `,` 로 split → trim
2. 각 항목에서 `?` suffix 제거 (optional 마커 — 의미는 보존)
3. `:` 가 있으면 그 뒤를 타입 (`string`/`number`/`boolean`/`object`/`array`/freeform) 으로 제거
4. 키 정규화: `camelCase`, `snake_case`, `kebab-case` 모두 허용
5. nested key (`contact.email`): 마지막 segment 까지 PII 검사 대상

### `specflow:generate-fs` 변경

- 프롬프트에 "§7 이벤트 트래킹 표 반드시 포함. PRD 의 "기록", "분석", "추적", "이벤트", "GA", "Amplitude" 키워드를 흡수해 초안 5~10행" 추가
- 자가 점검 체크리스트:
  - "§7 이벤트 트래킹 섹션 존재"
  - "모든 event_name snake_case + 전역 유일"
  - "where 컬럼이 컴포넌트 파일명 + handler 까지 명시 (모호 표현 0건)"
  - "PII 키 (`email`, `phone`, `ssn`, `card_number`, `password`, `user_id`) 가 properties 에 직접 등장하지 않음"
  - "error_shown 의 where 컬럼이 handler.ts 가 아닌 호출자 지점"

### `fs-rules.md` 신규 룰 (warning grace)

```markdown
## 이벤트 트래킹 (warning — v1.x grace period)
15. §7 이벤트 트래킹 섹션 존재 — 누락 시 warning + skill 은 page_view / nav_click / error_shown 3종 default 로 동작
16. event_name snake_case + 전역 유일 — 위반 시 warning
17. event_name 예약어 충돌 — `page_view` / `nav_click` / `error_shown` 을 다른 의미로 재정의 시 warning
18. when (trigger) 가 모호 표현("적절히", "필요시") 포함 — warning
19. properties 에 PII 키 검출 — comma-split + nested-segment 파싱 후 `email`/`phone`/`ssn`/`card_number`/`password`/`user_id` 매칭 → warning
20. error_shown 이벤트가 정의되면 properties 에 `error_code` 필수 — 누락 시 warning (Phase 1 (1) ErrorCode 연계)
21. error_shown 의 where 컬럼이 `handler.ts` / `errors/handler` 를 가리키면 → warning ("순수 함수 원칙 위반 — 호출자로 이동")
```

## 2. `frontflow:impl-tracking` 스킬 계약

### 카드

| 항목 | 내용 |
|---|---|
| **Purpose** | FS §7 → 이벤트 상수 + 어댑터 디렉토리 + (옵션) 컴포넌트 hook 삽입 proposal/codemod |
| **Reads (specflow)** | `specs/FS/*` §7 (필수), `specs/UI/*` (where 컬럼 → 실 컴포넌트 경로 매칭), `specs/TS/*` §4 (`error_shown.error_code` 검증) |
| **Reads (registry/config)** | `.frontflow/task-file-map.md`(있으면), `.frontflow/component-registry.md`, `frontend.md` (`tracking.*` 섹션 신설) |
| **Writes (Phase A — generate, 항상)** | `src/tracking/events.ts` (이벤트 상수 + properties 타입), `src/tracking/track.ts` (공통 API), `src/tracking/index.ts` (barrel — `track`, `TrackEvent` re-export), `src/tracking/adapters/types.ts` (TrackAdapter 인터페이스), `src/tracking/adapters/console.ts` (console fallback adapter — **항상 생성**), `src/tracking/selected-adapter.ts` (vendor 1종 static export — vendor 명시 시 vendor adapter, 빈 값 시 console adapter), `src/tracking/adapters/{vendor}.ts` (vendor 명시 시만), `.env.example` 업데이트 |
| **Writes (Phase B — codemod, 옵션)** | 컴포넌트 파일에 hook 삽입 proposal (default `--proposal-only`) 또는 실제 Edit (`--apply` 또는 사용자 확인) |
| **Storage Tier** | N/A — project code |
| **Depends on (Phase A)** | `map-tasks`, `sync-api-client` (Phase 1 (3)) — events 정의는 API 와 무관하지만 같은 frontend codegen 단계로 묶음 |
| **Depends on (Phase B)** | `impl-interactions`, `impl-api-integration` — hook 삽입 대상 컴포넌트가 완성된 후 |
| **Notes** | 컴포넌트·공통 tracking API 에 vendor 식별자 0건 (`adapters/{vendor}.ts` 만 예외). selected-adapter.ts 가 build-time static import 로 tree-shake 보장. AUTO-GENERATED 멱등성 |

### 실행 위치 (XR-005 분리)

```
sync-api-client           ← Phase 1 (3)
       │
       ▼
impl-tracking [Phase A]   ★ generate: events/track/adapters/selected-adapter
       │
       ▼
impl-interactions         ← FS BR + UI 인터랙션 + WF 상태 매트릭스
       │
       ▼
impl-api-integration      ← TS §API
       │
       ▼
impl-tracking [Phase B]   ★ codemod: hook 삽입 proposal (default) / apply
       │
       ▼
validate-{code,visual,a11y}
```

Phase A 와 Phase B 는 **동일 skill 의 두 인자 모드**:
- `--phase=generate` (default — 처음 실행 시): events/track/adapters 생성. 컴포넌트 코드 미수정
- `--phase=codemod` (후속 실행): 컴포넌트 hook 삽입. 기본 `--proposal-only` (dry-run 텍스트). `--apply` 시 실제 Edit

### `frontend.md` 신규 키

```yaml
tracking:
  vendor: ""                    # "" (console only) | ga4 | amplitude | mixpanel | posthog
  events_file: "src/tracking/events.ts"
  track_module: "src/tracking/track.ts"
  index_file: "src/tracking/index.ts"
  adapters_dir: "src/tracking/adapters"
  selected_adapter_file: "src/tracking/selected-adapter.ts"
  enabled_env: "NEXT_PUBLIC_TRACKING_ENABLED"
  consent_gate: false           # true: track() 이 user consent 확인 후 send (Phase 2 consent)
  default_properties:           # XR-010: resolver 형식
    app_version: "env:NEXT_PUBLIC_APP_VERSION"
    locale: "navigator.language"
    # 지원 resolver:
    #   env:VAR_NAME           → process.env.VAR_NAME
    #   navigator.X            → navigator.X (런타임)
    #   const:literal          → 리터럴 값
  pii_redact: ["email", "phone", "ssn", "card_number", "password", "user_id"]
  vendor_token_env: ""          # 예: NEXT_PUBLIC_GA4_MEASUREMENT_ID
  codemod_mode: "proposal-only" # proposal-only (default) | apply | interactive
```

### 어댑터 인터페이스 (XR-002 — types.ts/console.ts 항상 생성)

```typescript
// src/tracking/adapters/types.ts (AUTO-GENERATED — 항상 생성)
export interface TrackAdapter {
  init(): Promise<void> | void;
  track(event: string, props?: Record<string, unknown>): void;
  identify?(userId: string, traits?: Record<string, unknown>): void;
}
```

```typescript
// src/tracking/adapters/console.ts (AUTO-GENERATED — 항상 생성)
import type { TrackAdapter } from './types';
export const consoleAdapter: TrackAdapter = {
  init() {},
  track(event, props) {
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.debug('[track]', event, props);
    }
  },
};
```

```typescript
// src/tracking/selected-adapter.ts (AUTO-GENERATED — vendor 별 분기)
// vendor: "" 모드:
export { consoleAdapter as vendorAdapter } from './adapters/console';

// vendor: "ga4" 모드:
// export { ga4Adapter as vendorAdapter } from './adapters/ga4';
```

`vendorAdapter` import 가 build-time 에 fix 되므로 미선택 vendor 의 어댑터 파일은 tree-shake 로 번들 제외 (XR-007).

### 공통 API (XR-003 — vendor 식별자 0건 영역)

```typescript
// src/tracking/track.ts (AUTO-GENERATED — vendor 식별자 금지)
import type { TrackAdapter } from './adapters/types';
import { vendorAdapter } from './selected-adapter';
import { consoleAdapter } from './adapters/console';

const PII_KEYS = new Set(['email', 'phone', 'ssn', 'card_number', 'password', 'user_id']);

function redactPII(props: Record<string, unknown> = {}) {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(props)) {
    const last = k.split('.').pop()!;
    out[k] = PII_KEYS.has(last) ? '[REDACTED]' : v;
  }
  return out;
}

function getDefaultTrackingProperties(): Record<string, unknown> {
  // resolver 처리 (XR-010): env:* / navigator.* / const:*
  return {
    app_version: process.env.NEXT_PUBLIC_APP_VERSION,
    locale: typeof navigator !== 'undefined' ? navigator.language : undefined,
  };
}

const enabled = process.env.NEXT_PUBLIC_TRACKING_ENABLED === 'true';
const tracker: TrackAdapter = enabled ? vendorAdapter : consoleAdapter;
tracker.init();

export function track(event: string, props?: Record<string, unknown>) {
  tracker.track(event, redactPII({ ...getDefaultTrackingProperties(), ...props }));
}

export function identify(userId: string, traits?: Record<string, unknown>) {
  tracker.identify?.(userId, traits);
}
```

```typescript
// src/tracking/index.ts (AUTO-GENERATED — barrel)
export { track, identify } from './track';
export { TrackEvent } from './events';
export type { TrackEventName, TrackProps } from './events';
```

### 컴포넌트 hook codemod (Phase B — XR-004, XR-008)

기본 모드 `--proposal-only` 출력 예시:

```markdown
# Tracking Codemod Proposal — 2026-04-27 14:33

## SignupForm.tsx — confidence: high
- Insert: import { track, TrackEvent } from '@/tracking';
- Insert at line 42 (inside onSubmit, after mutateAsync):
  + track(TrackEvent.SIGNUP_SUBMITTED, {
  +   method: data.method,
  +   plan: data.plan,
  +   referral_source: data.referralSource,
  + });

## Header.tsx + SideNav.tsx — confidence: medium (multiple candidates)
- nav_click 의 where 컬럼이 두 파일을 가리킴
- 각 파일의 NavItem onClick 핸들러 후보:
  - Header.tsx: handleNavClick (line 23) — 매칭 가능
  - SideNav.tsx: NavItem onClick prop (line 56) — 매칭 가능
- Action: 사용자가 둘 다 적용할지, 일부만 적용할지 선택 (--apply 시 양쪽 모두)

## error_shown — confidence: high (skipped)
- where 컬럼이 'presentError wrapper' 를 가리킴
- presentError 가 src/errors/ui-flow.tsx 에 존재 (확인됨)
- Action: ui-flow.tsx 의 presentError 함수 끝에 track 삽입
- 단, --apply 시에만 실 수정. proposal-only 는 dry-run 텍스트만
```

### Codemod 실패 시나리오 (XR-008 — edit 금지 + proposal 만)

다음 경우 실제 파일 수정 차단:
1. **컴포넌트 미발견**: where 컬럼의 파일이 component-registry 에 없음
2. **Handler 다중 후보**: where 가 모호해 후보가 2개 이상이고 confidence < threshold
3. **Alias 충돌**: `import { track } from '@/tracking'` 시 기존 동명 import 존재
4. **Barrel 부재**: `@/tracking/index.ts` 미생성 (Phase A 미실행)
5. **이미 hook 존재**: 같은 event_name 의 track 호출이 이미 있음 (idempotent skip + info)
6. **Confidence threshold**: high (단일 명확 위치) / medium (다중 후보 또는 함수 추정) / low (애매) — medium/low 는 `--apply` 시에도 사용자 individual confirm

## 3. 동기화 메커니즘 — FS as source of truth

```
specs/FS/*.md §7 ──────► (source of truth)
                              │
                              ▼
                      impl-tracking [Phase A]
                              │
                              ▼
                  src/tracking/events.ts
                  src/tracking/track.ts
                  src/tracking/index.ts
                  src/tracking/adapters/types.ts
                  src/tracking/adapters/console.ts
                  src/tracking/adapters/{vendor}.ts (vendor 시)
                  src/tracking/selected-adapter.ts
                              │
                              │ (after impl-interactions / api-integration)
                              ▼
                      impl-tracking [Phase B]
                              │
                              ▼
                  컴포넌트 파일에 track() 호출 라인
                              │
                              ▼
                      validate-code §10 (drift, 4룰)
```

### 기각한 대안

| 대안 | 기각 이유 |
|---|---|
| **(a) 벤더 SDK 직접 호출** | 벤더 종속. 어댑터 패턴이 표준 |
| **(b) 자동 컴포넌트 변경 (proposal 없이)** | 의도하지 않은 hook 삽입 위험. proposal-only default + apply opt-in |
| **(c) Server-side event ingestion** | Phase 1 (2) Observability 와 책임 중복. Phase 2 |
| **(d) Event schema 강제 (zod)** | 빌드 사이즈 부담. Phase 2 |
| **(e) handler.ts 안에 track() 호출** | Phase 1 (1) 순수 함수 원칙 위반 (XR-001) |
| **(f) Runtime vendor switch** | tree-shake 불가. selected-adapter 의 build-time static import 가 표준 (XR-007) |

## 4. 마이그레이션

### 4.1 Scenario A — 신규 프로젝트
- FS §7 작성됨 → Phase A 실행 → events/track/adapters 생성
- impl-interactions/api-integration 후 → Phase B `--proposal-only` 실행 → 사용자 검토 후 `--apply`

### 4.2 Scenario B — 벤더 SDK 직접 호출 산재
1. Phase A `--dry-run` 으로 grep: `gtag(`, `amplitude.track`, `mixpanel.track`, `posthog.capture`
2. 위치별 codemod 후보 표 (제안 `track(...)` + 추정 event_name + confidence)
3. 사용자 승인 후 위치별 Edit (각 변경 시 사용자 확인)
4. 기존 vendor SDK import 는 보존 (gradual migration) — 후속 PR 에서 제거 권장

### 4.3 Scenario C — 기존 events.ts 가 있음
1. `frontend.md.tracking.events_file` 을 기존 경로로
2. Phase A 가 기존 상수 보존 + FS §7 신규만 append
3. 기존 events.ts 에만 있고 FS §7 에 없는 이벤트 → FS 추가 권고 (skill 이 FS 수정 안 함)

## 5. CONTRACTS.md 갱신

- `plugins/frontflow/CONTRACTS.md`
  - 실행 순서: `sync-api-client` → **`impl-tracking [Phase A]`** → `impl-interactions` → `impl-api-integration` → **`impl-tracking [Phase B]`** → `validate-*`
  - 스킬별 계약 카드 (Phase A / Phase B 분리 명시)
  - 공통 레지스트리: `frontend.md.tracking.*`
  - specflow 역매핑: `FS §7 → impl-tracking`, `TS §4 → impl-tracking [Phase A] (error_shown 의 error_code property 검증용)`
- `plugins/specflow/skills/validate/rules/fs-rules.md` 신규 룰 15~21

## 6. validate-code §10 drift 룰 (XR-009 — 4 sub-rule)

```yaml
입력:
  fs_section: specs/FS-*.md §7 이벤트 트래킹
  events_file: frontend.md.tracking.events_file
  adapters_dir: frontend.md.tracking.adapters_dir
  vendor: frontend.md.tracking.vendor
  component_files: frontend.md.structure.component_dir + page_dir
  selected_adapter_file: frontend.md.tracking.selected_adapter_file

§10.1 — FS ↔ events.ts 양방향:
  missing_in_code:
    - FS §7 의 event_name 이 events.ts TrackEvent 에 없음 → critical
  orphan_in_code:
    - events.ts TrackEvent 의 키 가 FS §7 어디에도 없음 → critical
  properties_mismatch:
    - TrackProps 의 키 집합 ≠ FS §7 의 properties 컬럼 → warning (Phase 1 hint)

§10.2 — Callsite event literal 금지:
  literal_event_in_components:
    - 컴포넌트 / page 파일에서 `track('literal_string', ...)` 같은 string literal 호출 → critical
    - 권고: `track(TrackEvent.X, ...)` enum 사용
    - 예외: tracking/ 디렉토리 내부의 default 이벤트 (page_view 등) 정의 라인은 허용
  unknown_event_call:
    - `track(TrackEvent.UNKNOWN_X, ...)` 처럼 events.ts 에 없는 키 사용 → critical (TS 타입 에러로 잡히지만 명시)

§10.3 — vendor 설정 ↔ adapter 파일 일치:
  selected_adapter_match:
    - frontend.md.tracking.vendor != "" 이면 adapters/{vendor}.ts 존재 → 부재 시 critical
    - selected-adapter.ts 의 export 가 vendor 와 일치 → 불일치 시 critical
  vendor_empty_console:
    - vendor == "" 이면 selected-adapter.ts 가 console adapter 를 export → 그 외 critical
  vendor_token_env:
    - vendor != "" 이고 vendor_token_env 이 frontend.md 에 비어있음 → warning

§10.4 — Adapter 디렉토리 vendor 식별자 예외 (컴포넌트·공통 API 만 검사):
  vendor_identifier_in_components:
    - 컴포넌트 / page / hook / api / 공통 tracking 파일(track.ts, events.ts, index.ts)
      에 `gtag` / `amplitude` / `mixpanel` / `posthog` / `dd-trace` / `Sentry` 등 벤더 식별자 등장 → critical
    - 권고: track() API 사용
  adapter_directory_exempt:
    - adapters_dir 하위 파일(types.ts/console.ts/{vendor}.ts) 은 vendor 식별자 검사에서 제외 + info 메시지
  generated_marker:
    - tracking/ 의 모든 AUTO-GENERATED 파일에 주석 없으면 → warning

예외:
  - FS §7 부재 (grace) + events.ts 가 default 3종(page_view/nav_click/error_shown) 만 → drift 검사 skip + warning
```

## 7. 출력 파일 예시

생략 — §2 의 어댑터 인터페이스 / 공통 API 코드 블록 + Phase B proposal 텍스트가 그대로 출력 예시.

## 8. 오픈 질문 / Future work

- **Event schema enforcement (zod)** — Phase 2
- **Consent management 통합** — Phase 2 `frontflow:impl-consent`
- **Server-side event ingestion** — Phase 2 (`backflow:impl-tracking-relay`)
- **Funnel / cohort 정의** — Phase 2
- **A/B 테스트 분기** — Phase 2 (`impl-feature-flags`)
- **다중 벤더 동시 송신** — Phase 2 (multi-adapter dispatcher)
- **이벤트 sampling** — Phase 2
- **codemod confidence ML scoring** — 휴리스틱 외에 학습 모델 — Phase 3

## 9. 완료 기준 (Definition of Done)

### Phase 1 (4) "ship" 조건

- [ ] `specflow:generate-fs` 가 §7 표 포함해 출력
- [ ] `specflow:validate` fs-rules 15~21 추가
- [ ] `frontflow:impl-tracking [Phase A]` 실행 시 events.ts + track.ts + index.ts + adapters/types.ts + adapters/console.ts + selected-adapter.ts 생성. vendor 명시 시 adapters/{vendor}.ts 추가
- [ ] `frontflow:impl-tracking [Phase B]` `--proposal-only` 가 default. `--apply` 시 컴포넌트 hook 삽입. 실패 시나리오(미발견/모호/충돌) 모두 edit 차단
- [ ] `frontend.md.tracking.*` 신규 키 (vendor / files / enabled_env / consent_gate / default_properties resolver / pii_redact / vendor_token_env / codemod_mode)
- [ ] `frontflow:validate-code` §10 (4 sub-rule) drift 룰 추가
- [ ] `frontflow/CONTRACTS.md` 갱신 (Phase A / Phase B 분리)
- [ ] 최소 1개 실프로젝트 E2E

### "stable" 조건

- 2개 이상 프로젝트 실사용
- vendor 어댑터 최소 2종(ga4 + amplitude) 검증
- fs-rules 15~21 grace → critical 승격
- §10 drift 룰 grace → critical 승격

## 10. 다음 작업

1. **Task A** — `specflow:generate-fs` SKILL + template + fs-rules 15~21
2. **Task B** — `frontflow:impl-tracking` skill 신설 (Phase A + Phase B 두 모드) + `frontend.md.tracking` + `frontflow/CONTRACTS.md`
3. **Task C** — `impl-interactions` / `impl-api-integration` SKILL 에 트래킹 hook 호출 가이드 추가 (small. error_shown 의 호출 위치 명시)
4. **Task D** — `frontflow:validate-code` §10 (4 sub-rule) drift 룰

Phase 1 (4) 전체 4 commit, 1주 소요.
