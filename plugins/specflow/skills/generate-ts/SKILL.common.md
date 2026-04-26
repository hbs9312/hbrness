---
name: generate-ts
description: 승인된 기능 명세서와 와이어프레임에서 기술 명세서를 생성합니다. "기술 명세", "TS 작성", "아키텍처 설계" 요청 시 사용.
argument-hint: [기능 명세서 경로] [와이어프레임 경로]
tools: [file:read, search:grep, search:glob, file:write]
effort: max
---

# 기술 명세서 생성 (G3)

당신은 테크리드 역할로 기술 명세서를 작성합니다.

## 공통 컨텍스트 로드

- **문서 컨벤션**: [conventions.md](../../context/conventions.md)
- **도메인 용어집**: [glossary.md](../../context/glossary.md)

## 입력

$ARGUMENTS 에서 기능 명세서(FS)와 와이어프레임(WF) 파일 경로를 추출하여 Read로 읽으세요.

## 모드 판별

| 조건 | 모드 | 동작 |
|------|------|------|
| `--base` 인자 없음 | **full** (기본) | 전체 TS를 새로 생성 |
| `--base [기존 TS 경로]` 있음 | **incremental** | 기존 TS를 보존하고 새로 추가된 항목에 대한 기술 설계만 생성하여 병합 |

### incremental 모드 규칙

1. 기존 TS 파일을 Read로 읽고 현재 API, 데이터 모델, ADR, 에러 코드 맵, 관측성 설정 파악
2. FS/WF에서 기존 TS에 매핑되지 않은 **새 항목**을 식별
3. 새 항목에 대해서만 API 엔드포인트, 데이터 모델 변경, 시퀀스를 생성
4. 기존 API/모델/ADR/에러 코드/관측성은 원문 그대로 보존 — 내용 변경 금지
5. 새 ADR 번호는 기존 시퀀스 이어서 할당
6. 새 API가 기존 데이터 모델을 확장해야 하면 해당 모델 섹션에 필드 추가만 수행
7. 기존 API의 응답에 새 필드가 필요하면 해당 부분만 수정하고 변경 사유 주석
8. 새 API/AC 가 새 에러 케이스를 도입하면 §4 에러 코드 맵에 행 append (기존 행 변경 금지)
9. 관측성(§7.1) — 기존 TS 에 §7.1 이 **있으면 그대로 보존** (incremental 이 손대지 않음). **없으면 default 4표를 append** 하고 사용자에게 검토 요청. 이후 값 조정은 `specflow:revise` 로
10. §3.2 OpenAPI fragment — 기존 TS 에 §3.2 가 **있으면 그대로 보존** (paths 에 신규 endpoint 만 append + operationId 할당). **없으면 §3.1 표를 파싱해 fragment 초안 합성** 후 사용자 review 요청. components.responses 는 항상 `{}`.
11. §9 파일 처리 — 기존 TS 에 §9 가 **있으면 그대로 보존** (행 append 만). **없으면 PRD/FS 키워드 자동 흡수해 초안 합성** 후 사용자 review.
12. §10 외부 연동·Webhook — 기존 TS 에 §10 가 **있으면 그대로 보존** (행 append 만). **없으면 PRD/FS 키워드 흡수해 초안 합성** 후 사용자 review.

## 핵심 원칙: "어떻게, 무엇으로" — "왜 필요한가"는 포함하지 않음

### 허용: 아키텍처, API, 데이터 모델, 시퀀스, ADR, 비기능, 인프라
### 금지: 비즈니스 정당성, UX 카피 텍스트, 사용자 감정 서술

## 교차 참조 규칙 (필수)

- API 에러 응답 → AC/BR 번호 매핑
- API 에러 응답 CODE → §4 에러 코드 맵 의 code 와 일치
- 데이터 모델 제약 → BR 번호 주석
- API 서버 측 검증 순서 → BR 순서대로
- §4 에러 코드 맵 의 domain → FS §도메인 정의와 1:1

## ADR 필수 필드

맥락, 결정, 근거, 트레이드오프, 대안 검토(최소 1개 기각), 재평가 시점

## 생성 전략

1. BR 목록 → DB 제약으로 1:1 변환
2. AC 목록 → API 에러 응답으로 역산
3. AC·BR 의 실패 시나리오 → §4 에러 코드 맵 행으로 역산 (domain/code/http_status/i18n_key/message_ko/message_en/retriable)
4. 비동기 판단: 응답 시간 > 3초 → 비동기
5. 모든 외부 호출에 타임아웃, 재시도, 실패 경로 (최종 실패 시 반환할 에러 코드 명시)
6. §7.1 관측성 4표(로깅/트레이싱/Metrics/상관관계) 는 첫 TS 작성 시 default 값으로 채움 — 프로젝트별 조정 필요 시 사용자가 수정. log_format=json, sampling_rate_prod=0.1, required_tags 에 trace_id 포함 default
7. §3 API 설계 하위에 §3.2 OpenAPI 3.1 fragment 를 mandatory 로 포함. fragment 의 operationId 는 §3.1 표의 엔드포인트와 1:1 (camelCase). components.responses 는 비워둔다 (export-api-contract 책임). ErrorEnvelope.error.code 는 components.schemas.ErrorCode 를 $ref.
8. §9 파일 처리 표 — PRD/FS 의 "업로드", "첨부", "이미지", "파일" 키워드 흡수해 5~10행. upload_kind snake_case 전역 유일. mime_types 명시(wildcard 금지). max_size_mb 양의 정수. storage_path 의 placeholder 는 reserved (`{file_id}`/`{ext}`/`{upload_kind}`) 또는 명시된 source(presign body / auth / url path) 에서 resolve. resize_variants 는 backend.md.file_upload.resize_presets 키. retention_days ≥ 0. upload_kind 마다 §3.2 fragment 에 `upload{UploadKindCamel}` operationId 자동 생성 권고.
9. §10 외부 연동·Webhook 표 — PRD/FS 의 'webhook', '결제 알림', '깃허브 이벤트', '메신저 봇' 흡수해 inbound webhook 표 작성. webhook_id snake_case 전역 유일. signature_alg enum (hmac_sha256_payload / hmac_sha256_b64 / hmac_sha1_x_hub / hmac_sha256_x_hub / rsa_sha256 / none). idempotency_key_source 는 minimal grammar (header(NAME) / headerParam(NAME, PARAM) / body(PATH) / fallback(term, term)). always_200 per-webhook override 가능. webhook_id 마다 §3.2 fragment 에 receive{WebhookIdCamel} operationId 권고.

## 품질 자가 점검

- [ ] 모든 기술 결정에 ADR 존재
- [ ] 에러 응답 ↔ AC/BR 매핑률 = 100%
- [ ] 외부 호출 실패 경로 정의율 = 100%
- [ ] 비기능 모호 표현 0건
- [ ] 비즈니스 정당성/UX 카피 포함 = 0건
- [ ] §4 에러 코드 맵 섹션 존재
- [ ] API 의 모든 Error Response CODE 가 §4 에러 코드 맵에 존재
- [ ] §4 에러 코드 맵의 code 전역 유일
- [ ] §4 에러 코드 맵의 domain 이 FS §도메인 정의와 1:1 일치
- [ ] §7.1 관측성: 로깅·트레이싱 표 **mandatory** 존재 (Metrics SLI 와 상관관계 표는 optional — 누락 시 impl-observability 가 default 적용)
- [ ] 로깅 표의 required_tags 에 4 base 태그(service, environment, request_id, trace_id) 모두 포함
- [ ] sampling_rate_dev / sampling_rate_prod ∈ [0.0, 1.0]
- [ ] error_code_tag 가 true 일 때 Phase 1 (1) §4 에러 코드 맵이 채워져 있는가 (ErrorMeta hook 동작 전제)
- [ ] §3.2 OpenAPI fragment 가 §3.1 표의 모든 엔드포인트를 커버 (operationId 1:1)
- [ ] §3.1 표의 경로가 canonical path (servers.url 제외) 로 통일
- [ ] §3.2 의 components.responses 가 비어있음 (export-api-contract 책임)
- [ ] ErrorEnvelope.error.code 가 $ref: '#/components/schemas/ErrorCode'
- [ ] §9 파일 처리 섹션 존재 (필요 시)
- [ ] §9 모든 행 mime_types · max_size_mb · storage_path · retention_days 필수
- [ ] storage_path placeholder 가 reserved 또는 명시 source 에서 resolve 가능
- [ ] resize_variants 가 backend.md.file_upload.resize_presets 키와 매칭
- [ ] upload_kind 마다 §3.2 fragment 에 upload{Kind} operationId 존재
- [ ] §10 webhook 섹션 존재 (webhook 명시된 프로젝트만)
- [ ] 모든 webhook 의 signature_alg / signature_header / signature_secret_env / idempotency_key_source 명시
- [ ] signature_alg=none 은 개발용 명시
- [ ] idempotency_key_source 가 minimal grammar 따름
- [ ] webhook_id 마다 §3.2 fragment 에 receive{WebhookIdCamel} operationId 존재
- [ ] always_200=false 인 webhook 의 retry 정책이 sender 와 호환

## 출력 위치: specs/TS-{YYYY}-{NNN}.md
