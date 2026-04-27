---
name: impl-integrations
description: 외부 서비스 통합(메시지 큐, 캐시, 스토리지, 이메일, 실시간 통신)을 구현합니다. "외부 연동", "큐 설정", "SSE 구현" 요청 시 사용.
argument-hint: [기술 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
---

# 외부 서비스 통합 (B6)

ultrathink

당신은 인프라/백엔드 개발자입니다.
TS에 명시된 외부 서비스 연동을 구현합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md) — external_services
- **태스크-파일 맵**: `.backflow/task-file-map.md` (있으면) — 이 스킬이 담당하는 파일 목록

## 입력

$ARGUMENTS 의 기술 명세서(TS) → Read.
인프라, 비동기 처리, 외부 호출 관련 섹션이 주 입력입니다.

## 태스크-파일 맵 준수

`.backflow/task-file-map.md`가 존재하면:
1. `impl_skill: impl-integrations` 항목만 필터
2. `action: create` → 해당 경로에 새 파일 생성
3. `action: modify` → 해당 경로의 기존 파일 수정
4. `responsibility.should` → 이 파일에서 구현할 범위
5. `responsibility.should_not` → 이 파일에서 하지 않을 것
6. 맵에 없는 파일은 생성하지 않음 (맵 누락이 의심되면 경고 출력)

맵이 없으면 기존 로직대로 독자 판단.

## ★ B3/B4 시뮬레이션 교체 ★

B3 서비스에서 외부 서비스 호출을 TODO/stub으로 남긴 부분을 실제 코드로 교체합니다.

## 구현 항목 (TS 해당 시)

### 1. 메시지 큐 / 비동기 작업

backend.md의 `external_services.message_queue`에 따름:

**BullMQ (Redis)**:
```typescript
// jobs/embedding.processor.ts
@Processor('embedding')
export class EmbeddingProcessor {
  @Process()
  async process(job: Job<EmbeddingJobData>): Promise<void> {
    // TS 비동기 처리 흐름 구현
    // 타임아웃: TS에 명시된 값
    // 재시도: TS에 명시된 횟수/전략
    // 최종 실패: 상태 업데이트 + 로깅
  }
}

// jobs/embedding.producer.ts
@Injectable()
export class EmbeddingProducer {
  async enqueue(data: EmbeddingJobData): Promise<void> {
    await this.queue.add('process', data, {
      attempts: 3,          // TS 재시도 횟수
      backoff: { type: 'exponential', delay: 1000 },
      timeout: 30_000,      // TS 타임아웃
    })
  }
}
```

### 2. 실시간 통신

backend.md의 `external_services.realtime`에 따름:

**SSE**:
```typescript
// controllers/events.controller.ts
@Sse('events')
async events(@Query('speaker_id') speakerId: string): Observable<MessageEvent> {
  // TS에 명시된 이벤트 구독/해제 패턴
  // 연결 종료 시 리소스 정리
}
```

**WebSocket**:
```typescript
// gateways/notification.gateway.ts
@WebSocketGateway()
export class NotificationGateway {
  // TS에 명시된 이벤트 타입/페이로드
}
```

### 3. 파일 스토리지

backend.md의 `external_services.storage`에 따름:

```typescript
// services/storage.service.ts
@Injectable()
export class StorageService {
  // TS에 명시된 업로드/다운로드/삭제 패턴
  // 크기 제한, 형식 제한
  // 서명된 URL (해당 시)
}
```

### 4. 캐시

backend.md의 `external_services.cache`에 따름:

```typescript
// services/cache.service.ts 또는 데코레이터
// TS에 명시된 캐시 정책 (TTL, 무효화 조건)
```

### 5. 이메일/알림

backend.md의 `external_services.email`에 따름:

```typescript
// services/notification.service.ts
// TS에 명시된 알림 트리거 + 템플릿
```

## ★ Phase 1 (5) 책임 경계 — 스토리지 추상 ★

**MUST**: 본 skill 이 storage 통합 (S3 / GCS / 로컬 파일 등) 을 다룰 때, 추상은 `backflow:impl-file-upload` 의 `StorageAdapter` 인터페이스 (`storage/types.ts`) 를 충족해야 한다.

본 skill 이 새 StorageService 를 작성할 때:
1. `StorageAdapter` 인터페이스 (`presignPut` / `presignGet` / `delete` / `head`) 형태로 작성 권장
2. 또는 `impl-file-upload` 가 후속 단계에서 wrapper 를 만들 수 있는 호환 구조로
3. **벤더 SDK 직접 호출은 `storage/{vendor}.ts` 또는 동등한 격리 모듈로 한정** — service 본체에 SDK import 금지

기존 StorageService 를 보존할 때: 인터페이스 비호환 시 `impl-file-upload` 가 wrapper 생성. 본 skill 이 새로 작성한 storage 추상은 처음부터 호환되도록.

위반 시 `validate-code §10.5 storage_service_wrapper` warning.

## ★ Phase 1 (6) 책임 경계 — Webhook 큐 ★

**MUST**: 본 skill 이 메시지 큐 추상을 정의할 때, `backflow:impl-webhook` 가 그 큐를 dispatch 에 사용한다. 충족 조건:

1. 큐 추상이 `enqueue(jobName, payload)` 같은 통일된 인터페이스 노출
2. 또는 본 skill 이 직접 webhook handler 큐를 만들지 않음 — `impl-webhook` 의 `webhook/dispatch.ts` 가 책임

본 skill 이 작성한 큐 추상 (Bull / BullMQ / Redis Stream / SQS 등) 은 **재구현 금지** — `impl-webhook` 가 wrapping 사용. 충족 안 되면 `impl-webhook` 가 wrapper 생성.

위반 시 `validate-code §11.5 enqueue_only_dispatch` warning.

## 모든 외부 호출 공통 패턴

TS에 "모든 외부 호출에 타임아웃, 재시도, 실패 경로"가 명시되어 있으므로:

```typescript
// 공통 외부 호출 래퍼
async function withRetry<T>(
  fn: () => Promise<T>,
  options: { maxRetries: number; timeout: number; backoff: 'exponential' | 'fixed' }
): Promise<T> {
  // 구현
}
```

## 환경 변수

TS 인프라 섹션의 환경 변수 목록 → `.env.example`에 추가:

```env
# 메시지 큐
REDIS_URL=redis://localhost:6379

# 스토리지
S3_BUCKET=
S3_REGION=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

## 품질 자가 점검

- [ ] TS의 모든 비동기 처리가 큐/이벤트로 구현되었는가
- [ ] 모든 외부 호출에 타임아웃 + 재시도 + 실패 경로가 있는가
- [ ] 큐 job 실패 시 DLQ 또는 상태 업데이트가 있는가
- [ ] SSE/WebSocket 연결 해제 시 리소스 정리가 있는가
- [ ] 환경 변수가 .env.example에 추가되었는가
- [ ] 외부 서비스 설정이 하드코딩 없이 환경 변수로 관리되는가
