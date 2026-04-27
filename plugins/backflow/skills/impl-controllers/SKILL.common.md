---
name: impl-controllers
description: API 엔드포인트(컨트롤러/라우트)를 구현합니다. TS의 API 설계 섹션을 코드로 변환. "API 구현", "컨트롤러 생성", "엔드포인트" 요청 시 사용.
argument-hint: [기술 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
---

# 컨트롤러 / API 엔드포인트 (B4)

ultrathink

당신은 백엔드 개발자입니다.
TS의 API 설계 섹션을 컨트롤러/라우트 코드로 구현합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md) — api, auth, error_handling
- **태스크-파일 맵**: `.backflow/task-file-map.md` (있으면) — 이 스킬이 담당하는 파일 목록

## 입력

$ARGUMENTS 의 기술 명세서(TS) → Read.
"API 설계" 섹션이 주 입력입니다.

추가로 자동 탐색:
- B3에서 생성한 서비스 파일 (메서드 시그니처 확인)
- backend.md의 `controller_dir` → 기존 컨트롤러 확인

## 태스크-파일 맵 준수

`.backflow/task-file-map.md`가 존재하면:
1. `impl_skill: impl-controllers` 항목만 필터
2. `action: create` → 해당 경로에 새 파일 생성
3. `action: modify` → 해당 경로의 기존 파일 수정
4. `responsibility.should` → 이 파일에서 구현할 범위
5. `responsibility.should_not` → 이 파일에서 하지 않을 것
6. 맵에 없는 파일은 생성하지 않음 (맵 누락이 의심되면 경고 출력)

맵이 없으면 기존 로직대로 독자 판단.

## ★ 컨트롤러의 책임 ★

컨트롤러는 얇게(thin) 유지합니다:
1. 요청 파싱 + DTO 변환
2. 서비스 호출
3. 응답 변환 + HTTP 상태 코드

비즈니스 로직은 서비스(B3)에, 데이터 접근은 리포지토리(B2)에 있어야 합니다.

## TS → 컨트롤러 매핑

### 1. 라우트 정의

TS의 각 API 엔드포인트 → 컨트롤러 메서드:

```
TS API                              →    컨트롤러
──────────────────────────────────────────────────────
POST /api/v1/speakers/enroll        →    @Post('enroll') enroll()
GET  /api/v1/speakers               →    @Get() list()
DELETE /api/v1/speakers/:id         →    @Delete(':id') remove()
```

### 2. 요청 DTO (입력 검증)

TS의 요청 스키마 → DTO 클래스:

```typescript
// dto/enroll-speaker.dto.ts
export class EnrollSpeakerDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(50)  // BR-004
  name: string

  @IsUUID()
  workspace_id: string
}
```

backend.md의 `request_validation` 설정에 따라:
- class-validator → 데코레이터 기반
- zod → 스키마 기반
- joi → 스키마 기반

### 3. 응답 변환

TS의 응답 스키마 → 응답 DTO:

```typescript
// dto/speaker-response.dto.ts
export class SpeakerResponseDto {
  id: string
  name: string
  embedding_status: EmbeddingStatus
  created_at: string
}

// 컨트롤러에서
@Post('enroll')
async enroll(@Body() dto: EnrollSpeakerDto): Promise<SpeakerResponseDto> {
  const speaker = await this.speakerService.enroll(dto, context)
  return this.toResponse(speaker)
}
```

backend.md의 `response_format`에 따라 래핑:

```typescript
// 래핑 패턴이 있으면
return { success: true, data: this.toResponse(speaker) }
```

### 4. HTTP 상태 코드

TS의 응답 정의에 따름:

```
TS 응답              →    HTTP 상태
───────────────────────────────
성공 생성             →    201 Created
성공 조회             →    200 OK
성공 삭제             →    204 No Content
검증 실패             →    400 Bad Request
인증 실패             →    401 Unauthorized
권한 부족             →    403 Forbidden
리소스 없음           →    404 Not Found
쿼터 초과             →    429 Too Many Requests
```

### 5. 에러 응답 형식

TS의 에러 응답 스키마를 정확히 따름:

```typescript
// TS에 정의된 에러 응답 형식
{
  error: "QUOTA_EXCEEDED",    // TS 에러 코드
  message: "워크스페이스당 최대 화자 수를 초과했습니다"
}
```

서비스에서 throw한 AppException을 에러 필터/미들웨어가 이 형식으로 변환 (B5).

### 6. Swagger / OpenAPI (설정에 따라)

backend.md의 `doc_tool`이 Swagger이면:
- 데코레이터로 API 문서화
- 요청/응답 스키마, 상태 코드, 설명 포함

## ★ Phase 1 (5) 책임 경계 — 파일 업로드 ★

**MUST**: TS §9 파일 처리에 정의된 upload_kind 의 operationId (`upload{UploadKindCamel}`) 는 **본 skill 이 처리하지 않는다**. `backflow:impl-file-upload` 가 자체 controller 를 생성한다.

본 skill 동작:
- §9 의 upload operationId 는 **stub 또는 skip** (빈 메서드 또는 생성 자체 안 함)
- §3.2 fragment 에 등장해도 multipart 처리·presigned URL·storage 호출 코드 작성 금지
- 위반 시 `validate-code §10.5 controller_no_duplication` warning

§9 가 부재한 프로젝트는 일반 endpoint 와 동일하게 본 skill 이 처리.

## ★ Phase 1 (6) 책임 경계 — Webhook ★

**MUST**: TS §10 외부 연동·Webhook 의 webhook operationId (`receive{WebhookIdCamel}`) 는 **본 skill 이 처리하지 않는다**. `backflow:impl-webhook` 가 자체 controller 를 생성한다.

본 skill 동작:
- §10 의 webhook operationId 는 **stub 또는 skip** (빈 메서드 또는 생성 자체 안 함)
- §3.2 fragment 에 등장해도 raw body / 서명 검증 / idempotency / 큐 dispatch 코드 작성 금지
- 위반 시 `validate-code §11.4 controller_no_duplication` warning

§10 가 부재한 프로젝트는 일반 endpoint 와 동일하게 본 skill 이 처리.

## 파일 업로드 엔드포인트

TS에 파일 업로드가 있으면:
- 멀티파트 처리 (multer, formidable 등)
- 파일 크기/형식 제한 (TS에 명시된 대로)
- 프레임워크별 파일 인터셉터 사용

## 품질 자가 점검

- [ ] TS의 모든 API 엔드포인트가 컨트롤러 메서드로 존재하는가
- [ ] 요청 DTO가 TS 요청 스키마와 정확히 일치하는가
- [ ] 응답 DTO가 TS 응답 스키마와 정확히 일치하는가
- [ ] HTTP 상태 코드가 TS 정의와 일치하는가
- [ ] 컨트롤러에 비즈니스 로직 = 0건 (서비스 호출만)
- [ ] 모든 입력에 검증이 있는가 (DTO 데코레이터/스키마)
- [ ] backend.md의 response_format 래핑을 따르는가

## dbflow 연계 (Phase 1.5)
API endpoint 구현 후 → 관련 E2E 시나리오 가 있으면 `dbflow:run` 으로 검증 권장.
