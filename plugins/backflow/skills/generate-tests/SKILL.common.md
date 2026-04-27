---
name: generate-tests
description: 서비스, 리포지토리, 컨트롤러의 단위/통합 테스트를 자동 생성합니다. "테스트 생성", "테스트 작성" 요청 시 사용.
argument-hint: [대상 파일 경로] [--type unit|integration]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
model: sonnet
---

# 테스트 자동 생성 (BU2)

ultrathink

당신은 테스트 엔지니어입니다.
대상 코드 + specflow 명세서로부터 테스트를 생성합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md) — testing

## 입력

$ARGUMENTS 에서:
1. **대상 파일 경로** → Read (테스트할 코드)
2. **--type** → unit 또는 integration (기본값: unit)

추가로 자동 탐색:
- specflow 산출물: FS (BR/AC), TS (에러 코드, 처리 흐름)
- 기존 테스트 파일 (패턴 참조)

## 테스트 유형별 전략

### 단위 테스트 (--type unit)

**서비스 테스트**:
```typescript
describe('SpeakerService', () => {
  // 모든 의존성 목(mock)
  let service: SpeakerService
  let speakerRepo: jest.Mocked<SpeakerRepository>

  // BR별 테스트 그룹
  describe('enroll', () => {
    it('should create speaker successfully', async () => { ... })
    it('should reject when quota exceeded (BR-001)', async () => { ... })
    it('should reject when name duplicated (BR-003)', async () => { ... })
    it('should reject when audio too short (BR-007)', async () => { ... })
  })
})
```

**리포지토리 테스트**:
- ORM 목(mock)으로 쿼리 호출 검증
- 또는 backend.md `db_strategy`에 따라 실제 DB 사용

### 통합 테스트 (--type integration)

**API 엔드포인트 테스트**:
```typescript
describe('POST /api/v1/speakers/enroll', () => {
  it('should return 201 with speaker data', async () => {
    const res = await request(app).post('/api/v1/speakers/enroll')
      .set('Authorization', `Bearer ${token}`)
      .send({ name: 'Test', workspace_id: wsId })
    expect(res.status).toBe(201)
    expect(res.body).toMatchObject({ id: expect.any(String), name: 'Test' })
  })

  it('should return 429 when quota exceeded', async () => { ... })
  it('should return 401 without auth', async () => { ... })
  it('should return 403 for viewer role', async () => { ... })
})
```

## FS/TS → 테스트 케이스 매핑

### BR → 테스트 케이스

```
BR-001: 최대 50명  →  성공(49명일 때) + 실패(50명일 때) + 경계(정확히 50명)
BR-003: 이름 중복  →  성공(고유 이름) + 실패(중복 이름)
BR-007: 3초 이상   →  성공(3.1초) + 실패(2.9초) + 경계(정확히 3초)
```

### 에러 코드 → 테스트 케이스

TS의 각 에러 코드에 대해:
- 해당 에러를 트리거하는 입력 구성
- 응답 상태 코드 검증
- 응답 body의 error 필드 검증

### AC → 테스트 케이스

FS의 수용 기준(AC)이 테스트 시나리오가 됩니다:
```
AC-001: "정상 등록 시 상태가 pending" → 통합 테스트
AC-002: "중복 이름 등록 시 에러 메시지 표시" → API 테스트
```

## 테스트 코드 규칙

- backend.md의 `testing.runner`에 따라 jest/vitest/pytest 구문 사용
- describe 블록으로 기능 그룹화
- it/test 설명에 BR/AC 번호 포함
- Arrange-Act-Assert 패턴
- 매직 넘버 대신 상수 사용

## 품질 자가 점검

- [ ] FS의 모든 BR에 최소 1개의 성공 + 실패 테스트가 있는가
- [ ] TS의 모든 에러 코드에 테스트가 있는가
- [ ] 경계값 테스트가 수치 제한마다 있는가
- [ ] 각 테스트가 독립적으로 실행 가능한가
- [ ] 외부 의존성이 목(mock)으로 교체되었는가
