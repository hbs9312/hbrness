---
name: impl-api-integration
description: 기술 명세서의 API를 프론트엔드에 연결합니다. F5의 시뮬레이션을 실제 호출로 교체. "API 연동", "백엔드 연결" 요청 시 사용.
argument-hint: [기술 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
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

### 1. API 클라이언트 함수

TS의 각 엔드포인트에 대응하는 함수:

```typescript
// api/speakers.ts
export const speakersApi = {
  enroll: (data: EnrollRequest): Promise<EnrollResponse> =>
    fetchClient.post('/api/v1/speakers/enroll', data),
  
  list: (workspaceId: string): Promise<SpeakerListResponse> =>
    fetchClient.get(`/api/v1/speakers?workspace_id=${workspaceId}`),
  
  delete: (speakerId: string): Promise<void> =>
    fetchClient.delete(`/api/v1/speakers/${speakerId}`),
}
```

frontend.md의 `api_client.method`에 따라 fetch/axios/ky 사용.

### 2. 타입 정의

TS의 요청/응답 스키마를 TypeScript 타입으로:

```typescript
// types/api.ts — TS 명세서와 1:1 대응
interface EnrollRequest {
  name: string
  audio_file: File
  workspace_id: string
}

interface EnrollResponse {
  speaker_id: string
  name: string
  embedding_status: EmbeddingStatus
  created_at: string
}

// 에러 응답도 타입화
interface ApiError {
  error: string    // AUDIO_TOO_SHORT, DUPLICATE_NAME 등
  message: string
}
```

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

TS의 에러 코드 → 프론트엔드 동작 매핑:

```typescript
// TS 에러 코드별 분기
function handleApiError(error: ApiError) {
  switch (error.error) {
    case 'AUDIO_TOO_SHORT':
      return { type: 'inline', field: 'audio', message: error.message }
    case 'DUPLICATE_NAME':
      return { type: 'inline', field: 'name', message: error.message }
    case 'PERMISSION_DENIED':
      return { type: 'toast', message: error.message, redirect: '/settings' }
    case 'QUOTA_EXCEEDED':
      return { type: 'modal', message: error.message }
    default:
      return { type: 'toast', message: '오류가 발생했습니다. 다시 시도해 주세요.' }
  }
}
```

### 5. 비동기 완료 처리 (해당 시)

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
