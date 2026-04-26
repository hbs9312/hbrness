# 기술 명세서 출력 템플릿

```yaml
문서 ID: TS-{YYYY}-{NNN}
기능 참조: {FS ID}
와이어프레임 참조: {WF ID}
작성일: {YYYY-MM-DD}
상태: Draft
작성자: 테크리드
리뷰어: 백엔드, 프론트엔드

# 1. 기술 결정 및 근거 (ADR)
### ADR-001: {제목}
- 맥락: {왜 필요}
- 결정: {선택}
- 근거: {정량적}
- 트레이드오프: {단점}
- 대안: (기각) {대안}: {사유}
- 재평가: {조건}

# 2. 시스템 아키텍처

# 3. API 설계

## 3.1 엔드포인트 표 (인간 가독)

> 경로는 servers[].url 또는 backend.md.api.base_path 를 제외한 canonical path 로 통일.

### {METHOD} {canonical 경로}
기능 참조: {AC/BR-NNN}
Request: ...
Response: ...
Error Responses:
  {status} {CODE}: {설명} → {AC/BR-NNN}   # CODE 는 §4 에러 코드 맵 참조

## 3.2 OpenAPI Fragment (source of truth)

```yaml
openapi: 3.1.0
info:
  title: {project name}
  version: {semver}
servers:
  - url: {base_path}
    description: production
paths:
  {canonical_path}:
    {method}:
      operationId: {camelCase}
      summary: {한줄 요약}
      tags: [{도메인}]
      security: [{securityScheme}: []] # 인증 필요 시
      requestBody: ...
      responses:
        '{성공 status}':
          description: ...
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/{ResponseType}'
        '{에러 status}':
          $ref: '#/components/responses/{ERROR_CODE}'  # §4 에러 코드 맵 행의 code
components:
  schemas:
    # 요청/응답 스키마는 §5 데이터 모델 기반
    {RequestType}: ...
    {ResponseType}: ...
    ErrorCode:
      type: string
      description: '§4 에러 코드 맵에서 export 시 enum 으로 합성됨'
    ErrorEnvelope:
      type: object
      required: [error]
      properties:
        error:
          type: object
          required: [code, message]
          properties:
            code: { $ref: '#/components/schemas/ErrorCode' }
            message: { type: string }
            meta: { type: object, additionalProperties: true }
  securitySchemes: {}  # 인증 방식에 따라 (bearerAuth / cookieAuth / apiKeyAuth)
  responses: {}  # 비워둠 — backflow:export-api-contract 가 §4 에서 합성
```

규칙:
- operationId: camelCase, 전역 유일. codegen 함수명·queryKey 의 안정 ID
- canonical path: servers[].url 제외. §3.1 표와 path 일치
- components.responses: 항상 비워둠 (`{}`). export-api-contract 가 합성 (Phase 1 (3) XR-001)
- ErrorEnvelope.error.code: ErrorCode 를 $ref (plain string 금지, Phase 1 (3) XR-003)
- 선택 필드: x-ts-adr (ADR 역참조 — Phase 2)

# 4. 에러 코드 맵
| domain | code | http_status | i18n_key | message_ko | message_en | retriable |
|---|---|---|---|---|---|---|
| {domain} | {DOMAIN_REASON} | {status} | errors.{domain}.{snake} | {한글 메시지} | {English message} | {true|false} |

규칙:
- code: UPPER_SNAKE_CASE, 도메인 prefix 필수 (예: USER_NOT_FOUND ○ / NOT_FOUND ✗)
- domain: FS §도메인 정의와 1:1 일치 (소문자 snake_case)
- http_status: 400/401/403/404/409/422/429/500/502/503/504 범위
- i18n_key: errors.{domain}.{snake} 패턴
- retriable=true: frontend 자동 재시도 허용 조건
- 선택 컬럼(선택): cause (계층 원인), ui_flow (inline/toast/modal/redirect/silent)

# 5. 데이터 모델
## {테이블명}
| 필드 | 타입 | 제약 | 설명 |
인덱스: ...  -- {BR-NNN}
관계: ... (ON DELETE {정책})

# 6. 처리 흐름
## 실패 처리
- 타임아웃: {N}초
- 재시도: 최대 {N}회
- 최종 실패: {동작} → {에러 코드 §4 참조}

# 7. 비기능 요구사항

## 7.1 관측성

### 로깅
| key | 값 |
|---|---|
| log_format | json |
| log_level_default | info |
| log_level_env | LOG_LEVEL |
| required_tags | service, environment, request_id, trace_id |
| optional_tags | user_id, error_code (예시 — 프로젝트별 선택) |
| sensitive_field_masking | password, token, ssn, card_number |

### 트레이싱
| key | 값 |
|---|---|
| trace_propagation | W3C Trace Context (`traceparent`) |
| sampling_strategy | head-based, ratio |
| sampling_rate_dev | 1.0 |
| sampling_rate_prod | 0.1 |
| custom_spans | DB 쿼리, 외부 호출, 비동기 작업 enqueue |

### Metrics (SLI)
| sli | type | unit | window |
|---|---|---|---|
| http_request_duration_seconds | histogram | seconds | 1m |
| http_requests_total | counter | requests | - |
| db_query_duration_seconds | histogram | seconds | 1m |
| external_call_duration_seconds | histogram | seconds | 1m |

### 상관 관계
- correlation_header: `X-Request-Id` (없으면 middleware 가 생성). `Traceparent` 는 §트레이싱 의 trace_propagation 으로 별도 처리 — correlation_header 와 혼용 금지
- error_code_tag: true (Phase 1 (1) ErrorCode 자동 주입 — backend.md `observability.error_code_tag` 와 동일 의미)

# 8. 인프라 & 배포

# 9. 파일 처리

| upload_kind | mime_types | max_size_mb | storage_path | resize_variants | retention_days | related |
|---|---|---|---|---|---|---|
| {snake_case} | {IANA MIME comma 구분 — wildcard 금지} | {양의 정수} | {reserved {file_id}/{ext}/{upload_kind} + custom ({key:auth}/{key:body}/{key:path})} | {variant 이름 comma 또는 (없음)} | {≥0 정수, 0=영구} | {US/AC/BR} |
| profile_image | image/jpeg, image/png, image/webp | 5 | users/{user_id:auth}/profile/{file_id}.{ext} | thumb_64, thumb_256 | 0 | US-002, AC-005 |
| document_attachment | application/pdf | 50 | docs/{doc_id:path}/{file_id}.pdf | (없음) | 365 | US-007 |

규칙:
- upload_kind: snake_case 전역 유일. operationId prefix (uploadProfileImage 등)
- mime_types: 명시적 IANA type. wildcard (image/*, */*) 금지
- max_size_mb: 양의 정수. server-side 강제
- storage_path: reserved placeholder = {file_id} (server 발급), {ext}, {upload_kind}.
  custom placeholder = inline source 표기로 명시:
    {key:auth}  — 인증된 user 정보 (user_id, tenant_id 등)
    {key:body}  — presign 요청 body 필드
    {key:path}  — URL path 매개변수
  source 미표기 시 body default. 예: users/{user_id:auth}/profile/{file_id}.{ext}
  미해결 placeholder 는 generation-time critical
- resize_variants: backend.md.file_upload.resize_presets 의 키만
- retention_days: ≥ 0 정수. > 0 시 메타에 expires_at 채움
```
