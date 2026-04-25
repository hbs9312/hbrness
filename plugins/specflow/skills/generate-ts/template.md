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
### {METHOD} {경로}
기능 참조: {AC/BR-NNN}
Request: ...
Response: ...
Error Responses:
  {status} {CODE}: {설명} → {AC/BR-NNN}   # CODE 는 §4 에러 코드 맵 참조

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
```
