# Phase 1 (6) — Webhook 멱등성 Skill 설계

> **Generated**: 2026-04-27
> **Scope**: Phase 1 마지막 항목 — `backflow:impl-webhook` 신설 + `specflow:generate-ts` `§10 외부 연동·webhook` 부속섹션 의무화 + `backflow:validate-code` §11 drift 룰
> **Parent roadmap**: `docs/plugin-gaps-and-plan.md` §3.3 (6)
> **Companion designs**: phase-1-error-contract (1), phase-1-observability (2), phase-1-api-sync (3), phase-1-tracking (4), phase-1-file-upload (5)
>
> **Revision (2026-04-27, Task 0 codex review — 9 findings, 4 critical · 5 warning)**:
> - **XR-001 (critical)**: `selected-signature.ts` facade 신설 — Phase 1 (5) `selected-storage` 패턴 완전 이식. controller/service 는 facade 만 호출, sender adapter 직접 import 금지.
> - **XR-002 (critical)**: idempotency race 처리 명시 — `INSERT ... ON CONFLICT` 패턴, transaction boundary, processing row 재도착 시 응답 정책 (409 또는 wait), request_hash mismatch 검출.
> - **XR-003 (critical)**: dispatch 동기/비동기 모순 해소 — **default 흐름 고정**: 서명 검증 → idempotency insert → queue enqueue → 200 즉시 응답. handler 결과는 비동기 worker 가 idempotency 행 갱신. `always_200_on_signature_pass=false` 는 enqueue 실패 시에만 503.
> - **XR-004 (critical)**: timing-safe signature comparison 의무 — adapter contract 에 명시, validate §11.2 timing_safe_compare 룰 추가.
> - **XR-005 (warning)**: `idempotency_key_source` minimal grammar — EBNF 형식 (`source := term ('+' term)*; term := header(NAME) | headerParam(NAME, PARAM) | body(PATH) | fallback(term, term)`).
> - **XR-006 (warning)**: raw body 보존 framework 별 패턴 명시 (NestJS rawBody:true / Express express.raw / Fastify rawBody addContentTypeParser / FastAPI Request.body() / Spring HttpServletRequest.getInputStream).
> - **XR-007 (warning)**: signature middleware 검출 anchor 명시 (framework 별 decorator / consumer.apply / @Middleware / dependency injection).
> - **XR-008 (warning)**: `always_200_on_signature_pass` 를 per-webhook override 가능하도록 §10 컬럼 + backend.md 둘 다.
> - **XR-009 (warning)**: WEBHOOK_REPLAY_DETECTED → 두 가지로 분리 — `WEBHOOK_TIMESTAMP_REPLAY` (timestamp 검사 실패) + `WEBHOOK_DUPLICATE_DELIVERY` (idempotency hit, error 가 아닌 정상 중복).

## 목표

Backend 의 **inbound webhook** 표준화 — 서명 검증 + idempotency + replay 차단 + 비동기 dispatch. 서명 알고리즘은 sender 별 어댑터, controller/service 는 facade 만 의존.

### Non-goals

- Outbound webhook 송신 — Phase 2
- Webhook subscription API 관리 — Phase 2
- Replay attack 외 보안 (DDoS / IP allowlist) — `impl-middleware` / 인프라
- Webhook delivery retry from sender — 외부 시스템
- Long-running task 직접 처리 — `impl-integrations` 큐 위임. 본 skill 은 enqueue 만 (XR-003)
- gRPC / GraphQL subscription / SSE — 별도 패턴
- 다중 secret rotation — Phase 2

## 1. TS 포맷 변경 — `§10 외부 연동·Webhook` 부속섹션

### 섹션 포맷

```markdown
# 10. 외부 연동 — Webhook (Inbound)

| webhook_id | sender | endpoint | signature_alg | signature_header | signature_secret_env | event_types | idempotency_key_source | timeout_sec | always_200 | related |
|---|---|---|---|---|---|---|---|---|---|---|
| stripe_payment | stripe | /webhooks/stripe | hmac_sha256_payload | Stripe-Signature | STRIPE_WEBHOOK_SECRET | payment_intent.succeeded, charge.refunded | headerParam(Stripe-Signature, t) + body(id) | 30 | true | US-010 |
| github_push | github | /webhooks/github | hmac_sha256_x_hub | X-Hub-Signature-256 | GITHUB_WEBHOOK_SECRET | push, pull_request | header(X-GitHub-Delivery) | 30 | true | US-018 |
| toss_payment | toss | /webhooks/toss | hmac_sha256_b64 | TossPayments-Signature | TOSS_WEBHOOK_SECRET | PAYMENT_CONFIRMED, PAYMENT_CANCELED | fallback(header(Idempotency-Key), body(paymentKey)) | 15 | false | AC-011 |
```

### 섹션 규약

| 필드 | 필수 | 규칙 |
|---|---|---|
| `webhook_id` | required | snake_case 전역 유일. operationId prefix |
| `sender` | required | 외부 서비스 식별자. SignatureAdapter 의 `sender` 와 일치 |
| `endpoint` | required | `/webhooks/{id}` 권장. impl-middleware 의 auth bypass 대상 |
| `signature_alg` | required | enum: `hmac_sha256_payload` / `hmac_sha256_b64` / `hmac_sha1_x_hub` / `hmac_sha256_x_hub` / `rsa_sha256` / `none` (개발용) |
| `signature_header` | required | 서명 헤더명 |
| `signature_secret_env` | required | env 변수명. 시크릿 자체 노출 금지 |
| `event_types` | optional | comma 구분. 빈 값 = 단일 handler |
| `idempotency_key_source` | required | minimal grammar (XR-005) — 아래 §1.1 |
| `timeout_sec` | required | 1~120 정수. sender SLA 와 일치 |
| `always_200` | optional (default true) | per-webhook override (XR-008). false 면 enqueue 실패 시 503 (sender 재시도 유도) |
| `related` | optional | US/AC/BR |

### 1.1 `idempotency_key_source` minimal grammar (XR-005)

```ebnf
source := term ('+' term)*
term   := header(NAME)                      # 헤더 전체 값
        | headerParam(NAME, PARAM)          # 'Stripe-Signature: t=123,v1=abc' 의 t 값
        | body(PATH)                        # JSON path (dot notation)
        | fallback(term, term)              # 첫 번째가 missing/empty 시 두 번째
```

**예시**:
- `header(X-GitHub-Delivery)` — 단일 헤더
- `headerParam(Stripe-Signature, t) + body(id)` — Stripe 의 timestamp 와 event id 결합
- `fallback(header(Idempotency-Key), body(paymentKey))` — 헤더 없으면 body fallback

**검증**:
- 모든 term 의 결과가 missing/empty 면 → `WEBHOOK_IDEMPOTENCY_KEY_MISSING` 에러 (400)
- concat delimiter: `:` (구현 fix)

### `specflow:generate-ts` 변경

- 프롬프트: "§10 webhook — PRD 의 'webhook', '결제 알림', '깃허브 이벤트' 흡수"
- 자가 점검:
  - "모든 webhook 의 signature_alg / signature_header / signature_secret_env / idempotency_key_source 명시"
  - "signature_alg=none 은 개발용 명시"
  - "idempotency_key_source 가 minimal grammar 따름"
  - "webhook_id 마다 §3.2 fragment 에 `receive{WebhookIdCamel}` operationId"
  - "always_200=false 인 webhook 의 retry 정책이 sender 와 호환"

### ts-rules 신규 룰 (warning grace)

```markdown
## Webhook (warning — v1.x grace period)
58. §10 섹션 존재 — webhook 명시된 프로젝트만. 부재 시 정상
59. webhook_id snake_case + 전역 유일 — 위반 시 warning
60. signature_alg enum — 그 외 warning
61. signature_alg=none 인데 production 환경에서 사용 의도 → warning ("개발 한정")
62. signature_header / signature_secret_env 모두 명시 → 누락 시 warning
63. idempotency_key_source minimal grammar 위반 (header/headerParam/body/fallback 외 사용) — warning
64. §10 webhook_id 마다 §3.2 fragment 에 `receive{WebhookIdCamel}` operationId — 누락 시 warning
65. timeout_sec 1~120 정수 — 위반 시 warning
```

## 2. `backflow:impl-webhook` 스킬 계약

### 카드

| 항목 | 내용 |
|---|---|
| **Purpose** | TS §10 → inbound webhook controller (서명 검증 + idempotency + enqueue) + sender 어댑터 + facade + idempotency entity |
| **Reads (specflow)** | `specs/TS/*` §10 (필수), §3.2 (operationId 검증), §4 (WEBHOOK_SIGNATURE_INVALID / WEBHOOK_TIMESTAMP_REPLAY / WEBHOOK_IDEMPOTENCY_KEY_MISSING 권고. **WEBHOOK_DUPLICATE_DELIVERY 는 에러가 아닌 idempotency hit** — XR-009), §5 (idempotency entity), §처리 흐름 |
| **Reads (registry/config)** | `.backflow/task-file-map.md`(있으면), `.backflow/service-registry.md`, `backend.md` (`webhook.*` 섹션, `framework.*`, `database.orm`, `external_services.message_queue`) |
| **Writes** | controller / service / module(Nest) / DTO / idempotency entity / migration / `webhook/signatures/types.ts` / `webhook/signatures/none.ts` (개발용) / `webhook/signatures/{sender}.ts` (TS §10 마다) / **`webhook/signatures/selected-signature.ts`** (XR-001 facade) / `webhook/dispatch.ts` (큐 enqueue). path 는 backend.md.structure / framework convention 에서 derive |
| **Storage Tier** | N/A — project code |
| **Depends on** | `map-tasks`, `impl-schema`, `impl-error-codes`, `impl-services`, `impl-integrations` (queue) 후. **책임 경계** §2.1 |
| **Notes** | sender 식별자 격리: `signatures/{sender}.ts` 내부만. controller / service / dispatch / signatures/types.ts / **selected-signature.ts** 모두 sender SDK import 금지. selected-signature.ts 는 정적 dispatch (Phase 1 (5) selected-storage 패턴) |

### 2.1 선행 skill 책임 경계

- **impl-controllers**: TS §10 의 webhook operationId 는 stub/skip
- **impl-middleware**: webhook endpoint 의 auth guard bypass + signature middleware 적용
- **impl-integrations**: 큐 추상이 있으면 본 skill 의 dispatch 가 wrapping (재구현 금지)

### 2.2 실행 위치

```
... → impl-services → impl-controllers (webhook stub) → impl-middleware (bypass auth + sig middleware) → impl-integrations
   → impl-file-upload → impl-webhook ★ → export-api-contract → generate-tests
```

### 2.3 `backend.md` 신규 키

```yaml
webhook:
  webhook_module_dir: "src/webhooks"
  signatures_subdir: "signatures"
  selected_signature_filename: "selected-signature.ts"
  dispatch_file: "dispatch.ts"
  idempotency_table: "webhook_idempotency"
  idempotency_entity_path: "src/webhooks/idempotency.entity.ts"
  idempotency_ttl_days: 30
  default_timeout_sec: 30
  bypass_auth_routes: ["/webhooks/**"]   # impl-middleware 가 참조
  signature_clock_skew_sec: 300
  always_200_default: true               # webhook 별 override 가능 (TS §10.always_200)
  retry_status_code: 503                 # always_200=false + enqueue 실패 시
  enqueue_only: true                     # XR-003: handler 는 큐로만. 동기 mode 는 Phase 2
  duplicate_delivery_logging: true       # WEBHOOK_DUPLICATE_DELIVERY 를 info log
```

### 2.4 SignatureAdapter 인터페이스 + facade (XR-001, XR-004)

```typescript
// webhook/signatures/types.ts
export interface SignatureVerifyInput {
  rawBody: Buffer | string;       // raw bytes (서명 일관성)
  headers: Record<string, string | string[]>;
  secret: string;
  clockSkewSec: number;
}

export interface SignatureVerifyResult {
  valid: boolean;
  reason?: string;                // production 응답 노출 금지
  timestamp?: number;             // replay 검사용
}

export interface SignatureAdapter {
  readonly sender: string;
  readonly alg: string;
  /**
   * MUST: HMAC 직접 비교 시 crypto.timingSafeEqual (Node) 또는 동등한
   * constant-time 비교 사용. SDK 검증 API 사용 시 SDK 가 보장 (Stripe 등).
   * MUST: timestamp 가 추출 가능한 alg 에서 timestamp 반환.
   */
  verify(input: SignatureVerifyInput): SignatureVerifyResult;
}
```

**Facade — `webhook/signatures/selected-signature.ts`** (XR-001):

```typescript
// AUTO-GENERATED by backflow:impl-webhook
// 정적 dispatch — TS §10 의 모든 sender 를 build-time 에 fix.
// 런타임 if/switch 또는 dynamic import 금지 (validate §11.2 critical).

import type { SignatureAdapter } from './types';
import { stripeSignatureAdapter } from './stripe';
import { githubSignatureAdapter } from './github';
import { tossSignatureAdapter } from './toss';
import { noneSignatureAdapter } from './none';

const ADAPTERS: Record<string, SignatureAdapter> = {
  stripe: stripeSignatureAdapter,
  github: githubSignatureAdapter,
  toss: tossSignatureAdapter,
  none: noneSignatureAdapter,
};

export function getAdapter(sender: string): SignatureAdapter {
  const a = ADAPTERS[sender];
  if (!a) throw new Error(`No SignatureAdapter for sender: ${sender}`);
  return a;
}
```

controller/service 는 `getAdapter(webhookCfg.sender)` 만 호출. sender 별 import 직접 금지.

### 2.5 raw body 보존 — framework 별 (XR-006)

| framework | 패턴 |
|---|---|
| **NestJS** | `NestFactory.create(AppModule, { rawBody: true })` + `@Req() req: RawBodyRequest<Request>` 에서 `req.rawBody` |
| **Express** | webhook route 만 `express.raw({ type: '*/*' })` (전역 `express.json()` 앞에 배치). 비-webhook route 는 일반 json parser |
| **Fastify** | `fastify.addContentTypeParser('*', { parseAs: 'buffer' }, ...)` route-specific. 또는 `@fastify/raw-body` plugin |
| **FastAPI** | `Request.body()` await — Pydantic 파싱 전 호출. 또는 dependency injection 으로 raw bytes 주입 |
| **Spring Boot** | `HttpServletRequest.getInputStream()` 또는 `@RequestBody byte[] body` (filter 가 wrap 하지 않은 환경) |

skill 은 framework 검출 후 적절한 패턴으로 boilerplate 작성. validate-code §11.1 `raw_body_preserved` 가 framework 별 anchor 검사.

### 2.6 Controller 동작 — default flow (XR-002, XR-003 명시)

```
1. raw body 캡처 (framework 별)
2. webhook_id 결정 (route 매칭)
3. webhookCfg = TS §10 lookup (webhook_id)
4. signatureAdapter = getAdapter(webhookCfg.sender)
5. result = signatureAdapter.verify({ rawBody, headers, secret, clockSkewSec })
   - invalid → 401 + WEBHOOK_SIGNATURE_INVALID (timing-safe 검증 실패)
6. timestamp replay 검사 (result.timestamp 있으면):
   - |now - timestamp| > clockSkewSec → 400 + WEBHOOK_TIMESTAMP_REPLAY
7. idempotency_key 추출 (TS §10.idempotency_key_source grammar 적용)
   - missing/empty → 400 + WEBHOOK_IDEMPOTENCY_KEY_MISSING
8. request_hash = sha256(rawBody)
9. INSERT ON CONFLICT (XR-002):
   ```sql
   INSERT INTO webhook_idempotency (id, webhook_id, idempotency_key, request_hash, status, expires_at)
   VALUES (..., 'pending', now() + interval '30 days')
   ON CONFLICT (webhook_id, idempotency_key) DO NOTHING
   RETURNING id;
   ```
   - 새 행 생성 (새 delivery): 정상 진행
   - 기존 행 존재 (idempotency hit):
     - 기존 행 status = complete: stored response_status / response_body 그대로 반환 + WEBHOOK_DUPLICATE_DELIVERY info log (XR-009 — 에러 아님)
     - 기존 행 status = pending/processing: 409 + Retry-After 또는 long-poll 결정 — Phase 1 default = 즉시 200 + "duplicate in flight" log (handler 재실행 안 함)
     - 기존 행 request_hash != now hash: 409 + WEBHOOK_REQUEST_HASH_MISMATCH (같은 key 다른 body — sender 버그 가능성)
10. queue enqueue (impl-integrations 의 큐 사용):
    - enqueue 실패 + always_200=true: 200 + idempotency 행 status: failed (worker 가 나중에 cleanup)
    - enqueue 실패 + always_200=false: 503 + idempotency 행 삭제 (sender 재시도 유도)
    - enqueue 성공: 200 즉시 응답
11. async worker (별도 process):
    - handler 실행 → idempotency 행 status: complete + response_body/status 기록
    - handler 실패 → status: failed + error 기록 + 재시도 정책 (impl-integrations 큐 의존)
```

**원칙** (XR-003): controller 는 enqueue 만. handler 결과는 worker 가 비동기로 idempotency 행 갱신. `always_200=false` 는 enqueue 실패 시에만 적용 — handler 실패 시점은 controller 가 모름.

### 2.7 Idempotency entity canonical schema

| 필드 | 타입 | 비고 |
|---|---|---|
| `id` | UUID v7 | PK |
| `webhook_id` | text | indexed |
| `idempotency_key` | text | |
| `request_hash` | text | sha256(rawBody). 같은 key 다른 body 검출 |
| `status` | enum (`pending` / `processing` / `complete` / `failed`) | |
| `response_body` | jsonb? | replay 시 재사용 |
| `response_status` | int? | |
| `error` | text? | failed 시 |
| `expires_at` | timestamptz | created_at + ttl_days |
| `created_at`, `updated_at`, `completed_at?` | timestamptz | |

**`UNIQUE(webhook_id, idempotency_key)` constraint** (race 방지 핵심).

## 3. 동기화 메커니즘

```
TS §10 → impl-webhook → controller + service + dispatch + module + DTO + idempotency entity + signatures + selected-signature
        → export-api-contract → sync-api-client (frontend 일반적으로 미사용)
        → validate-code §11
```

### 기각한 대안

| 대안 | 기각 이유 |
|---|---|
| **(a) 서명을 service 본문에서** | raw body 접근 위해 controller/middleware 필요 |
| **(b) Idempotency 메모리 캐시 only** | 영구 audit 필요 |
| **(c) sender SDK 를 service 에서** | 어댑터 패턴 표준 |
| **(d) 단일 endpoint 분기** | sender 별 알고리즘 다름 |
| **(e) 처음부터 always 200** | 일시적 장애 시 재시도 손실 — per-webhook override |
| **(f) controller 에서 동기 handler** | 30s timeout 위험. enqueue-only 표준 (XR-003) |
| **(g) Adapter 런타임 분기** | tree-shake 어려움 + sender 식별자 확산. 정적 facade (XR-001) |

## 4. validate-code §11 drift 룰 (5 sub-rule)

```yaml
입력:
  ts_section: specs/TS-*.md §10 외부 연동·Webhook
  service_registry: .backflow/service-registry.md
  webhook_dir: backend.md.webhook.webhook_module_dir
  signatures_dir: webhook_dir + "/" + backend.md.webhook.signatures_subdir
  selected_signature_file: signatures_dir + "/" + backend.md.webhook.selected_signature_filename
  idempotency_entity: backend.md.webhook.idempotency_entity_path

§11.1 — TS §10 ↔ controller/service 일관성:
  webhook_id_in_controller:
    - TS §10 모든 webhook_id 가 controller 핸들러/operationId 등장 → 누락 시 critical
  signature_alg_match / signature_header_match:
    - controller / adapter 가 사용한 alg / header 가 §10 명시값과 일치 → 불일치 시 critical
  signature_secret_env_used:
    - process.env[signature_secret_env] (또는 동등) 으로 secret 로드 → 미사용 시 critical
    - 시크릿 hardcoded → critical
  idempotency_key_extraction_grammar:
    - controller/service 의 key 추출 코드가 §10.idempotency_key_source 의 minimal grammar (header/headerParam/body/fallback) 따름 → 위반 시 critical
  raw_body_preserved:
    - framework 별 anchor 패턴 검출 (XR-006):
      - NestJS: `NestFactory.create(.., { rawBody: true })` + `@Req() req: RawBodyRequest`
      - Express: webhook route 가 `express.raw(...)` middleware 적용
      - Fastify: `addContentTypeParser` 또는 `@fastify/raw-body`
      - FastAPI: `Request.body()` await
      - Spring: `HttpServletRequest.getInputStream()` 또는 `byte[] body`
    - 위 패턴 부재 시 → critical
  related_error_codes:
    - TS §4 에 WEBHOOK_SIGNATURE_INVALID / WEBHOOK_TIMESTAMP_REPLAY / WEBHOOK_IDEMPOTENCY_KEY_MISSING / WEBHOOK_REQUEST_HASH_MISMATCH 부재 → warning
    - WEBHOOK_REPLAY_DETECTED 같은 모호한 단일 코드 사용 → warning ("XR-009: 분리 권고")

§11.2 — Sender 식별자 영역 검사 + facade:
  sender_identifier_in_layers:
    - controller / service / dispatch / signatures/types.ts / selected-signature.ts 에 sender SDK import (`stripe`, `@octokit`, `@slack/`, sender 별) 등장 → critical
  selected_signature_static_dispatch_only:
    - selected-signature.ts 가 `Record<sender, SignatureAdapter>` + `getAdapter` 외 형태 (런타임 if/switch / dynamic import / 동적 require) → critical (XR-001)
    - selected-signature.ts 자체의 sender adapter import 는 허용 (정적 dispatch facade)
    - TS §10 의 모든 sender 가 ADAPTERS 객체에 등장 → 누락 시 critical
  signature_adapter_interface_compliance:
    - signatures/{sender}.ts 가 SignatureAdapter (sender / alg / verify) 충족 → 불충족 시 critical
  none_adapter_dev_only:
    - signatures/none.ts 가 production 환경에서 활성화될 수 있는 분기 → critical
  timing_safe_compare:
    - signatures/{sender}.ts 의 직접 HMAC 비교 코드 (`===`, `Buffer.compare`, `==`) 검출 → critical (XR-004 — `crypto.timingSafeEqual` 또는 SDK 검증 API 사용 의무)
    - SDK 검증 API (`Stripe.webhooks.constructEvent` 등) 사용은 timing-safe 보장으로 통과

§11.3 — Idempotency entity & race:
  required_fields:
    - id / webhook_id / idempotency_key / request_hash / status / created_at / updated_at 모두 존재 → 누락 시 critical
  unique_constraint:
    - (webhook_id, idempotency_key) UNIQUE constraint 부재 → critical
  status_enum_match:
    - [pending, processing, complete, failed] → 추가/누락 시 warning
  insert_on_conflict_pattern:
    - controller 의 idempotency insert 가 ON CONFLICT 또는 동등 (try/catch + unique violation) 패턴 → 부재 시 critical (XR-002)
  request_hash_check:
    - 기존 행 발견 시 request_hash 비교 코드 부재 → warning ("같은 key 다른 body 검출 누락")
  replay_uses_stored_response:
    - status: complete 인 idempotency hit 시 stored response_body/status 그대로 반환 → 부재 시 critical
  duplicate_delivery_log:
    - WEBHOOK_DUPLICATE_DELIVERY info log 또는 동등 부재 → warning ("XR-009 logging 권고")

§11.4 — Middleware / 라우팅 책임 경계:
  webhook_routes_bypass_auth:
    - bypass_auth_routes 의 경로가 impl-middleware auth guard 에서 bypass → 부재 시 critical
  webhook_signature_middleware_applied:
    - bypass_auth_routes 의 경로에 signature 검증이 적용 (XR-007 framework anchor):
      - NestJS: `consumer.apply(WebhookSignatureMiddleware).forRoutes('webhooks/*')` 또는 controller-level decorator
      - Express: webhook router 의 `router.use(signatureMiddleware)`
      - Fastify: `addHook('preHandler', ...)` 또는 plugin
      - FastAPI: `Depends(verify_signature)` 또는 middleware
      - Spring: `@Component` filter / interceptor
    - 패턴 부재 시 critical
  controller_no_duplication:
    - 사전 조건: service-registry 에 controller operationId 추적 정보 존재 시 — generated_by != "impl-webhook" 가 §10 webhook 본문 구현 → warning
    - 추적 정보 부재 시: 휴리스틱 — controller 파일에서 webhook_id 매칭 핸들러 본문 비어있지 않으면 warning

§11.5 — Always-200 정책 + dispatch:
  always_200_per_webhook:
    - TS §10.always_200 컬럼 명시 시 controller/service 가 그 값 기준 분기 → 위반 시 warning
    - 미명시 시 backend.md.webhook.always_200_default 사용
  enqueue_only_dispatch:
    - controller 의 webhook handler 가 직접 비즈니스 로직 호출 (큐 enqueue 외) → critical (XR-003 — 동기 모드는 Phase 2)
    - enqueue 호출은 impl-integrations 의 큐 추상 사용 — 직접 큐 driver 호출 시 warning
  signature_failure_response:
    - 서명 검증 실패 시 401 또는 403 → 그 외 (특히 200) 시 critical
  enqueue_failure_response:
    - always_200=true 시 enqueue 실패에도 200 반환 → 그 외 critical
    - always_200=false 시 enqueue 실패 → backend.md.webhook.retry_status_code (default 503) 반환 → 불일치 시 warning

예외:
  - TS §10 부재 → §11 전체 skip + info
  - signature_alg=none 인 webhook 이 NODE_ENV=development 가드 존재 시 §11.2 none_adapter_dev_only 통과
  - bypass_auth_routes 미정의 → §11.4 webhook_routes_bypass_auth 검사 skip + warning
```

## 5. 마이그레이션

### 5.1 Scenario A — 신규
TS §10 작성 → 전체 생성. idempotency 마이그레이션

### 5.2 Scenario B — 기존 webhook 코드 산재
1. `--dry-run` grep: `crypto.createHmac`, `Stripe.webhooks.constructEvent`, `verifySignature`, `X-Hub-Signature`, `X-Slack-Signature`
2. webhook_id / signature_alg / source 추론
3. 사용자 승인 후 통합. timing-safe 비교 자동 codemod (`===` → `timingSafeEqual`)

### 5.3 Scenario C — sender 추가
새 webhook_id + signatures/{newSender}.ts. selected-signature.ts 의 ADAPTERS 객체에 1행 append. 기존 controller/service 보존

### 5.4 Scenario D — idempotency 가 다른 형식으로 존재
1. `idempotency_entity_path` 를 기존 entity 로
2. canonical 충족 시 보존, 비호환 시 사용자 confirm

## 6. CONTRACTS.md 갱신

- `plugins/backflow/CONTRACTS.md`
  - 실행 순서: `impl-file-upload` → **`impl-webhook`** → `export-api-contract`
  - 스킬 카드 신설
  - 공통 레지스트리: `backend.md.webhook.*`
  - specflow 역매핑: `TS §10 → impl-webhook`, `TS §3.2 → impl-webhook (operationId)`, `TS §4 → impl-webhook (WEBHOOK_* 권고)`, `TS §5 → impl-webhook (idempotency entity)`, `TS §처리 흐름 → impl-webhook (handler 큐 dispatch)`
  - **impl-controllers Notes**: TS §10 webhook operationId 도 stub/skip
  - **impl-middleware Notes**: bypass_auth_routes 경로는 auth bypass + signature middleware
  - **impl-integrations Notes**: 큐 추상은 impl-webhook 의 dispatch 가 wrapping 사용
- `plugins/specflow/skills/generate-ts/SKILL.common.md` — §10 추가 + 자가 점검
- `plugins/specflow/skills/generate-ts/template.md` — §10 섹션
- `plugins/specflow/skills/validate/rules/ts-rules.md` — 룰 58~65

## 7. Future work

- Outbound webhook dispatch — Phase 2
- Subscription API 관리 — Phase 2
- Cron 정리 (만료 idempotency) — Phase 2
- Dead-letter queue — Phase 2
- 동기 dispatch 모드 (long-poll wait for handler) — Phase 2
- Multi-secret rotation — Phase 2
- Webhook test fixture 자동 생성 — Phase 2
- Stripe / GitHub / Slack stable adapter 라이브러리 — Phase 2

## 8. 완료 기준 (Definition of Done)

### "ship"

- [ ] `specflow:generate-ts` §10 출력 (always_200 컬럼 + idempotency_key_source minimal grammar)
- [ ] ts-rules 58~65
- [ ] `backflow:impl-webhook` controller / service / module / DTO / idempotency entity / migration / signatures (types + none + {senders}) + **selected-signature.ts facade** + dispatch 생성. backend.md.structure 에서 path derive
- [ ] `backend.md.webhook.*` 신규 키 (always_200_default + always_200 per-webhook override + enqueue_only)
- [ ] SignatureAdapter 인터페이스 — sender/alg/verify + **timing-safe compare 의무**
- [ ] selected-signature.ts 정적 dispatch (Record + getAdapter)
- [ ] Controller 가 raw body 보존 + 서명 검증 + INSERT ON CONFLICT + replay stored response + queue enqueue (handler 직접 호출 X)
- [ ] `backflow:validate-code` §11 (5 sub-rule)
- [ ] CONTRACTS 갱신 (impl-controllers / impl-middleware / impl-integrations Notes)
- [ ] 1개 실프로젝트 E2E (가짜 sender + 서명 검증 + 같은 key 2회 도착 → 1회만 처리 + duplicate hit log)

### "stable"

- 2개 이상 프로젝트 실사용
- sender adapter 최소 3종 (stripe + github + 1개) 검증
- ts-rules 58~65 grace → critical
- §11 grace → critical
- Scenario A/B/C/D 마이그레이션 각각 1회

## 9. 다음 작업

1. **Task A** — `specflow:generate-ts` SKILL + template + ts-rules 58~65
2. **Task B** — `backflow:impl-webhook` skill + `backend.md.webhook` + `backflow/CONTRACTS.md` (impl-controllers / impl-middleware / impl-integrations Notes)
3. **Task D** — `backflow:validate-code` §11 (5 sub-rule)

Phase 1 (6) 전체 3 commit, 1주 소요.

## Phase 1 종합

본 phase 완료 시 Phase 1 (1)~(6) mandatory 영역 100%. 다음:
- **Phase 1.5 dbflow** (별도 plugin, 2~3주, velvetalk 포팅)
- Phase 2/3 (선택적 / 조직 표준)
