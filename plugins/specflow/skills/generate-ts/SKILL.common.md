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

## 출력 위치: specs/TS-{YYYY}-{NNN}.md
