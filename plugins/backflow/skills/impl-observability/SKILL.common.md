---
name: impl-observability
description: TS의 §7.1 관측성을 structured logger·tracing·request-id middleware·ErrorMeta hook 으로 구현합니다. "관측성 구현", "로거 설정", "OpenTelemetry", "tracing" 요청 시 사용.
argument-hint: [기술 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
model: sonnet
---

# Observability 구현 (B-Obs)

ultrathink

당신은 백엔드 인프라 엔지니어입니다.
기술 명세서(TS)의 §7.1 관측성을 OpenTelemetry 표준 위에서 structured logger, tracing, middleware, ErrorMeta hook 으로 구현합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md) — `observability` 섹션 **필수**, `framework.language`
- **설계 문서**: `docs/designs/phase-1-observability.md` (프로젝트 루트에 있으면 참조)
- **태스크-파일 맵**: `.backflow/task-file-map.md` (있으면)

## 입력

$ARGUMENTS 에서:
1. **기술 명세서(TS)** → `§7.1 관측성` 4표 (필수 — 로깅·트레이싱; optional — Metrics SLI·상관관계)
2. **선택**: TS §4 에러 코드 맵 — `error_code_tag=true` 시 ErrorMeta hook 의 입력

## 태스크-파일 맵 준수

`.backflow/task-file-map.md`가 존재하면:
1. `impl_skill: impl-observability` 항목만 필터
2. `action: create` → 해당 경로에 새 파일 생성
3. `action: modify` → 기존 파일 보존하며 OTel hook 만 추가
4. 맵에 없는 파일은 생성하지 않음

맵이 없으면 `backend.md.observability.*` + 표준 경로(`src/observability/`, `src/middleware/`) 기준 독자 판단.

## ★ 실행 위치 — impl-error-codes 후, impl-services 전 ★

이 스킬은 **impl-services 보다 먼저** 실행되어야 함 — 서비스 코드가 logger 를 import 하기 때문.
**impl-error-codes 보다는 뒤** — ErrorMeta 를 hook 하기 위해.

실행 순서:
```
map-tasks → impl-schema → impl-repositories → impl-error-codes
                                                    │
                                                    ▼
                                          impl-observability  ★ services 전
                                                    │
                                                    ▼
                                          impl-services (logger import 가능)
                                                    │
                                                    ▼
                                          impl-controllers
                                                    │
                                                    ▼
                                          impl-middleware
                                          (AppExceptionFilter 가 tagError 호출 — Task C 에서 SKILL 정리)
```

`impl-middleware` 의 AppExceptionFilter 는 이 스킬이 만든 `tagError(exception)` 를 catch 시점에 호출 (Task C 에서 SKILL 정리).

## ★ 계약: OTel only — 출력 코드에 벤더명 0건 ★

이 스킬은 **OpenTelemetry SDK 와 OTLP exporter** 만 사용. Datadog/NewRelic/Honeycomb/Sentry 같은 벤더명은 생성 코드에 등장하지 않음. 벤더 라우팅은 OTel Collector 설정(배포 시점)이 담당.

이렇게 하면 사용자가 벤더 변경(예: Datadog → Tempo) 시 **프로젝트 코드 변경 0**, OTel Collector 설정 파일만 갱신.

## 입력 TS 포맷

기대하는 §7.1 4표 (`specflow:generate-ts` 템플릿 참조):

```markdown
## 7.1 관측성

### 로깅
| key | 값 |
| log_format | json |
| required_tags | service, environment, request_id, trace_id |
| sensitive_field_masking | password, token, ssn, card_number |
...

### 트레이싱
| trace_propagation | W3C Trace Context (`traceparent`) |
| sampling_rate_dev | 1.0 |
| sampling_rate_prod | 0.1 |
...

### Metrics (SLI) — optional, 누락 시 4 default 적용
| sli | type | unit | window |
...

### 상관 관계 — optional
- correlation_header: X-Request-Id
- error_code_tag: true
```

### Grace period (v1.x)

TS 에 §7.1 이 없으면 **fallback**:
1. 경고: "TS-{ID}.md 에 §7.1 관측성 섹션이 없습니다. specflow:generate-ts 재실행 권장."
2. 다음 default 로 동작:
   - log_format: json
   - required_tags: [service, environment, request_id, trace_id]
   - sensitive_field_masking: [password, token, ssn, card_number]
   - sampling_rate: dev 1.0 / prod 0.1
   - correlation_header: X-Request-Id
   - error_code_tag: true (TS §4 에러 코드 맵 존재 시)

## 언어·라이브러리 분기

`backend.md.framework.language` + `observability.logger` / `observability.tracing_lib` 기준:

| language | logger canonical 값 | logger 실제 패키지 | tracing canonical 값 | tracing 실제 패키지·도구 |
|---|---|---|---|---|
| TypeScript / Node | `pino` (default), `winston`, `bunyan` | `pino` / `winston` / `bunyan` | `otel-sdk-node` | `@opentelemetry/sdk-node` + `@opentelemetry/auto-instrumentations-node` |
| Python | `structlog` (default), `logging` | `structlog` / `logging` + `python-json-logger` | `opentelemetry-distro` | `opentelemetry-distro` (auto-instrumentation) |
| Go | `slog` (1.21+, default), `zerolog` | `log/slog` / `github.com/rs/zerolog` | `otel-go` | `go.opentelemetry.io/otel` + `go.opentelemetry.io/contrib/instrumentation/...` |
| Java / Kotlin | `slf4j-logback` (default) | SLF4J + Logback + `net.logstash.logback:logstash-logback-encoder` | `otel-java-agent` | `-javaagent:opentelemetry-javaagent.jar` (JVM agent) |
| Rust | `tracing` (default) | `tracing` + `tracing-subscriber` | `otel-rust` | `opentelemetry` + `opentelemetry-otlp` |

- `backend.md.observability.logger` / `tracing_lib` 의 **canonical 값**(왼쪽 컬럼) 을 사용. 실제 import 문은 skill 이 매핑.
- `framework.language` 에 Rust 가 없으면 `framework.name` 이 axum/actix 등 Rust 프레임워크인지 보고 추론, 또는 backend.md 에 Rust 추가하도록 사용자에게 권고.
- `backend.md.observability.logger` 가 명시되어 있으면 그 값을 우선 사용 (예: 기존 winston 보존).
- `observability.logger` 가 비어있고 `error_handling.logging` (deprecated) 에 값이 있으면 fallback 으로 읽고 migration 권고.

## 출력

### 0. Request Context Store (`backend.md.observability.context_file`, 기본 `src/observability/context.ts`)

`request_id` 가 middleware 부터 logger 까지 흐르려면 request-scoped store 가 필요. Node.js 는 `AsyncLocalStorage`, Python 은 `contextvars`, Java 는 `ThreadLocal` (또는 SLF4J MDC), Go 는 `context.Context` 사용.

**TypeScript** (`src/observability/context.ts`):

```typescript
// AUTO-GENERATED by backflow:impl-observability
import { AsyncLocalStorage } from 'node:async_hooks';

export type RequestStore = { request_id: string };
export const requestStore = new AsyncLocalStorage<RequestStore>();

export function getRequestId(): string | undefined {
  return requestStore.getStore()?.request_id;
}
```

**Python** (`src/observability/context.py`):

```python
import contextvars
request_id_var = contextvars.ContextVar('request_id', default=None)
def get_request_id():
    return request_id_var.get()
```

(Java/Kotlin 은 SLF4J MDC, Go 는 `context.Context` 로 자연 처리 — context.ts 별도 파일 불요. framework.language 별 분기.)

### 1. Structured Logger (`backend.md.observability.logger_file`, 기본 `src/observability/logger.ts`)

**TypeScript + pino** 예 (request_id 는 §0 의 store 에서 읽음):

```typescript
// AUTO-GENERATED by backflow:impl-observability from specs/TS-{ID}.md §7.1
// Re-run the skill to regenerate. Manual edits trigger validate-code warning.

import pino from 'pino';
import { trace } from '@opentelemetry/api';
import { getRequestId } from './context';

const logLevelEnv = '{{log_level_env}}'; // §7.1 로깅 표 log_level_env 값 (default: LOG_LEVEL)
const logLevelDefault = '{{log_level_default}}'; // default: info

export const logger = pino({
  level: process.env[logLevelEnv] ?? logLevelDefault,
  formatters: {
    level: (label) => ({ level: label }),
    log: (object) => {
      const span = trace.getActiveSpan();
      const sc = span?.spanContext();
      return {
        ...object,
        service: process.env.OTEL_SERVICE_NAME,
        environment: process.env.NODE_ENV,
        request_id: getRequestId(),  // §0 context 에서 읽음 → required_tags 의 request_id 충족
        trace_id: sc?.traceId,
        span_id: sc?.spanId,
      };
    },
  },
  redact: {
    paths: [
      // §7.1 sensitive_field_masking 컬럼 값으로 자동 채움
      'password', 'token', 'ssn', 'card_number',
      '*.password', '*.token',
    ],
    censor: '[REDACTED]',
  },
});
```

required_tags 가 4 base + optional_tags 를 가지면 모두 formatter 출력에 포함되도록 분기.

### 2. Request-ID + Trace Context Middleware (`backend.md.observability.request_id_middleware_file`, 기본 `src/middleware/request-id.ts`)

middleware 가 `requestStore.run(...)` 으로 다음 핸들러를 wrapping → logger 가 그 안에서 호출되면 자동으로 request_id 보임.

```typescript
// AUTO-GENERATED by backflow:impl-observability
import { v4 as uuidv4 } from 'uuid';
import { propagation, context as otelContext } from '@opentelemetry/api';
import { requestStore } from '@/observability/context';

const CORRELATION_HEADER = '{{correlation_header}}'; // backend.md.observability.correlation_header

export function requestIdMiddleware(req, res, next) {
  // 1. W3C Trace Context: incoming `traceparent` 보존 (있으면 OTel context 에 추출)
  const carrier = { traceparent: req.headers.traceparent };
  const ctx = propagation.extract(otelContext.active(), carrier);

  // 2. Correlation ID — request 단위 식별자
  const headerKey = CORRELATION_HEADER.toLowerCase();
  const requestId = (req.headers[headerKey] as string) ?? uuidv4();
  res.setHeader(CORRELATION_HEADER, requestId);
  req.requestId = requestId; // 필요한 컨슈머용

  // 3. AsyncLocalStorage 로 wrapping → 이후 모든 logger 호출이 request_id 자동 노출
  otelContext.with(ctx, () => {
    requestStore.run({ request_id: requestId }, () => next());
  });
}
```

framework 별 wrapper (각각 위 핵심 로직을 둘러쌈):
- **Express**: 위 함수 그대로 `app.use(requestIdMiddleware)`
- **NestJS**: `NestMiddleware` 인터페이스 구현 → `AppModule` 의 `configure(consumer) { consumer.apply(...).forRoutes('*') }`
- **Fastify**: `fastify.addHook('onRequest', ...)`
- **Spring Boot**: `OncePerRequestFilter` 확장 + SLF4J MDC.put('request_id', ...) (AsyncLocalStorage 대신)
- **FastAPI**: `BaseHTTPMiddleware` 또는 `@app.middleware('http')` 데코레이터 + contextvars

### 2.5 Bootstrap 등록 — main.ts / server.ts / app.module.ts (필수 단계)

skill 은 단순히 파일 만들고 끝나지 않음. **app entrypoint** 를 `backend.md.observability.bootstrap_file` 또는 framework convention 으로 탐색하여 다음을 추가:

```typescript
// app entrypoint (예: src/main.ts) — TS 의 첫 import 는 반드시 tracing 초기화
import './observability/tracing'; // OTel SDK가 다른 import 보다 먼저 등록되도록
import { NestFactory } from '@nestjs/core';
// ... 기존 import
```

middleware 등록은 framework 별:
- Express: `app.use(requestIdMiddleware)` — 다른 미들웨어보다 먼저
- NestJS: `app.use(requestIdMiddleware)` 또는 `AppModule.configure` 에서 `forRoutes('*')`
- Fastify: `fastify.addHook('onRequest', ...)`
- FastAPI: `app.add_middleware(...)` — 첫 미들웨어로
- Spring Boot: `@Component` 로 자동 등록 또는 `WebSecurityConfigurerAdapter`

**기존 entrypoint 가 이미 다른 tracing/middleware 를 등록하고 있으면 사용자에게 confirm 후 추가** (Scenario C/D 참조).

### 3. Tracing 초기화 (`backend.md.observability.tracing_file`, 기본 `src/observability/tracing.ts`)

```typescript
// AUTO-GENERATED by backflow:impl-observability
import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { TraceIdRatioBasedSampler } from '@opentelemetry/sdk-trace-node';
import { Resource } from '@opentelemetry/resources';
import { SemanticResourceAttributes } from '@opentelemetry/semantic-conventions';

const samplingRate =
  process.env.NODE_ENV === 'production'
    ? Number(process.env.OTEL_SAMPLING_RATE_PROD ?? '{{sampling_rate_prod}}')
    : Number(process.env.OTEL_SAMPLING_RATE_DEV ?? '{{sampling_rate_dev}}');

export const sdk = new NodeSDK({
  resource: new Resource({
    [SemanticResourceAttributes.SERVICE_NAME]: process.env.OTEL_SERVICE_NAME ?? '{{service_name}}',
    [SemanticResourceAttributes.DEPLOYMENT_ENVIRONMENT]: process.env.NODE_ENV ?? 'development',
  }),
  traceExporter: new OTLPTraceExporter({
    url: process.env.OTEL_EXPORTER_OTLP_ENDPOINT, // Collector 가 vendor 라우팅
  }),
  instrumentations: [getNodeAutoInstrumentations()],
  sampler: new TraceIdRatioBasedSampler(samplingRate),
});

sdk.start();
```

`{{...}}` 자리는 `backend.md.observability.*` 또는 TS §7.1 값으로 치환.

### 4. ErrorMeta Hook (`error_code_tag=true` 시; 기본 `src/observability/error-tag.ts`)

Phase 1 (1) ErrorCode 를 자동으로 log tag + span attribute 로 주입.

```typescript
// AUTO-GENERATED by backflow:impl-observability
import { trace } from '@opentelemetry/api';
import { logger } from './logger';
// import path 는 backend.md.error_handling.error_code_enum 에서 계산
//   예: src/errors/codes.ts → '@/errors/codes' (tsconfig path alias 시) 또는 './errors/codes' (상대)
import { ErrorCode, ErrorMeta } from '{{error_code_module_path}}';

export function tagError(error: { code: ErrorCode; message?: string }): void {
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

**Preflight**:
- `error_code_tag=false` → 이 파일 생성 스킵
- `error_code_tag=true` 인데 `backend.md.error_handling.error_code_enum` 파일 없거나 ErrorMeta export 가 없음 → **error 출력 + 사용자에게 `backflow:impl-error-codes` 선행 실행 요청**, 이 파일 생성 스킵
- 모두 있으면 import path 계산 후 생성

import path 계산 규칙 (TypeScript 기준):
1. `tsconfig.json` 에 `paths` alias 가 있고 그 alias 가 `error_code_enum` 경로를 커버하면 alias 사용 (`@/errors/codes`)
2. 아니면 출력 파일 디렉토리 기준 상대 경로 (`./errors/codes` 또는 `../../errors/codes`)
3. 모호하면 사용자에게 prompt

`impl-middleware` 의 AppExceptionFilter 가 catch 시점에 `tagError(exception)` 호출 — Task C SKILL 정리에서 명시.

### 5. Default Metrics SLI — Phase 2 로 이전

> **Plan 변경 (2026-04-25 codex review XR-009)**: instrumentation 까지 가려면 framework 별 hook 으로 record/add 호출을 심어야 해서 단일 스킬 범위 초과. Phase 1 (2) 에서는 **Metrics 코드 생성 안 함**. TS §7.1 의 Metrics SLI 표는 specflow 가 캡처는 하되 impl 은 Phase 2 별도 skill (`backflow:impl-metrics`) 에서 수행.

이 스킬은 Metrics SLI 표를 **읽지 않음**. 로그·트레이스·ErrorMeta hook 까지만 책임.

### 6. `.env.example` append (멱등성 보장 — 이미 있으면 추가 안 함)

```bash
# AUTO-APPENDED by backflow:impl-observability
LOG_LEVEL=info
OTEL_SERVICE_NAME=
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318  # OTel Collector. 벤더는 Collector 설정으로
OTEL_SAMPLING_RATE_DEV=1.0
OTEL_SAMPLING_RATE_PROD=0.1
```

## 머지 전략

### Scenario A — 완전 신규
4-5종 파일 생성 + `.env.example` append. 끝.

### Scenario B — `console.log` / `print()` 산재

1. Grep: 비표준 로그 호출 위치 수집 (`console.log`, `console.warn`, `console.error`, `print(`, `System.out`, `fmt.Println`, `printf`, `puts`)
2. **`--dry-run`**: codemod 후보 표 출력 (위치 / 제안 logger 호출 / 추정 log level)
3. 사용자 승인 시: 위치별 `Edit` 로 `logger.{info|warn|error}(...)` 로 치환 (각 변경 사용자 확인). 10회 이상 시 배치 요약 후 일괄 처리.

### Scenario C — 기존 logger 가 있음

1. `backend.md.observability.logger` 에 기존 라이브러리 명시 (winston / bunyan / log4js 등)
2. **Deprecated fallback**: `observability.logger` 가 비어있고 `error_handling.logging` 이 있으면 거기 값을 fallback 으로 읽고 사용자에게 migration 권고
3. **추가 코드 검색** (사용자가 backend.md 에 명시하지 않은 경우): `pino(`, `winston.createLogger`, `LoggerModule.forRoot`, `bunyan.createLogger`, `structlog.get_logger`, `log/slog` import, `LoggerFactory.getLogger` 패턴
4. skill 은 OTel 초기화·middleware·error-tag 만 생성. logger 본체는 보존.
5. 기존 logger 에 trace_id + request_id 자동 주입 hook 만 추가:
   - winston → custom format 추가
   - bunyan → serializer 추가
   - structlog → processor chain
   - SLF4J/Logback → MDC + LogstashEncoder
6. 충돌 시 사용자 확인

### Scenario D — 기존 OTel 초기화가 이미 있음

**중복 감지 패턴** (Grep 으로 검색):
- `sdk.start()`
- `new NodeSDK(`
- `NodeTracerProvider.register`
- `registerInstrumentations`
- `OTEL_*` 가 entrypoint 에서 import 되는지
- Python: `opentelemetry-instrument` 또는 `OpenTelemetryMiddleware` import
- Java: `-javaagent:` JVM 옵션 또는 `OpenTelemetrySdk.builder()`
- Spring: `@EnableAutoConfiguration` 의 OTel starter

위 패턴 중 하나라도 발견되면:
1. 일치 (sampler / exporter / resource attributes 가 §7.1 과 같음) → no-op + info 메시지
2. 불일치 → 사용자 확인 후 어느 쪽 유지할지 결정. **두 sdk.start() 동시 실행 방지** 가 필수 — 이미 있으면 새 sdk init 추가하지 않고 sampler/exporter 만 patch 권고.

## 교차 검증

- `required_tags` 가 logger 출력에 모두 포함되는지 (logger config 의 `formatters.log` / serializer 검사)
- `sensitive_field_masking` 패턴이 logger redact 에 반영되었는지
- `sampling_rate` 가 tracing init 에 명시되었는지
- `error_code_tag=true` 일 때 `error-tag.ts` 가 생성되었는지
- `.env.example` 에 OTel env 변수 5종 모두 존재

## 멱등성

- 모든 출력 파일 상단 `// AUTO-GENERATED` 주석
- 재실행 시 사람이 편집한 영역 감지 → 중단 + 경고. `--force` 시 덮어쓰기
- `.env.example` 은 키 단위 idempotent (이미 있으면 skip, 없으면 append)

## 품질 자가 점검

- [ ] TS §7.1 의 mandatory 표(로깅·트레이싱) 가 구현에 반영 (Metrics SLI 는 Phase 2 — 이 스킬 범위 외)
- [ ] **request_id 가 logger 출력에 실제로 등장** (context store 또는 MDC 경로로 middleware 와 연결됨)
- [ ] required_tags 의 4 base 태그(service / environment / request_id / trace_id) + optional_tags 가 logger 출력에 포함
- [ ] sensitive_field_masking 패턴이 logger redact 에 반영 (TS 컬럼의 모든 패턴 포함)
- [ ] log_format 이 json 또는 text 로 logger 설정됨
- [ ] log_level_default / log_level_env 가 logger init 에 반영
- [ ] tracing 의 sampling_rate_dev / sampling_rate_prod 가 env 분기로 적용
- [ ] OTLP exporter URL 이 env 변수(`OTEL_EXPORTER_OTLP_ENDPOINT`) 로 주입
- [ ] correlation_header (TS §상관관계 또는 default `X-Request-Id`) middleware 가 incoming header 보존 + 없으면 UUID 생성
- [ ] `traceparent` 헤더가 incoming 시 OTel context 에 추출 (W3C Trace Context 호환)
- [ ] **app entrypoint(main.ts/server.ts/app.module.ts) 에 tracing 첫 import + middleware 등록 완료**
- [ ] error_code_tag=true 일 때 error-tag.ts 생성 + 정확한 ErrorMeta import path 계산
- [ ] error_code_tag=true 인데 §4 또는 codes.ts ErrorMeta 부재 시 error-tag.ts 생성 스킵 + 사용자에게 impl-error-codes 선행 권고
- [ ] 출력 코드 어디에도 벤더명(Datadog/NewRelic/Sentry/Honeycomb 등) 등장 0건
- [ ] AUTO-GENERATED 주석 모든 출력 파일에 포함
- [ ] `.env.example` 에 OTel 5 변수 idempotent append
- [ ] Scenario B 면 codemod 변경마다 사용자 확인
- [ ] Scenario C 면 deprecated `error_handling.logging` fallback 처리됨
- [ ] Scenario D 면 중복 sdk.start() 방지 (기존 OTel init 감지 시 새 init 추가 안 함)
- [ ] impl-middleware 가 이후 `tagError(exception)` 호출하도록 Task C 에서 정리됨을 문서화
