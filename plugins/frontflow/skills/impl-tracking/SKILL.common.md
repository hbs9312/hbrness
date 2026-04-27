---
name: impl-tracking
description: FS §7 이벤트 트래킹 → 이벤트 상수·어댑터·컴포넌트 hook codemod. "이벤트 트래킹", "GA 이벤트", "Amplitude" 요청 시 사용.
argument-hint: [기능 명세서 경로] [--phase=generate|codemod] [--proposal-only|--apply]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
model: sonnet
---

# 이벤트 트래킹 구현 (F-TRACK)

ultrathink

당신은 프론트엔드 분석/트래킹 엔지니어입니다.
FS §7 이벤트 트래킹 표를 source of truth 로 읽어 이벤트 상수·어댑터·컴포넌트 hook 을 생성·삽입합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [frontend.md](../../context/frontend.md) — `tracking.*` 섹션 **필수**
- **태스크-파일 맵**: `.frontflow/task-file-map.md` (있으면)
- **컴포넌트 레지스트리**: `.frontflow/component-registry.md`

## 입력

1. **FS §7 이벤트 트래킹** (필수) — `specs/FS-*.md` §7 표
2. **UI 명세서** (선택) — where 컬럼 → 실 컴포넌트 경로 매핑
3. **TS §4 에러 코드 맵** (선택) — `error_shown.error_code` 검증용
4. **인자 override**: `$ARGUMENTS` 로 직접 FS 경로 지정 가능

### Grace 모드 — FS §7 부재

FS §7 이 미작성된 프로젝트(grace period)에서는 다음 default 동작:

**Phase A (generate)**:
- events.ts 에 default 이벤트 3종 정의: `PAGE_VIEW`, `NAV_CLICK`, `ERROR_SHOWN`
- 각 이벤트의 properties 타입은 최소 (`page_view`: `{ path: string }`, `nav_click`: `{ from_path: string, to_path: string }`, `error_shown`: `{ error_code: string, ui_flow: string }`)
- track.ts / adapters / selected-adapter.ts 는 정상 생성

**Phase B (codemod)**:
- proposal 출력만 제한적으로 (default 3종에 대한 위치 추정)
- `--apply` 시에도 사용자 confirm 필수 (FS 가 ground truth 이므로 위험)

Grace 모드 진입 시 SKILL 출력 첫 줄에 명시: `[grace mode] FS §7 미작성 — default 3 events 사용`. 사용자가 §7 작성 후 재실행 시 grace 해제.

## ★ 실행 위치 (Phase 분리 — XR-005) ★

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

## ★ Phase A — generate (default) ★

### 생성 파일

| 파일 | 항상 생성 | 조건 |
|---|---|---|
| `src/tracking/events.ts` | O | — |
| `src/tracking/track.ts` | O | — |
| `src/tracking/index.ts` | O | — |
| `src/tracking/adapters/types.ts` | O | vendor 무관 항상 생성 (XR-002) |
| `src/tracking/adapters/console.ts` | O | vendor 무관 항상 생성 (XR-002) |
| `src/tracking/selected-adapter.ts` | O | vendor="" 시 console export, vendor 명시 시 vendor export |
| `src/tracking/adapters/{vendor}.ts` | — | vendor != "" 시만 생성 |
| `.env.example` | — | vendor_token_env 값 추가 |

경로는 `frontend.md.tracking.*` 설정을 따름.

### 어댑터 인터페이스 (XR-002 — 항상 생성)

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

### selected-adapter.ts (XR-007 — build-time static export)

```typescript
// src/tracking/selected-adapter.ts (AUTO-GENERATED — vendor 별 분기)
// vendor: "" 모드:
export { consoleAdapter as vendorAdapter } from './adapters/console';

// vendor: "ga4" 모드:
// export { ga4Adapter as vendorAdapter } from './adapters/ga4';
```

`vendorAdapter` import 가 build-time 에 fix 되므로 미선택 vendor 의 어댑터 파일은 tree-shake 로 번들 제외.

### 공통 API — vendor 식별자 0건 (XR-003)

```typescript
// src/tracking/track.ts (AUTO-GENERATED — vendor 식별자 금지)
import type { TrackAdapter } from './adapters/types';
import { vendorAdapter } from './selected-adapter';
import { consoleAdapter } from './adapters/console';

const PII_KEYS = new Set(['email', 'phone', 'ssn', 'card_number', 'password', 'user_id']);

// **fs-rules 19 / validate-code §10.1 와 동일한 정규화 규칙 사용** — lowercase + camelCase→snake_case + kebab-case→snake_case + nested 마지막 segment. PII set 은 frontend.md.tracking.pii_redact 의 값
function normalizeKey(k: string): string {
  const last = k.split('.').pop() ?? k;
  const snakeFromCamel = last.replace(/([a-z])([A-Z])/g, '$1_$2');
  const snakeFromKebab = snakeFromCamel.replace(/-/g, '_');
  return snakeFromKebab.toLowerCase();
}

function redactPII(props: Record<string, unknown> = {}) {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(props)) {
    out[k] = PII_KEYS.has(normalizeKey(k)) ? '[REDACTED]' : v;
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

### PII redaction 파싱 규칙 (XR-006 / XR-001 통일)

properties 컬럼 파싱 — **fs-rules 19 / validate-code §10.1 와 동일한 정규화 규칙**:
1. `,` 로 split → trim
2. 각 항목에서 `?` suffix 제거 (optional 마커)
3. `:` 가 있으면 그 뒤를 타입으로 제거
4. **lowercase** 변환
5. camelCase → snake_case (예: `userId` → `user_id`)
6. kebab-case → snake_case (예: `card-number` → `card_number`)
7. nested key (`contact.email`): 마지막 segment 까지 PII 검사 대상 (정규화 후 매칭)

PII set: `email / phone / ssn / card_number / password / user_id` — frontend.md.tracking.pii_redact 단일 source.

### default_properties resolver (XR-010)

`frontend.md.tracking.default_properties` 의 값 형식:
- `env:VAR_NAME` → `process.env.VAR_NAME`
- `navigator.X` → `navigator.X` (런타임)
- `const:literal` → 리터럴 값

## ★ Phase B — codemod ★

`impl-interactions` / `impl-api-integration` 완성 후 실행.

기본 모드 `--proposal-only` (dry-run 텍스트 출력). 실제 파일 수정은 `--apply` 또는 사용자 확인 후만 (XR-004).

### codemod 모드 우선순위 (높을수록 우선)

1. **CLI 인자** (`--proposal-only` / `--apply` / `--interactive`) — 명시 시 frontend.md 무시
2. **사용자 인터랙션 confirm** — interactive 모드에서 각 변경마다 사용자 답변
3. **frontend.md.tracking.codemod_mode** — 프로젝트 default
4. **`proposal-only` fallback** — frontend.md 미설정 시

### codemod proposal 출력 예시

```markdown
# Tracking Codemod Proposal — {날짜}

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

## 벤더 식별자 0건 원칙 (XR-003)

**금지 영역 (벤더 식별자 0건)**: `components/` / `pages/` / `hooks/` / `api/` 및 공통 tracking 파일(`track.ts`, `events.ts`, `index.ts`)
- gtag / amplitude / mixpanel / posthog / dd-trace / Sentry 등 벤더 식별자 금지
- `track()` API 사용

**예외**:
- `adapters/*` 디렉토리 내부: vendor 식별자 자유롭게 사용 가능 (벤더 SDK 호출이 격리되는 곳)
- `selected-adapter.ts`: **선택 vendor 1종의 static import/export 형태에 한해** vendor 식별자 허용
  (예: `export { ga4Adapter as vendorAdapter } from './adapters/ga4'`).
  이외 형태(런타임 분기, 다중 vendor) 는 금지. §10.3 의 `selected_adapter_static_export_only` 룰로만 검사.

## 마이그레이션 시나리오

### Scenario A — 신규 프로젝트
- FS §7 작성됨 → Phase A 실행 → events/track/adapters 생성
- impl-interactions/api-integration 후 → Phase B `--proposal-only` 실행 → 사용자 검토 후 `--apply`

### Scenario B — 벤더 SDK 직접 호출 산재
1. Phase A `--dry-run` 으로 grep: `gtag(`, `amplitude.track`, `mixpanel.track`, `posthog.capture`
2. 위치별 codemod 후보 표 (제안 `track(...)` + 추정 event_name + confidence)
3. 사용자 승인 후 위치별 Edit (각 변경 시 사용자 확인)
4. 기존 vendor SDK import 는 보존 (gradual migration) — 후속 PR 에서 제거 권장

### Scenario C — 기존 events.ts 가 있음
1. `frontend.md.tracking.events_file` 을 기존 경로로
2. Phase A 가 기존 상수 보존 + FS §7 신규만 append
3. 기존 events.ts 에만 있고 FS §7 에 없는 이벤트 → FS 추가 권고 (skill 이 FS 수정 안 함)

## 멱등성

- 모든 generated 파일 상단 `// AUTO-GENERATED` 주석
- 재실행 시 기존 파일 비교 → 변동 없으면 no-op
- `--force` 인자 시 강제 재생성

## 품질 자가 점검

- [ ] events.ts 에 `// AUTO-GENERATED` 주석 존재
- [ ] adapters/types.ts + adapters/console.ts 항상 생성 (vendor="" 여부 무관)
- [ ] selected-adapter.ts 의 export 가 frontend.md.tracking.vendor 와 일치
- [ ] vendor != "" 시 adapters/{vendor}.ts 생성
- [ ] components / pages / hooks / api / track.ts / events.ts / index.ts 에 vendor 식별자 0건
- [ ] adapters/* 내부는 vendor 식별자 검사 제외
- [ ] Phase B 기본 모드가 --proposal-only (실 파일 수정 없음)
- [ ] codemod 실패 시나리오 6종 발생 시 edit 차단 + proposal 텍스트만 출력
