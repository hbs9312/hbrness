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
