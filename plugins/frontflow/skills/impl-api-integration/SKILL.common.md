---
name: impl-api-integration
description: 기술 명세서의 API를 프론트엔드에 연결합니다. F5의 시뮬레이션을 실제 호출로 교체. "API 연동", "백엔드 연결" 요청 시 사용.
argument-hint: [기술 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
model: sonnet
---

# API 통합 (F6)

ultrathink

F5의 목/시뮬레이션을 실제 API 호출로 교체합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [frontend.md](../../context/frontend.md) — api_client, server_state

## 입력

$ARGUMENTS 의 기술 명세서(TS) → Read.
API 설계 섹션이 주 입력입니다.

## ★ 교체 전략 ★

F5의 시뮬레이션 코드를 찾아서 실제 API 호출로 교체합니다:

```typescript
// F5 (before)
await new Promise(resolve => setTimeout(resolve, 2000))
setStatus('ready')

// F6 (after)
const { mutate: enrollSpeaker } = useMutation({
  mutationFn: (data: EnrollRequest) => api.speakers.enroll(data),
  onSuccess: (res) => { /* 상태 업데이트 */ },
  onError: (err) => { /* 에러 핸들링 */ },
})
```

## 생성할 코드

### 1. API 클라이언트 함수 — codegen import

`frontflow:sync-api-client` 가 `frontend.md.api_contract.client_dir` 에 생성한 함수를 import:

```typescript
// codegen 출력 사용 — hand-write 금지
import { enrollSpeaker, listSpeakers } from '@/api/generated/speakers';
```

직접 API 함수를 작성하지 않는다. 함수가 없으면 `sync-api-client` 를 먼저 실행.

### 2. 타입 정의 — codegen import

`sync-api-client` 가 생성한 `types.gen.ts` 에서 import:

```typescript
import type { EnrollRequest, EnrollResponse, ErrorCode } from '@/api/types.gen';
```

직접 타입을 정의하지 않는다.

### 3. 커스텀 훅

frontend.md의 `server_state` 설정에 따라:

```typescript
// hooks/useSpeakers.ts
export function useSpeakers(workspaceId: string) {
  return useQuery({
    queryKey: ['speakers', workspaceId],
    queryFn: () => speakersApi.list(workspaceId),
  })
}

export function useEnrollSpeaker() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: speakersApi.enroll,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['speakers'] })
    },
  })
}
```

### 4. 에러 핸들링

에러 분기 로직은 **`frontflow:impl-error-handling` 이 생성한 `handler.ts` 를 import** 합니다 (인라인 switch/case 금지):

```typescript
import { handleError } from '@/errors/handler';
import { presentError } from '@/errors/ui-flow'; // 선택 — 프로젝트 디자인 시스템에 따라 대체 가능

const enroll = useMutation({
  mutationFn: speakersApi.enroll,
  onError: (err: unknown) => {
    const apiError = parseApiError(err);  // { code: string, message?: string, field?: string }
    const decision = handleError(apiError);
    presentError(decision); // 또는 inline 인 경우 form field 에 직접 바인딩
  },
});
```

경로(`@/errors/handler`, `@/errors/ui-flow`) 는 `frontend.md.error_handling.handler_file` / `ui_flow_file` 설정값을 따름.

inline 분기(form field error binding)는 호출자가 `decision.uiFlow === 'inline'` 일 때 `decision.field` 를 form 의 해당 필드에 바인딩:

```typescript
if (decision.uiFlow === 'inline' && decision.field) {
  form.setError(decision.field, { message: decision.message });
} else {
  presentError(decision);
}
```

`impl-error-handling` 이 아직 실행되지 않은 경우 (Phase 1 (1) 도입 전): `frontflow:impl-error-handling` 을 먼저 실행 권고. handler.ts 가 없으면 grace-period 5 기본 코드로 자동 생성됨.

### 5. 트래킹 hook (Phase 1 (4) 연계)

`frontflow:impl-tracking` 가 정의한 이벤트는 다음 위치에서 호출:

- useMutation `onSuccess`: 도메인 이벤트 (예: `speaker_enrolled`)
- useQuery 결과 변화 시: 필요한 경우 useEffect

- **error_shown** (단일 지점 원칙, Phase 1 (4) XR-005):
  - presentError wrapper 가 있으면 거기서만 호출
  - response interceptor 에서 호출 시 uiFlow 'silent' / 자동 retry 성공 케이스 제외
  - mutation onError 와 response interceptor 를 동시에 hook 하지 말 것 (중복)

handler.ts (Phase 1 (1)) 는 순수 함수 유지. error_shown 호출은 호출자 (presentError wrapper 우선, 없으면 mutation onError 또는 response interceptor 중 하나만) 에서.

import 는 `import { track, TrackEvent } from '@/tracking';`.

### 6. 비동기 완료 처리 (해당 시)

TS에 SSE/WebSocket 명시가 있으면:

```typescript
// 임베딩 완료 알림 수신
useEffect(() => {
  const eventSource = new EventSource(`/api/v1/events?speaker_id=${id}`)
  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.embedding_status === 'ready') {
      queryClient.invalidateQueries({ queryKey: ['speakers'] })
      eventSource.close()
    }
  }
  return () => eventSource.close()
}, [id])
```

## 품질 자가 점검

- [ ] F5의 모든 시뮬레이션이 실제 API 호출로 교체되었는가
- [ ] 타입이 TS API 스키마와 정확히 일치하는가
- [ ] TS의 모든 에러 코드에 프론트엔드 핸들링이 있는가
- [ ] 로딩/에러 상태가 실제 API 응답과 연결되었는가
- [ ] SSE/WebSocket이 필요하면 구현되었는가
- [ ] frontend.md의 api_client, server_state 패턴을 따르는가
- [ ] API 클라이언트 함수가 hand-written 되지 않고 codegen import 인가
- [ ] 타입이 types.gen.ts 에서 import 되었는가 (직접 정의 금지)
