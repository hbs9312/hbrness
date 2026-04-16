---
name: validate-tests
description: 테스트 코드의 커버리지와 품질을 검증합니다. "테스트 검증", "테스트 리뷰" 요청 시 사용.
argument-hint: [테스트 파일 또는 디렉토리 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write]
effort: high
---

# 테스트 품질 검증 (BV3)

ultrathink

생성된 테스트 코드가 비즈니스 룰과 에러 경로를 충분히 커버하는지 검증합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md) — testing

## 입력

$ARGUMENTS 의 테스트 파일/디렉토리를 Read/Glob으로 읽으세요.

추가로 자동 탐색:
- 대응하는 소스 파일 (테스트 대상)
- specflow 산출물 (FS의 BR/AC, TS의 에러 코드)

## 검증 항목

### 1. BR 커버리지 (critical)

```yaml
FS의 각 비즈니스 룰에 대응하는 테스트가 있는가:
  - BR-001: 쿼터 초과 → 거부 테스트
  - BR-003: 이름 중복 → 거부 테스트
  - BR-007: 오디오 길이 부족 → 거부 테스트
  각 BR에 최소 1개의 성공 + 1개의 실패 테스트
```

### 2. 에러 경로 커버리지 (critical)

```yaml
TS의 각 에러 코드에 대응하는 테스트가 있는가:
  - QUOTA_EXCEEDED → 429 응답 확인
  - DUPLICATE_NAME → 409 응답 확인
  - NOT_FOUND → 404 응답 확인
  에러 응답 body의 형식도 검증하는가
```

### 3. 경계값 테스트 (warning)

```yaml
수치 제한에 경계값 테스트가 있는가:
  - 정확히 50명일 때 (BR-001 경계)
  - 이름 최대 길이 (BR-004 경계)
  - 오디오 정확히 3초 (BR-007 경계)
```

### 4. 테스트 격리 (warning)

```yaml
- 각 테스트가 독립적으로 실행 가능한가
- DB 상태에 의존하지 않는가 (setUp/tearDown 확인)
- 외부 서비스가 목(mock)으로 교체되었는가
- 테스트 간 공유 상태 = 0건
```

### 5. assertion 품질 (warning)

```yaml
- 단순 truthy/falsy 검증이 아닌 구체적 값 비교인가
- 에러 메시지/코드까지 검증하는가
- 응답 구조(필드 존재)까지 검증하는가
```

## 출력

```yaml
검증 대상: {테스트 파일/디렉토리}
검증 유형: BV3 (테스트 품질)

coverage_check:
  br_coverage:
    total_brs: {N}
    covered: {N}
    missing: [BR-NNN, ...]
  error_code_coverage:
    total_codes: {N}
    covered: {N}
    missing: [CODE, ...]

findings:
  - id: "BV3-001"
    severity: critical | warning
    file: "{파일 경로}"
    issue: "{문제}"
    suggestion: "{수정 제안}"

summary:
  test_files_checked: {N}
  total_findings: {N}
  critical: {N}
  warning: {N}
  pass: {true | false}
```
