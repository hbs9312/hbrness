---
name: validate-code
description: 생성된 백엔드 코드의 품질을 검증합니다. "코드 검증", "코드 리뷰" 요청 시 사용.
argument-hint: [검증할 파일 또는 디렉토리 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write]
effort: high
---

# 코드 품질 검증 (BV1)

ultrathink

생성된 백엔드 코드가 프로젝트 컨벤션과 품질 기준을 충족하는지 검증합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md)
- **태스크-파일 맵**: `.backflow/task-file-map.md` (있으면)

## 입력

$ARGUMENTS 의 파일/디렉토리를 Read/Glob으로 읽으세요.

## ★ frontflow FV1과 동일한 비격리 원칙 ★

코드 검증은 "어떤 서비스를 어떤 맥락에서 만들었는지"를 알아야 정확합니다.
specflow V 스킬처럼 `context: fork`하지 않습니다.

## 검증 항목

### 1. 컨벤션 준수 (critical)

```yaml
파일 위치:
  - 엔티티가 backend.md의 entity_dir 하위에 있는가
  - 서비스가 service_dir 하위에 있는가
  - 컨트롤러가 controller_dir 하위에 있는가
  - module_pattern(flat/feature-module/domain-driven)과 일치하는가

네이밍:
  - 파일명이 backend.md의 naming 컨벤션을 따르는가
  - 클래스명이 파일명과 일치하는가 (speaker.service.ts → SpeakerService)

구조:
  - 계층 분리: 컨트롤러→서비스→리포지토리 방향으로만 의존
  - 순환 의존 = 0건
  - 리포지토리가 서비스를, 서비스가 컨트롤러를 import하지 않는가
```

### 2. 계층 경계 (critical)

```yaml
컨트롤러 침범:
  - 컨트롤러에 비즈니스 로직(조건 분기, 계산)이 있는가
  - 컨트롤러에서 리포지토리를 직접 호출하는가

서비스 침범:
  - 서비스에 HTTP 관심사(상태 코드, 헤더, 쿠키)가 있는가
  - 서비스에서 Request/Response 객체에 접근하는가

리포지토리 침범:
  - 리포지토리에 비즈니스 로직이 있는가
  - 리포지토리에서 다른 리포지토리를 직접 호출하는가

맵 대조 (task-file-map.md 있을 때):
  - 생성/수정된 파일이 맵에 선언된 파일과 일치하는가
  - 맵의 responsibility.should_not에 해당하는 코드가 파일에 없는가
  - 맵에 없는 파일이 생성되지 않았는가
```

### 3. 에러 핸들링 (critical)

```yaml
- 서비스의 모든 실패 경로에 적절한 에러 throw가 있는가
- try-catch에서 에러를 삼키지(swallow) 않는가
- 빈 catch 블록 = 0건
- 외부 호출에 타임아웃이 있는가
```

### 4. 타입 안전성 (critical)

```yaml
- any 사용 = 0건
- as 타입 단언 최소화
- DTO 필드 타입이 TS 명세서 스키마와 일치하는가
- nullable 처리가 명시적인가
```

### 5. 보안 (critical)

```yaml
- SQL injection 가능성 (raw 쿼리에 문자열 보간) = 0건
- 비밀번호/토큰의 평문 로깅 = 0건
- 사용자 입력의 검증 없는 사용 = 0건
- 민감 데이터가 응답에 노출되지 않는가
```

### 6. 테스트 가능성 (warning)

```yaml
- 의존성이 주입 가능한가 (new로 직접 생성하지 않는가)
- 외부 서비스가 인터페이스/추상화를 통해 접근되는가
- 테스트에서 목(mock) 교체가 가능한 구조인가
```

### 8. 관측성 계약 drift (critical) — Phase 1 (2)

`backflow:impl-observability` 가 생성한 산출물이 TS §7.1 관측성과 일치하는지 검사. 실 로그·trace 출력에 required_tags 가 모두 등장하는지, sensitive_field_masking 이 redact 에 반영됐는지 등. (참고: §7 에러 코드 drift 룰 아래에 위치하나 numerical ID 는 8 — 룰 ID 는 안정적, 파일 위치는 추후 정리.)

```yaml
입력:
  context_file: backend.md.observability.context_file (예: src/observability/context.ts)
  logger_file: backend.md.observability.logger_file (예: src/observability/logger.ts)
  request_id_middleware_file: backend.md.observability.request_id_middleware_file
  tracing_file: backend.md.observability.tracing_file
  error_tag_file: backend.md.observability.error_tag_file (error_code_tag=true 시)
  bootstrap_file: backend.md.observability.bootstrap_file (예: src/main.ts)
  ts_section: specs/TS-*.md §7.1 관측성

검사 항목 — 로깅:
  required_tags_in_logger:
    - logger_file 의 formatter 출력에 TS §7.1 required_tags 의 모든 키(service, environment, request_id, trace_id 등) 가 등장하지 않으면 → critical
    - "request_id" 가 logger formatter 에 있으나 context_file (AsyncLocalStorage 등) 와 연결되지 않으면 → critical (실 로그에 빈 값으로 나옴)
  sensitive_masking:
    - TS §7.1 sensitive_field_masking 의 모든 패턴이 logger redact (또는 winston format / structlog processor) 에 등장하지 않으면 → critical
  log_format:
    - logger 가 json 출력을 보장하지 않으면 → warning (text 는 dev only)
  log_level:
    - logger init 이 process.env[log_level_env] 또는 동등한 메커니즘으로 LOG_LEVEL 을 읽지 않으면 → warning

검사 항목 — 트레이싱:
  sampling_rate:
    - tracing_file 에 sampling_rate_dev / sampling_rate_prod 가 env 분기로 적용되지 않으면 → critical
    - sampling_rate_prod > 0.5 이면서 production 로 보이는 코드 경로면 → warning ("운영 트래픽에서 비용 폭증 가능")
  otlp_endpoint_env:
    - exporter URL 이 하드코딩 (`http://...` 리터럴) 이면 → critical (env 변수 사용 강제)
  resource_attributes:
    - service_name / deployment.environment 가 OTel resource 에 등록되지 않으면 → warning

검사 항목 — Middleware / Bootstrap:
  middleware_registered:
    - request_id_middleware_file 가 존재하는데 bootstrap_file (또는 framework convention 진입점) 에 등록되지 않으면 → critical
  tracing_first_import:
    - bootstrap_file 의 import 순서에서 tracing_file 이 첫 번째가 아니면 → critical (auto-instrumentation 누락)
  traceparent_passthrough:
    - middleware 가 incoming `traceparent` 헤더를 OTel context 에 추출하지 않으면 → critical (분산 추적 끊김)
  correlation_header:
    - middleware 가 backend.md.observability.correlation_header 값을 사용하지 않거나 응답 헤더로 echo 하지 않으면 → warning

검사 항목 — ErrorMeta hook:
  error_tag_present:
    - error_code_tag=true 이고 §4 에러 코드 맵 비어있지 않은데 error_tag_file 부재 → critical
    - error_code_tag=false 인데 error_tag_file 존재 → warning ("의도치 않은 hook 활성화")
  app_exception_filter_calls:
    - AppExceptionFilter (impl-middleware 출력) 가 tagError 를 import 하지 않거나 catch() 에서 호출하지 않으면 → critical (관측성 hook 무력화)
  errormeta_import_path:
    - error_tag_file 의 ErrorMeta import 가 backend.md.error_handling.error_code_enum 과 일치하지 않으면 → critical

검사 항목 — 비표준 로그 호출 검출:
  console_log_remaining:
    - 프로젝트 코드에서 `console.log(`, `console.warn(`, `console.error(`, `console.debug(`, `console.info(` → critical
    - 단 logger.ts / context.ts / tracing.ts 등 관측성 파일 자체는 예외 (debug 용 console 허용)
  print_statements:
    - Python: `print(`, `sys.stdout.write` (logger 모듈 외) → critical
    - Java: `System.out.println`, `System.err.println` → critical
    - Go: `fmt.Println`, `fmt.Printf` (main 외) → critical
    - Rust: `println!`, `eprintln!` (main / examples 외) → warning

검사 항목 — Vendor leakage (계약 핵심):
  vendor_name_in_code:
    - 생성 코드에 `datadog`, `dd-trace`, `newrelic`, `sentry`, `honeycomb`, `appdynamics`, `dynatrace` 등 벤더명 등장 → critical
    - "OTel only" 계약 위반. exporter URL 은 env 로만 결정.

generated_marker:
  - context.ts / logger.ts / tracing.ts / error-tag.ts 에 "AUTO-GENERATED" 주석 없으면 → warning

env 변수:
  - .env.example 에 OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_SERVICE_NAME / LOG_LEVEL 누락 시 → warning

예외:
  - TS §7.1 부재 (grace mode) 이고 logger/tracing 파일이 default 5종 코드만 가지면 drift 검사 스킵 + 단일 warning ("§7.1 미작성, grace mode")
  - Scenario D (기존 OTel init 보존) 시 tracing.ts 가 skill 출력이 아닐 수 있음. backend.md.observability.tracing_file 가 명시적으로 "external" 이면 tracing 검사 스킵 + info 메시지
```

### 7. 에러 코드 계약 drift (critical) — Phase 1 (1)

`backflow:impl-error-codes` 가 생성한 산출물이 TS §4 에러 코드 맵과 일치하는지 검사. **양방향**으로 비교한다 — 한쪽에만 있는 코드는 모두 finding 으로 보고.

```yaml
입력:
  codes_file: backend.md.error_handling.error_code_enum (예: src/errors/codes.ts)
  http_mapping_file: backend.md.error_handling.http_mapping_file
  i18n_output_dir: backend.md.error_handling.i18n_output_dir
  ts_section: specs/TS-*.md §4 에러 코드 맵 (자동 탐지; 여러 TS 가 있으면 합집합)

검사 항목:
  missing_in_code:
    - TS §4 행에 있으나 codes.ts ErrorCode enum 에 없는 code → critical
    - 권고: impl-error-codes 재실행
  orphan_in_code:
    - codes.ts ErrorCode 에 있으나 TS §4 어느 행에도 없는 code → critical
    - 권고: TS 에 추가하거나 코드에서 제거 (의도적 예약이면 주석 + 별도 화이트리스트)
  http_status_mismatch:
    - codes.ts ErrorMeta[code].httpStatus !== TS row.http_status → critical
  i18n_key_mismatch:
    - codes.ts ErrorMeta[code].i18nKey !== TS row.i18n_key → critical
  http_mapping_consistency:
    - HTTP_STATUS_MAP 의 키 집합 ≠ ErrorCode 키 집합 → critical
    - HTTP_STATUS_MAP[code] !== ErrorMeta[code].httpStatus → critical
  i18n_locale_files:
    - error_handling.i18n_enabled=true 시:
        languages 배열의 각 lang 에 대해 {i18n_output_dir}/errors.{lang}.json 존재 → warning
        JSON 의 i18nKey 집합 ⊇ ErrorMeta 의 i18nKey 집합 → warning
  generated_marker:
    - codes.ts 첫 줄에 "AUTO-GENERATED" 주석 없으면 → warning (사람 편집 의심)

예외:
  - TS §4 가 비어있고 codes.ts 가 grace-period 기본 5 코드(AUTH_UNAUTHORIZED,
    AUTH_FORBIDDEN, VALIDATION_FAILED, SYSTEM_INTERNAL_ERROR, NETWORK_TIMEOUT) 만
    가지고 있으면 drift 검사 스킵 + 단일 warning ("§4 미작성, grace mode")
```

## 출력

```yaml
검증 대상: {파일/디렉토리}
검증 유형: BV1 (코드 품질)

findings:
  - id: "BV1-001"
    severity: critical | warning | info
    file: "{파일 경로}"
    line: {라인 번호} (가능하면)
    issue: "{문제}"
    suggestion: "{수정 제안}"

summary:
  files_checked: {N}
  total_findings: {N}
  critical: {N}
  warning: {N}
  pass: {true | false}
```
