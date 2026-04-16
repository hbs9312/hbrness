---
name: impl-middleware
description: 인증, 인가, 에러 핸들링 등 횡단 관심사를 구현합니다. "미들웨어", "가드", "인증 구현", "에러 핸들러" 요청 시 사용.
argument-hint: [기술 명세서 경로] [기능 명세서 경로 (선택)]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
---

# 미들웨어 / 횡단 관심사 (B5)

ultrathink

당신은 백엔드 개발자입니다.
인증/인가, 요청 검증, 에러 핸들링, 로깅 등 횡단 관심사를 구현합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md) — auth, error_handling, api
- **태스크-파일 맵**: `.backflow/task-file-map.md` (있으면) — 이 스킬이 담당하는 파일 목록

## 입력

$ARGUMENTS 에서:
1. **기술 명세서(TS)** → 보안 섹션, 비기능 요구사항
2. **기능 명세서(FS)** (선택) → 권한 관련 BR

## 태스크-파일 맵 준수

`.backflow/task-file-map.md`가 존재하면:
1. `impl_skill: impl-middleware` 항목만 필터
2. `action: create` → 해당 경로에 새 파일 생성
3. `action: modify` → 해당 경로의 기존 파일 수정
4. `responsibility.should` → 이 파일에서 구현할 범위
5. `responsibility.should_not` → 이 파일에서 하지 않을 것
6. 맵에 없는 파일은 생성하지 않음 (맵 누락이 의심되면 경고 출력)

맵이 없으면 기존 로직대로 독자 판단.

## ★ B4 이후에 실행하는 이유 ★

컨트롤러(B4)가 먼저 존재해야 가드/미들웨어를 적용할 위치가 명확합니다.
B5는 B4의 엔드포인트에 횡단 관심사를 씌우는 작업입니다.

## 구현 항목

### 1. 인증 (Authentication)

backend.md의 `auth.strategy`에 따름:

**JWT**:
```typescript
// guards/jwt-auth.guard.ts
// 토큰 검증 → 사용자 정보를 request에 주입
// TS 보안 섹션의 토큰 검증 규칙 반영
```

**Session**:
```typescript
// middleware/session.middleware.ts
// 세션 저장소 설정 (Redis 등)
```

### 2. 인가 (Authorization)

FS의 권한 관련 BR → 가드/데코레이터:

```typescript
// BR-005: Admin/Member만 등록 가능
@Roles('admin', 'member')
@UseGuards(RolesGuard)
@Post('enroll')
async enroll() { ... }
```

backend.md의 `auth.role_model`에 따라:
- RBAC → Roles 데코레이터 + RolesGuard
- ABAC → Policy 기반 가드

### 3. 글로벌 에러 핸들러

backend.md의 `error_handling.strategy`에 따름:

```typescript
// filters/app-exception.filter.ts
// 서비스에서 throw한 AppException → TS 에러 응답 형식으로 변환
//
// AppException(ErrorCode.QUOTA_EXCEEDED, message)
// → { status: 429, body: { error: "QUOTA_EXCEEDED", message: "..." } }
```

에러 코드 → HTTP 상태 매핑 테이블:

```typescript
const ERROR_STATUS_MAP: Record<ErrorCode, number> = {
  QUOTA_EXCEEDED: 429,
  DUPLICATE_NAME: 409,
  NOT_FOUND: 404,
  PERMISSION_DENIED: 403,
  AUDIO_TOO_SHORT: 400,
  VALIDATION_ERROR: 400,
  INTERNAL_ERROR: 500,
}
```

### 4. 요청 로깅

```typescript
// middleware/request-logger.middleware.ts
// 요청/응답 로깅 (민감 정보 마스킹)
// TS 비기능 섹션의 로깅 요구사항 반영
```

로깅 내용:
- 요청: method, path, 사용자 ID, 타임스탬프
- 응답: 상태 코드, 소요 시간
- 에러: 스택 트레이스 (production에서는 제외)

### 5. 요청 속도 제한 (Rate Limiting)

TS 비기능 섹션에 명시되어 있으면:

```typescript
// guards/rate-limit.guard.ts
// 엔드포인트별 또는 글로벌 속도 제한
```

### 6. CORS 설정

TS 인프라/보안 섹션에 따라:

```typescript
// 허용 origin, methods, headers 설정
```

### 7. 요청 검증 파이프

backend.md의 `request_validation` 설정에 따라 글로벌 설정:

```typescript
// NestJS: ValidationPipe 글로벌 설정
app.useGlobalPipes(new ValidationPipe({
  whitelist: true,       // DTO에 없는 속성 제거
  forbidNonWhitelisted: true,
  transform: true,
}))
```

## 적용 범위

B4의 컨트롤러에 가드/미들웨어를 적용합니다:

```
엔드포인트              인증    인가              속도제한
─────────────────────────────────────────────────────
POST /speakers/enroll   ✅     admin, member     ✅
GET  /speakers          ✅     모든 인증 사용자   ❌
DELETE /speakers/:id    ✅     admin             ✅
```

위 매핑은 TS의 API 설계 + FS의 BR에서 도출합니다.

## 품질 자가 점검

- [ ] TS 보안 섹션의 모든 요구사항이 구현되었는가
- [ ] FS 권한 관련 BR이 가드로 구현되었는가
- [ ] 에러 코드 → HTTP 상태 매핑이 TS와 일치하는가
- [ ] 에러 응답 형식이 TS 스키마와 일치하는가
- [ ] 로깅에 민감 정보 마스킹이 적용되었는가
- [ ] CORS, 속도 제한이 TS 비기능 섹션과 일치하는가
- [ ] 가드 적용 범위가 TS API 보안 요구사항과 일치하는가
