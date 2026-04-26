# Phase 1 (6) — Webhook 멱등성 Skill 설계

> **Generated**: 2026-04-27
> **Scope**: Phase 1 마지막 항목 — `backflow:impl-webhook` 신설 + `specflow:generate-ts` `§10 외부 연동·webhook` 부속섹션 의무화 + `backflow:validate-code` §11 drift 룰
> **Parent roadmap**: `docs/plugin-gaps-and-plan.md` §3.3 (6)
> **Companion designs**: phase-1-error-contract (1), phase-1-observability (2), phase-1-api-sync (3), phase-1-tracking (4), phase-1-file-upload (5)

## 목표

Backend 의 **inbound webhook 수신** 을 표준화한다 — 서명 검증 → idempotency-key 저장 → 리플레이 차단 → 비동기 처리 dispatch. 외부 서비스(Stripe / GitHub / Slack / Toss / Linear / 기타) 마다 서명 알고리즘이 다르지만 어댑터로 격리. 같은 이벤트가 여러 번 도착해도 한 번만 처리됨을 보장.

### Non-goals

- **Outbound webhook 송신** (우리가 외부에 보내는 webhook) — `backflow:impl-integrations` 또는 별도 skill (Phase 2 `backflow:impl-webhook-dispatch`). 본 phase 는 inbound 만
- 외부 서비스의 비즈니스 로직 처리 — `backflow:impl-services` 책임 (webhook handler 가 service 호출)
- Webhook subscription 관리 (외부 API 로 구독 등록·해제) — Phase 2
- Replay attack 외의 보안 (DDoS 방어, IP allowlist 등) — `impl-middleware` / 인프라 책임
- Webhook delivery retry from sender — 외부 시스템 책임
- Long-running task 처리 — `impl-integrations` 의 message queue 위임. 본 skill 은 enqueue 만
- gRPC / GraphQL subscription / SSE 수신 — 본 phase 의 webhook 정의 밖

## 1. TS 포맷 변경 — `§10 외부 연동·Webhook` 부속섹션

### 섹션 포맷

```markdown
# 10. 외부 연동 — Webhook (Inbound)

| webhook_id | sender | endpoint | signature_alg | signature_header | signature_secret_env | event_types | idempotency_key_source | timeout_sec | related |
|---|---|---|---|---|---|---|---|---|---|
| stripe_payment | stripe | /webhooks/stripe | hmac_sha256_payload | Stripe-Signature | STRIPE_WEBHOOK_SECRET | payment_intent.succeeded, payment_intent.payment_failed, charge.refunded | header:Stripe-Signature.timestamp + body.id | 30 | US-010, AC-014 |
| github_push | github | /webhooks/github | hmac_sha256_x_hub | X-Hub-Signature-256 | GITHUB_WEBHOOK_SECRET | push, pull_request | header:X-GitHub-Delivery | 30 | US-018 |
| toss_payment | toss | /webhooks/toss | hmac_sha256_b64 | TossPayments-Signature | TOSS_WEBHOOK_SECRET | PAYMENT_CONFIRMED, PAYMENT_CANCELED | header:Idempotency-Key (없으면 body.paymentKey) | 15 | AC-011 |
```

### 섹션 규약

| 필드 | 필수 | 규칙 |
|---|---|---|
| `webhook_id` | required | snake_case 전역 유일. operationId prefix (`receive{WebhookId}`) |
| `sender` | required | 외부 서비스 식별자 (소문자). adapter 매칭 키 |
| `endpoint` | required | `/webhooks/{id}` 형식 권장. impl-middleware 의 인증 가드 우회 (대신 서명 검증으로 대체) |
| `signature_alg` | required | enum: `hmac_sha256_payload` / `hmac_sha256_b64` / `hmac_sha1_x_hub` / `hmac_sha256_x_hub` / `rsa_sha256` / `none` (개발용만) |
| `signature_header` | required | 서명이 담긴 HTTP 헤더명 |
| `signature_secret_env` | required | env 변수명. 시크릿 자체 노출 금지 |
| `event_types` | optional | comma 구분 — handler 가 분기 처리할 이벤트 목록. 빈 값이면 모든 event 1개 handler 통과 |
| `idempotency_key_source` | required | webhook 의 고유 식별자 추출 규칙 — `header:NAME` 또는 `body.PATH` 또는 둘 결합 (`header:X.timestamp + body.id`) |
| `timeout_sec` | required | inbound handler 응답 timeout — sender 의 SLA 와 일치 |
| `related` | optional | US/AC/BR |

### `specflow:generate-ts` 변경

- 프롬프트: "§10 외부 연동·Webhook — PRD 의 'webhook', '결제 알림', '깃허브 이벤트', '메신저 봇' 키워드 흡수"
- 자가 점검:
  - "§10 모든 webhook 의 signature_alg / signature_header / signature_secret_env / idempotency_key_source 명시"
  - "signature_alg=none 은 개발 환경 한정 명시"
  - "endpoint 가 `/webhooks/{webhook_id}` 권장 패턴"
  - "webhook_id 마다 §3.2 fragment 에 `receive{WebhookIdCamel}` operationId 존재"

### ts-rules 신규 룰 (warning grace)

```markdown
## Webhook (warning — v1.x grace period)
58. §10 webhook 섹션 존재 — webhook 명시된 프로젝트만 의무. 부재 시 정상 (skill no-op)
59. webhook_id snake_case + 전역 유일 — 위반 시 warning
60. signature_alg 가 enum 값 — 그 외 warning
61. signature_alg=none 인데 production 환경에서 사용 의도 → warning ("개발 환경 한정")
62. signature_header / signature_secret_env 모두 명시 → 누락 시 warning
63. idempotency_key_source 가 header: / body. 또는 결합 형식 → 위반 시 warning
64. §10 의 webhook_id 마다 §3.2 fragment 에 `receive{WebhookIdCamel}` operationId 존재 → 누락 시 warning
65. timeout_sec 정수 + 1~120 범위 → 위반 시 warning
```

## 2. `backflow:impl-webhook` 스킬 계약

### 카드

| 항목 | 내용 |
|---|---|
| **Purpose** | TS §10 → inbound webhook controller (서명 검증 + idempotency-key 저장 + 리플레이 차단 + 비동기 dispatch) + sender 별 어댑터 + idempotency-key entity |
| **Reads (specflow)** | `specs/TS/*` §10 (필수), §3.2 (operationId 검증), §4 (`WEBHOOK_SIGNATURE_INVALID` / `WEBHOOK_REPLAY_DETECTED` / `WEBHOOK_TIMEOUT` 자동 추가 권고), §5 데이터 모델 (idempotency_key entity), §처리 흐름 (handler 후속 동작) |
| **Reads (registry/config)** | `.backflow/task-file-map.md`(있으면), `.backflow/service-registry.md`, `backend.md` (`webhook.*` 섹션 신설, `framework.*`, `database.orm`, `external_services.message_queue`) |
| **Writes** | controller / service / module(Nest) / DTO / idempotency-key entity / migration / signature adapter dir / handler dispatch — 정확한 path 는 `backend.md.structure` derive. 항상 생성: `webhook/signatures/types.ts`, `webhook/signatures/none.ts` (개발용). sender 별 adapter 는 `webhook/signatures/{sender}.ts`. dispatch 는 `webhook/dispatch.ts` (또는 framework 별) |
| **Storage Tier** | N/A — project code |
| **Depends on** | `map-tasks`, `impl-schema` (idempotency-key 테이블), `impl-error-codes` (WEBHOOK_* 권고), `impl-services` (handler 가 호출), `impl-integrations` (queue 연계). **`impl-controllers` / `impl-middleware` 와 책임 경계** (§2.1) |
| **Notes** | sender 식별자 영역: `webhook/signatures/{sender}.ts` 만. controller / service / dispatch / signatures/types.ts 에는 sender 식별자 직접 호출 금지 (어댑터 인터페이스 경유). `impl-middleware` 의 auth guard 는 webhook endpoint 우회 — 대신 서명 검증이 인증 역할 |

### 2.1 선행 skill 책임 경계

- **impl-controllers**: TS §10 의 webhook operationId 는 **stub/skip**. impl-webhook 이 처리. (Phase 1 (5) 동일 패턴)
- **impl-middleware**: webhook endpoint 의 인증 (JWT / session) 가드는 **bypass**. 대신 서명 검증 미들웨어 적용. middleware SKILL 본문에 명시 필요
- **impl-integrations**: 외부 서비스의 *outbound* 통합 (REST 호출 등) 은 그대로. inbound webhook 만 본 skill 책임. 메시지 큐 (Bull/Redis 등) 추상은 본 skill 이 dispatch 시 사용 — `impl-integrations` 가 정의한 큐 추상을 wrapping

### 2.2 실행 위치

```
impl-schema → impl-repositories → impl-error-codes → impl-observability
       │
       ▼
   impl-services → impl-controllers (webhook operationId skip) → impl-middleware (webhook bypass auth) → impl-integrations
       │
       ▼
   impl-file-upload (Phase 1 (5))
       │
       ▼
   impl-webhook   ★ Phase 1 (6)
       │
       ▼
   export-api-contract (webhook controller 흡수)
       │
       ▼
   generate-tests
```

### 2.3 `backend.md` 신규 키

```yaml
webhook:
  webhook_module_dir: "src/webhooks"
  signatures_subdir: "signatures"
  dispatch_file: "dispatch.ts"  # 또는 framework 별
  idempotency_table: "webhook_idempotency"
  idempotency_entity_path: "src/webhooks/idempotency.entity.ts"  # framework 별 derive
  idempotency_ttl_days: 30      # 같은 key 보존 기간 (이후 정리 cron — Phase 2)
  default_timeout_sec: 30
  bypass_auth_routes: ["/webhooks/**"]   # impl-middleware 가 참조
  signature_clock_skew_sec: 300          # 서명에 timestamp 포함 시 허용 시계 오차
  retry_status_code: 503                 # 일시적 처리 실패 시 sender 가 재시도하도록 반환할 status
  always_200_on_signature_pass: true     # 서명 통과 시 처리 성공·실패 무관 200 반환 (sender 재시도 방지). false 시 처리 실패 → retry_status_code
```

### 2.4 SignatureAdapter 인터페이스

```typescript
// webhook/signatures/types.ts
export interface SignatureVerifyInput {
  rawBody: Buffer | string;       // 파싱 전 원본 (서명 계산 일관성 보장)
  headers: Record<string, string | string[]>;
  secret: string;                 // env 에서 로드된 시크릿
  clockSkewSec: number;           // backend.md.webhook.signature_clock_skew_sec
}

export interface SignatureVerifyResult {
  valid: boolean;
  reason?: string;                // 실패 시 디버깅용 (production 응답엔 노출 금지)
  timestamp?: number;             // 추출된 timestamp (replay 검사용)
}

export interface SignatureAdapter {
  /** sender 식별자 — 단일 파일 1 sender */
  readonly sender: string;
  /** 지원하는 signature_alg 값 */
  readonly alg: string;
  verify(input: SignatureVerifyInput): SignatureVerifyResult;
}
```

각 sender 의 adapter (`signatures/stripe.ts`, `signatures/github.ts`, `signatures/toss.ts` 등) 가 sender SDK 또는 직접 hmac 구현. `signatures/none.ts` 는 개발용 — 항상 valid:true 반환 + warning log.

### 2.5 Controller / Service 동작

**모든 inbound webhook 의 공통 흐름**:

1. **rawBody 보존**: framework 의 body parser 가 JSON 파싱하기 **전** raw bytes 캡처 (서명 검증에 필요). NestJS `RawBodyMiddleware`, Express `express.raw`, FastAPI `Request.body()` 등 framework 별로 분기
2. **서명 검증**: `signatureAdapter.verify({ rawBody, headers, secret, clockSkewSec })` 호출. invalid → `WEBHOOK_SIGNATURE_INVALID` 에러 + 401/403 (sender 별 정책)
3. **timestamp 검사 (replay 차단 1)**: signature 에 timestamp 포함 시 `Math.abs(now - timestamp) > clockSkewSec` 면 reject
4. **idempotency-key 추출**: TS §10.idempotency_key_source 규칙으로 추출 (header:NAME / body.PATH / 결합)
5. **idempotency 검사 (replay 차단 2)**: idempotency_table 에 key 존재하면 → 이전 결과 그대로 반환 (200 + 동일 응답 body)
6. **idempotency 행 생성** (status: processing) — 같은 key 동시 도착 시 race 방지 (DB unique constraint)
7. **handler dispatch**: TS §10.event_types 분기 — sender·event_type 별 handler 호출. 결과 (success/failed) idempotency 행에 기록
8. **응답**:
   - `always_200_on_signature_pass=true` (default): 처리 성공/실패 무관 200 (sender 재시도 방지)
   - false: 처리 실패 시 `retry_status_code` (default 503) 반환

### 2.6 Idempotency entity canonical schema

| 필드 | 타입 | 비고 |
|---|---|---|
| `id` | UUID v7 | PK |
| `webhook_id` | text | TS §10.webhook_id (indexed) |
| `idempotency_key` | text | extract 결과 |
| `request_hash` | text? | rawBody 의 sha256 — 같은 key 다른 body 검출 |
| `status` | enum (`processing` / `complete` / `failed`) | |
| `response_body` | jsonb? | 첫 처리 결과 (replay 시 재사용) |
| `response_status` | int? | |
| `error` | text? | failed 시 |
| `expires_at` | timestamptz | created_at + ttl_days |
| `created_at`, `updated_at`, `completed_at?` | timestamptz | |

`UNIQUE(webhook_id, idempotency_key)` constraint.

### 2.7 vendor SDK 사용 — sender adapter 만

- `webhook/signatures/stripe.ts` 에서는 `import Stripe from 'stripe'` + `Stripe.webhooks.constructEvent` 호출 OK (또는 자체 hmac 구현)
- `webhook/signatures/github.ts` — `crypto.createHmac` 등 표준 라이브러리. `@octokit` SDK 의존 회피 권장
- 그 외 layer (controller / service / dispatch / signatures/types.ts) 에는 **sender 식별자 0건**

## 3. 동기화 메커니즘

```
TS §10 (source of truth)
TS §3.2 (operationId 검증)
TS §4 (WEBHOOK_* 권고)
       │
       ▼
   impl-webhook
       │
       ▼
   controller + service + dispatch + module + DTO + idempotency entity + signature adapters
       │
       ▼
   export-api-contract
       │
       ▼
   sync-api-client (frontend 자동 — 단 inbound webhook 은 보통 frontend 가 호출 안 함)
       │
       ▼
   validate-code §11
```

### 기각한 대안

| 대안 | 기각 이유 |
|---|---|
| **(a) 서명 검증을 service 본문에서** | controller/middleware 와 분리되어야 raw body 접근 가능. middleware 패턴 표준 |
| **(b) idempotency 를 메모리 캐시 (Redis only)** | 영구 보관 필요 (audit). DB 가 source of truth + Redis 는 옵션 |
| **(c) sender SDK 를 service 에서 직접** | 어댑터 패턴 표준 (Phase 1 (4)/(5) 동일) |
| **(d) 모든 webhook 을 단일 endpoint 에서 분기** | 서명 알고리즘이 sender 마다 다름. endpoint 분리가 표준 |
| **(e) always 200 강제 (실패 시에도)** | 일시적 장애에도 sender 가 재시도 안 함 — 손실. `retry_status_code` 옵션 제공 |
| **(f) handler 를 webhook 내부에서 동기 처리** | 30s timeout 초과 위험. queue dispatch 권장 (impl-integrations 의 큐 사용) |

## 4. validate-code §11 drift 룰 (5 sub-rule)

```yaml
입력:
  ts_section: specs/TS-*.md §10 외부 연동·Webhook
  service_registry: .backflow/service-registry.md
  webhook_dir: backend.md.webhook.webhook_module_dir
  signatures_dir: webhook_dir + "/" + backend.md.webhook.signatures_subdir
  idempotency_entity: backend.md.webhook.idempotency_entity_path
  vendor: (sender 별)

§11.1 — TS §10 ↔ controller/service 일관성:
  webhook_id_in_controller:
    - TS §10 의 모든 webhook_id 가 controller 핸들러/operationId 에 등장 → 누락 시 critical
  signature_alg_match:
    - controller/service 가 사용한 signature_alg 가 §10 명시값과 일치 → 불일치 시 critical
  signature_header_match:
    - controller 가 추출하는 서명 헤더가 §10.signature_header 와 일치 → 불일치 시 critical
  signature_secret_env_used:
    - service/dispatch 가 process.env[signature_secret_env] (또는 동등) 으로 secret 로드 → 미사용 시 critical
    - 시크릿이 코드에 hardcoded → critical (보안)
  idempotency_key_extraction:
    - controller/service 가 §10.idempotency_key_source 의 형식 (`header:X` / `body.Y` / 결합) 으로 key 추출 → 형식 불일치 시 critical
  raw_body_preserved:
    - 서명 검증 전에 rawBody 캡처 코드 (NestJS RawBodyMiddleware / Express express.raw / FastAPI Request.body) 존재 → 부재 시 critical (서명 깨짐)
  timestamp_replay_check:
    - signature_alg 가 timestamp 포함 (hmac_sha256_payload Stripe / GitHub 의 X-Hub-Signature 등) 일 때 clock skew 검증 부재 → warning
  related_error_codes:
    - TS §4 에 WEBHOOK_SIGNATURE_INVALID / WEBHOOK_REPLAY_DETECTED / WEBHOOK_TIMEOUT 부재 → warning ("권고 추가")

§11.2 — Sender 식별자 영역 검사:
  sender_identifier_in_layers:
    - controller / service / dispatch / signatures/types.ts 에 sender SDK import (`stripe`, `@octokit`, `@slack/`, sender 별 SDK) 또는 sender 직접 호출 등장 → critical
  sender_directory_exempt:
    - signatures/{sender}.ts 는 sender 식별자 검사 제외 + info
  signature_adapter_interface_compliance:
    - signatures/{sender}.ts 가 SignatureAdapter 인터페이스 (verify 메서드) 충족 → 불충족 시 critical
  none_adapter_dev_only:
    - signatures/none.ts 가 production 환경에서 활성화될 수 있는 분기 부재 → 기본값으로 critical (production 에서 검증 우회 위험)

§11.3 — Idempotency entity 일관성:
  required_fields:
    - id / webhook_id / idempotency_key / status / created_at / updated_at 모두 존재 → 누락 시 critical
  unique_constraint:
    - (webhook_id, idempotency_key) UNIQUE constraint → 부재 시 critical (race condition)
  status_enum_match:
    - status enum 이 [processing, complete, failed] → 추가/누락 시 warning
  ttl_handling:
    - idempotency_ttl_days > 0 인데 expires_at 필드 부재 → warning
  replay_uses_stored_response:
    - 같은 key 재도착 시 stored response_body / response_status 그대로 반환하는 코드 → 부재 시 critical (replay 처리 깨짐)

§11.4 — Middleware / 라우팅 책임 경계:
  webhook_routes_bypass_auth:
    - backend.md.webhook.bypass_auth_routes 에 명시된 경로가 impl-middleware 의 auth guard 에서 bypass 되지 않음 → critical (정상 webhook 이 401 받음)
  webhook_signature_middleware_applied:
    - bypass_auth_routes 의 경로에 SignatureVerify middleware (또는 동등) 적용 → 부재 시 critical (보안 hole)
  controller_no_duplication:
    - 사전 조건: service-registry 에 controller operationId 추적 정보 존재 시
    - generated_by != "impl-webhook" 인 controller 가 §10 webhook operationId 본문 구현 → warning ("impl-webhook 가 처리")
    - 추적 정보 부재 시: 휴리스틱 — controller 파일에서 webhook_id 매칭 핸들러 본문 비어있지 않으면 warning

§11.5 — Always-200 및 응답 처리:
  always_200_default:
    - backend.md.webhook.always_200_on_signature_pass=true 인데 실제 controller 에서 처리 실패 시 200 외 응답 → critical (sender 재시도 폭주 위험)
  retry_status_code_match:
    - always_200_on_signature_pass=false 일 때 처리 실패 응답이 backend.md.webhook.retry_status_code 와 일치 → 불일치 시 warning
  signature_failure_response:
    - 서명 검증 실패 시 401 또는 403 응답 → 그 외 (예: 200) 시 critical (보안)

예외:
  - TS §10 부재 (의도된 미사용 — webhook 없는 프로젝트) → §11 검사 전체 skip + info
  - signature_alg=none 인 webhook 이 NODE_ENV=development 에서만 동작하는 가드 존재 시 §11.2 none_adapter_dev_only 통과
```

## 5. 마이그레이션

### 5.1 Scenario A — 신규
TS §10 작성 → 전체 생성. idempotency 테이블 마이그레이션 실행

### 5.2 Scenario B — 기존 webhook 코드 산재
1. `--dry-run` grep: `crypto.createHmac`, `Stripe.webhooks.constructEvent`, `verifySignature`, `X-Hub-Signature`, `X-Slack-Signature` 등
2. webhook_id 추정 + signature_alg / source 추론
3. 사용자 승인 후 통합. 기존 코드 → adapter 패턴으로 refactor

### 5.3 Scenario C — sender 추가
새 sender 만 추가 → impl-webhook 이 기존 controller / service 보존하고 새 webhook_id handler + signatures/{newSender}.ts 만 추가

### 5.4 Scenario D — idempotency 가 이미 다른 형식으로 있음
1. `backend.md.webhook.idempotency_entity_path` 를 기존 entity 로
2. 호환 검사 — canonical schema 충족 시 보존
3. 비호환 시 사용자 confirm 후 신규 entity 추가 + 기존 데이터 마이그레이션 스크립트 stub

## 6. CONTRACTS.md 갱신

- `plugins/backflow/CONTRACTS.md`
  - 실행 순서: `impl-file-upload` → **`impl-webhook`** → `export-api-contract`
  - 스킬 카드 신설 (책임 경계 명시)
  - 공통 레지스트리: `backend.md.webhook.*`
  - specflow 역매핑: `TS §10 → impl-webhook`, `TS §3.2 → impl-webhook (operationId 검증)`, `TS §4 → impl-webhook (WEBHOOK_* 권고)`, `TS §5 → impl-webhook (idempotency entity)`, `TS §처리 흐름 → impl-webhook (handler dispatch)`
  - **impl-controllers 카드 Notes 갱신**: TS §10 webhook operationId 도 stub/skip
  - **impl-middleware 카드 Notes**: backend.md.webhook.bypass_auth_routes 의 경로는 auth guard bypass + signature middleware 적용
  - **impl-integrations 카드 Notes**: 큐 추상이 있으면 impl-webhook 이 dispatch 시 사용 (재구현 금지)
- `plugins/specflow/skills/generate-ts/SKILL.common.md` — §10 webhook 추가 + 자가 점검
- `plugins/specflow/skills/generate-ts/template.md` — §10 섹션
- `plugins/specflow/skills/validate/rules/ts-rules.md` — 룰 58~65

## 7. Future work

- **Outbound webhook dispatch** (우리가 외부에 보내는 webhook) — Phase 2 (`backflow:impl-webhook-dispatch`)
- **Webhook subscription 관리 API** (외부 서비스 구독 등록·해제) — Phase 2
- **Cron 정리 (만료된 idempotency 행 삭제)** — Phase 2
- **Dead-letter queue** (처리 실패한 webhook) — Phase 2
- **Webhook event sourcing / replay tooling** — Phase 2
- **gRPC / GraphQL subscription / SSE 수신** — 별도 패턴
- **다중 secret rotation** — Phase 2 (현재는 단일 secret)
- **Webhook test fixture 자동 생성** — Phase 2
- **Common webhook senders 어댑터 라이브러리** (Stripe / GitHub / Slack 5종 stable 어댑터) — Phase 2

## 8. 완료 기준 (Definition of Done)

### "ship"

- [ ] `specflow:generate-ts` §10 출력
- [ ] ts-rules 58~65
- [ ] `backflow:impl-webhook` controller / service / module / DTO / idempotency entity / migration / signatures/types.ts / signatures/none.ts + sender 별 어댑터 (TS 명시 시) + dispatch 생성. backend.md.structure 에서 path derive
- [ ] `backend.md.webhook.*` 신규 키
- [ ] SignatureAdapter 인터페이스 (verify / sender / alg)
- [ ] Controller 가 rawBody 보존 + 서명 검증 + idempotency 검사 + replay 시 stored response 반환
- [ ] `backflow:validate-code` §11 (5 sub-rule)
- [ ] CONTRACTS 갱신 (impl-controllers / impl-middleware / impl-integrations Notes)
- [ ] 1개 실프로젝트 E2E (가짜 sender + 서명 검증 + 같은 key 2회 도착 → 1회만 처리)

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

(Task C 없음 — impl-webhook 가 자체 controller/service 생성. 단 Task B 의 CONTRACTS 갱신에 다른 skill Notes 변경 포함)

Phase 1 (6) 전체 3 commit, 1주 소요.

## Phase 1 종합 — 본 phase 완료 시점

Phase 1 (1)~(6) 모두 완료. mandatory 영역 100%. 다음:
- Phase 1.5 dbflow (별도 plugin, 2~3주, velvetalk 포팅)
- Phase 2/3 (선택적 / 조직 표준)
