# Phase 1 (1) — 에러 계약 Skill 설계

> **Generated**: 2026-04-24
> **Scope**: Phase 1 첫 번째 스킬 쌍 `backflow:impl-error-codes` + `frontflow:impl-error-handling` 및 동반되는 `specflow:generate-ts` 포맷 변경
> **Parent roadmap**: `docs/plugin-gaps-and-plan.md` §3.3 (1), §3.7

## 목표

Backend 와 Frontend 가 **같은 에러 코드 문자열 상수**를 참조하도록 자동화한다. 한쪽에서 새 에러 코드를 추가하면 다른 쪽이 자동으로 반영되는 계약 구조를 만드는 게 아니라, **기술 명세서(TS) 한 곳을 원천(source of truth)** 으로 두고 양쪽 skill 이 각자 생성한다.

### Non-goals (이 skill 의 책임이 아님)

- 런타임 에러 발생·throw — `backflow:impl-services` 의 책임
- 에러 로깅·모니터링 — Phase 1 (2) Observability skill 범위
- 에러 발생 시 UI 라우팅·토스트 노출 로직 — `frontflow:impl-interactions` 의 책임 (이 skill 은 "어떤 UI 플로우를 써야 하는지" 룩업 테이블만 생성)
- HTTP 응답 구조(envelope) 표준 — `backflow:impl-middleware` 의 에러 필터 책임

## 1. TS 포맷 변경 — `§에러 코드 맵` 섹션 의무화

`specflow:generate-ts` 출력에 아래 섹션을 **의무화** 한다. 기존 TS 는 이 섹션이 없어도 `specflow:validate` 가 warning 만 내도록 1회 릴리스에서 grace period 를 두고, 다음 마이너 버전부터 error.

### 섹션 포맷

```markdown
## 에러 코드 맵

| domain | code | http_status | i18n_key | message_ko | message_en | retriable |
|---|---|---|---|---|---|---|
| auth | AUTH_INVALID_CREDENTIALS | 401 | errors.auth.invalid_credentials | 아이디 또는 비밀번호가 올바르지 않습니다 | Invalid credentials | false |
| auth | AUTH_TOKEN_EXPIRED | 401 | errors.auth.token_expired | 로그인이 만료되었습니다. 다시 로그인해주세요 | Session expired | false |
| user | USER_NOT_FOUND | 404 | errors.user.not_found | 사용자를 찾을 수 없습니다 | User not found | false |
| order | ORDER_PAYMENT_FAILED | 402 | errors.order.payment_failed | 결제가 실패했습니다. 잠시 후 다시 시도해주세요 | Payment failed | true |
| system | SYSTEM_EXTERNAL_TIMEOUT | 504 | errors.system.external_timeout | 서비스가 일시적으로 원활하지 않습니다 | Service temporarily unavailable | true |
```

### 필드 규약

| 필드 | 타입 | 규칙 |
|---|---|---|
| `domain` | 소문자 `snake_case` | FS 의 도메인 경계와 일치. 새 domain 도입 시 FS §도메인 정의와 교차검증(`specflow:validate`) |
| `code` | `UPPER_SNAKE_CASE`, `{DOMAIN}_{REASON}` | 프로젝트 전역 유일. 도메인 prefix 필수(`USER_NOT_FOUND` ○, `NOT_FOUND` ✗) |
| `http_status` | 숫자, RFC 7231 준수 | 400/401/403/404/409/422/429/500/502/503/504 허용. 그 외는 review 필요 |
| `i18n_key` | 점(`.`) 구분자, `errors.{domain}.{snake}` | frontend i18n 라이브러리(i18next/formatjs/lingui) 공통 포맷 |
| `message_ko`, `message_en` | 자연어 | 사용자 노출용. 기술 용어·내부 상태 금지(예: "DB 연결 실패" ✗ → "서비스가 일시적으로 원활하지 않습니다") |
| `retriable` | `true`/`false` | frontend handler 가 자동 재시도 여부 판단. `false` 면 UI flow 에서 사용자 조치 유도 |

### 선택 필드 (이 Phase 에서 required 아님)

- `cause` — "parent error code" (계층적 원인 추적 필요 시)
- `ui_flow` — `inline`/`toast`/`modal`/`redirect`/`silent` (없으면 frontend skill 이 http_status 기반 기본값 할당)

### `specflow:generate-ts` 변경

- 프롬프트에 "에러 코드 맵 섹션을 반드시 포함" 지시 추가
- 기존 문서 재생성 시 이 섹션이 비어있으면 **제안 블록**을 자동 생성(FS §BR·AC 에 언급된 실패 시나리오를 스캔해서 초안 5~10행)
- `specflow:validate` 규칙 신설 (`ts-rules.md`):
  - 섹션 존재 여부
  - `code` 전역 유일성
  - `domain` ↔ FS §도메인 교차검증
  - `http_status` 범위
  - `i18n_key` 패턴 (`errors.*.*`)

### 호환성 — 1회 릴리스 grace period

- v1.x (grace): 섹션 없어도 warning. 구현 skill 은 warning 후 기본 에러 코드 5종(AUTH/USER/VALIDATION/SYSTEM/NETWORK) 으로 임시 동작
- v2.0: 섹션 없으면 validate error. 구현 skill 은 fail-fast

## 2. `backflow:impl-error-codes` 스킬 계약

### 카드

| 항목 | 내용 |
|---|---|
| **Purpose** | TS §에러 코드 맵 → 백엔드 상수·HTTP 매핑·i18n 리소스 |
| **Reads (specflow)** | `specs/TS/*` §에러 코드 맵, `specs/FS/*` §도메인 정의(교차 검증용) |
| **Reads (registry/config)** | `.backflow/task-file-map.md`(있으면), `backend.md` (error_handling.* 키) |
| **Writes** | `src/errors/codes.ts` (또는 ORM/프레임워크 별 path), `src/errors/http-mapping.ts`, `src/locales/errors.{ko,en}.json` |
| **Storage Tier** | N/A — project code |
| **Depends on** | `map-tasks`. `impl-services` 와 병렬 가능 (code 상수가 service 에서 쓰이지만 service 가 없어도 독립 생성 가능) |
| **Notes** | 기존 에러 코드 파일이 있으면 merge — TS 에 새로 추가된 코드만 append. 기존 코드 삭제·rename 은 경고 후 사용자 확인. |

### 실행 순서상 위치

```
map-tasks
   │
   ├── impl-schema → impl-repositories → impl-services → impl-controllers → ...
   │
   └── impl-error-codes  (T0)   ← 병렬 가능. impl-services 에 앞서가면 더 좋음
         ↓ (consumed by)
       impl-services, impl-middleware, generate-tests
```

**권장**: `impl-services` **직전** 또는 **같은 phase 에서 먼저** 실행. 서비스가 throw 할 에러 상수가 미리 존재하면 서비스 코드 품질이 더 좋아진다.

### `backend.md` 신규 키

```yaml
error_handling:
  codes_file: src/errors/codes.ts       # default
  http_mapping_file: src/errors/http-mapping.ts
  i18n_output_dir: src/locales/         # 파일명은 errors.{lang}.json 고정
  i18n_enabled: true                    # false 면 message_ko/en 을 코드에 inline
  exception_class: AppException         # throw 시 래핑할 공통 클래스명
```

## 3. `frontflow:impl-error-handling` 스킬 계약

### 카드

| 항목 | 내용 |
|---|---|
| **Purpose** | TS §에러 코드 맵 → 프론트엔드 에러 핸들러·UI 플로우 룩업·i18n 리소스 |
| **Reads (specflow)** | `specs/TS/*` §에러 코드 맵, `specs/UI/*` (UI flow 힌트 — 없으면 http_status 기본값) |
| **Reads (registry/config)** | `.frontflow/task-file-map.md`(있으면), `frontend.md` (error_handling.* 키, `state_management`) |
| **Writes** | `src/errors/codes.ts` (enum), `src/errors/handler.ts` (code → message·ui_flow), `src/locales/errors.{ko,en}.json`, (선택) `src/errors/ui-flow.tsx` (React 컴포넌트 프리셋) |
| **Storage Tier** | N/A — project code |
| **Depends on** | `map-tasks`. `impl-interactions`, `impl-api-integration` 에 앞서 실행 권장 |
| **Notes** | `handler.ts` 는 순수 함수 (렌더링 없음). 렌더링은 `impl-interactions`/`impl-api-integration` 이 handler 반환값을 해석해 toast/modal/redirect 수행. |

### `frontend.md` 신규 키

```yaml
error_handling:
  codes_file: src/errors/codes.ts
  handler_file: src/errors/handler.ts
  ui_flow_file: src/errors/ui-flow.tsx   # optional
  i18n_library: i18next                  # i18next | formatjs | lingui | inline
  i18n_output_dir: src/locales/
  default_ui_flow:
    "4xx": toast
    "5xx": modal
```

## 4. 동기화 메커니즘 — **양쪽이 TS 를 각자 읽음**

### 채택 방식

```
          specs/TS/*.md
          §에러 코드 맵
               │
        ┌──────┴──────┐
        ▼             ▼
 impl-error-codes  impl-error-handling
   (backflow)       (frontflow)
        │             │
        ▼             ▼
  src/errors/     src/errors/
  codes.ts        codes.ts
        └──── ErrorCode.USER_NOT_FOUND = "USER_NOT_FOUND" (양쪽 동일) ────┘
```

- **코드 문자열이 계약의 바이트**. Enum 이름·파일 위치·언어가 달라도 `code` 필드의 문자열 값이 일치하면 frontend 가 backend 응답의 `error.code` 를 자기 enum 으로 매칭 가능.
- Backend 응답 envelope:
  ```json
  { "error": { "code": "USER_NOT_FOUND", "message": "User not found", "meta": {...} } }
  ```
- Frontend handler:
  ```ts
  handler(response.error.code) → { message, ui_flow, retriable }
  ```

### 기각한 대안

| 대안 | 기각 이유 |
|---|---|
| **(b) Backend export → Frontend import (모노레포)** | monorepo 전제 강함. 백엔드와 프론트엔드가 별도 repo 인 많은 프로젝트에서 작동 안 함. 런타임 의존성이 생겨 배포 시 version bump lockstep 필요. |
| **(c) OpenAPI/JSON Schema 기반 codegen** | Phase 1 (3) API 계약 동기화 skill 의 영역. 에러 코드만을 위해 별도 codegen 레이어 도입은 과함. Phase 1 (3) 완료 후 OpenAPI components 의 Error schema 로 통합할 여지는 남김(Future Work). |

### Drift 방지

- **Backend 측**: `backflow:validate-code` 에 신규 룰 — `src/errors/codes.ts` 의 enum 값과 TS §에러 코드 맵 의 `code` 열이 1:1 일치하는지 검사
- **Frontend 측**: `frontflow:validate-code` 동일 룰
- **양방향**: TS 에만 있고 코드에 없으면 "missing"; 코드에만 있고 TS 에 없으면 "orphan, add to TS or remove"
- 런타임 방어: frontend handler 가 unknown code 를 받으면 `UNKNOWN_ERROR` fallback + 경고 로그

## 5. 출력 파일 예시

### 5.1 Backend `src/errors/codes.ts` (TypeScript + NestJS 가정)

```ts
export enum ErrorDomain {
  AUTH = 'auth',
  USER = 'user',
  ORDER = 'order',
  SYSTEM = 'system',
}

export const ErrorCode = {
  AUTH_INVALID_CREDENTIALS: 'AUTH_INVALID_CREDENTIALS',
  AUTH_TOKEN_EXPIRED: 'AUTH_TOKEN_EXPIRED',
  USER_NOT_FOUND: 'USER_NOT_FOUND',
  ORDER_PAYMENT_FAILED: 'ORDER_PAYMENT_FAILED',
  SYSTEM_EXTERNAL_TIMEOUT: 'SYSTEM_EXTERNAL_TIMEOUT',
} as const;
export type ErrorCode = typeof ErrorCode[keyof typeof ErrorCode];

export const ErrorMeta = {
  [ErrorCode.AUTH_INVALID_CREDENTIALS]: {
    domain: ErrorDomain.AUTH,
    i18nKey: 'errors.auth.invalid_credentials',
    retriable: false,
  },
  // ... 자동 생성
} as const;
```

### 5.2 Backend `src/errors/http-mapping.ts`

```ts
import { ErrorCode } from './codes';
export const HTTP_STATUS_MAP: Record<ErrorCode, number> = {
  [ErrorCode.AUTH_INVALID_CREDENTIALS]: 401,
  [ErrorCode.AUTH_TOKEN_EXPIRED]: 401,
  [ErrorCode.USER_NOT_FOUND]: 404,
  [ErrorCode.ORDER_PAYMENT_FAILED]: 402,
  [ErrorCode.SYSTEM_EXTERNAL_TIMEOUT]: 504,
};
```

### 5.3 Frontend `src/errors/handler.ts`

```ts
import { ErrorCode, ErrorMeta } from './codes';
import { t } from '@/i18n';

export type ErrorDecision = {
  code: ErrorCode | 'UNKNOWN_ERROR';
  message: string;
  uiFlow: 'inline' | 'toast' | 'modal' | 'redirect' | 'silent';
  retriable: boolean;
};

export function handleError(raw: { code: string; message?: string }): ErrorDecision {
  const known = raw.code in ErrorMeta ? (raw.code as ErrorCode) : null;
  if (!known) {
    console.warn('[error-handler] unknown code', raw.code);
    return { code: 'UNKNOWN_ERROR', message: t('errors.unknown'), uiFlow: 'toast', retriable: false };
  }
  const meta = ErrorMeta[known];
  return {
    code: known,
    message: t(meta.i18nKey),
    uiFlow: meta.uiFlow ?? defaultFlowForStatus(meta.httpStatus),
    retriable: meta.retriable,
  };
}
```

### 5.4 i18n `src/locales/errors.ko.json`

```json
{
  "errors": {
    "auth": {
      "invalid_credentials": "아이디 또는 비밀번호가 올바르지 않습니다",
      "token_expired": "로그인이 만료되었습니다. 다시 로그인해주세요"
    },
    "user": { "not_found": "사용자를 찾을 수 없습니다" },
    "order": { "payment_failed": "결제가 실패했습니다. 잠시 후 다시 시도해주세요" },
    "system": { "external_timeout": "서비스가 일시적으로 원활하지 않습니다" },
    "unknown": "알 수 없는 오류가 발생했습니다"
  }
}
```

## 6. 마이그레이션 — 기존 프로젝트

### 6.1 시나리오 A — 에러 코드가 전혀 없는 프로젝트
skill 이 전체 생성. 추가 작업 없음.

### 6.2 시나리오 B — 에러 코드가 애드혹으로 흩어진 프로젝트
1. 사용자가 `backflow:scan-codebase` 재실행 → `service-registry.md` 에 "기존 에러 상수 후보" 수집 (예: `throw new Error('...')`, `throw new HttpException(...)`, `NotFoundException` 서브클래스 등)
2. `impl-error-codes --dry-run` 으로 merge preview 생성 — 기존 사용처 ↔ 새 `ErrorCode` enum 매핑표 (사람 검토 필요)
3. 승인 후 실행: 신규 codes.ts 생성 + 기존 사용처에 codemod 제안 (Edit tool, 사용자 확인 대화 필수)

### 6.3 시나리오 C — 이미 표준화된 에러 코드 체계가 있는 프로젝트
1. `backend.md.error_handling.codes_file` 을 기존 파일 경로로 지정
2. skill 이 "기존 파일이 이미 표준을 따르는지" 자동 검사 — enum + HTTP mapping + i18n key 삼박자가 맞으면 no-op
3. TS 에만 있고 기존 파일에 없는 코드 → append (기존 파일 포맷 보존)
4. 기존 파일에만 있는 코드 → TS 에 반영하도록 사용자에게 경고 (skill 이 TS 를 수정하지 않음 — `specflow:revise` 제안)

## 7. CONTRACTS.md 갱신 필요 사항

이 skill 추가 시 같은 PR 에서 다음 변경 동반:

- `plugins/backflow/CONTRACTS.md`
  - 실행 순서 다이어그램에 `impl-error-codes` 노드 추가 (`map-tasks` 직후 병렬 브랜치)
  - 스킬별 계약 섹션에 `impl-error-codes` 카드 추가
  - 공통 레지스트리 테이블에 `backend.md.error_handling` 키 그룹 행 추가
  - specflow 역매핑 테이블에 "TS §에러 코드 맵 → impl-error-codes" 추가
- `plugins/frontflow/CONTRACTS.md`
  - 동일 구조로 `impl-error-handling` 추가
- `plugins/specflow/...` validate 룰 파일에 TS §에러 코드 맵 검증 규칙 추가

## 8. 오픈 질문 / Future work

- **에러 메시지 다국어 개수** — 현재 `message_ko`/`message_en` 만. 다국어 3+ 필요 프로젝트는 TS 섹션 컬럼 확장 방식(명시적 컬럼 vs 별도 파일)을 Phase 2 에서 결정.
- **에러 코드 버전 관리** — API 버저닝(v1/v2) 도입 시 코드도 버전별 분리해야 할 수 있음. Phase 3 API 버전 skill 과 연계.
- **에러 메타데이터 확장** — `meta` 필드(예: `field_name`, `rate_limit_retry_after`) 구조화. Phase 1 현재는 자유 `Record<string, unknown>`.
- **에러 코드 deprecation** — 구 코드를 TS 에 남기되 "deprecated: USE_X_INSTEAD" 표기. Phase 2.
- **Observability 연계** — Phase 1 (2) Observability skill 과 연계해 `ErrorCode` 가 자동으로 structured log tag 로 들어가게. 이 문서의 스킬은 훅 포인트만 노출(`ErrorMeta` export) 하고 실제 로깅 주입은 Observability 가 담당.
- **OpenAPI 통합** — Phase 1 (3) 완료 후 OpenAPI components 의 Error schema 를 TS §에러 코드 맵 에서 자동 생성(단방향) 할지 결정. 현재는 수동 일관성.

## 9. 완료 기준 (Definition of Done)

### Phase 1 (1) 스킬 페어가 "ship" 이라 불릴 조건

- [ ] `specflow:generate-ts` 가 새 섹션을 포함해 출력 (기본 동작)
- [ ] `specflow:validate` 가 섹션 존재·code 유일성·domain 교차검증 수행
- [ ] `backflow:impl-error-codes` 실행 시 `src/errors/codes.ts`, `http-mapping.ts`, `locales/errors.*.json` 생성·머지
- [ ] `frontflow:impl-error-handling` 실행 시 `src/errors/codes.ts`, `handler.ts`, `locales/errors.*.json` 생성·머지
- [ ] `backflow:validate-code`, `frontflow:validate-code` 가 drift(코드 ↔ TS 불일치) 감지
- [ ] 양쪽 CONTRACTS.md 갱신
- [ ] 최소 1개 실프로젝트(이 레포 또는 velvetalk) 에서 E2E 적용 — TS 에 새 에러 코드 추가 → `impl-error-*` 재실행 → 양쪽 코드 파일에 반영 확인

### "stable" 태그 조건 (로드맵 §3.10)

- 2개 이상 프로젝트에서 실사용
- 시나리오 A/B/C 마이그레이션 각각 최소 1회 성공

## 10. 다음 작업

이 설계 문서 머지 후 착수할 순서:

1. `specflow:generate-ts` 프롬프트·validate 룰 변경 (PR #1)
2. `backflow:impl-error-codes` skill 구현 (PR #2)
3. `frontflow:impl-error-handling` skill 구현 (PR #3)
4. 양쪽 `CONTRACTS.md` 갱신은 (2)(3) 각각에 포함 — 스킬 PR 자체가 CONTRACTS 갱신을 포함해야 리뷰어가 계약을 함께 검증
5. `backflow:validate-code`, `frontflow:validate-code` drift rule 추가 (PR #4, 작음)

Phase 1 (1) 전체 예상 4~5 PR, 2~3주 소요.
