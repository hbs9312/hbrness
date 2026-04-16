---
name: impl-services
description: 비즈니스 로직 서비스를 구현합니다. FS의 비즈니스 룰과 TS의 처리 흐름을 코드로 변환. "서비스 구현", "비즈니스 로직" 요청 시 사용.
argument-hint: [기능 명세서 경로] [기술 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
---

# 서비스 / 비즈니스 로직 (B3)

ultrathink

당신은 백엔드 개발자입니다.
FS의 비즈니스 룰과 TS의 처리 흐름을 서비스 계층으로 구현합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md) — error_handling, structure
- 기존 코드 레지스트리: `.backflow/service-registry.md` (있으면)
- **태스크-파일 맵**: `.backflow/task-file-map.md` (있으면) — 이 스킬이 담당하는 파일 목록

## 입력

$ARGUMENTS 에서:
1. **기능 명세서(FS)** → 비즈니스 룰(BR), 수용 기준(AC) 추출
2. **기술 명세서(TS)** → 처리 흐름(시퀀스), API 서버 측 검증 순서

## 태스크-파일 맵 준수

`.backflow/task-file-map.md`가 존재하면:
1. `impl_skill: impl-services` 항목만 필터
2. `action: create` → 해당 경로에 새 파일 생성
3. `action: modify` → 해당 경로의 기존 파일 수정
4. `responsibility.should` → 이 파일에서 구현할 범위
5. `responsibility.should_not` → 이 파일에서 하지 않을 것
6. 맵에 없는 파일은 생성하지 않음 (맵 누락이 의심되면 경고 출력)

맵이 없으면 기존 로직대로 독자 판단.

## ★ 핵심 원칙: BR = 코드 ★

FS의 모든 비즈니스 룰(BR)이 서비스 코드에 1:1 대응해야 합니다.

```
FS 비즈니스 룰                           →    서비스 코드
──────────────────────────────────────────────────────────────
BR-001: 워크스페이스당 화자 최대 50명      →    validateQuota() + 에러
BR-003: 화자명 중복 불가                   →    checkDuplicate() + 에러
BR-005: Admin/Member만 등록 가능          →    가드/미들웨어로 위임 (B5)
BR-007: 오디오 3초 이상                   →    validateAudio() + 에러
```

## 서비스 생성 규칙

### 파일 구조

backend.md의 `module_pattern`에 따름:

```
# flat 패턴
{service_dir}/{feature}.service.ts

# feature-module 패턴
{src_root}/modules/{feature}/services/{feature}.service.ts
```

### 서비스 코드 구조

```typescript
@Injectable()
export class SpeakerService {
  constructor(
    private readonly speakerRepo: SpeakerRepository,
    private readonly eventEmitter: EventEmitter2,  // 비동기 처리 시
  ) {}

  async enroll(dto: EnrollSpeakerDto, context: RequestContext): Promise<Speaker> {
    // TS 서버 측 검증 순서를 그대로 따름
    // 1. 쿼터 확인 (BR-001)
    await this.validateQuota(context.workspaceId)
    // 2. 이름 중복 확인 (BR-003)
    await this.checkDuplicate(dto.name, context.workspaceId)
    // 3. 오디오 검증 (BR-007)
    this.validateAudio(dto.audioFile)
    // 4. 생성
    const speaker = await this.speakerRepo.create({ ... })
    // 5. 비동기 작업 트리거 (TS에 비동기로 명시된 경우)
    this.eventEmitter.emit('speaker.enrolled', { speakerId: speaker.id })
    return speaker
  }
}
```

### TS 서버 측 검증 순서 → 코드 순서

TS에 "서버 측 검증 순서"가 명시되어 있으면 그 순서 그대로 구현합니다.
순서가 다르면 에러 응답이 달라져 프론트엔드와 불일치합니다.

### 트랜잭션 관리

- 복수 쓰기 연산 → 트랜잭션 래핑
- TS에 "트랜잭션 범위"가 명시되어 있으면 그대로 따름
- ORM별 트랜잭션 패턴:
  - Prisma: `this.prisma.$transaction()`
  - TypeORM: `@Transaction()` 또는 `queryRunner`

### 에러 처리

- TS의 에러 코드를 backend.md의 `error_handling.error_class`로 변환
- 각 에러에 AC/BR 번호 주석:

```typescript
// BR-001 위반
throw new AppException(
  ErrorCode.QUOTA_EXCEEDED,
  '워크스페이스당 최대 화자 수를 초과했습니다',
)
```

### 외부 서비스 호출 패턴

TS에 외부 호출이 있으면:
- 타임아웃 설정 (TS에 명시된 값)
- 재시도 로직 (TS에 명시된 횟수/전략)
- 최종 실패 경로 (TS에 명시된 fallback)

```typescript
// TS: "임베딩 API 호출, 타임아웃 30초, 재시도 2회, 실패 시 상태 failed"
try {
  await this.embeddingClient.process(audioData, { timeout: 30_000 })
} catch (error) {
  await this.speakerRepo.updateStatus(speakerId, 'failed')
  this.logger.error('Embedding failed', { speakerId, error })
}
```

## 품질 자가 점검

- [ ] FS의 모든 BR이 서비스 코드에 구현되었는가
- [ ] TS의 서버 측 검증 순서와 코드 순서가 일치하는가
- [ ] TS의 모든 에러 코드에 대응하는 throw가 있는가
- [ ] 복수 쓰기 연산에 트랜잭션이 있는가
- [ ] 외부 호출에 타임아웃 + 재시도 + 실패 경로가 있는가
- [ ] 리포지토리를 통해서만 DB에 접근하는가 (직접 쿼리 금지)
- [ ] 컨트롤러 관심사(HTTP 상태 코드, 요청 파싱)가 서비스에 없는가
