# Phase 1 (2) — Observability Skill 설계

> **Generated**: 2026-04-25
> **Scope**: Phase 1 두 번째 항목 — `backflow:impl-observability` 신설 + `specflow:generate-ts §비기능 요구사항` 의 관측성 부속 섹션 의무화 + `backflow:validate-code` 의 새 drift 룰
> **Parent roadmap**: `docs/plugin-gaps-and-plan.md` §3.3 (2)
> **Companion design**: `docs/designs/phase-1-error-contract.md` (Phase 1 (1)) — 본 문서와 패턴 동일
>
> **Revision (2026-04-25, Task B codex review)**:
> - 실행 위치 변경 — impl-observability 가 **impl-services 보다 먼저** 실행 (services 가 logger import).
> - Metrics SLI 는 Phase 1 (2) 에서 **Phase 2 로 이전** (`backflow:impl-metrics` 별도 skill).
> - 출력 파일 추가 — `src/observability/context.ts` (AsyncLocalStorage / contextvars / MDC) 와 app entrypoint 수정 (tracing 첫 import + middleware 등록).
> - backend.md `observability.bootstrap_file` / `context_file` 필드 추가, `log_level_*` / `optional_tags` / `trace_propagation` 노출.

## 목표

Backend 에 **structured logging + distributed tracing + 기본 metrics** 를 일관된 표준(OpenTelemetry) 으로 도입하고, 프로젝트가 어떤 관측 벤더를 쓰든 **프로젝트 코드 변경 없이** 옮길 수 있게 한다. ErrorCode (Phase 1 (1)) 를 자동 log tag 로 주입해 에러 추적이 즉시 가능하게.

### Non-goals

- Frontend RUM·tracking — Phase 1 (4) `frontflow:impl-tracking` 범위
- 비즈니스 KPI metrics (가입수·결제 성공률 등) — 도메인 측면 / impl-services 책임
- 알람·SLO 정의 — Observability 대시보드 IaC (Phase 3)
- 로그 보관·검색·시각화 인프라 — 배포 시점 결정 (OTel Collector 설정)
- 벤더(Datadog / NewRelic / Sentry) 별 분기 코드 — Skill 출력에 벤더명 0건

## 1. TS 포맷 변경 — `§비기능 요구사항.관측성` 의무화

`specflow:generate-ts` 출력의 §비기능 요구사항 (현재 §7) 하위에 **관측성** 부속 섹션 추가. 기존 §비기능에 prose 로 흩어진 "로깅", "p95 응답시간 모니터링" 같은 표현을 구조화 항목으로 흡수.

### 섹션 포맷

```markdown
## 7. 비기능 요구사항

### 7.1 관측성

#### 로깅
| key | 값 |
|---|---|
| log_format | json |
| log_level_default | info |
| log_level_env | LOG_LEVEL |
| required_tags | service, environment, request_id, trace_id, user_id?, error_code? |
| sensitive_field_masking | password, token, ssn, card_number |

#### 트레이싱
| key | 값 |
|---|---|
| trace_propagation | W3C Trace Context (`traceparent`) |
| sampling_strategy | head-based, ratio |
| sampling_rate_dev | 1.0 |
| sampling_rate_prod | 0.1 |
| custom_spans | DB 쿼리, 외부 호출, 비동기 작업 enqueue |

#### Metrics (SLI)
| sli | type | unit | window |
|---|---|---|---|
| http_request_duration_seconds | histogram | seconds | 1m |
| http_requests_total | counter | requests | - |
| db_query_duration_seconds | histogram | seconds | 1m |
| external_call_duration_seconds | histogram | seconds | 1m |

#### 상관 관계
- correlation_header: `X-Request-Id` (없으면 middleware 가 생성). `Traceparent` 는 trace_propagation 전용 — 혼용 금지
- error_code_tag: true (Phase 1 (1) ErrorCode 자동 주입)
```

### 섹션 규약

| 필드 | 필수 | 비고 |
|---|---|---|
| 로깅 | required | log_format / required_tags 필수, 나머지 default 적용 |
| 트레이싱 | required | sampling_rate_prod 누락 시 0.1 default |
| Metrics SLI | optional | 명시 없으면 skill 이 기본 4종(요청 latency·count, DB latency, 외부 호출 latency) 만 생성 |
| 상관 관계 | optional | 누락 시 `correlation_header: X-Request-Id` + `error_code_tag: true` default |

**용어 통일**: `error_code_tag` (boolean) — TS 섹션·backend.md config·ts-rules 모두 같은 키 사용.

### `specflow:generate-ts` 변경

- 프롬프트에 "§비기능 요구사항.관측성 섹션 반드시 포함" 추가
- 자가 점검 체크리스트에 "관측성 표 4종(로깅/트레이싱/Metrics/상관관계) 존재" 추가
- 기존 prose("p95 < 2초", "에러 로깅") 가 있으면 자동으로 구조화 표 초안 제안

### `specflow:validate/rules/ts-rules.md` 신규 룰 (warning — v1.x grace)

```markdown
## 관측성 (warning — v1.x grace; v2.0 critical 승격)
33. §7.1 관측성 섹션 존재 — 누락 시 warning + skill 은 기본 OTel 설정으로 동작
34. log_format 값이 json 또는 text — 그 외 warning
35. required_tags 에 trace_id 포함 — 누락 시 warning (분산 추적 연결 끊김)
36. sampling_rate_prod 가 0.0~1.0 범위 — 위반 시 warning
37. correlation_header 명이 X-Request-Id / X-Correlation-Id / Traceparent 중 하나 — 그 외 사용 시 review 권고
```

## 2. `backflow:impl-observability` 스킬 계약

### 카드

| 항목 | 내용 |
|---|---|
| **Purpose** | TS §관측성 → structured logger 설정 + tracing SDK 초기화 + middleware + ErrorMeta 자동 tag 주입 |
| **Reads (specflow)** | `specs/TS/*` §7.1 관측성 (필수), §4 에러 코드 맵 (Phase 1 (1) 산출 — error_code_tag 주입용) |
| **Reads (registry/config)** | `.backflow/task-file-map.md`(있으면), `backend.md` (`observability.*` 섹션, `framework.language`) |
| **Writes** | `src/observability/logger.ts`, `src/middleware/request-id.ts`, `src/observability/tracing.ts`, `src/observability/error-tag.ts`(ErrorMeta hook), `.env.example` 업데이트 |
| **Storage Tier** | N/A — project code |
| **Depends on** | `map-tasks`. `impl-error-codes` 보다 **뒤에** 실행 (ErrorMeta 를 hook). `impl-middleware` 와 **병렬 가능** (tracing middleware 가 impl-middleware 의 다른 미들웨어와 충돌 없음) |
| **Notes** | OTel only — 출력 코드에 벤더명 등장 0건. 언어별 logger·tracing 라이브러리 분기. AUTO-GENERATED 주석 멱등성. |

### 실행 위치 (revised after Task B review)

```
map-tasks
   │
   ▼
impl-schema → impl-repositories → impl-error-codes
                                       │
                                       ▼
                               impl-observability  ★ services 보다 먼저
                                       │ (consumed by services / middleware)
                                       ▼
                               impl-services (logger import)
                                       │
                                       ▼
                               impl-controllers
                                       │
                                       ▼
                               impl-middleware (HTTP_STATUS_MAP + tagError import)
                                       │
                                       ▼
                               impl-integrations
                                       │
                                       ▼
                               generate-tests (assertion: required_tags · trace_id 가 로그에 존재)
```

### `backend.md` 신규 키

```yaml
observability:
  logger: ""              # pino | winston | bunyan | structlog | slog | logback (language 별 default)
  tracing_lib: ""         # otel-sdk-node | opentelemetry-distro | otel-java-agent | otel-rust ...
  log_format: "json"      # json | text(dev only)
  sampling_rate: 1.0      # 0.0~1.0 (production override 는 env var)
  required_tags: ["service", "environment", "request_id", "trace_id"]
  error_code_tag: true    # ErrorCode 자동 log tag 주입
  correlation_header: "X-Request-Id"
  service_name: ""        # OTel resource attribute (없으면 framework.name 사용)
  environment_var: "NODE_ENV"  # 환경 식별 env 변수명
  otel_endpoint_env: "OTEL_EXPORTER_OTLP_ENDPOINT"  # OTel Collector 위치 (env 로 주입)
```

### 언어·라이브러리 분기

| language | logger default | tracing default |
|---|---|---|
| TypeScript / Node | `pino` (또는 winston/bunyan 보존) | `@opentelemetry/sdk-node` + auto-instrumentations |
| Python | `structlog` (또는 std `logging` + python-json-logger) | `opentelemetry-distro` (auto-instrumentation) |
| Go | `log/slog` (1.21+) 또는 zerolog | `go.opentelemetry.io/otel` |
| Java / Kotlin | SLF4J + Logback (`logstash-logback-encoder`) | OTel Java agent (`-javaagent:opentelemetry-javaagent.jar`) |
| Rust | `tracing` + `tracing-subscriber` | `opentelemetry-rust` |

기존 logger 가 이미 있으면 보존. 새 OTel 초기화만 추가.

## 3. 동기화 메커니즘 — TS as source of truth (단방향)

Phase 1 (1) 와 같은 패턴이지만 **backend 단독** 이라 cross-plugin 검증은 없음.

```
specs/TS/*.md
§7.1 관측성
     │
     ▼
impl-observability
     │
     ▼
src/observability/* + middleware
```

### Frontend 호환 — `traceparent` passthrough 만 명시

backend 의 request-id middleware 가:
1. incoming request 의 `traceparent` 헤더 존재 여부 확인
2. 있으면 OTel context 에 그대로 주입 (W3C Trace Context 표준 따름)
3. 없으면 새 trace ID 생성

이렇게 하면 미래 Phase 1 (4) frontend tracking 이 도입될 때 frontend 가 보낸 trace ID 가 자동으로 backend 와 연결됨. **이번 Phase 에서는 frontend 측 코드 생성 없음.**

### Drift 방지

Phase 1 (1) 와 동일 패턴 — `backflow:validate-code` 의 새 §8 룰:
- TS §7.1 의 `required_tags` 가 logger config 에 모두 존재하는가
- `sensitive_field_masking` 패턴이 logger middleware 에 존재하는가
- `sampling_rate` 가 tracing 초기화 코드에 명시되었는가
- ErrorMeta hook 이 활성화되었는가 (`error_code_tag: true` 시)
- `console.log` / `print()` / `System.out.println` 등 비표준 로그 호출 검출 → critical

## 4. 출력 파일 예시

### 4.1 `src/observability/logger.ts` (TypeScript + pino)

```typescript
// AUTO-GENERATED by backflow:impl-observability from specs/TS-{ID}.md §7.1
// Re-run the skill to regenerate. Manual edits trigger validate-code warning.

import pino from 'pino';
import { trace, context } from '@opentelemetry/api';

const REQUIRED_TAGS = ['service', 'environment', 'request_id', 'trace_id'];

export const logger = pino({
  level: process.env.LOG_LEVEL ?? 'info',
  formatters: {
    level: (label) => ({ level: label }),
    log: (object) => {
      const span = trace.getActiveSpan();
      const spanContext = span?.spanContext();
      return {
        ...object,
        service: process.env.OTEL_SERVICE_NAME,
        environment: process.env.NODE_ENV,
        trace_id: spanContext?.traceId,
        span_id: spanContext?.spanId,
      };
    },
  },
  redact: {
    paths: ['password', 'token', 'ssn', 'card_number', '*.password', '*.token'],
    censor: '[REDACTED]',
  },
});
```

### 4.2 `src/middleware/request-id.ts` (NestJS / Express)

```typescript
// AUTO-GENERATED by backflow:impl-observability
import { v4 as uuidv4 } from 'uuid';
import { propagation, context as otelContext } from '@opentelemetry/api';

export function requestIdMiddleware(req, res, next) {
  // W3C Trace Context: incoming `traceparent` 가 있으면 그대로 사용
  const carrier = { traceparent: req.headers.traceparent };
  const ctx = propagation.extract(otelContext.active(), carrier);

  // Correlation ID (request-id): 없으면 생성
  const requestId = req.headers['x-request-id'] ?? uuidv4();
  res.setHeader('x-request-id', requestId);
  req.requestId = requestId;

  otelContext.with(ctx, () => next());
}
```

### 4.3 `src/observability/tracing.ts`

```typescript
// AUTO-GENERATED by backflow:impl-observability
import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { TraceIdRatioBasedSampler } from '@opentelemetry/sdk-trace-node';
import { Resource } from '@opentelemetry/resources';
import { SemanticResourceAttributes } from '@opentelemetry/semantic-conventions';

const samplingRate = process.env.NODE_ENV === 'production' ? 0.1 : 1.0;

export const sdk = new NodeSDK({
  resource: new Resource({
    [SemanticResourceAttributes.SERVICE_NAME]: process.env.OTEL_SERVICE_NAME ?? 'app',
    [SemanticResourceAttributes.DEPLOYMENT_ENVIRONMENT]: process.env.NODE_ENV ?? 'development',
  }),
  traceExporter: new OTLPTraceExporter({
    url: process.env.OTEL_EXPORTER_OTLP_ENDPOINT, // Vendor agnostic — Collector 가 라우팅
  }),
  instrumentations: [getNodeAutoInstrumentations()],
  sampler: new TraceIdRatioBasedSampler(samplingRate),
});

sdk.start();
```

### 4.4 `src/observability/error-tag.ts` — ErrorMeta hook (Phase 1 (1) 연계)

```typescript
// AUTO-GENERATED by backflow:impl-observability
// Phase 1 (1) ErrorCode 를 자동으로 log tag + span attribute 로 주입.
import { trace } from '@opentelemetry/api';
import { logger } from './logger';
import { ErrorCode, ErrorMeta } from '@/errors/codes';

export function tagError(error: { code: ErrorCode; message?: string }) {
  const meta = ErrorMeta[error.code];
  const span = trace.getActiveSpan();
  span?.setAttributes({
    'error.code': error.code,
    'error.domain': meta?.domain,
    'error.http_status': meta?.httpStatus,
    'error.retriable': meta?.retriable,
  });
  logger.error({
    error_code: error.code,
    error_domain: meta?.domain,
    error_message: error.message,
  });
}
```

`backflow:impl-middleware` 의 AppExceptionFilter 가 catch 시점에 `tagError(exception)` 호출 — 후속 housekeeping 에서 SKILL 정리.

### 4.5 (revision) Request Context Store — `src/observability/context.ts`

middleware 의 `req.requestId` 가 logger 까지 도달하려면 request-scoped store 가 필요. 언어별 메커니즘:
- Node.js: `AsyncLocalStorage`
- Python: `contextvars`
- Java/Kotlin: SLF4J `MDC` + `ThreadLocal`
- Go: `context.Context` (별도 파일 불요)
- Rust: `tracing` 자체가 스팬 컨텍스트 제공 (별도 파일 불요)

middleware 가 `requestStore.run({ request_id }, () => next())` 형태로 wrapping → logger formatter 가 `getRequestId()` 호출.

### 4.6 (revision) App Entrypoint 수정

skill 은 `backend.md.observability.bootstrap_file` (또는 framework convention 으로 탐색) 에 두 가지를 추가:
1. **tracing 첫 import**: `import './observability/tracing';` 가 다른 import 보다 먼저
2. **middleware 등록**: framework 별 (Express `app.use`, Nest `consumer.apply`, Fastify `addHook`, FastAPI `add_middleware`, Spring `@Component` filter)

기존 entrypoint 에 다른 tracing/middleware 가 이미 있으면 사용자 confirm.

### 4.7 `.env.example` 업데이트

```bash
# AUTO-APPENDED by backflow:impl-observability
LOG_LEVEL=info
OTEL_SERVICE_NAME=
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318  # OTel Collector. 벤더는 Collector 설정으로
```

## 5. 마이그레이션

### 5.1 Scenario A — 완전 신규
4종 파일 모두 생성. `.env.example` append.

### 5.2 Scenario B — `console.log` / `print()` 산재
1. Grep: 비표준 로그 호출 위치 수집 (`console.log`, `console.warn`, `console.error`, `print(`, `System.out`, `fmt.Println`)
2. **`--dry-run`**: codemod 후보 표 출력 (위치 / 제안 logger 호출 / 추정 log level)
3. 사용자 승인 시: 위치별 `Edit` 로 `logger.{info|warn|error}(...)` 로 치환 (각 변경 시 사용자 확인)

### 5.3 Scenario C — 기존 logger 가 있음
1. `backend.md.observability.logger` 에 기존 라이브러리 명시
2. skill 은 OTel 초기화·middleware·error-tag 만 생성 (logger.ts 는 기존 보존)
3. 기존 logger 에 trace_id 자동 주입 hook 만 추가 (라이브러리별로 다름):
   - pino → `formatters.log`
   - winston → custom format
   - structlog → processor chain
4. 충돌 시 사용자 확인

## 6. CONTRACTS.md 갱신 필요 사항

이 skill 추가 시 같은 PR/커밋에서 동반:

- `plugins/backflow/CONTRACTS.md`
  - 실행 순서 다이어그램에 `impl-observability` 추가 (impl-error-codes 후, impl-middleware 와 병렬)
  - 스킬별 계약 섹션에 `impl-observability` 카드
  - 공통 레지스트리 테이블에 `backend.md.observability.*` 키 그룹
  - specflow 역매핑 테이블에 "TS §7.1 관측성 → impl-observability" 추가
- `plugins/specflow/.../validate/rules/ts-rules.md` 신규 룰 33~37 (warning grace)
- `plugins/backflow/skills/impl-middleware/SKILL.common.md` AppExceptionFilter 가 `tagError(exception)` 호출하도록 갱신 (Phase 1 (1) housekeeping 후속)

## 7. 오픈 질문 / Future work

- **Metrics SLI 구현 (Phase 2 로 이전)** — `backflow:impl-metrics` 별도 skill. histogram/counter 정의 + framework 별 record/add hook (HTTP middleware, DB query interceptor, external call wrapper). TS §7.1 의 Metrics 표는 이 skill 의 입력으로 그대로 재사용.
- **Sentry 어댑터** — error-only 측면이 OTel 과 다소 분리됨. Phase 2 어댑터 후보 (`backflow:impl-error-tracking-sentry`).
- **Profiling / Continuous profiling** (Pyroscope, Polar Signals) — Phase 2.
- **Custom business metrics** — 로그인 성공률 등. Phase 2 metrics skill 의 확장.
- **Frontend RUM** — Phase 1 (4) `frontflow:impl-tracking` 에서 다룸. `traceparent` passthrough 가 backend 측 호환 보장.
- **Log routing / multi-destination** — OTel Collector 설정 영역. Skill 외 영역.
- **PII / GDPR** — `redact` 기본 5종(password / token / ssn / card_number / email?) 외 도메인별 추가는 사용자 선언. `backend.md.observability.sensitive_field_masking` 확장.
- **Sampling 전략 고도화** — head-based ratio 외에 tail-based, error-priority, parent-based. Phase 2.

## 8. 완료 기준 (Definition of Done)

### Phase 1 (2) "ship" 조건

- [ ] `specflow:generate-ts` 가 §7.1 관측성 섹션 포함해 출력
- [ ] `specflow:validate` ts-rules 33~39 추가 (warning grace; 1번 fix 후 33~39 가 됨)
- [ ] `backflow:impl-observability` 실행 시 5종 파일(context / logger / request-id middleware / tracing / error-tag) + `.env.example` 갱신 + **app entrypoint 수정**
- [ ] `backend.md.observability.*` 신규 키 추가 (bootstrap_file / context_file 포함)
- [ ] ErrorMeta hook 으로 `tagError` 가 `error.code` span attribute + log field 주입 확인
- [ ] `traceparent` passthrough 동작 (incoming header → outgoing trace context)
- [ ] **request_id** 가 middleware → context store → logger 까지 흐르는 것 실 로그에서 확인
- [ ] `backflow:validate-code` §8 drift 룰 추가 (required_tags / masking / sampling / error_code_tag / 비표준 로그 호출 검출)
- [ ] `backflow/CONTRACTS.md` 갱신 (실행 순서 다이어그램 변경 반영)
- [ ] `impl-middleware` AppExceptionFilter 가 tagError 호출하도록 housekeeping
- [ ] 최소 1개 실프로젝트(이 레포 또는 velvetalk)에서 E2E 적용 — TS 작성 → impl 실행 → 실 로그 출력에서 `trace_id` / `request_id` / `error_code` 확인

### "stable" 조건

- 2개 이상 프로젝트에서 실사용
- 시나리오 A/B/C 마이그레이션 각각 최소 1회 성공
- TS-rules 33~37 grace → critical 승격

## 9. 다음 작업 (이 설계 문서 머지 후)

Phase 1 (1) 와 동일한 4-step 패턴:

1. **Task A** — `specflow:generate-ts` 프롬프트 + ts-rules 33~37 추가
2. **Task B** — `backflow:impl-observability` skill 신설 + `backend.md.observability` 섹션 + CONTRACTS.md 갱신
3. **Task C** — `backflow:impl-middleware` 의 AppExceptionFilter 가 `tagError` 호출하도록 housekeeping (Phase 1 (1) 와 동일 패턴, 작은 커밋)
4. **Task D** — `backflow:validate-code` §8 drift 룰 추가

Phase 1 (2) 전체 예상 4 커밋, 1~2주 소요.
